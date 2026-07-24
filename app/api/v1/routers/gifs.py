import base64
import time
from collections.abc import AsyncIterator

import httpx
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.core.deps import require_paired
from app.core.exceptions import UpstreamError, ValidationError
from app.core.security import sign_gif_proxy_url, verify_gif_proxy_signature
from app.models.user import User
from app.schemas.gifs import GifListResponse, GifResult
from app.services import klipy_service
from app.services.klipy_service import KlipyGif

router = APIRouter(prefix="/gifs", tags=["gifs"])

_PROXY_TTL_SECONDS = 600
_PROXY_FETCH_TIMEOUT_SECONDS = 10.0


def _rating_for(mature: bool) -> str:
    return "r" if mature else "pg-13"


def _proxy_url(real_url: str) -> str:
    expires_at = int(time.time()) + _PROXY_TTL_SECONDS
    signature = sign_gif_proxy_url(real_url, expires_at)
    encoded = base64.urlsafe_b64encode(real_url.encode()).decode().rstrip("=")
    return f"/api/v1/gifs/proxy?u={encoded}&exp={expires_at}&sig={signature}"


def _to_result(gif: KlipyGif) -> GifResult:
    return GifResult(
        id=gif.id,
        title=gif.title,
        width=gif.width,
        height=gif.height,
        preview_url=_proxy_url(gif.preview_url),
        full_url=_proxy_url(gif.full_url),
    )


@router.get("/search", response_model=GifListResponse)
async def search_gifs(
    q: str,
    page: int = Query(default=1, ge=1),
    mature: bool = False,
    current_user: User = Depends(require_paired),
) -> GifListResponse:
    results = await klipy_service.search(q, page, _rating_for(mature))
    return GifListResponse(items=[_to_result(gif) for gif in results])


@router.get("/trending", response_model=GifListResponse)
async def trending_gifs(
    page: int = Query(default=1, ge=1),
    mature: bool = False,
    current_user: User = Depends(require_paired),
) -> GifListResponse:
    results = await klipy_service.trending(page, _rating_for(mature))
    return GifListResponse(items=[_to_result(gif) for gif in results])


@router.get("/proxy")
async def proxy_gif(
    u: str,
    exp: int,
    sig: str,
    current_user: User = Depends(require_paired),
) -> StreamingResponse:
    """Streams the real Klipy asset behind a signed URL this server itself issued from a prior
    search/trending response — the client never contacts Klipy's CDN directly (see GifResult's
    doc comment). Not a general-purpose proxy: `verify_gif_proxy_signature` rejects any `u`/`exp`
    pair this server didn't sign moments earlier."""
    try:
        padded = u + "=" * (-len(u) % 4)
        real_url = base64.urlsafe_b64decode(padded).decode()
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValidationError("invalid proxy url") from exc
    if not verify_gif_proxy_signature(real_url, exp, sig):
        raise ValidationError("invalid or expired proxy signature")

    async def _stream() -> AsyncIterator[bytes]:
        try:
            async with httpx.AsyncClient(timeout=_PROXY_FETCH_TIMEOUT_SECONDS) as client:
                async with client.stream("GET", real_url) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes():
                        yield chunk
        except (httpx.HTTPError, OSError) as exc:
            raise UpstreamError("GIF provider is unavailable right now") from exc

    return StreamingResponse(_stream(), media_type="image/gif")
