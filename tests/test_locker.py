from tests.conftest import auth_headers


async def test_create_and_partner_can_view(client, paired):
    alice, bob = paired
    r = await client.post(
        "/api/v1/locker/items",
        json={"title": "Passport scan", "category": "document"},
        headers=auth_headers(alice),
    )
    assert r.status_code == 201
    item_id = r.json()["id"]

    r = await client.get(f"/api/v1/locker/items/{item_id}", headers=auth_headers(bob))
    assert r.status_code == 200
    assert r.json()["owner_id"] == alice["id"]

    r = await client.get("/api/v1/locker/items", headers=auth_headers(bob))
    assert len(r.json()) == 1


async def test_only_owner_can_edit_or_delete(client, paired):
    alice, bob = paired
    r = await client.post(
        "/api/v1/locker/items",
        json={"title": "Notes", "category": "note"},
        headers=auth_headers(alice),
    )
    item_id = r.json()["id"]

    r = await client.patch(
        f"/api/v1/locker/items/{item_id}", json={"title": "Edited by bob"}, headers=auth_headers(bob)
    )
    assert r.status_code == 403

    r = await client.delete(f"/api/v1/locker/items/{item_id}", headers=auth_headers(bob))
    assert r.status_code == 403

    r = await client.patch(
        f"/api/v1/locker/items/{item_id}", json={"title": "Edited by alice"}, headers=auth_headers(alice)
    )
    assert r.status_code == 200

    r = await client.delete(f"/api/v1/locker/items/{item_id}", headers=auth_headers(alice))
    assert r.status_code == 204


async def test_video_item_with_media(client, paired):
    alice, bob = paired
    r = await client.post(
        "/api/v1/media",
        files={"file": ("home_movie.mp4", b"fake video bytes", "video/mp4")},
        data={"category": "locker_file"},
        headers=auth_headers(alice),
    )
    assert r.status_code == 201, r.text
    media_id = r.json()["id"]

    r = await client.post(
        "/api/v1/locker/items",
        json={"title": "Home movie", "category": "video", "media_id": media_id},
        headers=auth_headers(alice),
    )
    assert r.status_code == 201, r.text
    item_id = r.json()["id"]
    assert r.json()["category"] == "video"

    r = await client.get(f"/api/v1/locker/items/{item_id}", headers=auth_headers(bob))
    assert r.status_code == 200
    assert r.json()["media_id"] == media_id


async def test_bulk_delete_is_owner_scoped_and_clears_albums(client, paired):
    alice, bob = paired
    r = await client.post("/api/v1/locker/albums", json={"name": "Alice's album"}, headers=auth_headers(alice))
    assert r.status_code == 201
    r = await client.post(
        "/api/v1/locker/items", json={"title": "Alice's note", "category": "note"}, headers=auth_headers(alice)
    )
    assert r.status_code == 201
    r = await client.post(
        "/api/v1/locker/items", json={"title": "Bob's note", "category": "note"}, headers=auth_headers(bob)
    )
    assert r.status_code == 201
    bob_item_id = r.json()["id"]

    r = await client.delete("/api/v1/locker/items", headers=auth_headers(alice))
    assert r.status_code == 204

    r = await client.get("/api/v1/locker/albums", headers=auth_headers(alice))
    assert r.json() == []

    r = await client.get("/api/v1/locker/items", headers=auth_headers(alice))
    items = r.json()
    assert len(items) == 1
    assert items[0]["id"] == bob_item_id

    # idempotent
    r = await client.delete("/api/v1/locker/items", headers=auth_headers(alice))
    assert r.status_code == 204
