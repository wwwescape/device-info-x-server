import asyncio
import ipaddress
import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser

import httpx

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)
_USER_AGENT = "Mozilla/5.0 (compatible; DeviceInfoXLinkPreview/1.0)"
_MAX_HTML_BYTES = 2 * 1024 * 1024
_MAX_IMAGE_BYTES = 5 * 1024 * 1024
_FETCH_TIMEOUT_SECONDS = 6.0
_MAX_REDIRECTS = 5
_MAX_TITLE_LENGTH = 512
_MAX_DESCRIPTION_LENGTH = 2000


def first_url_in(text: str) -> str | None:
    """The first http(s) URL substring in a message body, or None. Only ever called for
    MessageType.TEXT sends — see message_service.send_message."""
    match = _URL_RE.search(text)
    return match.group(0) if match else None


class _UnsafeUrlError(Exception):
    """Raised from the httpx request hook below to abort a fetch — including a redirect hop —
    the instant it targets an unsafe host, before any connection is opened."""


async def _is_safe_host(hostname: str) -> bool:
    try:
        # asyncio's own resolver, not the blocking socket.getaddrinfo — this server runs as a
        # single process (see app/storage/files.py's doc comment on offloading file I/O to a
        # thread for the same reason), so a synchronous DNS lookup here would stall every other
        # concurrent request for however long resolution takes, which can be several seconds for
        # a slow/nonexistent host.
        infos = await asyncio.get_running_loop().getaddrinfo(hostname, None)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        sockaddr = info[4]
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            return False
        # Blocks SSRF targets like a cloud metadata endpoint (169.254.169.254) or anything on
        # localhost/the private LAN this server itself runs on. Residual risk, accepted for this
        # app's scope: a DNS-rebinding attacker could still swap the resolved IP between this
        # check and the actual connection a moment later — closing that gap needs pinning the
        # resolved IP for the real TCP connect (a custom httpx transport), not done here.
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
    return True


async def _is_safe_url(url: httpx.URL | str) -> bool:
    parsed = httpx.URL(url)
    if parsed.scheme not in ("http", "https") or not parsed.host:
        return False
    return await _is_safe_host(parsed.host)


async def _reject_unsafe_hosts(request: httpx.Request) -> None:
    """An httpx `event_hooks["request"]` callback — fires for the initial request *and* every
    automatic redirect hop httpx follows, before it connects, so a redirect can't sneak past the
    safety check the original URL passed. See `fetch_preview`/`_fetch_image` for where it's wired
    in via `follow_redirects=True, max_redirects=_MAX_REDIRECTS`."""
    if not await _is_safe_url(request.url):
        raise _UnsafeUrlError(str(request.url))


class _OpenGraphParser(HTMLParser):
    """Collects <title> text plus the handful of <meta> tags a link preview needs. The caller
    only ever feeds it up to `_MAX_HTML_BYTES` — everything relevant always lives in <head>, so
    there's no need to parse (or even fully download) the rest of the page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.og_title: str | None = None
        self.og_description: str | None = None
        self.og_image: str | None = None
        self.meta_description: str | None = None
        self.title_tag: str | None = None
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
            return
        if tag != "meta":
            return
        attr_dict = {k: v for k, v in attrs if v is not None}
        prop = attr_dict.get("property") or attr_dict.get("name")
        content = attr_dict.get("content")
        if not prop or not content:
            return
        if prop == "og:title":
            self.og_title = content
        elif prop == "og:description":
            self.og_description = content
        elif prop == "og:image":
            self.og_image = content
        elif prop == "description":
            self.meta_description = content

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title and self.title_tag is None:
            self.title_tag = data.strip()


@dataclass
class ParsedPreview:
    url: str
    title: str | None
    description: str | None
    image_content: bytes | None
    image_mime_type: str | None


async def _fetch_image(image_url: str) -> tuple[bytes | None, str | None]:
    if not await _is_safe_url(image_url):
        return None, None
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            max_redirects=_MAX_REDIRECTS,
            timeout=_FETCH_TIMEOUT_SECONDS,
            event_hooks={"request": [_reject_unsafe_hosts]},
        ) as client:
            async with client.stream("GET", image_url, headers={"User-Agent": _USER_AGENT}) as response:
                if response.status_code != 200:
                    return None, None
                content_type = response.headers.get("content-type", "")
                if not content_type.lower().startswith("image/"):
                    return None, None
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > _MAX_IMAGE_BYTES:
                        return None, None
                return bytes(content), content_type.split(";")[0].strip()
    except (httpx.HTTPError, OSError, _UnsafeUrlError) as exc:
        logger.info("link preview image fetch failed for %s: %s", image_url, exc)
        return None, None


async def fetch_preview(url: str) -> ParsedPreview | None:
    """Fetches `url`, extracts OpenGraph/title metadata, and — if an og:image is present —
    fetches that too. Returns None for anything that isn't a clean, safe, useful preview
    (unreachable host, non-HTML response, no usable tags, unsafe redirect target, timeout, etc.)
    rather than raising — the caller (message_service._fetch_and_attach_link_preview) treats
    every failure mode identically: the message just never grows a preview."""
    if not await _is_safe_url(url):
        return None
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            max_redirects=_MAX_REDIRECTS,
            timeout=_FETCH_TIMEOUT_SECONDS,
            event_hooks={"request": [_reject_unsafe_hosts]},
        ) as client:
            async with client.stream("GET", url, headers={"User-Agent": _USER_AGENT}) as response:
                if response.status_code != 200:
                    return None
                content_type = response.headers.get("content-type", "")
                if "text/html" not in content_type.lower():
                    return None
                html_bytes = bytearray()
                async for chunk in response.aiter_bytes():
                    html_bytes.extend(chunk)
                    if len(html_bytes) >= _MAX_HTML_BYTES:
                        break
                resolved_url = str(response.url)
    except (httpx.HTTPError, OSError, _UnsafeUrlError) as exc:
        logger.info("link preview fetch failed for %s: %s", url, exc)
        return None

    parser = _OpenGraphParser()
    try:
        parser.feed(bytes(html_bytes).decode("utf-8", errors="ignore"))
    except Exception:
        logger.info("link preview HTML parse failed for %s", url)
        return None

    title = (parser.og_title or parser.title_tag or "").strip()[:_MAX_TITLE_LENGTH] or None
    description = (parser.og_description or parser.meta_description or "").strip()[:_MAX_DESCRIPTION_LENGTH] or None
    if title is None and description is None and not parser.og_image:
        return None

    image_content: bytes | None = None
    image_mime_type: str | None = None
    if parser.og_image:
        image_url = str(httpx.URL(resolved_url).join(parser.og_image))
        image_content, image_mime_type = await _fetch_image(image_url)

    return ParsedPreview(
        url=resolved_url,
        title=title,
        description=description,
        image_content=image_content,
        image_mime_type=image_mime_type,
    )
