import enum
import uuid

from sqlalchemy import BigInteger, ForeignKey, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin


class MediaCategory(str, enum.Enum):
    MESSAGE_IMAGE = "message_image"
    MESSAGE_VOICE = "message_voice"
    MESSAGE_VIDEO = "message_video"
    MESSAGE_LINK_PREVIEW = "message_link_preview"
    AVATAR = "avatar"
    LOCKER_FILE = "locker_file"


class MediaAsset(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Metadata for every uploaded file. The bytes live on disk under MEDIA_ROOT;
    this row is what access control and the /media/{id}/download endpoint key off."""

    __tablename__ = "media_assets"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[MediaCategory] = mapped_column(
        SAEnum(MediaCategory, name="media_category", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
