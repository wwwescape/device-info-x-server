import uuid

from tests.conftest import auth_headers


async def test_messaging_requires_pairing(client, alice):
    r = await client.get("/api/v1/messages", headers=auth_headers(alice))
    assert r.status_code == 409


async def test_send_and_list_message(client, paired):
    alice, bob = paired
    r = await client.post(
        "/api/v1/messages",
        json={"type": "text", "body": "hey", "client_message_id": str(uuid.uuid4())},
        headers=auth_headers(alice),
    )
    assert r.status_code == 201
    message = r.json()
    assert message["body"] == "hey"
    assert message["sender_id"] == alice["id"]

    r = await client.get("/api/v1/messages", headers=auth_headers(bob))
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["id"] == message["id"]


async def test_send_is_idempotent_on_client_message_id(client, paired):
    alice, _bob = paired
    client_message_id = str(uuid.uuid4())
    payload = {"type": "text", "body": "once", "client_message_id": client_message_id}

    r1 = await client.post("/api/v1/messages", json=payload, headers=auth_headers(alice))
    r2 = await client.post("/api/v1/messages", json=payload, headers=auth_headers(alice))
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]

    r = await client.get("/api/v1/messages", headers=auth_headers(alice))
    assert len(r.json()) == 1


async def test_only_sender_can_edit(client, paired):
    alice, bob = paired
    r = await client.post(
        "/api/v1/messages",
        json={"type": "text", "body": "typo", "client_message_id": str(uuid.uuid4())},
        headers=auth_headers(alice),
    )
    message_id = r.json()["id"]

    r = await client.patch(
        f"/api/v1/messages/{message_id}", json={"body": "not a typo"}, headers=auth_headers(bob)
    )
    assert r.status_code == 403

    r = await client.patch(
        f"/api/v1/messages/{message_id}", json={"body": "not a typo"}, headers=auth_headers(alice)
    )
    assert r.status_code == 200
    assert r.json()["body"] == "not a typo"
    assert r.json()["edited_at"] is not None


async def test_delete_scrubs_content(client, paired):
    alice, _bob = paired
    r = await client.post(
        "/api/v1/messages",
        json={"type": "text", "body": "secret", "client_message_id": str(uuid.uuid4())},
        headers=auth_headers(alice),
    )
    message_id = r.json()["id"]

    r = await client.delete(f"/api/v1/messages/{message_id}", headers=auth_headers(alice))
    assert r.status_code == 204

    # deleted messages drop out of the normal list
    r = await client.get("/api/v1/messages", headers=auth_headers(alice))
    assert r.json() == []


async def test_bulk_delete_wipes_entire_conversation_for_both_partners(client, paired):
    alice, bob = paired
    for sender, body in ((alice, "alice's"), (bob, "bob's")):
        r = await client.post(
            "/api/v1/messages",
            json={"type": "text", "body": body, "client_message_id": str(uuid.uuid4())},
            headers=auth_headers(sender),
        )
        assert r.status_code == 201

    # either partner can trigger the wipe — not scoped to who sent what
    r = await client.delete("/api/v1/messages", headers=auth_headers(alice))
    assert r.status_code == 204

    r = await client.get("/api/v1/messages", headers=auth_headers(bob))
    assert r.json() == []

    # idempotent — nothing left to delete a second time
    r = await client.delete("/api/v1/messages", headers=auth_headers(bob))
    assert r.status_code == 204


async def test_pin_is_visible_to_both_partners(client, paired):
    alice, bob = paired
    r = await client.post(
        "/api/v1/messages",
        json={"type": "text", "body": "important", "client_message_id": str(uuid.uuid4())},
        headers=auth_headers(alice),
    )
    message_id = r.json()["id"]

    r = await client.post(f"/api/v1/messages/{message_id}/pin", headers=auth_headers(bob))
    assert r.status_code == 200
    assert r.json()["is_pinned"] is True

    r = await client.get("/api/v1/messages/pinned", headers=auth_headers(alice))
    assert len(r.json()) == 1


