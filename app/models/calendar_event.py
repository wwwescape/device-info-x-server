import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import CreatedAtMixin, UpdatedAtMixin, UUIDPrimaryKeyMixin


class EventType(str, enum.Enum):
    BIRTHDAY = "birthday"
    WEDDING_ANNIVERSARY = "wedding_anniversary"
    ANNIVERSARY = "anniversary"
    VACATION = "vacation"
    PLANNED_TRIP = "planned_trip"
    PLANNED_DATE = "planned_date"
    UNPLANNED_DATE = "unplanned_date"
    PLANNED_DRIVE = "planned_drive"
    UNPLANNED_DRIVE = "unplanned_drive"
    REMINDER = "reminder"
    CUSTOM = "custom"


# The only types allowed to carry a recurrence_rule — enforced in calendar_service's
# create_event/update_event, alongside the existing _validate_rrule syntax check.
RECURRING_ALLOWED_TYPES = frozenset(
    {
        EventType.BIRTHDAY,
        EventType.WEDDING_ANNIVERSARY,
        EventType.ANNIVERSARY,
        EventType.REMINDER,
        EventType.CUSTOM,
    }
)

# The only types that may ever be marked cancelled — enforced in calendar_service's
# create_event/update_event, same shape as RECURRING_ALLOWED_TYPES above.
CANCELLABLE_TYPES = frozenset(
    {
        EventType.PLANNED_DATE,
        EventType.PLANNED_DRIVE,
        EventType.PLANNED_TRIP,
        EventType.CUSTOM,
    }
)


class CalendarEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    __tablename__ = "calendar_events"

    created_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[EventType] = mapped_column(
        SAEnum(EventType, name="event_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    all_day: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # RFC5545 RRULE, e.g. "FREQ=WEEKLY;BYDAY=MO". Occurrences are expanded at
    # runtime by the reminder scheduler, not pre-materialized as rows.
    recurrence_rule: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recurrence_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    color: Mapped[str | None] = mapped_column(String(16), nullable=True)
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CalendarEventReminder(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "calendar_event_reminders"

    event_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("calendar_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    minutes_before: Mapped[int] = mapped_column(Integer, nullable=False)
