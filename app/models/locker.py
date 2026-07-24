import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import CreatedAtMixin, UpdatedAtMixin, UUIDPrimaryKeyMixin


class LockerCategory(str, enum.Enum):
    DOCUMENT = "document"
    PHOTO = "photo"
    VIDEO = "video"
    NOTE = "note"
    OTHER = "other"


class LockerAlbum(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Groups LockerItems. Shared-but-owner-edits-only, same access rule as
    LockerItem: owner_id + owner's partner can both see it, only the creator
    can rename/delete. Deleting an album is a hard delete — LockerItem.album_id's
    ON DELETE SET NULL detaches its items rather than deleting them."""

    __tablename__ = "locker_albums"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class LockerItem(UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    """Safe Locker metadata. is_encrypted/encryption_metadata are placeholders
    for a future client-side E2E-encrypted-file feature — unused until then,
    but present now so adding it later doesn't require a migration."""

    __tablename__ = "locker_items"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True
    )
    album_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("locker_albums.id", ondelete="SET NULL"), nullable=True, index=True
    )
    category: Mapped[LockerCategory] = mapped_column(
        SAEnum(LockerCategory, name="locker_category", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    is_encrypted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    encryption_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
