import datetime

from tests.conftest import auth_headers


def _iso(delta: datetime.timedelta) -> str:
    return (datetime.datetime.now(datetime.UTC) + delta).isoformat()


async def test_create_scheduled_message(client, paired):
    alice, _bob = paired
    r = await client.post(
        "/api/v1/messages/scheduled",
        json={"body": "happy birthday!", "scheduled_at": _iso(datetime.timedelta(hours=1))},
        headers=auth_headers(alice),
    )
    assert r.status_code == 201, r.text
    assert r.json()["body"] == "happy birthday!"


async def test_create_scheduled_message_rejects_blank_body(client, paired):
    alice, _bob = paired
    r = await client.post(
        "/api/v1/messages/scheduled",
        json={"body": "", "scheduled_at": _iso(datetime.timedelta(hours=1))},
        headers=auth_headers(alice),
    )
    assert r.status_code == 422


async def test_scheduled_message_invisible_to_partner(client, paired):
    alice, bob = paired
    r = await client.post(
        "/api/v1/messages/scheduled",
        json={"body": "surprise", "scheduled_at": _iso(datetime.timedelta(hours=1))},
        headers=auth_headers(alice),
    )
    entry_id = r.json()["id"]

    r = await client.get("/api/v1/messages/scheduled", headers=auth_headers(bob))
    assert r.status_code == 200
    assert r.json() == []

    # Not just absent from the list — genuinely 404s for the partner, not 403 (mirrors
    # notepad_service._get_authorized's own "existence itself is hidden" reasoning).
    r = await client.delete(f"/api/v1/messages/scheduled/{entry_id}", headers=auth_headers(bob))
    assert r.status_code == 404

    r = await client.post(f"/api/v1/messages/scheduled/{entry_id}/send-now", headers=auth_headers(bob))
    assert r.status_code == 404


async def test_list_scheduled_messages_sorted_soonest_first(client, paired):
    alice, _bob = paired
    await client.post(
        "/api/v1/messages/scheduled",
        json={"body": "later one", "scheduled_at": _iso(datetime.timedelta(hours=5))},
        headers=auth_headers(alice),
    )
    await client.post(
        "/api/v1/messages/scheduled",
        json={"body": "sooner one", "scheduled_at": _iso(datetime.timedelta(minutes=30))},
        headers=auth_headers(alice),
    )

    r = await client.get("/api/v1/messages/scheduled", headers=auth_headers(alice))
    assert r.status_code == 200
    assert [item["body"] for item in r.json()] == ["sooner one", "later one"]


async def test_cancel_scheduled_message(client, paired):
    alice, _bob = paired
    r = await client.post(
        "/api/v1/messages/scheduled",
        json={"body": "cancel me", "scheduled_at": _iso(datetime.timedelta(hours=1))},
        headers=auth_headers(alice),
    )
    entry_id = r.json()["id"]

    r = await client.delete(f"/api/v1/messages/scheduled/{entry_id}", headers=auth_headers(alice))
    assert r.status_code == 204

    r = await client.get("/api/v1/messages/scheduled", headers=auth_headers(alice))
    assert r.json() == []


async def test_send_scheduled_message_now_creates_real_message_and_clears_staging_row(client, paired):
    alice, bob = paired
    r = await client.post(
        "/api/v1/messages/scheduled",
        json={"body": "sent early", "scheduled_at": _iso(datetime.timedelta(hours=1))},
        headers=auth_headers(alice),
    )
    entry_id = r.json()["id"]

    r = await client.post(f"/api/v1/messages/scheduled/{entry_id}/send-now", headers=auth_headers(alice))
    assert r.status_code == 204, r.text

    r = await client.get("/api/v1/messages/scheduled", headers=auth_headers(alice))
    assert r.json() == []

    r = await client.get("/api/v1/messages", headers=auth_headers(bob))
    assert r.status_code == 200
    assert "sent early" in [m["body"] for m in r.json()]
