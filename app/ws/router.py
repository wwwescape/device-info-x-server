import asyncio
import json
import logging
import uuid

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.security import decode_access_token
from app.db.session import async_session_factory
from app.models.user import User
from app.services import message_service, notification_service, presence_service
from app.ws.manager import connection_manager

router = APIRouter()
logger = logging.getLogger(__name__)

# Clients are expected to send `ping` roughly every 30s; if we hear nothing
# for twice that, the connection is presumed dead and closed server-side.
HEARTBEAT_TIMEOUT_SECONDS = 60


async def _authenticate(websocket: WebSocket) -> User | None:
    auth_header = websocket.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        logger.warning("WS auth rejected: missing/malformed Authorization header")
        return None
    token = auth_header.split(" ", 1)[1]

    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(payload["sub"])
    except jwt.ExpiredSignatureError:
        logger.warning("WS auth rejected: access token expired")
        return None
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        logger.warning("WS auth rejected: invalid token (%s)", exc)
        return None

    async with async_session_factory() as db:
        user = await db.get(User, user_id)
        if user is None or not user.is_active:
            logger.warning("WS auth rejected: user %s not found or inactive", user_id)
            return None
        return user


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    user = await _authenticate(websocket)
    if user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    await connection_manager.connect(user.id, websocket)
    await presence_service.mark_online(user.id)

    try:
        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(), timeout=HEARTBEAT_TIMEOUT_SECONDS
                )
            except TimeoutError:
                await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
                break
            await _handle_client_message(user, raw)
    except WebSocketDisconnect:
        pass
    finally:
        await connection_manager.disconnect(user.id, websocket)
        if not connection_manager.is_online(user.id):
            await presence_service.mark_offline(user.id)


async def _handle_client_message(user: User, raw: str) -> None:
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        return

    msg_type = envelope.get("type")
    data = envelope.get("data") or {}

    if msg_type == "ping":
        await connection_manager.send_to_user(user.id, "pong", {})
    elif msg_type == "typing.start":
        await _forward_typing(user, "start")
    elif msg_type == "typing.stop":
        await _forward_typing(user, "stop")
    elif msg_type == "message.read":
        await _handle_read(user, data)


async def _forward_typing(user: User, state: str) -> None:
    if user.partner_id is None:
        return
    await notification_service.notify_user(
        user.partner_id, "typing", {"user_id": str(user.id), "state": state}
    )


async def _handle_read(user: User, data: dict) -> None:
    message_id = data.get("message_id")
    if not message_id:
        return
    try:
        message_uuid = uuid.UUID(message_id)
    except ValueError:
        return

    async with async_session_factory() as db:
        db_user = await db.get(User, user.id)
        if db_user is None:
            return
        try:
            await message_service.mark_read(db, db_user, message_uuid)
        except Exception:
            # Bad/unknown message id from a client — ignore rather than
            # tearing down the whole connection over a malformed WS frame.
            pass
