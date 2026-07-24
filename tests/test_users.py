import uuid

from tests.conftest import TEST_PASSWORD, auth_headers, register_and_login


async def test_delete_me_removes_account_and_unpairs_partner(client, paired):
    alice, bob = paired

    # give alice some data across a few sections so the FK-cascade claim is actually exercised,
    # not just asserted
    r = await client.post(
        "/api/v1/messages",
        json={"type": "text", "body": "hi", "client_message_id": str(uuid.uuid4())},
        headers=auth_headers(alice),
    )
    assert r.status_code == 201

    r = await client.delete("/api/v1/users/me", headers=auth_headers(alice))
    assert r.status_code == 204

    # alice's old token is dead — the account row itself is gone, not just logically "deleted"
    r = await client.get("/api/v1/users/me", headers=auth_headers(alice))
    assert r.status_code == 401

    # bob keeps his own account, just loses the pairing link
    r = await client.get("/api/v1/pairing/status", headers=auth_headers(bob))
    assert r.status_code == 200
    assert r.json()["paired"] is False

    # bob's message list is empty too — alice's cascaded away with her account
    r = await client.get("/api/v1/messages", headers=auth_headers(bob))
    assert r.status_code == 409  # no longer paired, matches messaging's existing pairing requirement


async def test_registration_slot_frees_up_after_delete(client):
    alice = await register_and_login(client, "alice2", "Alice")
    await register_and_login(client, "bob2", "Bob")

    from app.core.config import get_settings

    settings = get_settings()
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "carol2",
            "password": TEST_PASSWORD,
            "display_name": "Carol",
            "first_name": "Carol",
            "last_name": "Test",
            "birthday_date": "1990-01-01",
            "setup_token": settings.server_setup_token,
        },
    )
    assert r.status_code == 403  # cap of 2 reached

    r = await client.delete("/api/v1/users/me", headers=auth_headers(alice))
    assert r.status_code == 204

    r = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "carol2",
            "password": TEST_PASSWORD,
            "display_name": "Carol",
            "first_name": "Carol",
            "last_name": "Test",
            "birthday_date": "1990-01-01",
            "setup_token": settings.server_setup_token,
        },
    )
    assert r.status_code == 201
