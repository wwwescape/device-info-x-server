import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.partner_code import PartnerCode


async def create(
    db: AsyncSession, *, user_id: uuid.UUID, code_hash: str, code_preview: str, expires_at: datetime
) -> PartnerCode:
    record = PartnerCode(
        user_id=user_id, code_hash=code_hash, code_preview=code_preview, expires_at=expires_at
    )
    db.add(record)
    await db.flush()
    return record


async def get_active_for_user(db: AsyncSession, user_id: uuid.UUID) -> PartnerCode | None:
    result = await db.execute(
        select(PartnerCode)
        .where(
            PartnerCode.user_id == user_id,
            PartnerCode.consumed_at.is_(None),
            PartnerCode.expires_at > datetime.now(UTC),
        )
        .order_by(PartnerCode.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_valid_by_hash(db: AsyncSession, code_hash: str) -> PartnerCode | None:
    result = await db.execute(
        select(PartnerCode).where(
            PartnerCode.code_hash == code_hash,
            PartnerCode.consumed_at.is_(None),
            PartnerCode.expires_at > datetime.now(UTC),
        )
    )
    return result.scalar_one_or_none()


async def invalidate_all_for_user(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Deletes all outstanding (unconsumed) codes for a user — used both when
    regenerating a code and after a successful pairing."""
    await db.execute(
        delete(PartnerCode).where(PartnerCode.user_id == user_id, PartnerCode.consumed_at.is_(None))
    )


async def consume(db: AsyncSession, code: PartnerCode) -> None:
    code.consumed_at = datetime.now(UTC)
    await db.flush()
