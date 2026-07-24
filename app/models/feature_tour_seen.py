import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class FeatureTourSeen(UUIDPrimaryKeyMixin, Base):
    """Which per-user coach-mark tours (the client's `FeatureTourCoordinator` `tourKey`s — one per
    guided-tour target, e.g. "online_ping") have already been shown and dismissed. Server-side by
    design, not a client `DataStore` flag: every other "seen this before" flag in the app is local
    only and gets wiped on uninstall/reinstall, but a tour should only ever show once per account,
    for the lifetime of that account — this is the one place that needs to survive a reinstall."""

    __tablename__ = "feature_tour_seen"
    __table_args__ = (UniqueConstraint("user_id", "tour_key", name="uq_feature_tour_seen_user_tour"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tour_key: Mapped[str] = mapped_column(String(64), nullable=False)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
