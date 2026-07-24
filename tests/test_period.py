from tests.conftest import auth_headers


async def test_period_data_does_not_require_pairing(client, alice):
    r = await client.get("/api/v1/period/cycles", headers=auth_headers(alice))
    assert r.status_code == 200
    assert r.json() == []


async def test_create_cycle(client, alice):
    r = await client.post(
        "/api/v1/period/cycles",
        json={
            "cycle_start_date": "2026-07-01",
            "cycle_length_days": 28,
            "period_end_date": "2026-07-05",
            "symptoms": ["cramps"],
            "flow_intensity": "medium",
        },
        headers=auth_headers(alice),
    )
    assert r.status_code == 201
    body = r.json()
    assert body["cycle_length_days"] == 28
    assert body["period_end_date"] == "2026-07-05"
    assert body["symptoms"] == ["cramps"]
    assert body["flow_intensity"] == "medium"


async def test_partner_can_view_but_not_edit_cycle(client, paired):
    alice, bob = paired
    r = await client.post(
        "/api/v1/period/cycles", json={"cycle_start_date": "2026-07-01"}, headers=auth_headers(alice)
    )
    cycle_id = r.json()["id"]

    # bob's own list is empty until he asks to view alice's
    r = await client.get("/api/v1/period/cycles", headers=auth_headers(bob))
    assert r.json() == []

    r = await client.get(f"/api/v1/period/cycles?user_id={alice['id']}", headers=auth_headers(bob))
    assert len(r.json()) == 1
    assert r.json()[0]["id"] == cycle_id

    r = await client.patch(
        f"/api/v1/period/cycles/{cycle_id}", json={"cycle_length_days": 30}, headers=auth_headers(bob)
    )
    assert r.status_code == 403

    r = await client.delete(f"/api/v1/period/cycles/{cycle_id}", headers=auth_headers(bob))
    assert r.status_code == 403


async def test_cannot_view_a_stranger_users_cycles(client, alice, bob):
    r = await client.get(f"/api/v1/period/cycles?user_id={bob['id']}", headers=auth_headers(alice))
    assert r.status_code == 422


async def test_bulk_delete_wipes_both_partners_cycles(client, paired):
    alice, bob = paired
    r = await client.post(
        "/api/v1/period/cycles", json={"cycle_start_date": "2026-07-01"}, headers=auth_headers(alice)
    )
    assert r.status_code == 201
    r = await client.post("/api/v1/period/cycles", json={"cycle_start_date": "2026-06-01"}, headers=auth_headers(bob))
    assert r.status_code == 201

    # either partner can trigger the wipe — not scoped to who logged what
    r = await client.delete("/api/v1/period/cycles", headers=auth_headers(alice))
    assert r.status_code == 204

    r = await client.get("/api/v1/period/cycles", headers=auth_headers(alice))
    assert r.json() == []

    # bob's own cycle is gone too
    r = await client.get(f"/api/v1/period/cycles?user_id={bob['id']}", headers=auth_headers(alice))
    assert r.json() == []
