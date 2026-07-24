import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_paired
from app.models.user import User
from app.schemas.locker import (
    LockerAlbumCreate,
    LockerAlbumOut,
    LockerAlbumUpdate,
    LockerItemCreate,
    LockerItemOut,
    LockerItemUpdate,
)
from app.services import locker_service

router = APIRouter(prefix="/locker", tags=["locker"])


@router.get("/albums", response_model=list[LockerAlbumOut])
async def list_albums(
    current_user: User = Depends(require_paired), db: AsyncSession = Depends(get_db)
) -> list[LockerAlbumOut]:
    return await locker_service.list_albums(db, current_user)


@router.post("/albums", response_model=LockerAlbumOut, status_code=status.HTTP_201_CREATED)
async def create_album(
    payload: LockerAlbumCreate,
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> LockerAlbumOut:
    return await locker_service.create_album(db, current_user, payload)


@router.patch("/albums/{album_id}", response_model=LockerAlbumOut)
async def rename_album(
    album_id: uuid.UUID,
    payload: LockerAlbumUpdate,
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> LockerAlbumOut:
    return await locker_service.rename_album(db, current_user, album_id, payload)


@router.delete("/albums/{album_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_album(
    album_id: uuid.UUID,
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> None:
    await locker_service.delete_album(db, current_user, album_id)


@router.get("/items", response_model=list[LockerItemOut])
async def list_items(
    current_user: User = Depends(require_paired), db: AsyncSession = Depends(get_db)
) -> list[LockerItemOut]:
    return await locker_service.list_items(db, current_user)


@router.post("/items", response_model=LockerItemOut, status_code=status.HTTP_201_CREATED)
async def create_item(
    payload: LockerItemCreate,
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> LockerItemOut:
    return await locker_service.create_item(db, current_user, payload)


@router.get("/items/{item_id}", response_model=LockerItemOut)
async def get_item(
    item_id: uuid.UUID,
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> LockerItemOut:
    return await locker_service.get_item(db, current_user, item_id)


@router.patch("/items/{item_id}", response_model=LockerItemOut)
async def update_item(
    item_id: uuid.UUID,
    payload: LockerItemUpdate,
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> LockerItemOut:
    return await locker_service.update_item(db, current_user, item_id, payload)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: uuid.UUID,
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> None:
    await locker_service.delete_item(db, current_user, item_id)


@router.delete("/items", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_my_locker_data(
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> None:
    await locker_service.delete_all_own_data(db, current_user)
