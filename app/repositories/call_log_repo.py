import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call_log import CallLog

DEFAULT_PAGE_LIMIT = 100


async def create(db: AsyncSession, **fields) -> CallLog:
    entry = CallLog(**fields)
    db.add(entry)
    await db.flush()
    return entry


async def list_for_couple(
    db: AsyncSession, user_id: uuid.UUID, partner_id: uuid.UUID, *, limit: int = DEFAULT_PAGE_LIMIT
) -> list[CallLog]:
    """Every call between this couple, newest first — the 2-person model means `caller_id` alone
    (always one of the pair) already scopes this correctly, no need to also check `callee_id`."""
    stmt = (
        select(CallLog)
        .where(CallLog.caller_id.in_((user_id, partner_id)))
        .order_by(CallLog.started_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
