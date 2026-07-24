from tests.conftest import auth_headers


async def test_notepad_requires_pairing(client, alice):
    r = await client.get("/api/v1/notepad/private", headers=auth_headers(alice))
    assert r.status_code == 409


async def test_create_private_entry_scopes_to_owner(client, paired):
    alice, _bob = paired
    r = await client.post(
        "/api/v1/notepad",
        json={"type": "private", "title": "Groceries", "body": "my private note"},
        headers=auth_headers(alice),
    )
    assert r.status_code == 201, r.text
    entry = r.json()
    assert entry["type"] == "private"
    assert entry["owner_id"] == alice["id"]
    assert entry["title"] == "Groceries"
    assert entry["body"] == "my private note"


async def test_create_entry_title_defaults_blank(client, paired):
    alice, _bob = paired
    r = await client.post("/api/v1/notepad", json={"type": "private", "body": ""}, headers=auth_headers(alice))
    assert r.status_code == 201, r.text
    assert r.json()["title"] == ""


async def test_create_shared_entry_has_no_owner(client, paired):
    alice, _bob = paired
    r = await client.post(
        "/api/v1/notepad", json={"type": "shared", "body": "shopping list"}, headers=auth_headers(alice)
    )
    assert r.status_code == 201, r.text
    assert r.json()["owner_id"] is None


async def test_private_entry_invisible_to_partner(client, paired):
    alice, bob = paired
    r = await client.post(
        "/api/v1/notepad", json={"type": "private", "body": "secret"}, headers=auth_headers(alice)
    )
    entry_id = r.json()["id"]

    r = await client.get("/api/v1/notepad/private", headers=auth_headers(bob))
    assert r.status_code == 200
    assert r.json() == []

    # not just absent from the list — genuinely 404s for the partner, not 403 (existence itself
    # is meant to be hidden, see notepad_service._get_authorized's own doc comment). The
    # expected_updated_at value is irrelevant here since the 404 fires before any concurrency
    # check is reached.
    r = await client.patch(
        f"/api/v1/notepad/{entry_id}",
        json={"title": "", "body": "changed", "expected_updated_at": "2026-01-01T00:00:00Z"},
        headers=auth_headers(bob),
    )
    assert r.status_code == 404

    r = await client.delete(f"/api/v1/notepad/{entry_id}", headers=auth_headers(bob))
    assert r.status_code == 404


async def test_shared_entry_visible_and_editable_by_both(client, paired):
    alice, bob = paired
    r = await client.post(
        "/api/v1/notepad", json={"type": "shared", "body": "v1"}, headers=auth_headers(alice)
    )
    entry = r.json()

    r = await client.get("/api/v1/notepad/shared", headers=auth_headers(bob))
    assert r.status_code == 200
    assert len(r.json()) == 1

    r = await client.patch(
        f"/api/v1/notepad/{entry['id']}",
        json={"title": "Shared title", "body": "v2 by bob", "expected_updated_at": entry["updated_at"]},
        headers=auth_headers(bob),
    )
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "Shared title"
    assert r.json()["body"] == "v2 by bob"
    assert r.json()["updated_by"] == bob["id"]


async def test_update_rejects_stale_expected_updated_at(client, paired):
    alice, bob = paired
    r = await client.post(
        "/api/v1/notepad", json={"type": "shared", "body": "v1"}, headers=auth_headers(alice)
    )
    entry = r.json()

    # bob updates first, moving updated_at forward
    r = await client.patch(
        f"/api/v1/notepad/{entry['id']}",
        json={"title": "", "body": "v2", "expected_updated_at": entry["updated_at"]},
        headers=auth_headers(bob),
    )
    assert r.status_code == 200, r.text

    # alice's save is still based on the original (now-stale) updated_at
    r = await client.patch(
        f"/api/v1/notepad/{entry['id']}",
        json={"title": "", "body": "v3 based on stale read", "expected_updated_at": entry["updated_at"]},
        headers=auth_headers(alice),
    )
    assert r.status_code == 409, r.text


async def test_private_entry_update_ignores_stale_expected_updated_at(client, paired):
    alice, _bob = paired
    r = await client.post(
        "/api/v1/notepad", json={"type": "private", "body": "v1"}, headers=auth_headers(alice)
    )
    entry = r.json()

    # alice updates once, moving updated_at forward
    r = await client.patch(
        f"/api/v1/notepad/{entry['id']}",
        json={"title": "", "body": "v2", "expected_updated_at": entry["updated_at"]},
        headers=auth_headers(alice),
    )
    assert r.status_code == 200, r.text

    # a second save still using the original (now-stale) updated_at succeeds anyway — PRIVATE
    # entries are last-write-wins, unlike SHARED (see test_update_rejects_stale_expected_updated_at)
    r = await client.patch(
        f"/api/v1/notepad/{entry['id']}",
        json={"title": "", "body": "v3 based on stale read", "expected_updated_at": entry["updated_at"]},
        headers=auth_headers(alice),
    )
    assert r.status_code == 200, r.text
    assert r.json()["body"] == "v3 based on stale read"


async def test_update_succeeds_with_fresh_expected_updated_at(client, paired):
    alice, _bob = paired
    r = await client.post(
        "/api/v1/notepad", json={"type": "private", "body": "v1"}, headers=auth_headers(alice)
    )
    entry = r.json()

    r = await client.patch(
        f"/api/v1/notepad/{entry['id']}",
        json={"title": "", "body": "v2", "expected_updated_at": entry["updated_at"]},
        headers=auth_headers(alice),
    )
    assert r.status_code == 200, r.text
    assert r.json()["body"] == "v2"


async def test_delete_entry(client, paired):
    alice, _bob = paired
    r = await client.post(
        "/api/v1/notepad", json={"type": "private", "body": "temp"}, headers=auth_headers(alice)
    )
    entry_id = r.json()["id"]

    r = await client.delete(f"/api/v1/notepad/{entry_id}", headers=auth_headers(alice))
    assert r.status_code == 204

    r = await client.get("/api/v1/notepad/private", headers=auth_headers(alice))
    assert r.json() == []


async def test_shared_entry_can_be_deleted_by_either_partner(client, paired):
    alice, bob = paired
    r = await client.post(
        "/api/v1/notepad", json={"type": "shared", "body": "delete me"}, headers=auth_headers(alice)
    )
    entry_id = r.json()["id"]

    r = await client.delete(f"/api/v1/notepad/{entry_id}", headers=auth_headers(bob))
    assert r.status_code == 204


async def test_duplicate_entry_stays_within_same_type(client, paired):
    alice, _bob = paired
    r = await client.post(
        "/api/v1/notepad",
        json={"type": "private", "title": "Original title", "body": "original"},
        headers=auth_headers(alice),
    )
    entry_id = r.json()["id"]

    r = await client.post(f"/api/v1/notepad/{entry_id}/duplicate", headers=auth_headers(alice))
    assert r.status_code == 201, r.text
    duplicate = r.json()
    assert duplicate["id"] != entry_id
    assert duplicate["type"] == "private"
    assert duplicate["owner_id"] == alice["id"]
    assert duplicate["title"] == "Original title"
    assert duplicate["body"] == "original"

    r = await client.get("/api/v1/notepad/private", headers=auth_headers(alice))
    assert len(r.json()) == 2
