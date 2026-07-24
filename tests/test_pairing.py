from tests.conftest import auth_headers


async def test_generate_code_returns_plaintext_once(client, alice):
    r = await client.post("/api/v1/pairing/code", headers=auth_headers(alice))
    assert r.status_code == 200
    body = r.json()
    assert len(body["code"]) >= 4
    assert body["code_preview"] == body["code"][-4:]

    r = await client.get("/api/v1/pairing/code", headers=auth_headers(alice))
    assert r.status_code == 200
    status_body = r.json()
    assert status_body["has_active_code"] is True
    assert "code" not in status_body  # plaintext is never retrievable again


async def test_pair_happy_path(client, alice, bob):
    r = await client.post("/api/v1/pairing/code", headers=auth_headers(alice))
    code = r.json()["code"]

    r = await client.post("/api/v1/pairing/pair", json={"code": code}, headers=auth_headers(bob))
    assert r.status_code == 200
    assert r.json()["id"] == alice["id"]

    r = await client.get("/api/v1/pairing/status", headers=auth_headers(alice))
    assert r.status_code == 200
    body = r.json()
    assert body["paired"] is True
    assert body["partner"]["id"] == bob["id"]


async def test_pair_rejects_garbage_code(client, alice):
    r = await client.post("/api/v1/pairing/pair", json={"code": "NOPE"}, headers=auth_headers(alice))
    assert r.status_code == 404


async def test_cannot_pair_with_own_code(client, alice):
    r = await client.post("/api/v1/pairing/code", headers=auth_headers(alice))
    code = r.json()["code"]

    r = await client.post("/api/v1/pairing/pair", json={"code": code}, headers=auth_headers(alice))
    assert r.status_code == 409


async def test_regenerating_code_invalidates_previous(client, alice, bob):
    r = await client.post("/api/v1/pairing/code", headers=auth_headers(alice))
    old_code = r.json()["code"]

    r = await client.post("/api/v1/pairing/code", headers=auth_headers(alice))
    assert r.status_code == 200
    new_code = r.json()["code"]
    assert new_code != old_code

    r = await client.post("/api/v1/pairing/pair", json={"code": old_code}, headers=auth_headers(bob))
    assert r.status_code == 404


async def test_unpair_clears_both_sides(client, paired):
    alice, bob = paired

    r = await client.delete("/api/v1/pairing", headers=auth_headers(alice))
    assert r.status_code == 204

    r = await client.get("/api/v1/pairing/status", headers=auth_headers(alice))
    assert r.json()["paired"] is False

    r = await client.get("/api/v1/pairing/status", headers=auth_headers(bob))
    assert r.json()["paired"] is False


async def test_already_paired_users_cannot_generate_new_code(client, paired):
    alice, _bob = paired
    r = await client.post("/api/v1/pairing/code", headers=auth_headers(alice))
    assert r.status_code == 409
