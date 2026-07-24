from fastapi import APIRouter, Depends, status

from app.core.deps import require_paired
from app.models.user import User
from app.schemas.location import LocationStatusResponse, LocationUpdate
from app.services import location_service

router = APIRouter(prefix="/location", tags=["location"])


@router.post("/enable", status_code=status.HTTP_204_NO_CONTENT)
async def enable_location_sharing(current_user: User = Depends(require_paired)) -> None:
    await location_service.enable_sharing(current_user)


@router.post("/disable", status_code=status.HTTP_204_NO_CONTENT)
async def disable_location_sharing(current_user: User = Depends(require_paired)) -> None:
    await location_service.disable_sharing(current_user.id, current_user.partner_id, reason="manual")


@router.post("/update", status_code=status.HTTP_204_NO_CONTENT)
async def update_location(
    payload: LocationUpdate,
    current_user: User = Depends(require_paired),
) -> None:
    await location_service.update_location(current_user, payload.lat, payload.lng, payload.accuracy_m)


@router.get("/status", response_model=LocationStatusResponse)
async def get_location_status(current_user: User = Depends(require_paired)) -> LocationStatusResponse:
    return await location_service.get_status(current_user)
