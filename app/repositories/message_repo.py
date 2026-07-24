import uuid
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message, MessageReaction, MessageStar, PollOption, PollVote

DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 100


async def get_by_id(db: AsyncSession, message_id: uuid.UUID) -> Message | None:
    return await db.get(Message, message_id)


async def get_by_client_message_id(db: AsyncSession, client_message_id: uuid.UUID) -> Message | None:
    result = await db.execute(select(Message).where(Message.client_message_id == client_message_id))
    return result.scalar_one_or_none()


async def create(db: AsyncSession, **fields) -> Message:
    message = Message(**fields)
    db.add(message)
    await db.flush()
    return message


async def list_messages(
    db: AsyncSession, *, before: datetime | None = None, after: datetime | None = None, limit: int = DEFAULT_PAGE_LIMIT
) -> list[Message]:
    """Chat history pagination. `after` walks forward (sync/poll); `before`
    (or neither) walks backward from the newest message (initial load / load
    older). Always returns results in chronological (ascending) order."""
    limit = min(max(limit, 1), MAX_PAGE_LIMIT)

    if after is not None:
        stmt = (
            select(Message)
            .where(Message.created_at > after, Message.deleted_at.is_(None))
            .order_by(Message.created_at.asc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    stmt = select(Message).where(Message.deleted_at.is_(None))
    if before is not None:
        stmt = stmt.where(Message.created_at < before)
    stmt = stmt.order_by(Message.created_at.desc()).limit(limit)
    result = await db.execute(stmt)
    messages = list(result.scalars().all())
    messages.reverse()
    return messages


async def bulk_hard_delete_conversation(db: AsyncSession) -> list[uuid.UUID]:
    """Full conversation wipe — no sender filter (replaces the old sender-scoped soft delete),
    and a genuine hard delete rather than a tombstone: `MessageStar`/`MessageReaction` rows
    cascade automatically (`ondelete="CASCADE"` on their `message_id` FK); `reply_to_id` is
    `ondelete="SET NULL"` but irrelevant here since every row goes at once. Returns every
    non-null `media_id` so the caller can sweep the now-orphaned `media_assets` rows/files."""
    media_result = await db.execute(select(Message.media_id).where(Message.media_id.is_not(None)))
    media_ids = list(media_result.scalars().all())
    await db.execute(delete(Message))
    return media_ids


async def list_recent(
    db: AsyncSession, *, sender_id: uuid.UUID | None = None, limit: int = 10
) -> list[Message]:
    """Debug helper (`cli.list_messages`) — most recent non-deleted messages, newest first.
    Unlike `list_messages`, this isn't chat pagination: no cursor, and no chronological
    reversal, since the whole point is "what does the DB actually have, right now, on top"."""
    stmt = select(Message).where(Message.deleted_at.is_(None))
    if sender_id is not None:
        stmt = stmt.where(Message.sender_id == sender_id)
    stmt = stmt.order_by(Message.created_at.desc()).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_pinned(db: AsyncSession) -> list[Message]:
    stmt = (
        select(Message)
        .where(Message.is_pinned.is_(True), Message.deleted_at.is_(None))
        .order_by(Message.pinned_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_starred_by_user(db: AsyncSession, user_id: uuid.UUID) -> list[Message]:
    stmt = (
        select(Message)
        .join(MessageStar, MessageStar.message_id == Message.id)
        .where(MessageStar.user_id == user_id, Message.deleted_at.is_(None))
        .order_by(Message.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def search(db: AsyncSession, query: str, limit: int = DEFAULT_PAGE_LIMIT) -> list[Message]:
    ts_query = func.plainto_tsquery("english", query)
    stmt = (
        select(Message)
        .where(Message.search_vector.op("@@")(ts_query), Message.deleted_at.is_(None))
        .order_by(Message.created_at.desc())
        .limit(min(max(limit, 1), MAX_PAGE_LIMIT))
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# --- Reactions -----------------------------------------------------------------


async def get_reaction(db: AsyncSession, message_id: uuid.UUID, user_id: uuid.UUID) -> MessageReaction | None:
    result = await db.execute(
        select(MessageReaction).where(
            MessageReaction.message_id == message_id, MessageReaction.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def set_reaction(db: AsyncSession, message_id: uuid.UUID, user_id: uuid.UUID, emoji: str) -> MessageReaction:
    existing = await get_reaction(db, message_id, user_id)
    if existing is not None:
        existing.emoji = emoji
        await db.flush()
        return existing
    reaction = MessageReaction(message_id=message_id, user_id=user_id, emoji=emoji)
    db.add(reaction)
    await db.flush()
    return reaction


async def remove_reaction(db: AsyncSession, message_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    result = await db.execute(
        delete(MessageReaction).where(
            MessageReaction.message_id == message_id, MessageReaction.user_id == user_id
        )
    )
    return result.rowcount > 0


async def reactions_for_messages(
    db: AsyncSession, message_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[MessageReaction]]:
    if not message_ids:
        return {}
    result = await db.execute(select(MessageReaction).where(MessageReaction.message_id.in_(message_ids)))
    grouped: dict[uuid.UUID, list[MessageReaction]] = {}
    for reaction in result.scalars().all():
        grouped.setdefault(reaction.message_id, []).append(reaction)
    return grouped


# --- Stars -----------------------------------------------------------------------


async def get_star(db: AsyncSession, message_id: uuid.UUID, user_id: uuid.UUID) -> MessageStar | None:
    result = await db.execute(
        select(MessageStar).where(MessageStar.message_id == message_id, MessageStar.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def add_star(db: AsyncSession, message_id: uuid.UUID, user_id: uuid.UUID) -> MessageStar:
    existing = await get_star(db, message_id, user_id)
    if existing is not None:
        return existing
    star = MessageStar(message_id=message_id, user_id=user_id)
    db.add(star)
    await db.flush()
    return star


async def remove_star(db: AsyncSession, message_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    result = await db.execute(
        delete(MessageStar).where(MessageStar.message_id == message_id, MessageStar.user_id == user_id)
    )
    return result.rowcount > 0


async def starred_message_ids(
    db: AsyncSession, user_id: uuid.UUID, message_ids: list[uuid.UUID]
) -> set[uuid.UUID]:
    if not message_ids:
        return set()
    result = await db.execute(
        select(MessageStar.message_id).where(
            MessageStar.user_id == user_id, MessageStar.message_id.in_(message_ids)
        )
    )
    return set(result.scalars().all())


# --- Polls -----------------------------------------------------------------------


async def create_poll_options(db: AsyncSession, message_id: uuid.UUID, option_texts: list[str]) -> list[PollOption]:
    options = [
        PollOption(message_id=message_id, option_text=text, order_index=index)
        for index, text in enumerate(option_texts)
    ]
    db.add_all(options)
    await db.flush()
    return options


async def poll_options_for_messages(
    db: AsyncSession, message_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[PollOption]]:
    if not message_ids:
        return {}
    result = await db.execute(
        select(PollOption).where(PollOption.message_id.in_(message_ids)).order_by(PollOption.order_index)
    )
    grouped: dict[uuid.UUID, list[PollOption]] = {}
    for option in result.scalars().all():
        grouped.setdefault(option.message_id, []).append(option)
    return grouped


async def poll_votes_for_options(db: AsyncSession, option_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[uuid.UUID]]:
    """option_id -> the list of user_ids who voted for it — always at most 2 per option in
    practice (this app's whole premise), so no pagination/limit concerns here."""
    if not option_ids:
        return {}
    result = await db.execute(select(PollVote).where(PollVote.option_id.in_(option_ids)))
    grouped: dict[uuid.UUID, list[uuid.UUID]] = {}
    for vote in result.scalars().all():
        grouped.setdefault(vote.option_id, []).append(vote.user_id)
    return grouped


async def set_poll_votes(
    db: AsyncSession, all_option_ids_in_poll: list[uuid.UUID], user_id: uuid.UUID, selected_option_ids: set[uuid.UUID]
) -> None:
    """Replaces this voter's entire selection within one poll — deletes every existing vote row
    of theirs across all of this poll's options, then inserts exactly [selected_option_ids]. See
    PollVoteUpdate's own doc comment for why "replace the whole selection" is simpler than
    incremental add/remove-vote calls."""
    await db.execute(
        delete(PollVote).where(PollVote.option_id.in_(all_option_ids_in_poll), PollVote.user_id == user_id)
    )
    db.add_all([PollVote(option_id=option_id, user_id=user_id) for option_id in selected_option_ids])
    await db.flush()
