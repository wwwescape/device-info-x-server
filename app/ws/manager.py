import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import WebSocket

from app.ws.protocol import build_envelope


@dataclass(frozen=True)
class LocationPoint:
    lat: float
    lng: float
    accuracy_m: float | None
    updated_at: datetime


class ConnectionManager:
    """Tracks live WebSocket connections per user (a set, since a user may
    have several devices connected at once). Process-local: see the note in
    docker/entrypoint.sh on why the API must run as a single worker."""

    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, set[WebSocket]] = {}
        self._lock = asyncio.Lock()
        # Which connected users currently have the Messages screen open — the "Here" presence
        # tier (see app/services/presence_service.py's send_snapshot). Purely in-memory, same as
        # the connection sets themselves: it only ever makes sense while online, so it's cleared
        # the moment a user's last connection drops rather than persisted anywhere.
        self._in_messages_screen: set[uuid.UUID] = set()
        # Same "Here" shape as _in_messages_screen above, for the Tic Tac Toe game room (Settings'
        # dice icon) — see app/services/game_room_service.py for the room state this backs.
        self._in_tic_tac_toe_screen: set[uuid.UUID] = set()
        # Live Location Sharing — deliberately independent of WebSocket connection state (unlike
        # everything else in this class): a sender's position updates arrive over plain REST
        # (app/services/location_service.py), specifically so a backgrounded sender (WS
        # disconnected, per ConsoleWebSocketClient's own "nothing runs once it's not open" design)
        # can still keep sharing via its foreground service. Ephemeral by design, same as
        # _in_messages_screen — no DB table, nothing survives a server restart, matching the
        # typing-indicator precedent for this kind of live-only relay state.
        self._location_sharing_since: dict[uuid.UUID, datetime] = {}
        self._last_location: dict[uuid.UUID, LocationPoint] = {}

    async def connect(self, user_id: uuid.UUID, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.setdefault(user_id, set()).add(websocket)

    async def disconnect(self, user_id: uuid.UUID, websocket: WebSocket) -> None:
        async with self._lock:
            connections = self._connections.get(user_id)
            if connections is None:
                return
            connections.discard(websocket)
            if not connections:
                del self._connections[user_id]
                self._in_messages_screen.discard(user_id)
                self._in_tic_tac_toe_screen.discard(user_id)

    def is_online(self, user_id: uuid.UUID) -> bool:
        return bool(self._connections.get(user_id))

    def set_in_messages_screen(self, user_id: uuid.UUID, in_messages: bool) -> None:
        if in_messages:
            self._in_messages_screen.add(user_id)
        else:
            self._in_messages_screen.discard(user_id)

    def is_in_messages_screen(self, user_id: uuid.UUID) -> bool:
        return user_id in self._in_messages_screen

    def set_in_tic_tac_toe_screen(self, user_id: uuid.UUID, in_screen: bool) -> None:
        if in_screen:
            self._in_tic_tac_toe_screen.add(user_id)
        else:
            self._in_tic_tac_toe_screen.discard(user_id)

    def is_in_tic_tac_toe_screen(self, user_id: uuid.UUID) -> bool:
        return user_id in self._in_tic_tac_toe_screen

    def enable_location_sharing(self, user_id: uuid.UUID, *, since: datetime) -> None:
        self._location_sharing_since[user_id] = since

    def disable_location_sharing(self, user_id: uuid.UUID) -> None:
        self._location_sharing_since.pop(user_id, None)
        self._last_location.pop(user_id, None)

    def is_sharing_location(self, user_id: uuid.UUID) -> bool:
        return user_id in self._location_sharing_since

    def location_sharing_since(self, user_id: uuid.UUID) -> datetime | None:
        return self._location_sharing_since.get(user_id)

    def update_location(self, user_id: uuid.UUID, point: LocationPoint) -> None:
        self._last_location[user_id] = point

    def last_location(self, user_id: uuid.UUID) -> LocationPoint | None:
        return self._last_location.get(user_id)

    def all_location_sharing_since(self) -> dict[uuid.UUID, datetime]:
        """Snapshot for `location_service`'s 2-hour auto-disable sweep — a plain copy so the
        sweep's own mutation (disabling overdue users mid-iteration) can't change the dict out
        from under the loop it's iterating."""
        return dict(self._location_sharing_since)

    async def send_to_user(self, user_id: uuid.UUID, event_type: str, data: dict[str, Any]) -> bool:
        """Returns True if the send actually reached at least one live connection — not merely
        whether the user had connections on record. `notification_service.notify_user` uses this
        return value to decide whether to fall back to an FCM push, so a stale/broken socket that
        hasn't been reaped yet must not count as a successful delivery; if it did, a real delivery
        failure would silently suppress the FCM fallback that's supposed to catch exactly that
        case."""
        connections = list(self._connections.get(user_id, ()))
        if not connections:
            return False

        envelope = build_envelope(event_type, data)
        dead: list[WebSocket] = []
        for websocket in connections:
            try:
                await websocket.send_json(envelope)
            except Exception:
                dead.append(websocket)

        if dead:
            async with self._lock:
                live = self._connections.get(user_id)
                if live is not None:
                    for websocket in dead:
                        live.discard(websocket)
                    if not live:
                        del self._connections[user_id]

        return len(dead) < len(connections)


connection_manager = ConnectionManager()
