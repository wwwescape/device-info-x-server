import hmac
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ConflictError, ForbiddenError, UnauthorizedError
from app.core.security import (
    create_access_token,
    generate_one_time_password,
    generate_refresh_token,
    hash_opaque_token,
    hash_password,
    verify_password,
)
from app.models.calendar_event import EventType
from app.models.user import Gender, User
from app.repositories import refresh_token_repo, user_repo
from app.schemas.auth import TokenPair
from app.schemas.calendar import CalendarEventCreate
from app.services import calendar_service

settings = get_settings()

MAX_ACCOUNTS = 2


async def register(
    db: AsyncSession,
    *,
    username: str,
    password: str,
    display_name: str,
    first_name: str,
    last_name: str,
    gender: Gender,
    birthday_date: date,
    setup_token: str,
) -> User:
    if not settings.server_setup_token or not hmac.compare_digest(setup_token, settings.server_setup_token):
        raise UnauthorizedError("invalid setup token")

    if await user_repo.count_users(db) >= MAX_ACCOUNTS:
        raise ForbiddenError("registration is closed — this server already has 2 accounts")

    if await user_repo.get_by_username(db, username) is not None:
        raise ConflictError("username is taken")

    user = await user_repo.create(
        db,
        username=username,
        password_hash=hash_password(password),
        display_name=display_name,
        first_name=first_name,
        last_name=last_name,
        gender=gender,
        birthday_date=birthday_date,
    )
    await db.commit()
    await db.refresh(user)

    # A brand-new account has no partner yet, so create_event's notify-partner branch is a
    # correctly-guarded no-op here — safe to call unconditionally right after registration.
    await calendar_service.create_event(
        db,
        user,
        CalendarEventCreate(
            type=EventType.BIRTHDAY,
            title=f"{first_name}'s Birthday",
            start_at=datetime.combine(birthday_date, time.min, tzinfo=UTC),
            all_day=True,
            recurrence_rule="FREQ=YEARLY",
        ),
    )
    return user


async def authenticate(db: AsyncSession, *, username: str, password: str) -> User:
    user = await user_repo.get_by_username(db, username)
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise UnauthorizedError("invalid username or password")
    return user


async def issue_token_pair(
    db: AsyncSession, user: User, *, device_label: str | None = None, timezone: str | None = None
) -> TokenPair:
    access_token = create_access_token(str(user.id))

    refresh_plain = generate_refresh_token()
    expires_at = datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days)
    await refresh_token_repo.create(
        db,
        user_id=user.id,
        token_hash=hash_opaque_token(refresh_plain),
        expires_at=expires_at,
        device_label=device_label,
    )

    user.last_seen_at = datetime.now(UTC)
    if timezone:
        user.timezone = timezone
    await db.commit()

    return TokenPair(access_token=access_token, refresh_token=refresh_plain)


async def refresh_tokens(db: AsyncSession, refresh_token_plain: str) -> TokenPair:
    token_hash = hash_opaque_token(refresh_token_plain)
    token = await refresh_token_repo.get_by_hash(db, token_hash)

    now = datetime.now(UTC)
    if token is None or token.revoked_at is not None or token.expires_at < now:
        raise UnauthorizedError("invalid or expired refresh token")

    user = await user_repo.get_by_id(db, token.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("invalid or expired refresh token")

    # Rotation: the old token is dead the instant a new pair is issued.
    await refresh_token_repo.revoke(db, token)
    return await issue_token_pair(db, user, device_label=token.device_label)


async def logout(db: AsyncSession, refresh_token_plain: str) -> None:
    token = await refresh_token_repo.get_by_hash(db, hash_opaque_token(refresh_token_plain))
    if token is not None and token.revoked_at is None:
        await refresh_token_repo.revoke(db, token)
    await db.commit()


def verify_current_password(user: User, password: str) -> None:
    if not verify_password(password, user.password_hash):
        raise UnauthorizedError("incorrect password")


async def change_password(db: AsyncSession, user: User, *, current_password: str, new_password: str) -> User:
    verify_current_password(user, current_password)
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    await db.commit()
    await db.refresh(user)
    return user


async def admin_reset_password(db: AsyncSession, user: User) -> str:
    """`python -m app.cli reset-password` — generates a one-time password, sets
    `must_change_password` so the client forces a real password to be chosen before letting the
    account owner into the console, and revokes every existing session (a reset implies the old
    password may no longer be trustworthy, so every device gets signed out, not just the one
    that requested it). Returns the plaintext OTP — it's relayed to the account owner out of band
    and never stored anywhere."""
    otp = generate_one_time_password()
    user.password_hash = hash_password(otp)
    user.must_change_password = True
    await refresh_token_repo.revoke_all_for_user(db, user.id)
    await db.commit()
    return otp
