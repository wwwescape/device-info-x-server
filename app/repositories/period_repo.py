import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.period import PeriodCycle


async def get_cycle(db: AsyncSession, cycle_id: uuid.UUID) -> PeriodCycle | None:
    return await db.get(PeriodCycle, cycle_id)


async def list_cycles(db: AsyncSession, user_id: uuid.UUID) -> list[PeriodCycle]:
    result = await db.execute(
        select(PeriodCycle).where(PeriodCycle.user_id == user_id).order_by(PeriodCycle.cycle_start_date.desc())
    )
    return list(result.scalars().all())


async def create_cycle(db: AsyncSession, **fields) -> PeriodCycle:
    cycle = PeriodCycle(**fields)
    db.add(cycle)
    await db.flush()
    return cycle


async def delete_cycle(db: AsyncSession, cycle: PeriodCycle) -> None:
    await db.delete(cycle)


async def delete_all_cycles(db: AsyncSession) -> None:
    """The "Delete data" action for Period Tracker in the client's Settings screen — wipes
    logged cycles for *both* partners, not just the caller's own (a deliberate, confirmed
    divergence from the single-cycle path above, which stays owner-only). No `WHERE` clause is
    correct here: every deployment of this server hard-caps at exactly 2 accounts (see the
    README), so "both partners' cycles" and "every row in this table" are the same set — same
    shape as `calendar_repo.bulk_hard_delete_all`."""
    await db.execute(delete(PeriodCycle))
