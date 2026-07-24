from tests.conftest import auth_headers


async def test_period_data_does_not_require_pairing(client, alice):
    r = await client.get("/api/v1/period/days", headers=auth_headers(alice))
    assert r.status_code == 200
    assert r.json() == []


async def test_create_day_log(client, alice):
    r = await client.post(
        "/api/v1/period/days",
        json={
            "log_date": "2026-07-01",
            "symptoms": ["cramps"],
            "flow_intensity": "medium",
            "notes": "felt tired",
        },
        headers=auth_headers(alice),
    )
    assert r.status_code == 201
    body = r.json()
    assert body["log_date"] == "2026-07-01"
    assert body["symptoms"] == ["cramps"]
    assert body["flow_intensity"] == "medium"
    assert body["notes"] == "felt tired"


async def test_partner_can_view_but_not_edit_day_log(client, paired):
    alice, bob = paired
    r = await client.post("/api/v1/period/days", json={"log_date": "2026-07-01"}, headers=auth_headers(alice))
    day_log_id = r.json()["id"]

    # bob's own list is empty until he asks to view alice's
    r = await client.get("/api/v1/period/days", headers=auth_headers(bob))
    assert r.json() == []

    r = await client.get(f"/api/v1/period/days?user_id={alice['id']}", headers=auth_headers(bob))
    assert len(r.json()) == 1
    assert r.json()[0]["id"] == day_log_id

    r = await client.patch(
        f"/api/v1/period/days/{day_log_id}", json={"flow_intensity": "heavy"}, headers=auth_headers(bob)
    )
    assert r.status_code == 403

    r = await client.delete(f"/api/v1/period/days/{day_log_id}", headers=auth_headers(bob))
    assert r.status_code == 403


async def test_cannot_view_a_stranger_users_day_logs(client, alice, bob):
    r = await client.get(f"/api/v1/period/days?user_id={bob['id']}", headers=auth_headers(alice))
    assert r.status_code == 422


async def test_bulk_delete_wipes_both_partners_day_logs(client, paired):
    alice, bob = paired
    r = await client.post("/api/v1/period/days", json={"log_date": "2026-07-01"}, headers=auth_headers(alice))
    assert r.status_code == 201
    r = await client.post("/api/v1/period/days", json={"log_date": "2026-06-01"}, headers=auth_headers(bob))
    assert r.status_code == 201

    # either partner can trigger the wipe — not scoped to who logged what
    r = await client.delete("/api/v1/period/days", headers=auth_headers(alice))
    assert r.status_code == 204

    r = await client.get("/api/v1/period/days", headers=auth_headers(alice))
    assert r.json() == []

    # bob's own day logs are gone too
    r = await client.get(f"/api/v1/period/days?user_id={bob['id']}", headers=auth_headers(alice))
    assert r.json() == []
