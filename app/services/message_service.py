import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.db.session import async_session_factory
from app.models.media_asset import MediaCategory
from app.models.message import Message, MessageType
from app.models.user import User
from app.repositories import media_asset_repo, message_repo
from app.schemas.message import MessageOut, PollOptionOut, PollOut, ReactionOut
from app.services import link_preview_service, media_service, notification_service
from app.storage import files as storage

logger = logging.getLogger(__name__)

_MEDIA_CATEGORY_BY_TYPE = {
    MessageType.IMAGE: MediaCategory.MESSAGE_IMAGE,
    MessageType.VOICE: MediaCategory.MESSAGE_VOICE,
    MessageType.VIDEO: MediaCategory.MESSAGE_VIDEO,
    MessageType.DOCUMENT: MediaCategory.MESSAGE_DOCUMENT,
}


async def _to_message_out(
    message: Message, *, reactions: list[ReactionOut], is_starred_by_me: bool, poll: PollOut | None
) -> MessageOut:
    return MessageOut(
        id=message.id,
        sender_id=message.sender_id,
        type=message.type,
        body=message.body,
        media_id=message.media_id,
        reply_to_id=message.reply_to_id,
        client_message_id=message.client_message_id,
        edited_at=message.edited_at,
        deleted_at=message.deleted_at,
        read_at=message.read_at,
        delivered_at=message.delivered_at,
        is_pinned=message.is_pinned,
        pinned_at=message.pinned_at,
        created_at=message.created_at,
        reactions=reactions,
        is_starred_by_me=is_starred_by_me,
        link_preview_url=message.link_preview_url,
        link_preview_title=message.link_preview_title,
        link_preview_description=message.link_preview_description,
        link_preview_media_id=message.link_preview_media_id,
        poll=poll,
    )


async def _build_polls(db: AsyncSession, poll_messages: list[Message]) -> dict[uuid.UUID, PollOut]:
    if not poll_messages:
        return {}
    message_ids = [m.id for m in poll_messages]
    options_by_message = await message_repo.poll_options_for_messages(db, message_ids)
    all_option_ids = [option.id for options in options_by_message.values() for option in options]
    votes_by_option = await message_repo.poll_votes_for_options(db, all_option_ids)
    return {
        message.id: PollOut(
            allows_multiple=message.poll_allows_multiple,
            closed_at=message.poll_closed_at,
            options=[
                PollOptionOut(
                    id=option.id,
                    text=option.option_text,
                    order_index=option.order_index,
                    vote_count=len(votes_by_option.get(option.id, [])),
                    voted_by=votes_by_option.get(option.id, []),
                )
                for option in options_by_message.get(message.id, [])
            ],
        )
        for message in poll_messages
    }


async def _enrich(db: AsyncSession, messages: list[Message], current_user_id: uuid.UUID) -> list[MessageOut]:
    ids = [m.id for m in messages]
    reactions_by_message = await message_repo.reactions_for_messages(db, ids)
    starred_ids = await message_repo.starred_message_ids(db, current_user_id, ids)
    polls_by_message = await _build_polls(db, [m for m in messages if m.type == MessageType.POLL])
    return [
        await _to_message_out(
            m,
            reactions=[
                ReactionOut(user_id=r.user_id, emoji=r.emoji) for r in reactions_by_message.get(m.id, [])
            ],
            is_starred_by_me=m.id in starred_ids,
            poll=polls_by_message.get(m.id),
        )
        for m in messages
    ]


async def _get_or_404(db: AsyncSession, message_id: uuid.UUID) -> Message:
    message = await message_repo.get_by_id(db, message_id)
    if message is None or message.deleted_at is not None:
        raise NotFoundError("message not found")
    return message


async def _partner_id(user: User) -> uuid.UUID:
    if user.partner_id is None:
        raise ConflictError("not paired")
    return user.partner_id


