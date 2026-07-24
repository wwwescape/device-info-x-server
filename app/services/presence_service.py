import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RateLimitedError
from app.db.session import async_session_factory
from app.models.user import User
from app.services import game_room_service, notification_service
from app.ws.manager import connection_manager

# How often the manual "I'm online" push (send_online_ping) can be sent per user.
ONLINE_PING_COOLDOWN = timedelta(minutes=15)


async def mark_online(user_id: uuid.UUID) -> None:
    async with async_session_factory() as db:
        user = await db.get(User, user_id)
        partner_id = user.partner_id if user is not None else None

    if partner_id is not None:
        await notification_service.notify_user(
            partner_id, "presence", {"user_id": str(user_id), "status": "online", "last_seen_at": None}
        )


async def mark_offline(user_id: uuid.UUID) -> None:
    now = datetime.now(UTC)
    async with async_session_factory() as db:
        user = await db.get(User, user_id)
        if user is None:
            return
        user.last_seen_at = now
        await db.commit()
        partner_id = user.partner_id

    if partner_id is not None:
        await notification_service.notify_user(
            partner_id,
            "presence",
            {"user_id": str(user_id), "status": "offline", "last_seen_at": now.isoformat()},
        )
        # The "Here" tier (`ws/router.py`'s `_forward_screen`) is only ever pushed on an *explicit*
        # screen.messages_enter/leave from the client — but the far more common way a user actually
        # leaves the Messages screen is by backgrounding the app entirely (ConsoleActivity.onStop
        # disconnects the socket outright), which never sends a messages_leave first. ConnectionManager
        # already clears its own in-memory `_in_messages_screen` flag the moment this user's last
        # connection drops (`disconnect`'s own `_in_messages_screen.discard`), so the *next* snapshot
        # would report it correctly — but the partner's already-connected device has no reason to ask
        # for a new snapshot, so without this explicit push it was left showing a stale "Here" for the
        # rest of that session, even after the presence event above correctly flipped it to offline.
        # A disconnected user is definitionally not looking at any screen, so this is unconditional.
        await notification_service.notify_user(
            partner_id,
            "presence.screen",
            {"user_id": str(user_id), "in_messages": False},
        )

    # Same "disconnect never sends an explicit leave first" gap as the Messages "Here" tier above
    # — the game room needs its own equivalent cleanup, since a killed/backgrounded app never gets
    # to send screen.tic_tac_toe_leave. No-ops internally unless this user actually had the game
    # screen open, so this stays unconditional here rather than gated on anything already known
    # at this call site.
    await game_room_service.handle_disconnect(user_id)


async def send_snapshot(user_id: uuid.UUID) -> None:
    """Sent once, right after this user's own WebSocket finishes connecting (`ws/router.py`'s
    `websocket_endpoint`, immediately after `mark_online`) — describes the *partner's* current
    presence and screen location as of right now.

    Without this, a freshly-connected client only ever learns about the partner from the next
    online/offline/screen delta broadcast, and [notification_service.notify_user] only delivers
    those live to a connection that's already open at the exact moment they fire — so two people
    who are rarely online at the same instant (the common case for a private two-person app) could
    go for a long time seeing neither device ever update, looking indistinguishable from presence
    being silently broken rather than just "no delta has happened to overlap with yet."
    """
    async with async_session_factory() as db:
        user = await db.get(User, user_id)
        partner_id = user.partner_id if user is not None else None
        partner = await db.get(User, partner_id) if partner_id is not None else None

    if partner_id is None or partner is None:
        return

    await notification_service.notify_user(
        user_id,
        "presence",
        {
            "user_id": str(partner_id),
            "status": "online" if connection_manager.is_online(partner_id) else "offline",
            "last_seen_at": partner.last_seen_at.isoformat() if partner.last_seen_at else None,
        },
    )
    await notification_service.notify_user(
        user_id,
        "presence.screen",
        {"user_id": str(partner_id), "in_messages": connection_manager.is_in_messages_screen(partner_id)},
    )


async def send_online_ping(db: AsyncSession, current_user: User) -> None:
    """The manual "I'm online" header icon in Messages — unlike [mark_online]/[mark_offline]
    (automatic, tied to the WebSocket connecting/disconnecting), this is a one-off, user-initiated
    push telling the partner this device is available right now. `current_user.partner_id` is
    guaranteed non-null by the `require_paired` dependency on the route that calls this.

    Rate-limited to once per [ONLINE_PING_COOLDOWN] *server-side* — a client-only disabled button
    would be trivially bypassed by killing/reopening the app, so `last_online_ping_sent_at` is the
    source of truth, not just something the client mirrors locally to grey out its own icon.
    """
    now = datetime.now(UTC)
    last_sent = current_user.last_online_ping_sent_at
    if last_sent is not None and now - last_sent < ONLINE_PING_COOLDOWN:
        raise RateLimitedError("You can only do this once every 15 minutes")

    current_user.last_online_ping_sent_at = now
    await db.commit()

    await notification_service.notify_user(
        current_user.partner_id,
        "presence.online_ping",
        {"user_id": str(current_user.id)},
        fcm_data={"type": "presence_online_ping"},
    )
