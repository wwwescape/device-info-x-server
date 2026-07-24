import asyncio
import uuid
from typing import Any

from fastapi import WebSocket

from app.ws.protocol import build_envelope


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

    def is_online(self, user_id: uuid.UUID) -> bool:
        return bool(self._connections.get(user_id))

    def set_in_messages_screen(self, user_id: uuid.UUID, in_messages: bool) -> None:
        if in_messages:
            self._in_messages_screen.add(user_id)
        else:
            self._in_messages_screen.discard(user_id)

    def is_in_messages_screen(self, user_id: uuid.UUID) -> bool:
        return user_id in self._in_messages_screen

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
