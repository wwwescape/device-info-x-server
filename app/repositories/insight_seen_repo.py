import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.insight_seen import InsightSeen


async def list_seen_ids_for_user(db: AsyncSession, user_id: uuid.UUID) -> list[uuid.UUID]:
    result = await db.execute(select(InsightSeen.insight_id).where(InsightSeen.user_id == user_id))
    return list(result.scalars().all())


async def has_seen(db: AsyncSession, user_id: uuid.UUID, insight_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(InsightSeen.id).where(InsightSeen.user_id == user_id, InsightSeen.insight_id == insight_id)
    )
    return result.scalar_one_or_none() is not None


async def mark_seen(db: AsyncSession, user_id: uuid.UUID, insight_id: uuid.UUID) -> None:
    """Idempotent, same check-then-insert convention as `whats_new_seen_repo.mark_seen`."""
    if await has_seen(db, user_id, insight_id):
        return
    db.add(InsightSeen(user_id=user_id, insight_id=insight_id))
    await db.commit()


async def count_seen(db: AsyncSession, insight_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count()).select_from(InsightSeen).where(InsightSeen.insight_id == insight_id)
    )
    return result.scalar_one()


async def reset_seen_for_user(db: AsyncSession, user_id: uuid.UUID, insight_id: uuid.UUID) -> None:
    """The CLI's `reset-insight-seen --user`. No-op if that account hadn't seen it."""
    await db.execute(delete(InsightSeen).where(InsightSeen.user_id == user_id, InsightSeen.insight_id == insight_id))
    await db.commit()


async def reset_seen_for_all(db: AsyncSession, insight_id: uuid.UUID) -> None:
    """The CLI's `reset-insight-seen` with no `--user` — clears every account's seen-state for
    this insight at once, e.g. after fixing a typo in its text."""
    await db.execute(delete(InsightSeen).where(InsightSeen.insight_id == insight_id))
    await db.commit()
