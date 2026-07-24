import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.holiday_event_notified import HolidayEventNotified


async def has_notified(db: AsyncSession, user_id: uuid.UUID, event_name: str, event_date: date) -> bool:
    result = await db.execute(
        select(HolidayEventNotified.id).where(
            HolidayEventNotified.user_id == user_id,
            HolidayEventNotified.event_name == event_name,
            HolidayEventNotified.event_date == event_date,
        )
    )
    return result.scalar_one_or_none() is not None


async def mark_notified(db: AsyncSession, user_id: uuid.UUID, event_name: str, event_date: date) -> None:
    """Check-then-insert, matching this codebase's existing dedup convention (`ReminderDelivery`'s
    own checks in `app.tasks.scheduler`, `feature_tour_seen_repo.mark_seen`) rather than a
    database-level upsert."""
    if await has_notified(db, user_id, event_name, event_date):
        return
    db.add(HolidayEventNotified(user_id=user_id, event_name=event_name, event_date=event_date))
    await db.commit()
