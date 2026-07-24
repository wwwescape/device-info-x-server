import datetime
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.period import PeriodDayLog


async def get_day_log(db: AsyncSession, day_log_id: uuid.UUID) -> PeriodDayLog | None:
    return await db.get(PeriodDayLog, day_log_id)


async def get_day_log_by_date(db: AsyncSession, user_id: uuid.UUID, log_date: datetime.date) -> PeriodDayLog | None:
    result = await db.execute(
        select(PeriodDayLog).where(PeriodDayLog.user_id == user_id, PeriodDayLog.log_date == log_date)
    )
    return result.scalar_one_or_none()


async def list_day_logs(db: AsyncSession, user_id: uuid.UUID) -> list[PeriodDayLog]:
    result = await db.execute(
        select(PeriodDayLog).where(PeriodDayLog.user_id == user_id).order_by(PeriodDayLog.log_date.desc())
    )
    return list(result.scalars().all())


async def create_day_log(db: AsyncSession, **fields) -> PeriodDayLog:
    day_log = PeriodDayLog(**fields)
    db.add(day_log)
    await db.flush()
    return day_log


async def delete_day_log(db: AsyncSession, day_log: PeriodDayLog) -> None:
    await db.delete(day_log)


async def delete_all_day_logs(db: AsyncSession) -> None:
    """The "Delete data" action for Period Tracker in the client's Settings screen — wipes
    logged days for *both* partners, not just the caller's own (a deliberate, confirmed
    divergence from the single-day-log path above, which stays owner-only). No `WHERE` clause is
    correct here: every deployment of this server hard-caps at exactly 2 accounts (see the
    README), so "both partners' day logs" and "every row in this table" are the same set — same
    shape as `calendar_repo.bulk_hard_delete_all`."""
    await db.execute(delete(PeriodDayLog))