async def test_star_is_private_per_user(client, paired):
    alice, bob = paired
    r = await client.post(
        "/api/v1/messages",
        json={"type": "text", "body": "starred by alice", "client_message_id": str(uuid.uuid4())},
        headers=auth_headers(alice),
    )
    message_id = r.json()["id"]

    r = await client.post(f"/api/v1/messages/{message_id}/star", headers=auth_headers(alice))
    assert r.status_code == 204

    r = await client.get("/api/v1/messages/starred", headers=auth_headers(alice))
    assert len(r.json()) == 1

    r = await client.get("/api/v1/messages/starred", headers=auth_headers(bob))
    assert r.json() == []


async def test_reaction_add_and_remove(client, paired):
    alice, bob = paired
    r = await client.post(
        "/api/v1/messages",
        json={"type": "text", "body": "funny", "client_message_id": str(uuid.uuid4())},
        headers=auth_headers(alice),
    )
    message_id = r.json()["id"]

    r = await client.post(
        f"/api/v1/messages/{message_id}/reactions", json={"emoji": "😂"}, headers=auth_headers(bob)
    )
    assert r.status_code == 200
    assert r.json()["reactions"] == [{"user_id": bob["id"], "emoji": "😂"}]

    r = await client.delete(f"/api/v1/messages/{message_id}/reactions", headers=auth_headers(bob))
    assert r.status_code == 204


async def test_mark_read_only_by_non_sender(client, paired):
    alice, bob = paired
    r = await client.post(
        "/api/v1/messages",
        json={"type": "text", "body": "read me", "client_message_id": str(uuid.uuid4())},
        headers=auth_headers(alice),
    )
    message_id = r.json()["id"]
    assert r.json()["read_at"] is None

    r = await client.post(f"/api/v1/messages/{message_id}/read", headers=auth_headers(bob))
    assert r.status_code == 200
    assert r.json()["read_at"] is not None


async def test_mark_delivered_only_by_non_sender(client, paired):
    alice, bob = paired
    r = await client.post(
        "/api/v1/messages",
        json={"type": "text", "body": "deliver me", "client_message_id": str(uuid.uuid4())},
        headers=auth_headers(alice),
    )
    message_id = r.json()["id"]
    assert r.json()["delivered_at"] is None

    r = await client.post(f"/api/v1/messages/{message_id}/delivered", headers=auth_headers(bob))
    assert r.status_code == 200
    assert r.json()["delivered_at"] is not None
    assert r.json()["read_at"] is None


async def test_mark_read_backfills_delivered_at(client, paired):
    alice, bob = paired
    r = await client.post(
        "/api/v1/messages",
        json={"type": "text", "body": "skip straight to read", "client_message_id": str(uuid.uuid4())},
        headers=auth_headers(alice),
    )
    message_id = r.json()["id"]

    r = await client.post(f"/api/v1/messages/{message_id}/read", headers=auth_headers(bob))
    assert r.status_code == 200
    assert r.json()["read_at"] is not None
    assert r.json()["delivered_at"] is not None


async def test_video_message_requires_media_of_right_category(client, paired):
    alice, _bob = paired
    r = await client.post(
        "/api/v1/messages",
        json={"type": "video", "client_message_id": str(uuid.uuid4())},
        headers=auth_headers(alice),
    )
    assert r.status_code == 422

    r = await client.post(
        "/api/v1/media",
        files={"file": ("clip.mp4", b"fake video bytes", "video/mp4")},
        data={"category": "message_video"},
        headers=auth_headers(alice),
    )
    assert r.status_code == 201, r.text
    media_id = r.json()["id"]

    r = await client.post(
        "/api/v1/messages",
        json={"type": "video", "media_id": media_id, "client_message_id": str(uuid.uuid4())},
        headers=auth_headers(alice),
    )
    assert r.status_code == 201, r.text
    assert r.json()["type"] == "video"
    assert r.json()["media_id"] == media_id


async def test_search_finds_matching_body(client, paired):
    alice, _bob = paired
    await client.post(
        "/api/v1/messages",
        json={"type": "text", "body": "let's get pizza tonight", "client_message_id": str(uuid.uuid4())},
        headers=auth_headers(alice),
    )
    await client.post(
        "/api/v1/messages",
        json={"type": "text", "body": "completely unrelated", "client_message_id": str(uuid.uuid4())},
        headers=auth_headers(alice),
    )

    r = await client.get("/api/v1/messages/search", params={"q": "pizza"}, headers=auth_headers(alice))
    assert r.status_code == 200
    results = r.json()
    assert len(results) == 1
    assert "pizza" in results[0]["body"]
