import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class HolidayEventNotified(UUIDPrimaryKeyMixin, Base):
    """Dedup log for the national/catholic/hindu holiday-greeting push
    (`app.tasks.scheduler._sweep_holiday_events`) — one row per (user, event, calendar date) the
    push has already fired for. Deliberately its own small table rather than either
    `ReminderDelivery` (assumes a real DB-row `source_id`; a bundled `events.json` entry isn't one)
    or a bespoke single column on `User` like `last_birthday_notified_year` (that shape only works
    for "one date per user" — a holiday event is the same for every user, and there are many of
    them, so the dedup key needs to be per (user, event) too, not just per user)."""

    __tablename__ = "holiday_event_notified"
    __table_args__ = (
        UniqueConstraint("user_id", "event_name", "event_date", name="uq_holiday_event_notified_user_event_date"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_name: Mapped[str] = mapped_column(String(128), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    notified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
