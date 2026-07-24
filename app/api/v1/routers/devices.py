from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.device import DeviceRegisterRequest
from app.services import device_service

router = APIRouter(prefix="/devices", tags=["devices"])


@router.post("", status_code=status.HTTP_204_NO_CONTENT)
async def register_device(
    payload: DeviceRegisterRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await device_service.register_device(
        db,
        current_user,
        fcm_token=payload.fcm_token,
        platform=payload.platform,
        app_version=payload.app_version,
    )


@router.delete("/{fcm_token}", status_code=status.HTTP_204_NO_CONTENT)
async def unregister_device(
    fcm_token: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await device_service.unregister_device(db, current_user, fcm_token)
