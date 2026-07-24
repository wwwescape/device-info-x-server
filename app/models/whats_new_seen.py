import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class WhatsNewSeen(UUIDPrimaryKeyMixin, Base):
    """Which per-user "What's New" entries (the client's static `WHATS_NEW_ENTRIES` catalog's own
    `tag`s — one per shipped-feature bullet, e.g. "duress_code_2026_08") have already been shown
    and dismissed. Exact structural mirror of `FeatureTourSeen` — server-side by design for the
    same reason: this should only ever show once per account, for the lifetime of that account,
    surviving an uninstall/reinstall unlike a local `DataStore` flag. Unlike guided tours, the
    bullet copy itself lives client-side too (a string resource per tag, localized), not here —
    this table is pure seen-state, never content."""

    __tablename__ = "whats_new_seen"
    __table_args__ = (UniqueConstraint("user_id", "tag", name="uq_whats_new_seen_user_tag"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tag: Mapped[str] = mapped_column(String(64), nullable=False)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
