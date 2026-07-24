import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.media_asset import MediaCategory


class MediaAssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    category: MediaCategory
    original_filename: str | None = None
    mime_type: str
    size_bytes: int
    width: int | None = None
    height: int | None = None
    duration_ms: int | None = None
    thumbnail_media_id: uuid.UUID | None = None
    created_at: datetime
