from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import generate_partner_code, hash_partner_code
from app.models.partner_code import PartnerCode
from app.models.user import User
from app.repositories import partner_code_repo, user_repo
from app.services import notification_service

settings = get_settings()

CODE_LENGTH = 8


async def generate_code(db: AsyncSession, user: User) -> tuple[str, PartnerCode]:
    if user.partner_id is not None:
        raise ConflictError("already paired — unpair before generating a new code")

    await partner_code_repo.invalidate_all_for_user(db, user.id)

    plaintext = generate_partner_code(CODE_LENGTH)
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.partner_code_expire_minutes)
    record = await partner_code_repo.create(
        db,
        user_id=user.id,
        code_hash=hash_partner_code(plaintext),
        code_preview=plaintext[-4:],
        expires_at=expires_at,
    )
    await db.commit()
    return plaintext, record


async def get_active_code(db: AsyncSession, user: User) -> PartnerCode | None:
    return await partner_code_repo.get_active_for_user(db, user.id)


async def pair(db: AsyncSession, user: User, code_plain: str) -> User:
    """Pairs `user` with the owner of `code_plain`. Returns the partner."""
    if user.partner_id is not None:
        raise ConflictError("already paired")

    code = await partner_code_repo.get_valid_by_hash(db, hash_partner_code(code_plain))
    if code is None:
        raise NotFoundError("invalid or expired code")
    if code.user_id == user.id:
        raise ConflictError("cannot pair with your own code")

    partner = await user_repo.get_by_id(db, code.user_id)
    if partner is None or partner.partner_id is not None:
        raise ConflictError("that code's owner is no longer available for pairing")

    user.partner_id = partner.id
    partner.partner_id = user.id
    await partner_code_repo.consume(db, code)
    await partner_code_repo.invalidate_all_for_user(db, user.id)
    await db.commit()
    await db.refresh(user)
    await db.refresh(partner)

    for recipient, other in ((user, partner), (partner, user)):
        await notification_service.notify_user(
            recipient.id,
            "pairing.updated",
            {
                "paired": True,
                "partner": {"id": str(other.id), "display_name": other.display_name},
            },
            fcm_data={"type": "pairing_updated"},
        )

    return partner


async def get_partner(db: AsyncSession, user: User) -> User | None:
    if user.partner_id is None:
        return None
    return await user_repo.get_by_id(db, user.partner_id)


async def unpair(db: AsyncSession, user: User) -> None:
    if user.partner_id is None:
        raise ConflictError("not paired")

    partner = await user_repo.get_by_id(db, user.partner_id)
    user.partner_id = None
    if partner is not None:
        partner.partner_id = None
    await db.commit()

    if partner is not None:
        for recipient in (user, partner):
            await notification_service.notify_user(
                recipient.id,
                "pairing.updated",
                {"paired": False, "partner": None},
                fcm_data={"type": "pairing_updated"},
            )
