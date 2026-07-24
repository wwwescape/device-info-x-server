import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class InsightSeen(UUIDPrimaryKeyMixin, Base):
    """Which per-user DIX AI insights (`Insight.id`) have already been shown and dismissed.
    Structural mirror of `WhatsNewSeen`/`FeatureTourSeen`, one content namespace over — except
    unlike those two, the thing being marked seen is itself a DB row (`Insight`) rather than a
    client-hardcoded tag string, so [insight_id] cascades on the insight's own deletion too, not
    just the user's."""

    __tablename__ = "insight_seen"
    __table_args__ = (UniqueConstraint("user_id", "insight_id", name="uq_insight_seen_user_insight"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    insight_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("insights.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
