from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.user import User
from app.repositories import device_repo


async def register_device(
    db: AsyncSession, user: User, *, fcm_token: str, platform: str, app_version: str | None
) -> None:
    await device_repo.upsert(db, user_id=user.id, fcm_token=fcm_token, platform=platform, app_version=app_version)
    await db.commit()


async def unregister_device(db: AsyncSession, user: User, fcm_token: str) -> None:
    deleted = await device_repo.delete_by_token(db, user.id, fcm_token)
    await db.commit()
    if not deleted:
        raise NotFoundError("device not found")
