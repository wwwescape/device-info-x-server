import enum
import uuid

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import CreatedAtMixin, UpdatedAtMixin, UUIDPrimaryKeyMixin


class NotepadEntryType(str, enum.Enum):
    PRIVATE = "private"
    SHARED = "shared"


class NotepadEntry(UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    """A single note, in one of two scopes. PRIVATE: [owner_id] set to its creator, visible/
    editable by that user only — the service layer never falls back to owner_id's partner the
    way locker_service does for Safe Locker, since a private note must stay genuinely invisible
    to the partner, not merely partner-can't-edit. SHARED: [owner_id] null, visible/editable by
    both paired users equally — no per-pair scoping column exists anywhere (this app only ever
    pairs exactly 2 users total), so a SHARED row simply has no owner at all.

    [updated_at] (via UpdatedAtMixin) doubles as the optimistic-concurrency token for SHARED
    entries only: a save must include the value it last read, and the service rejects the write
    (ConflictError) if the row has moved since — see notepad_service.update_entry. This is the
    first such check anywhere in this codebase; every other editable record here is
    last-write-wins. PRIVATE entries are last-write-wins too, deliberately — a PRIVATE note has
    exactly one possible writer (its own owner, across however many of their own devices), so
    there's nothing meaningful for a version conflict to protect against."""

    __tablename__ = "notepad_entries"

    type: Mapped[NotepadEntryType] = mapped_column(
        SAEnum(NotepadEntryType, name="notepad_entry_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
