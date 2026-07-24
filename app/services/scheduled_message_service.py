import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.message import MessageType
from app.models.scheduled_message import ScheduledMessage
from app.models.user import User
from app.repositories import scheduled_message_repo
from app.schemas.message import MessageCreate
from app.schemas.scheduled_message import ScheduledMessageCreate, ScheduledMessageOut
from app.services import message_service, notification_service


def _to_out(row: ScheduledMessage) -> ScheduledMessageOut:
    return ScheduledMessageOut(id=row.id, body=row.body, scheduled_at=row.scheduled_at, created_at=row.created_at)


async def _get_authorized(db: AsyncSession, current_user: User, scheduled_message_id: uuid.UUID) -> ScheduledMessage:
    """404s (not 403) for anyone but the sender — a scheduled message has exactly one owner, ever;
    unlike Notepad's PRIVATE/SHARED split there's no second legitimate viewer to distinguish from
    a stranger, so any mismatch collapses to the same not-found response (mirrors
    `notepad_service._get_authorized`'s own reasoning)."""
    row = await scheduled_message_repo.get_by_id(db, scheduled_message_id)
    if row is None or row.sender_id != current_user.id:
        raise NotFoundError("scheduled message not found")
    return row


async def _push(sender_id: uuid.UUID, event_suffix: str, ws_data: dict) -> None:
    """Always pushes to the sender's own other devices only, never the partner — the partner
    isn't meant to know a message is queued until it actually arrives as a real message (see
    `ScheduledMessage`'s own doc comment on why this stays a surprise until then). No `fcm_data`:
    unlike Notepad's push (which represents a real change the owner might want a system
    notification for), every event here fires while the sender's own app is the only thing that
    could plausibly be listening (creating/canceling/sending-now are all things *this device*
    just did), so a WS-only nudge to refresh the list is enough — no push notification needed."""
    await notification_service.notify_user(sender_id, f"scheduled_message.{event_suffix}", ws_data)


async def list_scheduled(db: AsyncSession, current_user: User) -> list[ScheduledMessageOut]:
    return [_to_out(r) for r in await scheduled_message_repo.list_for_sender(db, current_user.id)]


async def create_scheduled_message(
    db: AsyncSession, current_user: User, payload: ScheduledMessageCreate
) -> ScheduledMessageOut:
    row = await scheduled_message_repo.create(
        db, sender_id=current_user.id, body=payload.body, scheduled_at=payload.scheduled_at
    )
    await db.commit()
    await db.refresh(row)

    out = _to_out(row)
    await _push(current_user.id, "created", {"scheduled_message": out.model_dump(mode="json")})
    return out


async def cancel_scheduled_message(db: AsyncSession, current_user: User, scheduled_message_id: uuid.UUID) -> None:
    row = await _get_authorized(db, current_user, scheduled_message_id)
    row_id = row.id
    await scheduled_message_repo.delete(db, row)
    await db.commit()

    await _push(current_user.id, "deleted", {"scheduled_message_id": str(row_id)})


async def send_scheduled_message_now(db: AsyncSession, current_user: User, scheduled_message_id: uuid.UUID) -> None:
    """Fires immediately rather than waiting for the sweep to find it naturally due — moves the
    send *earlier*, never edits its content, matching the product decision that there's still no
    in-place edit surface for a pending scheduled message."""
    row = await _get_authorized(db, current_user, scheduled_message_id)
    await deliver_scheduled_message(db, current_user, row)


async def deliver_scheduled_message(db: AsyncSession, sender: User, row: ScheduledMessage) -> None:
    """Turns a staging row into a real message via the exact same path a live send uses
    (`message_service.send_message`) — called both by `send_scheduled_message_now` above (an
    on-demand, user-triggered early send) and by `app.tasks.scheduler._sweep_scheduled_messages`
    (the 60s sweep finding it naturally due), so there's only one place that actually does this.

    `client_message_id` is deliberately `row.id` itself, not a fresh `uuid.uuid4()` —
    `send_message` already no-ops idempotently on a repeated `client_message_id` (see its own
    dedup check at the top). Reusing the staging row's own id makes this whole function safely
    retryable: if the process crashes after `send_message`'s own commit but before this
    function's delete+commit below, the staging row is still here on the next sweep tick, and
    re-running this exact function hits `send_message`'s dedup path instead of creating a genuine
    duplicate message — sending happens *before* deleting the staging row for exactly this reason
    (deleting first would risk losing the message entirely if `send_message` then failed)."""
    payload = MessageCreate(type=MessageType.TEXT, body=row.body, client_message_id=row.id)
    await message_service.send_message(db, sender, payload)

    row_id = row.id
    await scheduled_message_repo.delete(db, row)
    await db.commit()

    await _push(sender.id, "sent", {"scheduled_message_id": str(row_id)})
