"""Shared "Call Room" — voice/video calling between paired partners. The room *state* itself is
pure in-memory, process-local, same ephemeral shape as the Tic Tac Toe game room
(`app/services/game_room_service.py`): no DB table, nothing survives a server restart. The one
deliberate exception is `CallLog` (`app/models/call_log.py`) — a single row written per resolved
call, at the exact moment `_resolve` ends whatever was ringing/active. This was originally scoped
"no call history, ever" (`CALLING_PLAN.md` §14); reversed in a later discussion (see TODOS.md)
specifically for this metadata-only log, given messages already persist in full elsewhere in this
app — the signaling/room state itself is still exactly as ephemeral as it always was.

Unlike Game Room, leaving the screen doesn't wipe anything outright — screen presence
(`connection_manager.is_in_call_room_screen`) and call status (`idle`/`ringing`/`active`) are
tracked separately, since a call can be started toward a partner who isn't in the Call Room screen
at all (they get an app-wide incoming-call banner instead — see the client side). Leaving the
*screen* resolves whatever call is actually in-flight for the couple, if any, per the exact
reason table below; it's a no-op if nothing was happening.

Full design: `CALLING_PLAN.md` (repo root) — the state machine, the six-reason resolution table,
and the "never pass `fcm_data` on any `call.*` event" rule are documented there in depth and
implemented here exactly as specified. Reason table (§3 of that doc):

| Trigger                                                    | reason        |
|-------------------------------------------------------------|---------------|
| Caller cancels / leaves / disconnects while ringing          | cancelled     |
| Callee declines                                              | declined      |
| Ring timer elapses, or callee leaves/disconnects while ringing | no_response |
| Either ends an active call                                    | ended         |
| Either leaves/disconnects during an active call               | left          |
| A real GSM call arrives (client-detected, not this module)    | interrupted   |
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.db.session import async_session_factory
from app.models.call_log import CallLogStatus, CallLogType
from app.models.user import User
from app.repositories import call_log_repo
from app.services import notification_service
from app.ws.manager import connection_manager

# How long a ring goes unanswered before auto-resolving as "no_response" — confirmed value,
# see CALLING_PLAN.md §13.
RING_TIMEOUT_SECONDS = 30


@dataclass
class CallRoomState:
    status: str = "idle"  # "idle" | "ringing" | "active"
    call_type: str | None = None  # "voice" | "video"
    caller_id: uuid.UUID | None = None
    callee_id: uuid.UUID | None = None
    # Set the moment `call.start` fires (before ringing even begins) — the timestamp a CallLog
    # row's own `started_at` uses, matching every mainstream phone app's "when was this call
    # placed" convention rather than when (if ever) it was actually answered.
    ring_started_at: datetime | None = None
    # Set the moment status becomes "active" — drives the client's elapsed-time display, and is
    # what a CallLog row's `duration_seconds` is actually measured from.
    started_at: datetime | None = None
    # Self-reported mic/camera state during an active call, relayed so the partner's UI can show
    # "they're muted" — unused/empty in Phase 1 (no `call.control` handler wired up yet; the real
    # audio/video track that would drive this doesn't exist until Phase 2), but the shape is
    # already correct so Phase 2 only needs to add the WS handler, not touch this dataclass.
    muted: dict[uuid.UUID, bool] = field(default_factory=dict)
    camera_on: dict[uuid.UUID, bool] = field(default_factory=dict)


# Keyed exactly like Game Room's `_rooms` — the canonical (order-independent) pair of a couple's
# two user ids, so either partner's own id resolves to the same room. One room per couple.
_rooms: dict[uuid.UUID, CallRoomState] = {}
# Ring-timeout tasks, keyed by the same room key — cancelled the instant a ring resolves any other
# way, so at most one live timer ever exists per room at a time.
_ring_timers: dict[uuid.UUID, asyncio.Task] = {}


def _room_key(user: User) -> uuid.UUID | None:
    if user.partner_id is None:
        return None
    return min(user.id, user.partner_id)


def _cancel_ring_timer(key: uuid.UUID) -> None:
    task = _ring_timers.pop(key, None)
    if task is not None and not task.done():
        task.cancel()


async def _broadcast_state(key: uuid.UUID, user_a_id: uuid.UUID, user_b_id: uuid.UUID) -> None:
    room = _rooms.get(key)
    if room is None:
        return
    payload = {
        "present": {
            str(user_a_id): connection_manager.is_in_call_room_screen(user_a_id),
            str(user_b_id): connection_manager.is_in_call_room_screen(user_b_id),
        },
        "status": room.status,
        "call_type": room.call_type,
        "caller_id": str(room.caller_id) if room.caller_id is not None else None,
        "callee_id": str(room.callee_id) if room.callee_id is not None else None,
        "started_at": room.started_at.isoformat() if room.started_at is not None else None,
        "muted": {str(uid): m for uid, m in room.muted.items()},
        "camera_on": {str(uid): c for uid, c in room.camera_on.items()},
    }
    # No fcm_data, ever, on any call.* event — see this module's own doc comment and
    # CALLING_PLAN.md §10. A partner who isn't live-connected simply doesn't get this.
    await notification_service.notify_user(user_a_id, "call.state", payload, fcm_data=None)
    await notification_service.notify_user(user_b_id, "call.state", payload, fcm_data=None)


async def _resolve(key: uuid.UUID, *, reason: str, by: uuid.UUID | None) -> None:
    """Ends whatever's in-flight (ringing or active), notifies both sides via a one-shot
    `call.ended` — kept separate from the persistent `call.state` for the same reason Game Room's
    `game.partner_left` is: a later reconnect/resync can't replay a stale status line — records
    the resulting `CallLog` row, then broadcasts the now-idle `call.state`."""
    room = _rooms.get(key)
    if room is None or room.status == "idle":
        return

    caller_id, callee_id = room.caller_id, room.callee_id
    call_type, was_active = room.call_type, room.status == "active"
    ring_started_at, active_started_at = room.ring_started_at, room.started_at

    _cancel_ring_timer(key)
    room.status = "idle"
    room.call_type = None
    room.caller_id = None
    room.callee_id = None
    room.ring_started_at = None
    room.started_at = None
    room.muted = {}
    room.camera_on = {}

    payload = {"reason": reason, "by": str(by) if by is not None else None}
    for uid in (caller_id, callee_id):
        if uid is not None:
            await notification_service.notify_user(uid, "call.ended", payload, fcm_data=None)

    if caller_id is not None and callee_id is not None:
        await _broadcast_state(key, caller_id, callee_id)
        await _record_call_log(
            caller_id=caller_id,
            callee_id=callee_id,
            call_type=call_type,
            reason=reason,
            was_active=was_active,
            ring_started_at=ring_started_at,
            active_started_at=active_started_at,
        )


async def _record_call_log(
    *,
    caller_id: uuid.UUID,
    callee_id: uuid.UUID,
    call_type: str | None,
    reason: str,
    was_active: bool,
    ring_started_at: datetime | None,
    active_started_at: datetime | None,
) -> None:
    """Writes the one `CallLog` row this call attempt will ever get — see that model's own doc
    comment for the reason-to-status mapping. `call_type`/`ring_started_at` are only ever `None`
    if this is somehow called against a room that never actually started ringing, which
    `_resolve`'s own `room.status == "idle"` guard already rules out; the check here is just
    defensive."""
    if call_type not in ("voice", "video") or ring_started_at is None:
        return

    if was_active:
        status = CallLogStatus.ANSWERED
        duration = (
            int((datetime.now(UTC) - active_started_at).total_seconds()) if active_started_at is not None else 0
        )
    else:
        duration = None
        if reason == "declined":
            status = CallLogStatus.DECLINED
        elif reason == "cancelled":
            status = CallLogStatus.CANCELLED
        else:  # no_response, or interrupted while still only ringing
            status = CallLogStatus.MISSED

    async with async_session_factory() as db:
        await call_log_repo.create(
            db,
            caller_id=caller_id,
            callee_id=callee_id,
            call_type=CallLogType(call_type),
            status=status,
            started_at=ring_started_at,
            duration_seconds=duration,
        )
        await db.commit()


async def enter_room(user: User) -> None:
    connection_manager.set_in_call_room_screen(user.id, True)
    key = _room_key(user)
    if key is None:
        return
    _rooms.setdefault(key, CallRoomState())
    await _broadcast_state(key, user.id, user.partner_id)


async def leave_room(user: User) -> None:
    """Leaving the screen doesn't wipe an in-flight call the way Game Room wipes its board — it
    resolves it, per the couple's current `status` and this user's role: mid-`ringing`, the caller
    leaving reads as `cancelled` and the callee leaving reads as `no_response` (deliberately
    indistinguishable from silently not answering); mid-`active`, either side leaving reads as
    `left`. If nothing was in flight, this is just a presence update (the informational
    "partner is in the Call Room" pill)."""
    connection_manager.set_in_call_room_screen(user.id, False)
    key = _room_key(user)
    if key is None:
        return
    room = _rooms.get(key)
    if room is None:
        return
    if room.status == "idle":
        await _broadcast_state(key, user.id, user.partner_id)
        return

    if room.status == "ringing":
        reason = "cancelled" if user.id == room.caller_id else "no_response"
    else:  # "active"
        reason = "left"
    await _resolve(key, reason=reason, by=user.id)


async def handle_disconnect(user_id: uuid.UUID) -> None:
    """Called from `presence_service.mark_offline` on every full-offline transition — cheap no-op
    unless [user_id] actually had the Call Room screen open, so the call site there can stay
    unconditional. Covers the app being killed/backgrounded or the connection dropping, none of
    which send an explicit `screen.call_room_leave` first — routes through the exact same
    [leave_room] resolution logic a deliberate leave does, which is also how "ringing/vibration
    ends the instant either partner exits the app" (CALLING_PLAN.md §13) actually happens."""
    if not connection_manager.is_in_call_room_screen(user_id):
        return
    async with async_session_factory() as db:
        user = await db.get(User, user_id)
        if user is None:
            return
        await leave_room(user)


