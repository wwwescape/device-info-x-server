import logging
import uuid
from datetime import UTC, datetime, timedelta

from app.core.exceptions import ValidationError
from app.db.session import async_session_factory
from app.models.user import User
from app.schemas.location import LocationStatusResponse, PartnerLocationStatus
from app.services import notification_service
from app.ws.manager import LocationPoint, connection_manager

logger = logging.getLogger(__name__)

# Hard cutoff enforced here, not just client-side — a killed/crashed client can't leave sharing
# on forever otherwise. The client independently enforces its own 2h timer as a fast-path (so the
# UI reacts instantly rather than waiting on this sweep's cadence); this is the authoritative
# backstop, same "client convenience, server authority" split ONLINE_PING_COOLDOWN uses in
# presence_service.
AUTO_DISABLE_AFTER = timedelta(hours=2)


async def enable_sharing(user: User) -> None:
    connection_manager.enable_location_sharing(user.id, since=datetime.now(UTC))
    if user.partner_id is not None:
        await notification_service.notify_user(
            user.partner_id,
            "location.enabled",
            {"user_id": str(user.id)},
            fcm_data={"type": "location_enabled"},
        )


async def disable_sharing(user_id: uuid.UUID, partner_id: uuid.UUID | None, *, reason: str) -> None:
    """Mutual by design — either partner disabling ends the whole shared session for both, not
    just the caller (confirmed in the TODOS.md design discussion), since a one-sided live share
    doesn't match what either partner would expect once one side has stopped. Only notifies
    whichever side(s) were actually sharing, so disabling twice (or a partner who was never
    sharing) doesn't push a spurious event."""
    was_sharing = connection_manager.is_sharing_location(user_id)
    connection_manager.disable_location_sharing(user_id)

    partner_was_sharing = False
    if partner_id is not None:
        partner_was_sharing = connection_manager.is_sharing_location(partner_id)
        connection_manager.disable_location_sharing(partner_id)

    if not was_sharing and not partner_was_sharing:
        return

    recipients = [uid for uid in (user_id, partner_id) if uid is not None]
    for recipient_id in recipients:
        await notification_service.notify_user(
            recipient_id,
            "location.disabled",
            {"reason": reason},
            fcm_data={"type": "location_disabled"},
        )


async def update_location(user: User, lat: float, lng: float, accuracy_m: float | None) -> None:
    if not connection_manager.is_sharing_location(user.id):
        raise ValidationError("location sharing is not enabled")

    now = datetime.now(UTC)
    connection_manager.update_location(user.id, LocationPoint(lat=lat, lng=lng, accuracy_m=accuracy_m, updated_at=now))

    if user.partner_id is not None:
        await notification_service.notify_user(
            user.partner_id,
            "location.update",
            {
                "user_id": str(user.id),
                "lat": lat,
                "lng": lng,
                "accuracy_m": accuracy_m,
                "updated_at": now.isoformat(),
            },
        )


def _status_for(user_id: uuid.UUID) -> PartnerLocationStatus:
    point = connection_manager.last_location(user_id)
    return PartnerLocationStatus(
        user_id=user_id,
        sharing=connection_manager.is_sharing_location(user_id),
        lat=point.lat if point else None,
        lng=point.lng if point else None,
        accuracy_m=point.accuracy_m if point else None,
        updated_at=point.updated_at if point else None,
    )


async def get_status(user: User) -> LocationStatusResponse:
    return LocationStatusResponse(
        self_status=_status_for(user.id),
        partner_status=_status_for(user.partner_id) if user.partner_id is not None else None,
    )


async def sweep_auto_disable() -> None:
    """Runs on the same 60s cadence as `app/tasks/scheduler.py`'s reminder sweep (added there, not
    a second scheduler) — reuses the existing sweep infrastructure per that module's own precedent
    for time-based checks, even though this one reads process-local in-memory state instead of the
    database."""
    now = datetime.now(UTC)
    for user_id, since in connection_manager.all_location_sharing_since().items():
        # Re-checked (not just trusted from the snapshot) — disabling one overdue partner also
        # disables the other (see disable_sharing's mutual behavior), so by the time this loop
        # reaches a partner pair's second entry it may already be off.
        if not connection_manager.is_sharing_location(user_id):
            continue
        if now - since < AUTO_DISABLE_AFTER:
            continue

        async with async_session_factory() as db:
            user = await db.get(User, user_id)
        if user is None:
            connection_manager.disable_location_sharing(user_id)
            continue

        logger.info("live location auto-disabled for user %s after 2 hours", user_id)
        await disable_sharing(user.id, user.partner_id, reason="auto_timeout")
