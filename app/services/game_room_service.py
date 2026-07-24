"""Shared Tic Tac Toe "game room" — Settings' dice icon feature. Pure in-memory, process-local,
same ephemeral shape as `_in_messages_screen`/Live Location sharing in `app/ws/manager.py`: no DB
table, nothing survives a server restart, and (per explicit product decision) either partner
leaving the screen — on purpose or via a dropped connection — wipes the room completely rather
than trying to preserve or resync an in-progress game.

Presence ("who's currently on this screen") and game state (board/turn/marks/score) are broadcast
together in one `game.state` event per change, keyed by user id on every field, so each client can
read both "is my partner here" and "what does the board look like" off the same message — no
separate presence event to keep in sync with it. `game.partner_left` is the one exception: a
one-shot signal (not folded into `game.state`) specifically so the client can drive a one-shot
popup rather than a StateFlow-style persistent value.
"""

import uuid
from dataclasses import dataclass, field

from app.db.session import async_session_factory
from app.models.user import User
from app.services import notification_service
from app.ws.manager import connection_manager

_WIN_LINES = (
    (0, 1, 2), (3, 4, 5), (6, 7, 8),  # rows
    (0, 3, 6), (1, 4, 7), (2, 5, 8),  # columns
    (0, 4, 8), (2, 4, 6),  # diagonals
)


@dataclass
class GameRoomState:
    # First to enter is "X", second is "O" — assigned once per room and never reassigned until
    # the room is wiped by a leave/disconnect (see module doc comment).
    marks: dict[uuid.UUID, str] = field(default_factory=dict)
    scores: dict[uuid.UUID, int] = field(default_factory=dict)
    board: list[str | None] = field(default_factory=lambda: [None] * 9)
    turn: uuid.UUID | None = None
    started: bool = False


# Keyed by the canonical (order-independent) pair of a couple's two user ids, so either partner's
# own user id resolves to the same room — see `_room_key`. One room per couple, matching this
# app's hardcoded 2-person-pair model everywhere else.
_rooms: dict[uuid.UUID, GameRoomState] = {}


def _room_key(user: User) -> uuid.UUID | None:
    if user.partner_id is None:
        return None
    return min(user.id, user.partner_id)


async def _broadcast_state(user: User, *, result: dict | None = None) -> None:
    key = _room_key(user)
    if key is None:
        return
    room = _rooms.get(key)
    if room is None:
        return

    payload = {
        "present": {
            str(user.id): connection_manager.is_in_tic_tac_toe_screen(user.id),
            str(user.partner_id): connection_manager.is_in_tic_tac_toe_screen(user.partner_id),
        },
        "marks": {str(uid): mark for uid, mark in room.marks.items()},
        "scores": {str(uid): score for uid, score in room.scores.items()},
        "board": room.board,
        "turn": str(room.turn) if room.turn is not None else None,
        "started": room.started,
        "result": result,
    }
    await notification_service.notify_user(user.id, "game.state", payload)
    await notification_service.notify_user(user.partner_id, "game.state", payload)


def _check_winner(room: GameRoomState) -> uuid.UUID | None:
    for a, b, c in _WIN_LINES:
        mark = room.board[a]
        if mark is not None and mark == room.board[b] == room.board[c]:
            return next((uid for uid, m in room.marks.items() if m == mark), None)
    return None


async def enter_room(user: User) -> None:
    connection_manager.set_in_tic_tac_toe_screen(user.id, True)
    key = _room_key(user)
    if key is None:
        return

    room = _rooms.setdefault(key, GameRoomState())
    if user.id not in room.marks:
        room.marks[user.id] = "X" if not room.marks else "O"
        room.scores.setdefault(user.id, 0)

    await _broadcast_state(user)


async def leave_room(user: User) -> None:
    """Wipes the whole room outright — board, marks, score, everything — per the explicit product
    decision that a leave (deliberate or a dropped connection) ends the shared session entirely
    rather than trying to preserve or resync it. The remaining partner is only notified if they'd
    actually joined this room themselves (`user.partner_id in room.marks`); if nobody but [user]
    ever entered, there's nobody meaningfully "left behind" to tell."""
    connection_manager.set_in_tic_tac_toe_screen(user.id, False)
    key = _room_key(user)
    if key is None:
        return

    room = _rooms.pop(key, None)
    if room is None:
        return
    if user.partner_id is not None and user.partner_id in room.marks:
        await notification_service.notify_user(
            user.partner_id, "game.partner_left", {"user_id": str(user.id)}
        )


async def handle_disconnect(user_id: uuid.UUID) -> None:
    """Called from `presence_service.mark_offline` on every full-offline transition — cheap no-op
    unless [user_id] actually had the game screen open, so the call site there can stay
    unconditional. Covers the app being killed/backgrounded or the connection dropping, none of
    which send an explicit `screen.tic_tac_toe_leave` first."""
    if not connection_manager.is_in_tic_tac_toe_screen(user_id):
        return
    async with async_session_factory() as db:
        user = await db.get(User, user_id)
        if user is None:
            return
        await leave_room(user)


async def start_game(user: User) -> None:
    key = _room_key(user)
    if key is None:
        return
    room = _rooms.get(key)
    if room is None or room.started:
        return
    if user.partner_id is None or user.partner_id not in room.marks:
        return  # both partners must have joined first

    x_user_id = next((uid for uid, mark in room.marks.items() if mark == "X"), None)
    if x_user_id is None:
        return

    room.started = True
    room.turn = x_user_id
    room.board = [None] * 9
    await _broadcast_state(user)


async def apply_move(user: User, cell: object) -> None:
    if not isinstance(cell, int) or isinstance(cell, bool) or not 0 <= cell <= 8:
        return
    key = _room_key(user)
    if key is None:
        return
    room = _rooms.get(key)
    if room is None or not room.started or room.turn != user.id or room.board[cell] is not None:
        return

    room.board[cell] = room.marks[user.id]

    result = None
    winner_id = _check_winner(room)
    if winner_id is not None:
        room.scores[winner_id] = room.scores.get(winner_id, 0) + 1
        result = {"type": "win", "winner": str(winner_id)}
    elif all(mark is not None for mark in room.board):
        result = {"type": "draw"}

    if result is not None:
        # Same X-always-opens convention as the room's very first round — simplest option that
        # doesn't need extra "who goes first next" bookkeeping across rounds, deliberate for a
        # casual, low-stakes 2-person game.
        room.board = [None] * 9
        room.turn = next((uid for uid, mark in room.marks.items() if mark == "X"), None)
    else:
        room.turn = user.partner_id

    await _broadcast_state(user, result=result)
