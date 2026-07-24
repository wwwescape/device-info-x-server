import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Computed, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin


class MessageType(str, enum.Enum):
    TEXT = "text"
    IMAGE = "image"
    VOICE = "voice"
    VIDEO = "video"
    DOCUMENT = "document"
    POLL = "poll"
    SYSTEM = "system"


class Message(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_search_vector", "search_vector", postgresql_using="gin"),
        # Backward pagination (GET /messages?before=...) filters/sorts on this column on every
        # scroll-to-top load, not just the rare cold-start sync — previously unindexed, a
        # sequential scan.
        Index("ix_messages_created_at", "created_at"),
    )

    sender_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[MessageType] = mapped_column(
        SAEnum(MessageType, name="message_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )
    reply_to_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    # Lets the client retry a send without risking a duplicate insert.
    client_message_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), unique=True, nullable=False)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Only 2 users ever exist, so "read by the other party" collapses to one column.
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Same collapse as read_at: set once the other party's device has the message.
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pinned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', coalesce(body, ''))", persisted=True), nullable=True
    )
    # Fetched asynchronously, once, shortly after send (see message_service._fetch_and_attach_link_preview)
    # — all four null means either "no URL in the body" or "fetch failed/found nothing," which are
    # deliberately not distinguished (no retry mechanism exists to care which).
    link_preview_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    link_preview_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    link_preview_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    link_preview_media_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )
    # Poll-only fields — sit unused (default/null) on every other type, same treatment the
    # link_preview_* columns above already get for TEXT-only data.
    poll_allows_multiple: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    poll_closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MessageStar(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Starring is per-user — each partner can star independently."""

    __tablename__ = "message_stars"
    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_message_stars_message_id_user_id"),
    )

    message_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )


class MessageReaction(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One reaction per user per message."""

    __tablename__ = "message_reactions"
    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_message_reactions_message_id_user_id"),
    )

    message_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    emoji: Mapped[str] = mapped_column(String(16), nullable=False)


class PollOption(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One row per option on a `MessageType.POLL` message — never mutated after creation
    (options can't be added/edited/removed post-send, matching WhatsApp)."""

    __tablename__ = "poll_options"

    message_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    option_text: Mapped[str] = mapped_column(String(200), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)


class PollVote(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One row per (option, voter) pair — unique per pair rather than per (message, user) so a
    multi-answer poll can hold several rows for the same voter across different options in the
    same poll. Single-answer enforcement (at most one option per voter per poll) is a service-
    layer check, not a DB constraint, since it only applies when `Message.poll_allows_multiple`
    is false."""

    __tablename__ = "poll_votes"
    __table_args__ = (
        UniqueConstraint("option_id", "user_id", name="uq_poll_votes_option_id_user_id"),
    )

    option_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("poll_options.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
