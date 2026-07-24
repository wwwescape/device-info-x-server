import logging
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dateutil.rrule import rrulestr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.models.calendar_event import CalendarEvent, CalendarEventReminder
from app.models.reminder_delivery import ReminderDelivery, ReminderSourceType
from app.models.user import Gender, User
from app.repositories import holiday_event_notified_repo, period_repo, scheduled_message_repo
from app.services import (
    holiday_events_service,
    location_service,
    notification_service,
    period_service,
    scheduled_message_service,
)

logger = logging.getLogger(__name__)

SWEEP_INTERVAL_SECONDS = 60
LOOKAHEAD = timedelta(hours=48)
# A reminder whose trigger time is further in the past than this is treated
# as stale (e.g. the server was down) — recorded as delivered but not sent,
# so a long outage doesn't dump a backlog of late notifications on restart.
STALE_THRESHOLD = timedelta(hours=24)

# How many days ahead of a predicted cycle start "period.upcoming" fires, and how many days
# past it "period.not_logged" fires if nothing new has been logged by then. Both are product
# decisions (not derived from anything in the data) confirmed when this feature was scoped.
PERIOD_UPCOMING_DAYS_BEFORE = 2
PERIOD_NOT_LOGGED_DAYS_AFTER = 1
# Beyond this many days past a stale prediction, stop trying to fire "not logged" for it at all
# (still marks it as handled) — mirrors STALE_THRESHOLD's reasoning: an outage or long absence
# shouldn't produce a surprise nag once the person eventually reopens the app.
PERIOD_NOT_LOGGED_STALE_DAYS = 14


async def _already_delivered(
    db: AsyncSession,
    source_type: ReminderSourceType,
    source_id: uuid.UUID,
    occurrence_at: datetime,
    minutes_before: int,
) -> bool:
    result = await db.execute(
        select(ReminderDelivery.id).where(
            ReminderDelivery.source_type == source_type,
            ReminderDelivery.source_id == source_id,
            ReminderDelivery.occurrence_at == occurrence_at,
            ReminderDelivery.minutes_before == minutes_before,
        )
    )
    return result.scalar_one_or_none() is not None


async def _record_delivery(
    db: AsyncSession,
    source_type: ReminderSourceType,
    source_id: uuid.UUID,
    occurrence_at: datetime,
    minutes_before: int,
) -> None:
    db.add(
        ReminderDelivery(
            source_type=source_type,
            source_id=source_id,
            occurrence_at=occurrence_at,
            minutes_before=minutes_before,
        )
    )
    await db.commit()


async def _notify_both_partners(
    db: AsyncSession, creator_id: uuid.UUID, event_type: str, ws_data: dict, fcm_data: dict
) -> None:
    creator = await db.get(User, creator_id)
    if creator is None:
        return
    recipients = [creator.id]
    if creator.partner_id is not None:
        recipients.append(creator.partner_id)
    for recipient_id in recipients:
        await notification_service.notify_user(recipient_id, event_type, ws_data, fcm_data=fcm_data)


async def _fire_or_skip(
    db: AsyncSession,
    *,
    now: datetime,
    source_type: ReminderSourceType,
    source_id: uuid.UUID,
    occurrence_at: datetime,
    minutes_before: int,
    creator_id: uuid.UUID,
    title: str,
) -> None:
    fire_at = occurrence_at - timedelta(minutes=minutes_before)
    if fire_at > now:
        return  # not due yet

    if now - fire_at > STALE_THRESHOLD:
        await _record_delivery(db, source_type, source_id, occurrence_at, minutes_before)
        return

    if await _already_delivered(db, source_type, source_id, occurrence_at, minutes_before):
        return

    await _record_delivery(db, source_type, source_id, occurrence_at, minutes_before)
    await _notify_both_partners(
        db,
        creator_id,
        "reminder.fired",
        {
            "source_type": source_type.value,
            "source_id": str(source_id),
            "title": title,
            "occurrence_at": occurrence_at.isoformat(),
        },
        fcm_data={
            "type": "reminder",
            "source_type": source_type.value,
            "source_id": str(source_id),
            "minutes_before": str(minutes_before),
        },
    )


def _expand_calendar_occurrences(
    event: CalendarEvent, window_start: datetime, window_end: datetime
) -> list[datetime]:
    if not event.recurrence_rule:
        if window_start <= event.start_at <= window_end:
            return [event.start_at]
        return []

    try:
        rule = rrulestr(event.recurrence_rule, dtstart=event.start_at)
    except (ValueError, TypeError):
        logger.warning("calendar event %s has an unparseable recurrence_rule, skipping", event.id)
        return []

    occurrences = list(rule.between(window_start, window_end, inc=True))
    if event.recurrence_end_at is not None:
        occurrences = [o for o in occurrences if o <= event.recurrence_end_at]
    return occurrences


