import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scheduled_message import ScheduledMessage


async def get_by_id(db: AsyncSession, scheduled_message_id: uuid.UUID) -> ScheduledMessage | None:
    return await db.get(ScheduledMessage, scheduled_message_id)


async def list_for_sender(db: AsyncSession, sender_id: uuid.UUID) -> list[ScheduledMessage]:
    result = await db.execute(
        select(ScheduledMessage)
        .where(ScheduledMessage.sender_id == sender_id)
        .order_by(ScheduledMessage.scheduled_at.asc())
    )
    return list(result.scalars().all())


async def list_due(db: AsyncSession, now: datetime.datetime) -> list[ScheduledMessage]:
    result = await db.execute(select(ScheduledMessage).where(ScheduledMessage.scheduled_at <= now))
    return list(result.scalars().all())


async def create(db: AsyncSession, **fields) -> ScheduledMessage:
    row = ScheduledMessage(**fields)
    db.add(row)
    await db.flush()
    return row


async def delete(db: AsyncSession, row: ScheduledMessage) -> None:
    await db.delete(row)
    await db.flush()
