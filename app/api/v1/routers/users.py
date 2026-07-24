from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.exceptions import ConflictError
from app.models.user import User
from app.schemas.auth import ChangePasswordRequest
from app.schemas.feature_tour import SeenToursOut
from app.schemas.user import PartnerPublic, UpdateProfileRequest, UserPublic
from app.services import auth_service, pairing_service, user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserPublic)
async def get_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.patch("/me", response_model=UserPublic)
async def update_me(
    payload: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    return await user_service.update_profile(
        db,
        current_user,
        display_name=payload.display_name,
        first_name=payload.first_name,
        last_name=payload.last_name,
        gender=payload.gender,
        birthday_date=payload.birthday_date,
        birthday_message=payload.birthday_message,
    )


@router.post("/me/change-password", response_model=UserPublic)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    return await auth_service.change_password(
        db, current_user, current_password=payload.current_password, new_password=payload.new_password
    )


@router.post("/me/avatar", response_model=UserPublic)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    return await user_service.set_avatar(db, current_user, file)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await user_service.delete_account(db, current_user)


@router.get("/partner", response_model=PartnerPublic)
async def get_partner(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> User:
    partner = await pairing_service.get_partner(db, current_user)
    if partner is None:
        raise ConflictError("not paired")
    return partner


@router.get("/me/seen-tours", response_model=SeenToursOut)
async def get_seen_tours(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> SeenToursOut:
    return SeenToursOut(seen_tour_keys=await user_service.list_seen_tour_keys(db, current_user))


@router.post("/me/seen-tours/{tour_key}", status_code=status.HTTP_204_NO_CONTENT)
async def mark_tour_seen(
    tour_key: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await user_service.mark_tour_seen(db, current_user, tour_key)
