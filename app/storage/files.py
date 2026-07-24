import asyncio
import hashlib
import uuid
from pathlib import Path

from app.core.config import get_settings

settings = get_settings()


def build_storage_path(category: str, extension: str) -> str:
    filename = f"{uuid.uuid4().hex}{extension}"
    return f"{category}/{filename}"


def absolute_path(storage_path: str) -> Path:
    return Path(settings.media_root) / storage_path


def _write_sync(full_path: Path, content: bytes) -> str:
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


async def save_upload(category: str, extension: str, content: bytes) -> tuple[str, str, int]:
    """Writes `content` under MEDIA_ROOT/<category>/<random>.<ext>. File I/O
    is offloaded to a thread so a large upload can't stall the event loop —
    important since the API runs as a single process (see entrypoint.sh)."""
    storage_path = build_storage_path(category, extension)
    checksum = await asyncio.to_thread(_write_sync, absolute_path(storage_path), content)
    return storage_path, checksum, len(content)


async def delete_file(storage_path: str) -> None:
    await asyncio.to_thread(lambda: absolute_path(storage_path).unlink(missing_ok=True))
