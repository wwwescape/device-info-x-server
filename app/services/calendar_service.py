import uuid
from datetime import UTC, datetime

from dateutil.rrule import rrulestr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.calendar_event import CANCELLABLE_TYPES, RECURRING_ALLOWED_TYPES, CalendarEvent, EventType
from app.models.intimacy_log import INITIATED_BY_BOTH, ORGASMED_BY_NONE, IntimacyLog
from app.models.user import User
from app.repositories import calendar_repo
from app.schemas.calendar import CalendarEventCreate, CalendarEventOut, CalendarEventUpdate
from app.schemas.intimacy_log import IntimacyLogOut
from app.services import notification_service

# The only types an intimacy log may be attached to — enforced alongside the "date must be
# today-or-past" rule below, mirroring _validate_recurrence_allowed's shape.
INTIMACY_ELIGIBLE_TYPES = frozenset(
    {
        EventType.PLANNED_DATE,
        EventType.UNPLANNED_DATE,
        EventType.PLANNED_DRIVE,
        EventType.UNPLANNED_DRIVE,
        EventType.CUSTOM,
    }
)


def _validate_rrule(rule: str, dtstart: datetime) -> None:
    try:
        rrulestr(rule, dtstart=dtstart)
    except (ValueError, TypeError) as exc:
        raise ValidationError(f"invalid recurrence_rule: {exc}") from exc


def _validate_recurrence_allowed(event_type: EventType, recurrence_rule: str | None) -> None:
    if recurrence_rule and event_type not in RECURRING_ALLOWED_TYPES:
        raise ValidationError(f"{event_type.value} events cannot recur")


def _validate_cancelled_allowed(event_type: EventType, cancelled: bool, cancellation_reason: str | None) -> None:
    if cancelled and event_type not in CANCELLABLE_TYPES:
        raise ValidationError(f"{event_type.value} events cannot be cancelled")
    # A reason implies cancelled=True, which above already narrows the type down to
    # CANCELLABLE_TYPES — no separate type check needed for the reason itself.
    if cancellation_reason and not cancelled:
        raise ValidationError("cancellation_reason can only be set on a cancelled event")


def _intimacy_has_data(intimacy: dict) -> bool:
    return any(
        [
            intimacy.get("rating") is not None,
            intimacy.get("duration_minutes") is not None,
            intimacy.get("initiated_by") is not None,
            intimacy.get("protection_used") is not None,
            intimacy.get("positions"),
            intimacy.get("locations"),
            intimacy.get("moods"),
            intimacy.get("rounds") is not None,
            intimacy.get("orgasmed_by") is not None,
        ]
    )


def _validate_intimacy_allowed(event_type: EventType, reference_at: datetime, intimacy: dict | None) -> None:
    if intimacy is None or not _intimacy_has_data(intimacy):
        return
    if event_type not in INTIMACY_ELIGIBLE_TYPES:
        raise ValidationError(f"{event_type.value} events cannot have an intimacy log")
    if reference_at > datetime.now(UTC):
        raise ValidationError("cannot log intimacy for a future event")


def _validate_initiated_by(initiated_by: str | None, user: User) -> None:
    if initiated_by is None:
        return
    valid = {INITIATED_BY_BOTH, str(user.id)}
    if user.partner_id is not None:
        valid.add(str(user.partner_id))
    if initiated_by not in valid:
        raise ValidationError("initiated_by must be 'both' or one of the paired partners")


def _validate_orgasmed_by(orgasmed_by: str | None, user: User) -> None:
    if orgasmed_by is None:
        return
    valid = {INITIATED_BY_BOTH, ORGASMED_BY_NONE, str(user.id)}
    if user.partner_id is not None:
        valid.add(str(user.partner_id))
    if orgasmed_by not in valid:
        raise ValidationError("orgasmed_by must be 'both', 'none', or one of the paired partners")


def _intimacy_out_from_orm(log: IntimacyLog | None) -> IntimacyLogOut | None:
    if log is None:
        return None
    return IntimacyLogOut(
        rating=log.rating,
        duration_minutes=log.duration_minutes,
        initiated_by=log.initiated_by,
        protection_used=log.protection_used,
        positions=sorted(log.positions),
        locations=sorted(log.locations),
        moods=sorted(log.moods),
        rounds=log.rounds,
        orgasmed_by=log.orgasmed_by,
    )


