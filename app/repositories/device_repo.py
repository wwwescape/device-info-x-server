import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device


async def get_by_token(db: AsyncSession, fcm_token: str) -> Device | None:
    result = await db.execute(select(Device).where(Device.fcm_token == fcm_token))
    return result.scalar_one_or_none()


async def upsert(
    db: AsyncSession, *, user_id: uuid.UUID, fcm_token: str, platform: str, app_version: str | None
) -> Device:
    now = datetime.now(UTC)
    existing = await get_by_token(db, fcm_token)
    if existing is not None:
        # Reassign ownership too: a reinstalled app can hand the same FCM
        # token to a different account on the same physical device.
        existing.user_id = user_id
        existing.platform = platform
        existing.app_version = app_version
        existing.last_active_at = now
        await db.flush()
        return existing

    device = Device(
        user_id=user_id, fcm_token=fcm_token, platform=platform, app_version=app_version, last_active_at=now
    )
    db.add(device)
    await db.flush()
    return device


async def delete_by_token(db: AsyncSession, user_id: uuid.UUID, fcm_token: str) -> bool:
    result = await db.execute(delete(Device).where(Device.fcm_token == fcm_token, Device.user_id == user_id))
    return result.rowcount > 0


async def list_tokens_for_user(db: AsyncSession, user_id: uuid.UUID) -> list[str]:
    result = await db.execute(select(Device.fcm_token).where(Device.user_id == user_id))
    return list(result.scalars().all())


async def list_for_user(db: AsyncSession, user_id: uuid.UUID) -> list[Device]:
    result = await db.execute(
        select(Device).where(Device.user_id == user_id).order_by(Device.last_active_at.desc())
    )
    return list(result.scalars().all())
