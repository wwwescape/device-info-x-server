import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class CallLogType(str, enum.Enum):
    VOICE = "voice"
    VIDEO = "video"


class CallLogStatus(str, enum.Enum):
    ANSWERED = "answered"
    MISSED = "missed"
    DECLINED = "declined"
    CANCELLED = "cancelled"


class CallLog(UUIDPrimaryKeyMixin, Base):
    """One row per resolved call attempt — written once, at the moment
    `call_room_service._resolve` ends whatever was ringing/active, never updated afterward.
    Deliberately the one piece of calling that *does* persist, unlike the room state itself
    (still fully ephemeral, no `Call` table backs it) — see `CALLING_PLAN.md` for why calling was
    originally scoped "no history, ever," and TODOS.md for the follow-up discussion that reversed
    that specifically for this table, given messages already persist in full elsewhere in this
    app and this is metadata-only, not content.

    [status] collapses the six raw resolution reasons
    (`cancelled`/`declined`/`no_response`/`ended`/`left`/`interrupted`) into what a call-log UI
    actually wants to show: if the room ever reached `active`, this is `ANSWERED` regardless of
    which of `ended`/`left`/`interrupted` finally ended it — otherwise it's whichever of
    `DECLINED`/`CANCELLED`/`MISSED` (`no_response`, or `interrupted` while still only ringing)
    actually applied. See `call_room_service._resolve`'s own call site for the exact mapping."""

    __tablename__ = "call_logs"

    caller_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    callee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    call_type: Mapped[CallLogType] = mapped_column(
        SAEnum(CallLogType, name="call_log_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    status: Mapped[CallLogStatus] = mapped_column(
        SAEnum(CallLogStatus, name="call_log_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    # When the call was initiated (ring start), not when this row was written — matches every
    # mainstream phone app's own "call log shows when you placed/received the call" convention.
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    # Only meaningful when status == ANSWERED — measured from when the room actually went
    # `active` (not from `started_at`/ring-start), matching the Call Room screen's own elapsed
    # timer. Null for every other status.
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
