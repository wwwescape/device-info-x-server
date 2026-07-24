import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class ReminderSourceType(str, enum.Enum):
    CALENDAR_EVENT = "calendar_event"
    SPECIAL_EVENT = "special_event"


class ReminderDelivery(UUIDPrimaryKeyMixin, Base):
    """Dedupe log so the scheduler's periodic sweep never sends the same
    reminder twice, across both calendar events and special events."""

    __tablename__ = "reminder_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "source_type",
            "source_id",
            "occurrence_at",
            "minutes_before",
            name="uq_reminder_deliveries_source_occurrence_minutes",
        ),
    )

    source_type: Mapped[ReminderSourceType] = mapped_column(
        SAEnum(ReminderSourceType, name="reminder_source_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    occurrence_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    minutes_before: Mapped[int] = mapped_column(Integer, nullable=False)
    delivered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
