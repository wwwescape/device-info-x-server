from fastapi import APIRouter

from app.api.v1.routers import (
    auth,
    calendar,
    devices,
    health,
    locker,
    media,
    messages,
    pairing,
    period,
    turn,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(pairing.router)
api_router.include_router(messages.router)
api_router.include_router(media.router)
api_router.include_router(users.router)
api_router.include_router(devices.router)
api_router.include_router(calendar.router)
api_router.include_router(period.router)
api_router.include_router(locker.router)
api_router.include_router(turn.router)
