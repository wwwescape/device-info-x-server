import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_paired
from app.models.user import User
from app.schemas.notepad import NotepadEntryCreate, NotepadEntryOut, NotepadEntryUpdate
from app.services import notepad_service

router = APIRouter(prefix="/notepad", tags=["notepad"])


@router.get("/private", response_model=list[NotepadEntryOut])
async def list_private_entries(
    current_user: User = Depends(require_paired), db: AsyncSession = Depends(get_db)
) -> list[NotepadEntryOut]:
    return await notepad_service.list_private(db, current_user)


@router.get("/shared", response_model=list[NotepadEntryOut])
async def list_shared_entries(
    current_user: User = Depends(require_paired), db: AsyncSession = Depends(get_db)
) -> list[NotepadEntryOut]:
    return await notepad_service.list_shared(db)


@router.post("", response_model=NotepadEntryOut, status_code=status.HTTP_201_CREATED)
async def create_entry(
    payload: NotepadEntryCreate,
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> NotepadEntryOut:
    return await notepad_service.create_entry(db, current_user, payload)


@router.patch("/{entry_id}", response_model=NotepadEntryOut)
async def update_entry(
    entry_id: uuid.UUID,
    payload: NotepadEntryUpdate,
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> NotepadEntryOut:
    return await notepad_service.update_entry(db, current_user, entry_id, payload)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(
    entry_id: uuid.UUID,
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> None:
    await notepad_service.delete_entry(db, current_user, entry_id)


@router.post("/{entry_id}/duplicate", response_model=NotepadEntryOut, status_code=status.HTTP_201_CREATED)
async def duplicate_entry(
    entry_id: uuid.UUID,
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> NotepadEntryOut:
    return await notepad_service.duplicate_entry(db, current_user, entry_id)
