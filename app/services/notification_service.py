"""Fan-out point for realtime + push notifications.

Every write-path service (pairing, messaging, calendar, ...) calls into this
module instead of touching the WebSocket manager or FCM client directly. The
WebSocket half is wired up in the ws package (see connect_manager below,
populated once app/ws/manager.py exists); the FCM half is wired up once
app/integrations/fcm.py exists. Until both land, this is a no-op sink so
earlier features (pairing) can call it without a circular/forward dependency.
"""

import uuid
from typing import Any, Protocol


class ConnectionBroadcaster(Protocol):
    async def send_to_user(self, user_id: uuid.UUID, event_type: str, data: dict[str, Any]) -> bool:
        """Returns True if the user had at least one live connection."""
        ...


class PushSender(Protocol):
    async def send_data_message(self, user_id: uuid.UUID, data: dict[str, str]) -> None: ...


_connection_broadcaster: ConnectionBroadcaster | None = None
_push_sender: PushSender | None = None


def register_connection_broadcaster(broadcaster: ConnectionBroadcaster) -> None:
    global _connection_broadcaster
    _connection_broadcaster = broadcaster


def register_push_sender(sender: PushSender) -> None:
    global _push_sender
    _push_sender = sender


async def notify_user(
    user_id: uuid.UUID, event_type: str, ws_data: dict[str, Any], fcm_data: dict[str, str] | None = None
) -> None:
    """Push a WS event to a live connection; fall back to an FCM data-only
    message (never containing message content) if the user isn't connected."""
    delivered_live = False
    if _connection_broadcaster is not None:
        delivered_live = await _connection_broadcaster.send_to_user(user_id, event_type, ws_data)

    if not delivered_live and _push_sender is not None and fcm_data is not None:
        await _push_sender.send_data_message(user_id, fcm_data)
