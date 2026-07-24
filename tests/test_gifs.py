import base64
import time

from app.core.security import sign_gif_proxy_url
from app.services import klipy_service
from app.services.klipy_service import KlipyGif
from tests.conftest import auth_headers

_FAKE_GIFS = [
    KlipyGif(
        id="abc123",
        title="a fake gif",
        width=480,
        height=270,
        preview_url="https://media.klipy.co/abc123/thumb.gif",
        full_url="https://media.klipy.co/abc123/full.gif",
    )
]


async def test_search_requires_pairing(client, alice):
    r = await client.get("/api/v1/gifs/search", params={"q": "cat"}, headers=auth_headers(alice))
    assert r.status_code == 409


async def test_search_returns_proxied_urls_not_klipy_urls(client, paired, monkeypatch):
    alice, _bob = paired

    async def fake_search(query, page, rating):
        assert query == "cat"
        assert rating == "pg-13"
        return _FAKE_GIFS

    monkeypatch.setattr(klipy_service, "search", fake_search)

    r = await client.get("/api/v1/gifs/search", params={"q": "cat"}, headers=auth_headers(alice))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == "abc123"
    # Neither URL ever exposes the real Klipy host — both are our own signed /gifs/proxy links.
    for key in ("preview_url", "full_url"):
        assert items[0][key].startswith("/api/v1/gifs/proxy?")
        assert "klipy" not in items[0][key]


async def test_mature_flag_maps_to_r_rating(client, paired, monkeypatch):
    alice, _bob = paired
    seen_ratings = []

    async def fake_trending(page, rating):
        seen_ratings.append(rating)
        return []

    monkeypatch.setattr(klipy_service, "trending", fake_trending)

    await client.get("/api/v1/gifs/trending", headers=auth_headers(alice))
    await client.get("/api/v1/gifs/trending", params={"mature": "true"}, headers=auth_headers(alice))
    assert seen_ratings == ["pg-13", "r"]


async def test_proxy_rejects_tampered_signature(client, paired):
    alice, _bob = paired
    r = await client.get(
        "/api/v1/gifs/proxy",
        params={"u": "aHR0cHM6Ly9ldmlsLmV4YW1wbGUveA", "exp": int(time.time()) + 600, "sig": "not-a-real-signature"},
        headers=auth_headers(alice),
    )
    assert r.status_code == 422


async def test_proxy_rejects_expired_signature(client, paired):
    alice, _bob = paired
    url = "https://media.klipy.co/abc123/full.gif"
    expired_at = int(time.time()) - 10
    sig = sign_gif_proxy_url(url, expired_at)
    encoded = base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")

    r = await client.get(
        "/api/v1/gifs/proxy",
        params={"u": encoded, "exp": expired_at, "sig": sig},
        headers=auth_headers(alice),
    )
    assert r.status_code == 422
