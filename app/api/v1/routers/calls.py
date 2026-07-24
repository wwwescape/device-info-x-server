from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_paired
from app.models.user import User
from app.repositories import call_log_repo
from app.schemas.call_log import CallLogOut, CallLogPage

router = APIRouter(prefix="/calls", tags=["calls"])


@router.get("/log", response_model=CallLogPage)
async def get_call_log(
    current_user: User = Depends(require_paired),
    db: AsyncSession = Depends(get_db),
) -> CallLogPage:
    entries = await call_log_repo.list_for_couple(db, current_user.id, current_user.partner_id)
    return CallLogPage(items=[CallLogOut.model_validate(entry, from_attributes=True) for entry in entries])
