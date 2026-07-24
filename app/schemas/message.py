import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.message import MessageType

# WhatsApp's own bounds — a poll needs at least 2 options to mean anything, and a hard cap keeps
# a poll bubble from growing unboundedly tall.
MIN_POLL_OPTIONS = 2
MAX_POLL_OPTIONS = 12


class PollOptionCreate(BaseModel):
    text: str = Field(min_length=1, max_length=200)


class PollCreate(BaseModel):
    options: list[PollOptionCreate] = Field(min_length=MIN_POLL_OPTIONS, max_length=MAX_POLL_OPTIONS)
    allows_multiple: bool = False


class MessageCreate(BaseModel):
    type: MessageType
    body: str | None = Field(default=None, max_length=8000)
    media_id: uuid.UUID | None = None
    reply_to_id: uuid.UUID | None = None
    # Lets the Android client retry a send after a dropped response without
    # risking a duplicate message; the server treats a repeat as a no-op.
    client_message_id: uuid.UUID
    # Poll-only — the question itself is carried in `body` above (already free-form, type-
    # agnostic text on every message type), this is just the option list + settings.
    poll: PollCreate | None = None


class MessageUpdate(BaseModel):
    body: str = Field(min_length=1, max_length=8000)


class PollVoteUpdate(BaseModel):
    """The voter's complete current selection, not an incremental toggle — the server replaces
    whatever this voter had selected before with exactly this set. Simpler and less error-prone
    than separate add/remove-vote endpoints, and matches how a single-select poll's "tap a
    different option to move your vote" already reads as one full state to set, not two events."""

    option_ids: list[uuid.UUID]


class ReactionCreate(BaseModel):
    emoji: str = Field(min_length=1, max_length=16)


class ReactionOut(BaseModel):
    user_id: uuid.UUID
    emoji: str


class PollOptionOut(BaseModel):
    id: uuid.UUID
    text: str
    order_index: int
    vote_count: int
    voted_by: list[uuid.UUID]


class PollOut(BaseModel):
    allows_multiple: bool
    closed_at: datetime | None
    options: list[PollOptionOut]


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
    poll: PollOut | None = None


class MessagePage(BaseModel):
    items: list[MessageOut]