async def _sweep_calendar_events(db: AsyncSession, now: datetime) -> None:
    window_end = now + LOOKAHEAD
    result = await db.execute(
        select(CalendarEvent).where(
            CalendarEvent.deleted_at.is_(None), CalendarEvent.start_at < window_end + timedelta(days=1)
        )
    )
    events = list(result.scalars().all())
    if not events:
        return

    reminders_result = await db.execute(
        select(CalendarEventReminder).where(CalendarEventReminder.event_id.in_([e.id for e in events]))
    )
    reminders_by_event: dict[uuid.UUID, list[int]] = {}
    for reminder in reminders_result.scalars().all():
        reminders_by_event.setdefault(reminder.event_id, []).append(reminder.minutes_before)

    for event in events:
        minutes_list = reminders_by_event.get(event.id, [])
        if not minutes_list:
            continue

        for occurrence_at in _expand_calendar_occurrences(event, now, window_end):
            for minutes_before in minutes_list:
                await _fire_or_skip(
                    db,
                    now=now,
                    source_type=ReminderSourceType.CALENDAR_EVENT,
                    source_id=event.id,
                    occurrence_at=occurrence_at,
                    minutes_before=minutes_before,
                    creator_id=event.created_by,
                    title=event.title,
                )


async def _sweep_birthdays(db: AsyncSession, now: datetime) -> None:
    """Self-only, once-a-year "Happy Birthday" push — deliberately separate from
    `_sweep_calendar_events`/`ReminderDelivery`: those exist for rrule-expanded, configurable
    per-offset reminders fanned out to both partners, which is more machinery than a single
    fixed local-midnight push per user needs, and would notify the wrong person (the partner)
    without extra special-casing. Dedup is a plain `last_birthday_notified_year` column instead
    of the source_type/source_id/occurrence_at triple `ReminderDelivery` uses for that reason."""
    result = await db.execute(select(User).where(User.timezone.is_not(None)))
    for user in result.scalars().all():
        try:
            local_now = now.astimezone(ZoneInfo(user.timezone))
        except ZoneInfoNotFoundError:
            logger.warning("user %s has an unrecognized timezone %r, skipping", user.id, user.timezone)
            continue

        if (local_now.month, local_now.day) != (user.birthday_date.month, user.birthday_date.day):
            continue
        if user.last_birthday_notified_year == local_now.year:
            continue

        user.last_birthday_notified_year = local_now.year
        await db.commit()
        await notification_service.notify_user(user.id, "birthday", {}, fcm_data={"type": "birthday"})
        logger.info("birthday notification sent to user %s", user.id)


async def _sweep_holiday_events(db: AsyncSession, now: datetime) -> None:
    """National/catholic/hindu holiday greetings from the bundled `app/data/events.json` — unlike
    `_sweep_birthdays` (self-only, one fixed date per user), a holiday event is the same for
    *every* user, so this fans out to every user independently (each checked against their own
    local date, same per-user-timezone approach `_sweep_birthdays` already uses) rather than
    picking one "creator" and fanning out to their partner via `_notify_both_partners`. Dedup is
    `HolidayEventNotified` (per user *and* event *and* date), not a single column — see that
    model's own doc comment for why `_sweep_birthdays`'s shape doesn't fit here."""
    events = holiday_events_service.load_events()
    if not events:
        return

    result = await db.execute(select(User).where(User.timezone.is_not(None)))
    for user in result.scalars().all():
        try:
            local_today = now.astimezone(ZoneInfo(user.timezone)).date()
        except ZoneInfoNotFoundError:
            logger.warning("user %s has an unrecognized timezone %r, skipping", user.id, user.timezone)
            continue

        for event in events:
            if event.date != local_today:
                continue
            if await holiday_event_notified_repo.has_notified(db, user.id, event.name, event.date):
                continue

            await holiday_event_notified_repo.mark_notified(db, user.id, event.name, event.date)
            await notification_service.notify_user(
                user.id,
                "holiday_event",
                {"name": event.name, "wishes": event.wishes},
                fcm_data={"type": "holiday_event", "title": event.name, "body": event.wishes},
            )
            logger.info("holiday-event notification (%s) sent to user %s", event.name, user.id)


