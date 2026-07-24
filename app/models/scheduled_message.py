import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin


class ScheduledMessage(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A staged text message waiting to be delivered at [scheduled_at]. Always privately owned by
    [sender_id] — the partner never sees a pending row here, only the real `Message` once
    `app.tasks.scheduler._sweep_scheduled_messages` (or an on-demand "send now") actually delivers
    it, so a scheduled message stays a surprise until it fires. No `status` column: the row's mere
    existence *is* the pending state, and its deletion (in
    `scheduled_message_service.deliver_scheduled_message`) is itself the once-only delivery
    guarantee — no separate `ReminderDelivery`-style dedup table needed, unlike the reminder-style
    sweeps in `scheduler.py`."""

    __tablename__ = "scheduled_messages"

    sender_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    scheduled_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
