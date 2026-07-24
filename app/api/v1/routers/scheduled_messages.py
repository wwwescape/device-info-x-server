import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_paired
from app.models.user import User
from app.schemas.scheduled_message import ScheduledMessageCreate, ScheduledMessageOut
from app.services import scheduled_message_service

router = APIRouter(prefix="/messages/scheduled", tags=["scheduled-messages"])


@router.get("", response_model=list[ScheduledMessageOut])
async def list_scheduled_messages(
    current_user: User = Depends(require_paired), db: AsyncSession = Depends(get_db)
) -> list[ScheduledMessageOut]:
    return await scheduled_message_service.list_scheduled(db, current_user)


@router.post("", response_model=ScheduledMessageOut, status_code=status.HTTP_201_CREATED)
async def create_scheduled_message(
    payload: ScheduledMessageCreate,
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> ScheduledMessageOut:
    return await scheduled_message_service.create_scheduled_message(db, current_user, payload)


@router.delete("/{scheduled_message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_scheduled_message(
    scheduled_message_id: uuid.UUID,
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> None:
    await scheduled_message_service.cancel_scheduled_message(db, current_user, scheduled_message_id)


@router.post("/{scheduled_message_id}/send-now", status_code=status.HTTP_204_NO_CONTENT)
async def send_scheduled_message_now(
    scheduled_message_id: uuid.UUID,
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> None:
    await scheduled_message_service.send_scheduled_message_now(db, current_user, scheduled_message_id)
