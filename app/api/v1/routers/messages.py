import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_paired
from app.models.user import User
from app.schemas.message import MessageCreate, MessageOut, MessageUpdate, PollVoteUpdate, ReactionCreate
from app.services import message_service

router = APIRouter(prefix="/messages", tags=["messages"])


@router.get("/search", response_model=list[MessageOut])
async def search_messages(
    q: str,
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> list[MessageOut]:
    return await message_service.search_messages(db, current_user, q, limit)


@router.get("/pinned", response_model=list[MessageOut])
async def list_pinned(
    current_user: User = Depends(require_paired), db: AsyncSession = Depends(get_db)
) -> list[MessageOut]:
    return await message_service.list_pinned(db, current_user)


@router.get("/starred", response_model=list[MessageOut])
async def list_starred(
    current_user: User = Depends(require_paired), db: AsyncSession = Depends(get_db)
) -> list[MessageOut]:
    return await message_service.list_starred(db, current_user)


@router.get("", response_model=list[MessageOut])
async def list_messages(
    before: datetime | None = None,
    after: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> list[MessageOut]:
    return await message_service.list_messages(db, current_user, before=before, after=after, limit=limit)


@router.post("", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
async def send_message(
    payload: MessageCreate,
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    return await message_service.send_message(db, current_user, payload)


@router.patch("/{message_id}", response_model=MessageOut)
async def edit_message(
    message_id: uuid.UUID,
    payload: MessageUpdate,
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    return await message_service.edit_message(db, current_user, message_id, payload.body)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def wipe_conversation(
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> None:
    await message_service.wipe_conversation(db, current_user)


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    message_id: uuid.UUID,
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> None:
    await message_service.delete_message(db, current_user, message_id)


@router.post("/{message_id}/pin", response_model=MessageOut)
async def pin_message(
    message_id: uuid.UUID,
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    return await message_service.set_pinned(db, current_user, message_id, True)


@router.delete("/{message_id}/pin", response_model=MessageOut)
async def unpin_message(
    message_id: uuid.UUID,
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    return await message_service.set_pinned(db, current_user, message_id, False)


@router.post("/{message_id}/star", status_code=status.HTTP_204_NO_CONTENT)
async def star_message(
    message_id: uuid.UUID,
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> None:
    await message_service.set_starred(db, current_user, message_id, True)


@router.delete("/{message_id}/star", status_code=status.HTTP_204_NO_CONTENT)
async def unstar_message(
    message_id: uuid.UUID,
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> None:
    await message_service.set_starred(db, current_user, message_id, False)


@router.post("/{message_id}/reactions", response_model=MessageOut)
async def add_reaction(
    message_id: uuid.UUID,
    payload: ReactionCreate,
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    return await message_service.set_reaction(db, current_user, message_id, payload.emoji)


@router.delete("/{message_id}/reactions", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reaction(
    message_id: uuid.UUID,
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> None:
    await message_service.remove_reaction(db, current_user, message_id)


@router.put("/{message_id}/poll/vote", response_model=MessageOut)
async def vote_poll(
    message_id: uuid.UUID,
    payload: PollVoteUpdate,
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    return await message_service.vote_poll(db, current_user, message_id, payload.option_ids)


@router.post("/{message_id}/poll/close", response_model=MessageOut)
async def close_poll(
    message_id: uuid.UUID,
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    return await message_service.close_poll(db, current_user, message_id)


@router.post("/{message_id}/delivered", response_model=MessageOut)
async def mark_delivered(
    message_id: uuid.UUID,
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    return await message_service.mark_delivered(db, current_user, message_id)


@router.post("/{message_id}/read", response_model=MessageOut)
async def mark_read(
    message_id: uuid.UUID,
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    return await message_service.mark_read(db, current_user, message_id)
