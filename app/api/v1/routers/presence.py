from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_paired
from app.models.user import User
from app.services import presence_service

router = APIRouter(prefix="/presence", tags=["presence"])


@router.post("/notify-online", status_code=status.HTTP_204_NO_CONTENT)
async def notify_online(
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> None:
    await presence_service.send_online_ping(db, current_user)
