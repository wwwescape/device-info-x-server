import enum
import uuid
from datetime import date

from sqlalchemy import ARRAY, Date, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import CreatedAtMixin, UpdatedAtMixin, UUIDPrimaryKeyMixin


class FlowIntensity(str, enum.Enum):
    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"


class PeriodCycle(UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    """One row per cycle, matching Android's CycleEntryEntity — symptoms/flow
    are recorded per cycle, not per day. Prediction math lives in the Android
    app; the backend just stores what the user records."""

    __tablename__ = "period_cycles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cycle_start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    cycle_length_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    period_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    symptoms: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    flow_intensity: Mapped[FlowIntensity | None] = mapped_column(
        SAEnum(FlowIntensity, name="flow_intensity", values_callable=lambda e: [m.value for m in e]),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
