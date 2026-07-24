import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import Gender, User


async def count_users(db: AsyncSession) -> int:
    result = await db.execute(select(func.count()).select_from(User))
    return result.scalar_one()


async def any_paired(db: AsyncSession) -> bool:
    result = await db.execute(select(User.id).where(User.partner_id.isnot(None)).limit(1))
    return result.scalar_one_or_none() is not None


async def get_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await db.get(User, user_id)


async def get_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def create(
    db: AsyncSession,
    *,
    username: str,
    password_hash: str,
    display_name: str,
    first_name: str,
    last_name: str,
    gender: Gender,
    birthday_date: date,
) -> User:
    user = User(
        username=username,
        password_hash=password_hash,
        display_name=display_name,
        first_name=first_name,
        last_name=last_name,
        gender=gender,
        birthday_date=birthday_date,
    )
    db.add(user)
    await db.flush()
    return user


async def delete(db: AsyncSession, user: User) -> None:
    """"Destroy all data" in the client's Settings screen. Every FK to `users.id` across the
    schema is `ON DELETE CASCADE` except `partner_id` itself (`ON DELETE SET NULL`), so this one
    delete removes every row this user owns (messages, calendar/reminder events, cycles, locker
    items/albums, media assets, devices, refresh tokens, partner codes) while the partner's own
    account and rows are untouched — they just lose the pairing link. On-disk media blobs are
    NOT touched by the cascade (it only removes DB rows) — see `user_service.delete_account`,
    which sweeps those before calling this."""
    await db.delete(user)