async def _sweep_period_cycles(db: AsyncSession, now: datetime) -> None:
    """Two pushes off the same prediction, scoped to FEMALE users only (the confirmed scope for
    this feature): `period_upcoming` fans out to both partners same as any other reminder,
    `period_not_logged` goes only to the account holder herself. Both intentionally read as
    near-identical, vague "cycle" wording client-side (ConsoleFcmService) so neither leaks which
    one fired to anyone glancing at a lock screen.

    Dedup is keyed off the *predicted* date rather than a sweep timestamp (see the doc comment
    on the User columns) — logging a new cycle changes the prediction and naturally re-arms both
    checks without any explicit reset.
    """
    result = await db.execute(select(User).where(User.gender == Gender.FEMALE, User.timezone.is_not(None)))
    for user in result.scalars().all():
        try:
            local_today = now.astimezone(ZoneInfo(user.timezone)).date()
        except ZoneInfoNotFoundError:
            logger.warning("user %s has an unrecognized timezone %r, skipping", user.id, user.timezone)
            continue

        day_logs = await period_repo.list_day_logs(db, user.id)
        predicted = period_service.predict_next_cycle_start(day_logs)
        if predicted is None:
            continue

        days_until = (predicted - local_today).days
        if 0 <= days_until <= PERIOD_UPCOMING_DAYS_BEFORE and user.last_period_upcoming_notified_for != predicted:
            user.last_period_upcoming_notified_for = predicted
            await db.commit()
            await _notify_both_partners(
                db,
                user.id,
                "period.upcoming",
                {"predicted_start": predicted.isoformat()},
                fcm_data={"type": "period_upcoming"},
            )
            logger.info("period-upcoming notification sent to user %s", user.id)

        days_since = (local_today - predicted).days
        if days_since >= PERIOD_NOT_LOGGED_DAYS_AFTER and user.last_period_not_logged_notified_for != predicted:
            user.last_period_not_logged_notified_for = predicted
            await db.commit()
            if days_since <= PERIOD_NOT_LOGGED_STALE_DAYS:
                await notification_service.notify_user(
                    user.id,
                    "period.not_logged",
                    {"predicted_start": predicted.isoformat()},
                    fcm_data={"type": "period_not_logged"},
                )
                logger.info("period-not-logged notification sent to user %s", user.id)


async def _sweep_scheduled_messages(db: AsyncSession, now: datetime) -> None:
    """Delivers due scheduled messages via `scheduled_message_service.deliver_scheduled_message`
    — unlike the reminder-style sweeps above, no `ReminderDelivery`-style dedup table is needed:
    the staging row's own presence/absence, plus that function's `client_message_id` reuse (see
    its own doc comment), is the entire once-only guarantee.

    Each row gets its own `try/except`, deliberately unlike `_sweep_birthdays`/`_sweep_holiday_events`
    above (which let one bad user abort the whole per-tick loop, safe there since both are
    naturally idempotent and simply retry clean next tick) — a stuck or failing row here shouldn't
    be able to delay every *other* user's on-time delivery in the same tick, since unlike a
    birthday reminder a late scheduled message is a real, user-visible miss, not just a delayed
    notification."""
    for row in await scheduled_message_repo.list_due(db, now):
        sender = await db.get(User, row.sender_id)
        if sender is None:
            # Orphaned row (sender account deleted since scheduling) — nothing to send to, just
            # clear it rather than retrying forever.
            await scheduled_message_repo.delete(db, row)
            await db.commit()
            continue
        try:
            await scheduled_message_service.deliver_scheduled_message(db, sender, row)
        except Exception:
            logger.exception("failed to deliver scheduled message %s", row.id)


async def run_reminder_sweep() -> None:
    now = datetime.now(UTC)
    async with async_session_factory() as db:
        try:
            await _sweep_calendar_events(db, now)
        except Exception:
            logger.exception("reminder sweep failed")
        try:
            await _sweep_birthdays(db, now)
        except Exception:
            logger.exception("birthday sweep failed")
        try:
            await _sweep_holiday_events(db, now)
        except Exception:
            logger.exception("holiday event sweep failed")
        try:
            await _sweep_period_cycles(db, now)
        except Exception:
            logger.exception("period cycle sweep failed")
        try:
            await _sweep_scheduled_messages(db, now)
        except Exception:
            logger.exception("scheduled message sweep failed")
    # Deliberately outside the `async with async_session_factory()` block above — unlike every
    # other sweep, this one reads process-local in-memory state (ConnectionManager), not the
    # database, and opens its own short-lived session per overdue user internally
    # (location_service.sweep_auto_disable) rather than sharing one across the whole sweep.
    try:
        await location_service.sweep_auto_disable()
    except Exception:
        logger.exception("location auto-disable sweep failed")


def start_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=UTC)
    scheduler.add_job(
        run_reminder_sweep, "interval", seconds=SWEEP_INTERVAL_SECONDS, id="reminder_sweep", max_instances=1
    )
    scheduler.start()
    return scheduler
