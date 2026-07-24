import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.whats_new_seen import WhatsNewSeen


async def list_tags_for_user(db: AsyncSession, user_id: uuid.UUID) -> list[str]:
    result = await db.execute(select(WhatsNewSeen.tag).where(WhatsNewSeen.user_id == user_id))
    return list(result.scalars().all())


async def has_seen(db: AsyncSession, user_id: uuid.UUID, tag: str) -> bool:
    result = await db.execute(
        select(WhatsNewSeen.id).where(WhatsNewSeen.user_id == user_id, WhatsNewSeen.tag == tag)
    )
    return result.scalar_one_or_none() is not None


async def mark_seen(db: AsyncSession, user_id: uuid.UUID, tag: str) -> None:
    """Idempotent — a tag marked seen twice (e.g. a retried request) is a no-op the second time,
    not a constraint-violation error, so the client's fire-and-forget call never needs to handle a
    conflict response. Check-then-insert rather than a database-level upsert, matching
    `feature_tour_seen_repo.mark_seen`'s exact same dedup convention. Also used directly by the
    CLI's `disable-whats-new` command, to pre-emptively suppress an entry the account hasn't
    reached yet."""
    if await has_seen(db, user_id, tag):
        return
    db.add(WhatsNewSeen(user_id=user_id, tag=tag))
    await db.commit()


async def reset_seen(db: AsyncSession, user_id: uuid.UUID, tag: str) -> None:
    """The CLI's `enable-whats-new` command — lets a dismissed entry show again (re-testing after
    a copy change, or a user who wants to see one again). No-op if it was never seen."""
    await db.execute(delete(WhatsNewSeen).where(WhatsNewSeen.user_id == user_id, WhatsNewSeen.tag == tag))
    await db.commit()
