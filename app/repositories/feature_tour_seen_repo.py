import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feature_tour_seen import FeatureTourSeen


async def list_tour_keys_for_user(db: AsyncSession, user_id: uuid.UUID) -> list[str]:
    result = await db.execute(select(FeatureTourSeen.tour_key).where(FeatureTourSeen.user_id == user_id))
    return list(result.scalars().all())


async def has_seen(db: AsyncSession, user_id: uuid.UUID, tour_key: str) -> bool:
    result = await db.execute(
        select(FeatureTourSeen.id).where(
            FeatureTourSeen.user_id == user_id, FeatureTourSeen.tour_key == tour_key
        )
    )
    return result.scalar_one_or_none() is not None


async def mark_seen(db: AsyncSession, user_id: uuid.UUID, tour_key: str) -> None:
    """Idempotent — a tour marked seen twice (e.g. a retried request) is a no-op the second time,
    not a constraint-violation error, so the client's fire-and-forget call never needs to handle a
    conflict response. Check-then-insert rather than a database-level upsert, matching this
    codebase's existing dedup convention (`app.tasks.scheduler`'s `ReminderDelivery` checks).
    Also used directly by the CLI's `disable-tours` command, to pre-emptively suppress a tour the
    account hasn't reached yet."""
    if await has_seen(db, user_id, tour_key):
        return
    db.add(FeatureTourSeen(user_id=user_id, tour_key=tour_key))
    await db.commit()


async def reset_seen(db: AsyncSession, user_id: uuid.UUID, tour_key: str) -> None:
    """The CLI's `enable-tours` command — lets a dismissed tour show again (re-testing after a
    copy/target change, or a user who wants to see it again). No-op if it was never seen."""
    await db.execute(
        delete(FeatureTourSeen).where(FeatureTourSeen.user_id == user_id, FeatureTourSeen.tour_key == tour_key)
    )
    await db.commit()
