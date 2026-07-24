import asyncio
import logging
import uuid

import firebase_admin
from firebase_admin import credentials, messaging

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.repositories import device_repo

logger = logging.getLogger(__name__)
settings = get_settings()

_firebase_app: firebase_admin.App | None = None


def init_firebase() -> None:
    """Call once at application startup (see main.py lifespan). No-op (with
    a warning) if no service-account JSON is configured, so the rest of the
    app still runs without push notifications during local dev."""
    global _firebase_app
    if _firebase_app is not None:
        return
    if not settings.firebase_service_account_json:
        logger.warning("FIREBASE_SERVICE_ACCOUNT_JSON not set — push notifications disabled")
        return
    try:
        cred = credentials.Certificate(settings.firebase_service_account_json)
        _firebase_app = firebase_admin.initialize_app(cred)
    except Exception:
        logger.exception("failed to initialize Firebase Admin SDK — push notifications disabled")


def _send_multicast_sync(tokens: list[str], data: dict[str, str]) -> list[str]:
    """Runs in a worker thread (firebase-admin's HTTP calls are sync).
    Returns tokens Firebase reports as permanently invalid, for cleanup."""
    message = messaging.MulticastMessage(
        data=data, tokens=tokens, android=messaging.AndroidConfig(priority="high")
    )
    try:
        response = messaging.send_each_for_multicast(message, app=_firebase_app)
    except Exception:
        logger.exception("FCM send failed")
        return []

    invalid_tokens = []
    for token, result in zip(tokens, response.responses, strict=True):
        if not result.success and isinstance(result.exception, messaging.UnregisteredError):
            invalid_tokens.append(token)
    return invalid_tokens


def _send_test_sync(tokens: list[str]) -> tuple[int, list[str]]:
    """Runs in a worker thread. Only ever called from the `test-notification` CLI command, never
    from a real notification path. Returns (success_count, invalid_tokens) — invalid_tokens are
    ones FCM itself reports as permanently unregistered (e.g. superseded by a newer token issued
    to the same install, which happens on every rebuild/reinstall during development — a token's
    *age* says nothing about whether it's still valid, only FCM's own response does).

    Sent data-only (`type: "test"`), exactly like every real push — deliberately reversed from an
    earlier version of this diagnostic that included an FCM `notification` block so FCM would
    auto-display it, on the theory that this verified delivery "independent of the Android app's
    own rendering logic." In practice that block bypassed `ConsoleFcmService`'s own channel
    selection entirely: an auto-displayed notification message with no `android_channel_id` set
    lands on the FCM SDK's own built-in fallback channel, not either of `ConsolePushChannelManager`'s
    two app channels — so none of the app's own notification settings (Alert style/importance,
    Sound Mode, Sound Tone) had any effect on it, and its tap carried no `notification_category`
    extra either, so it never exercised the Dashboard's fake card. `"test"` isn't a type
    `ConsoleFcmService.pushCategoryOf` recognizes, so it falls through to the same `PushCategory.OTHER`
    bucket a locker upload or pairing change would — from there this rides the *exact* pipeline a
    real push does: `ConsoleSettingsRepository`-driven channel/importance/sound selection, the
    per-category unseen counter, and on tap, `MainActivity`'s category-driven fake card. The
    trade-off: this no longer independently verifies raw FCM wire delivery isolated from
    `ConsoleFcmService.onMessageReceived`'s own code — a bug there would now make this diagnostic
    silently show nothing too, same blind spot every real push already has. The per-token
    success/invalid-token detection below is unaffected either way — that reflects FCM's own
    server-side send result, not whether anything was actually displayed on-device."""
    message = messaging.MulticastMessage(
        data={"type": "test"},
        tokens=tokens,
        android=messaging.AndroidConfig(priority="high"),
    )
    response = messaging.send_each_for_multicast(message, app=_firebase_app)
    invalid_tokens = [
        token
        for token, result in zip(tokens, response.responses, strict=True)
        if not result.success and isinstance(result.exception, messaging.UnregisteredError)
    ]
    success_count = sum(1 for r in response.responses if r.success)
    return success_count, invalid_tokens


async def send_test_notification(user_id: uuid.UUID) -> str:
    """CLI diagnostic only — see `_send_test_sync`. The only write this can make is deleting
    tokens FCM itself confirms are dead (mirrors the cleanup FcmPushSender.send_data_message
    already does for real notifications), so it never touches message/calendar/period data."""
    if _firebase_app is None:
        return "Firebase Admin SDK not initialized (FIREBASE_SERVICE_ACCOUNT_JSON not set)."

    async with async_session_factory() as db:
        tokens = await device_repo.list_tokens_for_user(db, user_id)
    if not tokens:
        return "No registered devices (FCM tokens) for this user."

    total = len(tokens)
    sent, invalid_tokens = await asyncio.to_thread(_send_test_sync, tokens)

    remaining = total - len(invalid_tokens)
    result = f"Sent to {sent}/{remaining} device(s)."

    if not invalid_tokens:
        return result

    async with async_session_factory() as db:
        for token in invalid_tokens:
            await device_repo.delete_by_token(db, user_id, token)
        await db.commit()
    return f"{result}\n\nAdditionally, removed {len(invalid_tokens)} dead token(s) (superseded/uninstalled)."


class FcmPushSender:
    """Implements notification_service.PushSender. Payloads are always
    data-only — never message content — per the design doc; the Android
    app decides how (and whether, in discreet mode) to render a
    notification from the data it receives."""

    async def send_data_message(self, user_id: uuid.UUID, data: dict[str, str]) -> None:
        if _firebase_app is None:
            return

        async with async_session_factory() as db:
            tokens = await device_repo.list_tokens_for_user(db, user_id)
            if not tokens:
                return

            invalid_tokens = await asyncio.to_thread(_send_multicast_sync, tokens, data)

            if invalid_tokens:
                for token in invalid_tokens:
                    await device_repo.delete_by_token(db, user_id, token)
                await db.commit()


fcm_push_sender = FcmPushSender()