async def start_call(user: User, call_type: str) -> None:
    """Silently no-ops rather than erroring on either failure case — the client's own Start row
    is already gated on the partner being online, so a rejection here should only ever happen from
    the two-callers-race case (see CALLING_PLAN.md §3: whichever `call.start` the server processes
    first wins, the second finds `status != "idle"` and is dropped) or a stale UI, neither of which
    is worth surfacing as a user-visible error."""
    if call_type not in ("voice", "video"):
        return
    key = _room_key(user)
    if key is None:
        return
    room = _rooms.setdefault(key, CallRoomState())
    if room.status != "idle":
        return
    if user.partner_id is None or not connection_manager.is_online(user.partner_id):
        return

    room.status = "ringing"
    room.call_type = call_type
    room.caller_id = user.id
    room.callee_id = user.partner_id
    room.ring_started_at = datetime.now(UTC)

    _cancel_ring_timer(key)
    _ring_timers[key] = asyncio.create_task(_ring_timeout(key))

    await _broadcast_state(key, user.id, user.partner_id)


async def _ring_timeout(key: uuid.UUID) -> None:
    try:
        await asyncio.sleep(RING_TIMEOUT_SECONDS)
    except asyncio.CancelledError:
        return
    room = _rooms.get(key)
    if room is None or room.status != "ringing":
        return
    await _resolve(key, reason="no_response", by=room.callee_id)


