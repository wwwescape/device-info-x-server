import logging
import uuid
from datetime import UTC, datetime

from dateutil.rrule import rrulestr
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calendar_event import CalendarEvent, CalendarEventAttachment, CalendarEventReminder
from app.models.intimacy_log import IntimacyLog
from app.models.media_asset import MediaAsset
from app.repositories import media_asset_repo

logger = logging.getLogger(__name__)


async def get_by_id(db: AsyncSession, event_id: uuid.UUID) -> CalendarEvent | None:
    event = await db.get(CalendarEvent, event_id)
    if event is not None and event.deleted_at is not None:
        return None
    return event


def _recurring_event_touches_window(event: CalendarEvent, start: datetime, end: datetime) -> bool:
    try:
        rule = rrulestr(event.recurrence_rule, dtstart=event.start_at)
    except (ValueError, TypeError):
        logger.warning("calendar event %s has an unparseable recurrence_rule, skipping", event.id)
        return False
    return rule.between(start, end, inc=True) != []


async def list_in_range(db: AsyncSession, *, start: datetime, end: datetime) -> list[CalendarEvent]:
    """Returns every event whose series actually has an occurrence in [start, end) — the SQL
    query narrows to series that haven't ended before `start` (cheap, index-friendly), then a
    recurring series is only kept once its RRULE is expanded and confirmed to land an occurrence
    inside the window (same expansion `tasks/scheduler.py` does for reminders)."""
    stmt = (
        select(CalendarEvent)
        .where(
            CalendarEvent.deleted_at.is_(None),
            CalendarEvent.start_at < end,
            or_(CalendarEvent.recurrence_end_at.is_(None), CalendarEvent.recurrence_end_at >= start),
            or_(
                CalendarEvent.recurrence_rule.is_not(None),
                CalendarEvent.end_at > start,
                and_(CalendarEvent.end_at.is_(None), CalendarEvent.start_at >= start),
            ),
        )
        .order_by(CalendarEvent.start_at.asc())
    )
    result = await db.execute(stmt)
    events = list(result.scalars().all())
    return [e for e in events if not e.recurrence_rule or _recurring_event_touches_window(e, start, end)]


async def list_all(db: AsyncSession) -> list[CalendarEvent]:
    result = await db.execute(
        select(CalendarEvent).where(CalendarEvent.deleted_at.is_(None)).order_by(CalendarEvent.start_at.asc())
    )
    return list(result.scalars().all())


async def create(db: AsyncSession, **fields) -> CalendarEvent:
    event = CalendarEvent(**fields)
    db.add(event)
    await db.flush()
    return event


async def reminders_for_event(db: AsyncSession, event_id: uuid.UUID) -> list[CalendarEventReminder]:
    result = await db.execute(select(CalendarEventReminder).where(CalendarEventReminder.event_id == event_id))
    return list(result.scalars().all())


async def reminders_for_events(db: AsyncSession, event_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[int]]:
    if not event_ids:
        return {}
    result = await db.execute(select(CalendarEventReminder).where(CalendarEventReminder.event_id.in_(event_ids)))
    grouped: dict[uuid.UUID, list[int]] = {}
    for reminder in result.scalars().all():
        grouped.setdefault(reminder.event_id, []).append(reminder.minutes_before)
    return grouped


async def set_reminders(db: AsyncSession, event_id: uuid.UUID, minutes_list: list[int]) -> None:
    await db.execute(delete(CalendarEventReminder).where(CalendarEventReminder.event_id == event_id))
    for minutes in minutes_list:
        db.add(CalendarEventReminder(event_id=event_id, minutes_before=minutes))
    await db.flush()


async def attachments_for_events(db: AsyncSession, event_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[MediaAsset]]:
    if not event_ids:
        return {}
    result = await db.execute(
        select(CalendarEventAttachment).where(CalendarEventAttachment.event_id.in_(event_ids))
    )
    join_rows = list(result.scalars().all())
    assets_by_id = {a.id: a for a in await media_asset_repo.get_by_ids(db, [r.media_id for r in join_rows])}
    grouped: dict[uuid.UUID, list[MediaAsset]] = {}
    for row in join_rows:
        asset = assets_by_id.get(row.media_id)
        if asset is not None:
            grouped.setdefault(row.event_id, []).append(asset)
    return grouped