async def send_message(db: AsyncSession, sender: User, payload) -> MessageOut:
    existing = await message_repo.get_by_client_message_id(db, payload.client_message_id)
    if existing is not None:
        return (await _enrich(db, [existing], sender.id))[0]

    if payload.type == MessageType.TEXT and not (payload.body and payload.body.strip()):
        raise ValidationError("text messages require a non-empty body")

    if payload.type in _MEDIA_CATEGORY_BY_TYPE:
        if payload.media_id is None:
            raise ValidationError(f"{payload.type.value} messages require media_id")
        asset = await media_asset_repo.get_by_id(db, payload.media_id)
        expected_category = _MEDIA_CATEGORY_BY_TYPE[payload.type]
        if asset is None or asset.owner_id != sender.id or asset.category != expected_category:
            raise ValidationError("media_id does not reference a valid upload of the right type")

    if payload.type == MessageType.POLL:
        if not (payload.body and payload.body.strip()):
            raise ValidationError("poll messages require a non-empty question (in body)")
        if payload.poll is None:
            raise ValidationError("poll messages require poll options")

    if payload.reply_to_id is not None:
        await _get_or_404(db, payload.reply_to_id)

    message = await message_repo.create(
        db,
        sender_id=sender.id,
        type=payload.type,
        body=payload.body,
        media_id=payload.media_id,
        reply_to_id=payload.reply_to_id,
        client_message_id=payload.client_message_id,
        poll_allows_multiple=payload.poll.allows_multiple if payload.poll else False,
    )
    if payload.type == MessageType.POLL:
        await message_repo.create_poll_options(db, message.id, [option.text for option in payload.poll.options])
    await db.commit()
    await db.refresh(message)

    out = (await _enrich(db, [message], sender.id))[0]
    partner_id = await _partner_id(sender)
    await notification_service.notify_user(
        partner_id,
        "message.new",
        {"message": out.model_dump(mode="json")},
        fcm_data={"type": "message_new", "message_id": str(message.id)},
    )
    # WS-only sync back to the sender's own other devices — mirrors set_starred's existing
    # self-sync precedent. A normal interactive send doesn't need this: the sending device
    # already applied this exact message from this function's own return value before any WS
    # event could arrive, and MessageRepository's senderId-self checks already no-op the
    # delivery-ack/notification side effects for a message this device sent itself, so this is a
    # harmless no-op there. It matters for a send that *didn't* originate from a live, currently
    # open device with its own local copy already applied — a scheduled message delivered by
    # scheduled_message_service (the sweep, or an on-demand "Send Now") is exactly that case:
    # without this, the sender has no way to learn their own message now exists until the next
    # periodic resync happens to run. fcm_data=None deliberately — this is a private "keep my own
    # other devices in sync" signal, not "you have an incoming message," so it should never
    # produce a push notification on the sender's own idle devices.
    await notification_service.notify_user(
        sender.id,
        "message.new",
        {"message": out.model_dump(mode="json")},
        fcm_data=None,
    )

    if payload.type == MessageType.TEXT and payload.body:
        url = link_preview_service.first_url_in(payload.body)
        if url is not None:
            # Deliberately not awaited — the fetch can take several seconds (or time out), and
            # send_message must return the instant the message itself is persisted, not once a
            # third-party site has responded. See _fetch_and_attach_link_preview's own doc
            # comment for why this needs its own DB session and can never raise back into here.
            asyncio.create_task(_fetch_and_attach_link_preview(message.id, sender.id, partner_id, url))

    return out


async def _fetch_and_attach_link_preview(
    message_id: uuid.UUID, sender_id: uuid.UUID, partner_id: uuid.UUID, url: str
) -> None:
    """Runs detached from the request that triggered it (fired via `asyncio.create_task` in
    `send_message`, never awaited) — by the time this executes, the request's own DB session is
    already closed, so this opens a fresh one, and by the time it might fail, there's no HTTP
    response left to fail *onto*. Every exception is therefore caught and logged here rather than
    left to propagate, matching how `fcm.py` treats a failed third-party call: log it, never let
    it surface as a user-facing error, never retry."""
    try:
        preview = await link_preview_service.fetch_preview(url)
        if preview is None:
            return

        async with async_session_factory() as db:
            media_id = None
            if preview.image_content and preview.image_mime_type:
                asset = await media_service.store_fetched_bytes(
                    db,
                    owner_id=sender_id,
                    category=MediaCategory.MESSAGE_LINK_PREVIEW,
                    content=preview.image_content,
                    mime_type=preview.image_mime_type,
                )
                media_id = asset.id

            message = await message_repo.get_by_id(db, message_id)
            if message is None or message.deleted_at is not None:
                return
            message.link_preview_url = preview.url
            message.link_preview_title = preview.title
            message.link_preview_description = preview.description
            message.link_preview_media_id = media_id
            await db.commit()

        await notification_service.notify_user(
            partner_id,
            "message.link_preview_ready",
            {
                "message_id": str(message_id),
                "link_preview": {
                    "url": preview.url,
                    "title": preview.title,
                    "description": preview.description,
                    "media_id": str(media_id) if media_id else None,
                },
            },
        )
    except Exception:
        logger.exception("link preview fetch/attach failed for message %s (%s)", message_id, url)


