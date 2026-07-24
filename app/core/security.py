import base64
import hashlib
import hmac
import secrets
import time
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

settings = get_settings()

_password_hasher = PasswordHasher()

# Unambiguous alphabet for partner codes: no 0/O/1/I/L confusion pairs.
_PARTNER_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"


def _peppered(value: str) -> str:
    return value + settings.password_pepper


# --- Passwords ---------------------------------------------------------------


def hash_password(password: str) -> str:
    return _password_hasher.hash(_peppered(password))


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, _peppered(password))
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _password_hasher.check_needs_rehash(password_hash)


def generate_one_time_password(length: int = 12) -> str:
    """An admin-relayed reset password (`app.cli reset-password`) — same unambiguous alphabet as
    a partner code since this also has to be read aloud/typed by a human, just longer for a
    password's higher entropy needs. Satisfies `RegisterRequest.password`'s own min_length=8."""
    return "".join(secrets.choice(_PARTNER_CODE_ALPHABET) for _ in range(length))


# --- JWT access tokens ---------------------------------------------------------


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes))
    payload = {"sub": subject, "iat": now, "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("not an access token")
    return payload


# --- Opaque refresh tokens ---------------------------------------------------------


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_opaque_token(token: str) -> str:
    """SHA-256 is fine here: these are 256-bit random tokens, not low-entropy
    passwords, so we don't need Argon2's deliberate slowness — and refresh/
    partner-code lookups happen on every request, where that slowness would hurt."""
    return hashlib.sha256(token.encode()).hexdigest()


# --- Partner codes ---------------------------------------------------------------


def generate_partner_code(length: int = 8) -> str:
    return "".join(secrets.choice(_PARTNER_CODE_ALPHABET) for _ in range(length))


def hash_partner_code(code: str) -> str:
    return hash_opaque_token(code.strip().upper())


# --- TURN (coturn) time-limited credentials -----------------------------------------


def generate_turn_credentials(username_prefix: str) -> tuple[str, str, int]:
    """Coturn's REST API auth mechanism: username is `<expiry_unix>:<label>`,
    credential is base64(HMAC-SHA1(secret, username)). See coturn docs on
    `use-auth-secret` / `static-auth-secret`."""
    ttl = settings.turn_credential_ttl_seconds
    expiry = int(time.time()) + ttl
    turn_username = f"{expiry}:{username_prefix}"
    digest = hmac.new(
        settings.turn_static_secret.encode(), turn_username.encode(), hashlib.sha1
    ).digest()
    credential = base64.b64encode(digest).decode()
    return turn_username, credential, ttl