def _intimacy_out_from_payload(data: dict | None) -> IntimacyLogOut | None:
    """Builds the response directly from what was just validated/saved in create/update,
    rather than an extra round-trip query — the row we'd re-fetch would hold exactly this
    data, since `set_intimacy_log` just wrote it."""
    if data is None or not _intimacy_has_data(data):
        return None
    return IntimacyLogOut(
        rating=data.get("rating"),
        duration_minutes=data.get("duration_minutes"),
        initiated_by=data.get("initiated_by"),
        protection_used=data.get("protection_used"),
        positions=sorted(data.get("positions") or []),
        locations=sorted(data.get("locations") or []),
        moods=sorted(data.get("moods") or []),
        rounds=data.get("rounds"),
        orgasmed_by=data.get("orgasmed_by"),
    )


def _to_out(event: CalendarEvent, reminders: list[int], intimacy: IntimacyLogOut | None) -> CalendarEventOut:
    return CalendarEventOut(
        id=event.id,
        created_by=event.created_by,
        type=event.type,
        title=event.title,
        description=event.description,
        start_at=event.start_at,
        end_at=event.end_at,
        all_day=event.all_day,
        location=event.location,
        recurrence_rule=event.recurrence_rule,
        recurrence_end_at=event.recurrence_end_at,
        color=event.color,
        cancelled=event.cancelled,
        cancellation_reason=event.cancellation_reason,
        reminder_minutes_before=sorted(reminders),
        intimacy=intimacy,
        created_at=event.created_at,
        updated_at=event.updated_at,
    )


async def _get_or_404(db: AsyncSession, event_id: uuid.UUID) -> CalendarEvent:
    event = await calendar_repo.get_by_id(db, event_id)
    if event is None:
        raise NotFoundError("calendar event not found")
    return event


async def create_event(db: AsyncSession, user: User, payload: CalendarEventCreate) -> CalendarEventOut:
    if payload.recurrence_rule:
        _validate_rrule(payload.recurrence_rule, payload.start_at)
    _validate_recurrence_allowed(payload.type, payload.recurrence_rule)
    _validate_cancelled_allowed(payload.type, payload.cancelled, payload.cancellation_reason)

    intimacy_data = payload.intimacy.model_dump() if payload.intimacy is not None else None
    _validate_intimacy_allowed(payload.type, payload.end_at or payload.start_at, intimacy_data)
    if intimacy_data is not None:
        _validate_initiated_by(intimacy_data.get("initiated_by"), user)
        _validate_orgasmed_by(intimacy_data.get("orgasmed_by"), user)

    event = await calendar_repo.create(
        db,
        created_by=user.id,
        type=payload.type,
        title=payload.title,
        description=payload.description,
        start_at=payload.start_at,
        end_at=payload.end_at,
        all_day=payload.all_day,
        location=payload.location,
        recurrence_rule=payload.recurrence_rule,
        recurrence_end_at=payload.recurrence_end_at,
        color=payload.color,
        cancelled=payload.cancelled,
        cancellation_reason=payload.cancellation_reason,
    )
    await calendar_repo.set_reminders(db, event.id, payload.reminder_minutes_before)
    if intimacy_data is not None and _intimacy_has_data(intimacy_data):
        await calendar_repo.set_intimacy_log(db, event.id, intimacy_data)
    await db.commit()
    await db.refresh(event)

    out = _to_out(event, payload.reminder_minutes_before, _intimacy_out_from_payload(intimacy_data))
    if user.partner_id is not None:
        await notification_service.notify_user(
            user.partner_id,
            "calendar.event.created",
            {"event": out.model_dump(mode="json")},
            fcm_data={"type": "calendar_event_created", "event_id": str(event.id)},
        )
    return out