async def accept_call(user: User) -> None:
    key = _room_key(user)
    if key is None:
        return
    room = _rooms.get(key)
    if room is None or room.status != "ringing" or user.id != room.callee_id:
        return
    _cancel_ring_timer(key)
    room.status = "active"
    room.started_at = datetime.now(UTC)
    is_video = room.call_type == "video"
    room.muted = {room.caller_id: False, room.callee_id: False}
    room.camera_on = {room.caller_id: is_video, room.callee_id: is_video}
    await _broadcast_state(key, user.id, user.partner_id)


async def decline_call(user: User) -> None:
    key = _room_key(user)
    if key is None:
        return
    room = _rooms.get(key)
    if room is None or room.status != "ringing" or user.id != room.callee_id:
        return
    await _resolve(key, reason="declined", by=user.id)


async def cancel_call(user: User) -> None:
    key = _room_key(user)
    if key is None:
        return
    room = _rooms.get(key)
    if room is None or room.status != "ringing" or user.id != room.caller_id:
        return
    await _resolve(key, reason="cancelled", by=user.id)


async def end_call(user: User) -> None:
    key = _room_key(user)
    if key is None:
        return
    room = _rooms.get(key)
    if room is None or room.status != "active" or user.id not in (room.caller_id, room.callee_id):
        return
    await _resolve(key, reason="ended", by=user.id)


async def interrupt_call(user: User) -> None:
    """A real GSM call arrived on this device (client-detected via `TelephonyCallback`/
    `PhoneStateListener`) — ends whatever's in-flight, ringing or active, with a dedicated
    `interrupted` reason shown to both partners regardless of role (CALLING_PLAN.md §3/§13.5),
    unlike every other reason here, which is role-specific."""
    key = _room_key(user)
    if key is None:
        return
    room = _rooms.get(key)
    if room is None or room.status == "idle" or user.id not in (room.caller_id, room.callee_id):
        return
    await _resolve(key, reason="interrupted", by=user.id)


async def relay_signal(user: User, event_type: str, payload: dict) -> None:
    """Pure relay for WebRTC `call.offer`/`call.answer`/`call.ice_candidate` — the server never
    inspects the payload (SDP/ICE are meaningless to it), just forwards it to the partner while
    a call is actually ringing or active. No `fcm_data`, ever, same as every other `call.*`
    event — if the partner isn't live-connected, there's no call to signal to them."""
    key = _room_key(user)
    if key is None:
        return
    room = _rooms.get(key)
    if room is None or room.status == "idle" or user.partner_id is None:
        return
    await notification_service.notify_user(user.partner_id, event_type, payload, fcm_data=None)


async def set_control(user: User, *, muted: bool | None, camera_on: bool | None) -> None:
    """Relays self-reported mic/camera state during an active call so the partner's UI can show
    "they're muted" — see `CallRoomState.muted`/`camera_on`'s own doc comment for why this field
    existed unused since Phase 1."""
    key = _room_key(user)
    if key is None:
        return
    room = _rooms.get(key)
    if room is None or room.status != "active":
        return
    if muted is not None:
        room.muted[user.id] = muted
    if camera_on is not None:
        room.camera_on[user.id] = camera_on
    await _broadcast_state(key, user.id, user.partner_id)
