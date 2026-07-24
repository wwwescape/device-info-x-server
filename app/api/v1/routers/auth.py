from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.rate_limit import login_rate_limiter, rate_limit_dependency, register_rate_limiter
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    VerifyPasswordRequest,
)
from app.schemas.user import UserPublic
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_dependency(register_rate_limiter))],
)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> User:
    return await auth_service.register(
        db,
        username=payload.username,
        password=payload.password,
        display_name=payload.display_name,
        first_name=payload.first_name,
        last_name=payload.last_name,
        gender=payload.gender,
        birthday_date=payload.birthday_date,
        setup_token=payload.setup_token,
    )


@router.post(
    "/login",
    response_model=TokenPair,
    dependencies=[Depends(rate_limit_dependency(login_rate_limiter))],
)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenPair:
    user = await auth_service.authenticate(db, username=payload.username, password=payload.password)
    return await auth_service.issue_token_pair(db, user, device_label=payload.device_label, timezone=payload.timezone)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenPair:
    return await auth_service.refresh_tokens(db, payload.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: LogoutRequest, db: AsyncSession = Depends(get_db)) -> None:
    await auth_service.logout(db, payload.refresh_token)


@router.get("/me", response_model=UserPublic)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.post(
    "/verify-password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(rate_limit_dependency(login_rate_limiter))],
)
async def verify_password(
    payload: VerifyPasswordRequest,
    current_user: User = Depends(get_current_user),
) -> None:
    auth_service.verify_current_password(current_user, payload.password)