async def update_event(
    db: AsyncSession, user: User, event_id: uuid.UUID, payload: CalendarEventUpdate
) -> CalendarEventOut:
    event = await _get_or_404(db, event_id)

    data = payload.model_dump(exclude_unset=True)
    reminder_minutes = data.pop("reminder_minutes_before", None)
    intimacy_data = data.pop("intimacy", None)

    new_start = data.get("start_at", event.start_at)
    new_end = data.get("end_at", event.end_at)
    new_rule = data.get("recurrence_rule", event.recurrence_rule)
    new_type = data.get("type", event.type)
    new_cancelled = data.get("cancelled", event.cancelled)
    new_cancellation_reason = data.get("cancellation_reason", event.cancellation_reason)
    if new_rule:
        _validate_rrule(new_rule, new_start)
    _validate_recurrence_allowed(new_type, new_rule)
    _validate_cancelled_allowed(new_type, new_cancelled, new_cancellation_reason)
    _validate_intimacy_allowed(new_type, new_end or new_start, intimacy_data)
    if intimacy_data is not None:
        _validate_initiated_by(intimacy_data.get("initiated_by"), user)
        _validate_orgasmed_by(intimacy_data.get("orgasmed_by"), user)

    for field, value in data.items():
        setattr(event, field, value)

    if reminder_minutes is not None:
        await calendar_repo.set_reminders(db, event.id, reminder_minutes)
    if intimacy_data is not None:
        await calendar_repo.set_intimacy_log(db, event.id, intimacy_data if _intimacy_has_data(intimacy_data) else None)

    await db.commit()
    await db.refresh(event)

    if reminder_minutes is None:
        reminder_minutes = [r.minutes_before for r in await calendar_repo.reminders_for_event(db, event.id)]
    if intimacy_data is not None:
        intimacy_out = _intimacy_out_from_payload(intimacy_data)
    else:
        intimacy_out = _intimacy_out_from_orm(await calendar_repo.get_intimacy_log(db, event.id))

    out = _to_out(event, reminder_minutes, intimacy_out)
    if user.partner_id is not None:
        await notification_service.notify_user(
            user.partner_id,
            "calendar.event.updated",
            {"event": out.model_dump(mode="json")},
            fcm_data={"type": "calendar_event_updated", "event_id": str(event.id)},
        )
    return out


async def delete_event(db: AsyncSession, user: User, event_id: uuid.UUID) -> None:
    event = await _get_or_404(db, event_id)
    await calendar_repo.soft_delete(db, event)
    await db.commit()

    if user.partner_id is not None:
        await notification_service.notify_user(
            user.partner_id,
            "calendar.event.deleted",
            {"event_id": str(event_id)},
            fcm_data={"type": "calendar_event_deleted", "event_id": str(event_id)},
        )


async def wipe_shared_calendar(db: AsyncSession, user: User) -> None:
    """The "Delete data" action for Calendar in the client's Settings screen. Sends one
    `calendar.wiped` event with no payload — unlike a single delete, there's no meaningful id
    list to send when the answer is "everything." """
    await calendar_repo.bulk_hard_delete_all(db)
    await db.commit()

    if user.partner_id is not None:
        await notification_service.notify_user(
            user.partner_id,
            "calendar.wiped",
            {},
            fcm_data={"type": "calendar_wiped"},
        )


async def list_events(db: AsyncSession, *, start: datetime, end: datetime) -> list[CalendarEventOut]:
    events = await calendar_repo.list_in_range(db, start=start, end=end)
    event_ids = [e.id for e in events]
    reminders_map = await calendar_repo.reminders_for_events(db, event_ids)
    intimacy_map = await calendar_repo.intimacy_logs_for_events(db, event_ids)
    return [
        _to_out(e, reminders_map.get(e.id, []), _intimacy_out_from_orm(intimacy_map.get(e.id)))
        for e in events
    ]


async def get_event(db: AsyncSession, event_id: uuid.UUID) -> CalendarEventOut:
    event = await _get_or_404(db, event_id)
    reminders = [r.minutes_before for r in await calendar_repo.reminders_for_event(db, event.id)]
    intimacy = await calendar_repo.get_intimacy_log(db, event.id)
    return _to_out(event, reminders, _intimacy_out_from_orm(intimacy))
