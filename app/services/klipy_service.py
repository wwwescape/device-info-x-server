import logging
import time
from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.core.exceptions import UpstreamError

logger = logging.getLogger(__name__)
settings = get_settings()

_BASE_URL = "https://api.klipy.com/api/v1"
_FETCH_TIMEOUT_SECONDS = 6.0
_RESULTS_PER_PAGE = 24
# Klipy's free test key is capped at 100 requests/hour; trending doesn't change per-request, so
# it's cheap and safe to serve a short-lived cached copy instead of spending a call on every open
# of the GIF tab.
_TRENDING_CACHE_TTL_SECONDS = 300


@dataclass
class KlipyGif:
    id: str
    title: str | None
    width: int | None
    height: int | None
    preview_url: str
    full_url: str


_trending_cache: dict[str, tuple[float, list[KlipyGif]]] = {}

# Verified against a real response (2026-09-18): each item's real-media URLs live at
# `item["file"][<size>]["gif"]["url"]` — singular "file", keyed by size tier (hd/md/sm/xs), then
# by format (gif/webp/jpg/mp4/webm). Not documented anywhere consulted while building this, so
# this is the ground truth, not the earlier guess. Tries each size in priority order and returns
# the first that actually has a "gif" variant, since not every item necessarily has all four.
_PREVIEW_SIZE_PRIORITY = ("sm", "xs", "md", "hd")
_FULL_SIZE_PRIORITY = ("md", "hd", "sm", "xs")


def _gif_variant(file_field: dict, size_priority: tuple[str, ...]) -> tuple[str | None, int | None, int | None]:
    for size_key in size_priority:
        variant = ((file_field.get(size_key) or {}).get("gif")) or {}
        url = variant.get("url")
        if url:
            return url, variant.get("width"), variant.get("height")
    return None, None, None


def _parse_results(payload: dict) -> list[KlipyGif]:
    items = payload.get("data", {}).get("data", [])
    results = []
    for item in items:
        file_field = item.get("file") or {}
        # Both preview and full always point at the real (animated) GIF, never the mp4 variant —
        # the client's Coil setup only registers a GIF decoder, and a sent message needs to
        # actually be an image/gif for the existing MESSAGE_IMAGE pipeline to accept it unmodified.
        preview_url, _preview_w, _preview_h = _gif_variant(file_field, _PREVIEW_SIZE_PRIORITY)
        full_url, full_w, full_h = _gif_variant(file_field, _FULL_SIZE_PRIORITY)
        gif_id = item.get("id")
        if not preview_url or not full_url or gif_id is None:
            continue
        results.append(
            KlipyGif(
                id=str(gif_id),
                title=item.get("title"),
                width=full_w,
                height=full_h,
                preview_url=preview_url,
                full_url=full_url,
            )
        )
    return results


async def _get(path: str, params: dict) -> dict:
    if not settings.klipy_api_key:
        raise UpstreamError("GIF search is not configured on this server")
    url = f"{_BASE_URL}/{settings.klipy_api_key}/{path}"
    try:
        async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, OSError, ValueError) as exc:
        logger.warning("Klipy request to %s failed: %s", path, exc)
        raise UpstreamError("GIF provider is unavailable right now") from exc


async def search(query: str, page: int, rating: str) -> list[KlipyGif]:
    payload = await _get("gifs/search", {"q": query, "page": page, "per_page": _RESULTS_PER_PAGE, "rating": rating})
    return _parse_results(payload)


async def trending(page: int, rating: str) -> list[KlipyGif]:
    cache_key = f"{page}:{rating}"
    now = time.monotonic()
    cached = _trending_cache.get(cache_key)
    if cached is not None and now - cached[0] < _TRENDING_CACHE_TTL_SECONDS:
        return cached[1]

    payload = await _get("gifs/trending", {"page": page, "per_page": _RESULTS_PER_PAGE, "rating": rating})
    results = _parse_results(payload)
    _trending_cache[cache_key] = (now, results)
    return results
