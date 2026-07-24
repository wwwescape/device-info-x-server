from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.pairing import (
    PairingStatusResponse,
    PairRequest,
    PartnerCodeCreateResponse,
    PartnerCodeStatusResponse,
)
from app.schemas.user import PartnerPublic
from app.services import pairing_service

router = APIRouter(prefix="/pairing", tags=["pairing"])


@router.post("/code", response_model=PartnerCodeCreateResponse)
async def generate_code(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> PartnerCodeCreateResponse:
    plaintext, record = await pairing_service.generate_code(db, current_user)
    return PartnerCodeCreateResponse(
        code=plaintext, code_preview=record.code_preview, expires_at=record.expires_at
    )


@router.get("/code", response_model=PartnerCodeStatusResponse)
async def get_code_status(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> PartnerCodeStatusResponse:
    record = await pairing_service.get_active_code(db, current_user)
    if record is None:
        return PartnerCodeStatusResponse(has_active_code=False)
    return PartnerCodeStatusResponse(
        has_active_code=True, code_preview=record.code_preview, expires_at=record.expires_at
    )


@router.post("/pair", response_model=PartnerPublic)
async def pair(
    payload: PairRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    return await pairing_service.pair(db, current_user, payload.code)


@router.get("/status", response_model=PairingStatusResponse)
async def pairing_status(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> PairingStatusResponse:
    partner = await pairing_service.get_partner(db, current_user)
    return PairingStatusResponse(paired=partner is not None, partner=partner)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def unpair(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> None:
    await pairing_service.unpair(db, current_user)
