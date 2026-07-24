import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.message import MessageType


class MessageCreate(BaseModel):
    type: MessageType
    body: str | None = Field(default=None, max_length=8000)
    media_id: uuid.UUID | None = None
    reply_to_id: uuid.UUID | None = None
    # Lets the Android client retry a send after a dropped response without
    # risking a duplicate message; the server treats a repeat as a no-op.
    client_message_id: uuid.UUID


class MessageUpdate(BaseModel):
    body: str = Field(min_length=1, max_length=8000)


class ReactionCreate(BaseModel):
    emoji: str = Field(min_length=1, max_length=16)


class ReactionOut(BaseModel):
    user_id: uuid.UUID
    emoji: str


class MessageOut(BaseModel):
    id: uuid.UUID
    sender_id: uuid.UUID
    type: MessageType
    body: str | None
    media_id: uuid.UUID | None
    reply_to_id: uuid.UUID | None
    client_message_id: uuid.UUID
    edited_at: datetime | None
    deleted_at: datetime | None
    read_at: datetime | None
    delivered_at: datetime | None
    is_pinned: bool
    pinned_at: datetime | None
    created_at: datetime
    reactions: list[ReactionOut] = []
    is_starred_by_me: bool = False
    link_preview_url: str | None = None
    link_preview_title: str | None = None
    link_preview_description: str | None = None
    link_preview_media_id: uuid.UUID | None = None


class MessagePage(BaseModel):
    items: list[MessageOut]