async def edit_message(db: AsyncSession, current_user: User, message_id: uuid.UUID, body: str) -> MessageOut:
    message = await _get_or_404(db, message_id)
    if message.sender_id != current_user.id:
        raise ForbiddenError("only the sender can edit this message")
    if message.type != MessageType.TEXT:
        raise ConflictError("only text messages can be edited")

    message.body = body
    message.edited_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(message)

    out = (await _enrich(db, [message], current_user.id))[0]
    # WS-only, deliberately — an edit shouldn't produce a "New message" push (the client's
    # PushCategory.MESSAGE wording can't distinguish it from a genuinely new one). Matches
    # mark_delivered/mark_read's own fcm_data=None shape; the live WS update above still keeps
    # the other device's UI in sync in real time either way.
    await notification_service.notify_user(
        await _partner_id(current_user),
        "message.updated",
        {"message": out.model_dump(mode="json")},
        fcm_data=None,
    )
    return out


async def delete_message(db: AsyncSession, current_user: User, message_id: uuid.UUID) -> None:
    message = await _get_or_404(db, message_id)
    if message.sender_id != current_user.id:
        raise ForbiddenError("only the sender can delete this message")

    message.deleted_at = datetime.now(UTC)
    message.body = None
    message.media_id = None
    message.is_pinned = False
    message.pinned_at = None
    await db.commit()

    # WS-only, deliberately — see edit_message's identical reasoning just above. The client's
    # own live WS handling of this event already stays silent (no PushCategory notification);
    # this closes the gap where a disconnected/backgrounded recipient used to get a real
    # "New message" push for a delete instead.
    await notification_service.notify_user(
        await _partner_id(current_user),
        "message.deleted",
        {"message_id": str(message_id)},
        fcm_data=None,
    )


async def wipe_conversation(db: AsyncSession, current_user: User) -> None:
    """The "Delete data" action for Messages in the client's Settings screen — a genuine hard
    wipe of the *entire* conversation, for both partners, not the sender-scoped soft-delete this
    used to be. "Delete my messages" leaving tombstones and the partner's own messages fully
    intact turned out not to be what "nothing should show" meant in practice — this now matches
    how Calendar's bulk-delete already behaves (whole shared resource, no ownership filter, real
    hard delete). The existing *single*-message delete is unchanged: still sender-scoped
    soft-delete with a tombstone, still 403s if you try it on a message you didn't send — this
    only affects the bulk action.

    DB writes (the message hard-delete + the now-orphaned media_assets rows, including each
    deleted video's poster thumbnail — see `media_service.delete_assets_with_thumbnails`) land in
    one commit; on-disk blobs are only removed after that commit succeeds — same ordering as
    `locker_service.delete_all_own_data`."""
    media_ids = await message_repo.bulk_hard_delete_conversation(db)
    storage_paths = await media_service.delete_assets_with_thumbnails(db, media_ids)
    await db.commit()

    for storage_path in storage_paths:
        await storage.delete_file(storage_path)

    if current_user.partner_id is not None:
        # WS-only, deliberately — same reasoning as edit_message/delete_message above.
        await notification_service.notify_user(
            current_user.partner_id,
            "message.bulk_deleted",
            {},
            fcm_data=None,
        )


async def set_pinned(db: AsyncSession, current_user: User, message_id: uuid.UUID, pinned: bool) -> MessageOut:
    message = await _get_or_404(db, message_id)
    message.is_pinned = pinned
    message.pinned_at = datetime.now(UTC) if pinned else None
    await db.commit()
    await db.refresh(message)

    out = (await _enrich(db, [message], current_user.id))[0]
    await notification_service.notify_user(
        await _partner_id(current_user),
        "message.pinned" if pinned else "message.unpinned",
        {"message_id": str(message_id)},
        fcm_data=None,
    )
    return out


async def set_starred(db: AsyncSession, current_user: User, message_id: uuid.UUID, starred: bool) -> None:
    await _get_or_404(db, message_id)
    if starred:
        await message_repo.add_star(db, message_id, current_user.id)
    else:
        await message_repo.remove_star(db, message_id, current_user.id)
    await db.commit()

    # Starring is private — only push to the starring user's own other devices.
    await notification_service.notify_user(
        current_user.id,
        "message.starred" if starred else "message.unstarred",
        {"message_id": str(message_id), "user_id": str(current_user.id)},
        fcm_data=None,
    )


