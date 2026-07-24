import datetime
import uuid

from pydantic import BaseModel, Field

from app.models.locker import LockerCategory


class LockerAlbumCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class LockerAlbumUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class LockerAlbumOut(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    created_at: datetime.datetime


class LockerItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    media_id: uuid.UUID | None = None
    album_id: uuid.UUID | None = None
    category: LockerCategory
    is_encrypted: bool = False
    encryption_metadata: dict | None = None
    is_favorite: bool = False


class LockerItemUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    media_id: uuid.UUID | None = None
    album_id: uuid.UUID | None = None
    category: LockerCategory | None = None
    is_encrypted: bool | None = None
    encryption_metadata: dict | None = None
    is_favorite: bool | None = None


class LockerItemOut(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    title: str
    description: str | None
    media_id: uuid.UUID | None
    album_id: uuid.UUID | None
    category: LockerCategory
    is_encrypted: bool
    encryption_metadata: dict | None
    is_favorite: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime
