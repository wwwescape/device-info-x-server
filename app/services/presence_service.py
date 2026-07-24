import uuid
from datetime import UTC, datetime

from app.db.session import async_session_factory
from app.models.user import User
from app.services import notification_service


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
