import uuid

from sqlalchemy import ARRAY, Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Fixed vocabularies — validated at the schema layer (app/schemas/intimacy_log.py), stored as
# plain string arrays here rather than native Postgres enums so the list can be tweaked without
# an ALTER TYPE migration (same trade-off already made for reminder_minutes_before/reminder_days_before).
POSITIONS = (
    "69",
    "69 Sixty Nine",
    "Ballerina",
    "Cowgirl",
    "Doggy Style",
    "Lotus",
    "Missionary",
    "Mutual Masturbation",
    "Oral",
    "Pretzel Dip",
    "Prone Boning",
    "Reverse Cowgirl",
    "Scissoring",
    "Spooning",
    "Standing",
    "Wheelbarrow",
)

LOCATIONS = (
    "Balcony",
    "Bathroom",
    "Beach",
    "Bedroom",
    "Car",
    "Elevator",
    "Gym",
    "Hotel",
    "Kitchen",
    "Living Room",
    "Office",
    "Outdoors",
    "Pool",
    "Rooftop",
)

MOODS = (
    "Romantic",
    "Horny",
    "Playful",
    "Passionate",
    "Spontaneous",
    "Relaxed",
    "Adventurous",
)

# Sentinel for "initiated_by" meaning "both partners" — the other valid values are a real
# user-id string, validated against the pair's own two ids in calendar_service, not here.
INITIATED_BY_BOTH = "both"

# Sentinel for "orgasmed_by" meaning "neither partner" — a real answer, distinct from the field
# simply being unset. The other valid values are INITIATED_BY_BOTH or a real user-id string,
# validated the same way as initiated_by in calendar_service.
ORGASMED_BY_NONE = "none"


class IntimacyLog(Base):
    """1:1 with `CalendarEvent` — `event_id` is the primary key, not a separate generated id,
    since there is never more than one log per event (see calendar_service's create/update,
    which upsert-or-clear this row the same way `CalendarEventReminder` rows are replaced
    wholesale rather than diffed)."""

    __tablename__ = "intimacy_logs"

    event_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("calendar_events.id", ondelete="CASCADE"), primary_key=True
    )
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    initiated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    protection_used: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    positions: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    locations: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    moods: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    rounds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    orgasmed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
