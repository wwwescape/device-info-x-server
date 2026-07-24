import enum
import uuid
from datetime import date

from sqlalchemy import ARRAY, Date, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import CreatedAtMixin, UpdatedAtMixin, UUIDPrimaryKeyMixin


class FlowIntensity(str, enum.Enum):
    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"


class PeriodDayLog(UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    """One row per logged day, not per whole period — symptoms/flow/notes are recorded per day.
    A "period day" (what the prediction math groups into cycles, see
    `period_service.predict_next_cycle_start`) is any row with [flow_intensity] set; a row with
    only [symptoms]/[notes] (e.g. spotting, cramps, mood on a day that isn't part of a period at
    all) doesn't count toward a cycle until/unless it's edited to add a real flow value. Cycle
    start/end/length are never stored — they're derived at read time from contiguous period-day
    runs, so there's nothing that can drift out of sync with the day logs themselves."""

    __tablename__ = "period_day_logs"
    __table_args__ = (UniqueConstraint("user_id", "log_date", name="uq_period_day_logs_user_date"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    log_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    symptoms: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    flow_intensity: Mapped[FlowIntensity | None] = mapped_column(
        SAEnum(FlowIntensity, name="flow_intensity", values_callable=lambda e: [m.value for m in e]),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