async def set_attachments(db: AsyncSession, event_id: uuid.UUID, media_ids: list[uuid.UUID]) -> None:
    """Same "replace, don't diff" choice as [set_reminders] — the caller (`calendar_service`)
    has already validated every id in [media_ids] before this runs."""
    await db.execute(delete(CalendarEventAttachment).where(CalendarEventAttachment.event_id == event_id))
    for media_id in media_ids:
        db.add(CalendarEventAttachment(event_id=event_id, media_id=media_id))
    await db.flush()


async def cover_media_for_events(db: AsyncSession, event_ids: list[uuid.UUID]) -> dict[uuid.UUID, MediaAsset]:
    """Bulk-resolves each event's single cover asset — no join table involved (`cover_media_id` is
    a plain column on `CalendarEvent`), so this is a narrow column select plus a batched asset
    fetch, mirroring [attachments_for_events]'s two-step shape for the list case."""
    if not event_ids:
        return {}
    result = await db.execute(
        select(CalendarEvent.id, CalendarEvent.cover_media_id).where(
            CalendarEvent.id.in_(event_ids), CalendarEvent.cover_media_id.is_not(None)
        )
    )
    rows = result.all()
    assets_by_id = {a.id: a for a in await media_asset_repo.get_by_ids(db, [r.cover_media_id for r in rows])}
    return {row.id: assets_by_id[row.cover_media_id] for row in rows if row.cover_media_id in assets_by_id}


async def get_intimacy_log(db: AsyncSession, event_id: uuid.UUID) -> IntimacyLog | None:
    return await db.get(IntimacyLog, event_id)


async def intimacy_logs_for_events(db: AsyncSession, event_ids: list[uuid.UUID]) -> dict[uuid.UUID, IntimacyLog]:
    if not event_ids:
        return {}
    result = await db.execute(select(IntimacyLog).where(IntimacyLog.event_id.in_(event_ids)))
    return {log.event_id: log for log in result.scalars().all()}


async def set_intimacy_log(db: AsyncSession, event_id: uuid.UUID, data: dict | None) -> None:
    """Always replaces the log wholesale — there's exactly one per event, so there's no
    per-field diffing to do (same "replace, don't patch" choice `set_reminders` makes for
    `CalendarEventReminder`). `data=None` clears it (deletes the row) entirely."""
    existing = await db.get(IntimacyLog, event_id)
    if data is None:
        if existing is not None:
            await db.delete(existing)
        await db.flush()
        return

    if existing is None:
        db.add(IntimacyLog(event_id=event_id, **data))
    else:
        for field, value in data.items():
            setattr(existing, field, value)
    await db.flush()


async def soft_delete(db: AsyncSession, event: CalendarEvent) -> None:
    event.deleted_at = datetime.now(UTC)
    await db.flush()


async def bulk_hard_delete_all(db: AsyncSession) -> list[uuid.UUID]:
    """The "Delete data" action for Calendar in the client's Settings screen — a genuine hard
    delete (unlike single-event `soft_delete` above, which only hides a row and leaves its
    content in the database forever), deliberately chosen for the bulk case since the whole
    point of this action is that the data is actually gone. `CalendarEventReminder`/`IntimacyLog`
    rows cascade via `ondelete="CASCADE"` on their `event_id` FK, no separate cleanup needed. No
    `WHERE` clause — the calendar is shared with no per-item ownership (matching single-event
    delete's existing lack of an ownership check) and this server is single-pair-per-deployment,
    so there's structurally only ever one couple's events in this table.

    `CalendarEventAttachment` rows cascade the same way, but that only removes the join row —
    the `media_assets` row and on-disk file it points at are a separate resource the cascade
    can't touch (mirrors `message_repo.bulk_hard_delete_conversation`'s reasoning), so every
    attachment's `media_id` is captured here, before the cascade, for the caller to sweep. Each
    event's own `cover_media_id` is captured the same way — it's `ON DELETE SET NULL`, not
    `CASCADE`, so deleting the event wouldn't otherwise touch its cover asset/file at all."""
    media_result = await db.execute(select(CalendarEventAttachment.media_id))
    media_ids = list(media_result.scalars().all())
    cover_result = await db.execute(
        select(CalendarEvent.cover_media_id).where(CalendarEvent.cover_media_id.is_not(None))
    )
    media_ids += list(cover_result.scalars().all())
    await db.execute(delete(CalendarEvent))
    return media_ids