async def vote_poll(
    db: AsyncSession, current_user: User, message_id: uuid.UUID, option_ids: list[uuid.UUID]
) -> MessageOut:
    """[option_ids] is the voter's complete selection, replacing whatever they had before — see
    PollVoteUpdate's own doc comment. An empty list is a valid, ordinary way to retract every
    vote, not an error."""
    message = await _get_or_404(db, message_id)
    if message.type != MessageType.POLL:
        raise ConflictError("not a poll message")
    if message.poll_closed_at is not None:
        raise ConflictError("this poll is closed")

    options = (await message_repo.poll_options_for_messages(db, [message_id])).get(message_id, [])
    valid_option_ids = {option.id for option in options}
    selected = set(option_ids)
    if not selected.issubset(valid_option_ids):
        raise ValidationError("option_ids must reference this poll's own options")
    if not message.poll_allows_multiple and len(selected) > 1:
        raise ValidationError("this poll only allows a single selection")

    await message_repo.set_poll_votes(db, list(valid_option_ids), current_user.id, selected)
    await db.commit()

    out = (await _enrich(db, [message], current_user.id))[0]
    await notification_service.notify_user(
        await _partner_id(current_user),
        "message.poll_voted",
        {"message": out.model_dump(mode="json")},
        fcm_data=None,
    )
    return out


async def close_poll(db: AsyncSession, current_user: User, message_id: uuid.UUID) -> MessageOut:
    """Poll creator only, matching WhatsApp — once closed, votes stay visible but
    `vote_poll`/`ConflictError` above refuses any further change from either side."""
    message = await _get_or_404(db, message_id)
    if message.type != MessageType.POLL:
        raise ConflictError("not a poll message")
    if message.sender_id != current_user.id:
        raise ForbiddenError("only the poll's creator can close it")

    if message.poll_closed_at is None:
        message.poll_closed_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(message)

    out = (await _enrich(db, [message], current_user.id))[0]
    await notification_service.notify_user(
        await _partner_id(current_user),
        "message.poll_closed",
        {"message": out.model_dump(mode="json")},
        fcm_data=None,
    )
    return out


async def set_reaction(db: AsyncSession, current_user: User, message_id: uuid.UUID, emoji: str) -> MessageOut:
    message = await _get_or_404(db, message_id)
    await message_repo.set_reaction(db, message_id, current_user.id, emoji)
    await db.commit()
    await db.refresh(message)

    out = (await _enrich(db, [message], current_user.id))[0]
    await notification_service.notify_user(
        await _partner_id(current_user),
        "message.reaction.added",
        {"message_id": str(message_id), "user_id": str(current_user.id), "emoji": emoji},
        fcm_data=None,
    )
    return out


async def remove_reaction(db: AsyncSession, current_user: User, message_id: uuid.UUID) -> None:
    await _get_or_404(db, message_id)
    await message_repo.remove_reaction(db, message_id, current_user.id)
    await db.commit()

    await notification_service.notify_user(
        await _partner_id(current_user),
        "message.reaction.removed",
        {"message_id": str(message_id), "user_id": str(current_user.id)},
        fcm_data=None,
    )


async def mark_delivered(db: AsyncSession, current_user: User, message_id: uuid.UUID) -> MessageOut:
    message = await _get_or_404(db, message_id)
    if message.sender_id != current_user.id and message.delivered_at is None:
        message.delivered_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(message)
        await notification_service.notify_user(
            message.sender_id,
            "message.delivered",
            {"message_id": str(message_id), "delivered_at": message.delivered_at.isoformat()},
            fcm_data=None,
        )

    return (await _enrich(db, [message], current_user.id))[0]


async def mark_read(db: AsyncSession, current_user: User, message_id: uuid.UUID) -> MessageOut:
    message = await _get_or_404(db, message_id)
    if message.sender_id != current_user.id and message.read_at is None:
        # A read implies delivery — backfill in case the client's delivered ack never landed.
        if message.delivered_at is None:
            message.delivered_at = datetime.now(UTC)
        message.read_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(message)
        await notification_service.notify_user(
            message.sender_id,
            "message.read",
            {"message_id": str(message_id), "read_at": message.read_at.isoformat()},
            fcm_data=None,
        )

    return (await _enrich(db, [message], current_user.id))[0]


async def list_messages(
    db: AsyncSession,
    current_user: User,
    *,
    before: datetime | None,
    after: datetime | None,
    limit: int,
) -> list[MessageOut]:
    messages = await message_repo.list_messages(db, before=before, after=after, limit=limit)
    return await _enrich(db, messages, current_user.id)


async def list_pinned(db: AsyncSession, current_user: User) -> list[MessageOut]:
    messages = await message_repo.list_pinned(db)
    return await _enrich(db, messages, current_user.id)


async def list_starred(db: AsyncSession, current_user: User) -> list[MessageOut]:
    messages = await message_repo.list_starred_by_user(db, current_user.id)
    return await _enrich(db, messages, current_user.id)


async def search_messages(db: AsyncSession, current_user: User, query: str, limit: int) -> list[MessageOut]:
    if not query.strip():
        raise ValidationError("q must not be empty")
    messages = await message_repo.search(db, query, limit=limit)
    return await _enrich(db, messages, current_user.id)
