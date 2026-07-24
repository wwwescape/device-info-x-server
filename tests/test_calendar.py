import datetime

from tests.conftest import auth_headers


async def test_create_and_list_event(client, paired):
    alice, bob = paired
    r = await client.post(
        "/api/v1/calendar/events",
        json={
            "type": "planned_date",
            "title": "Dinner",
            "start_at": "2026-08-01T18:00:00Z",
            "end_at": "2026-08-01T20:00:00Z",
            "reminder_minutes_before": [60, 10],
        },
        headers=auth_headers(alice),
    )
    assert r.status_code == 201
    event = r.json()
    assert event["reminder_minutes_before"] == [10, 60]

    r = await client.get(
        "/api/v1/calendar/events",
        params={"from": "2026-07-01T00:00:00Z", "to": "2026-09-01T00:00:00Z"},
        headers=auth_headers(bob),
    )
    assert r.status_code == 200
    assert len(r.json()) == 1


async def test_invalid_recurrence_rule_rejected(client, paired):
    alice, _bob = paired
    r = await client.post(
        "/api/v1/calendar/events",
        json={
            "type": "custom",
            "title": "Bad",
            "start_at": "2026-08-01T18:00:00Z",
            "recurrence_rule": "NOT A RULE",
        },
        headers=auth_headers(alice),
    )
    assert r.status_code == 422


async def test_either_partner_can_update_or_delete(client, paired):
    alice, bob = paired
    r = await client.post(
        "/api/v1/calendar/events",
        json={"type": "planned_date", "title": "Movie night", "start_at": "2026-08-05T19:00:00Z"},
        headers=auth_headers(alice),
    )
    event_id = r.json()["id"]

    r = await client.patch(
        f"/api/v1/calendar/events/{event_id}", json={"title": "Movie night (rescheduled)"}, headers=auth_headers(bob)
    )
    assert r.status_code == 200
    assert r.json()["title"] == "Movie night (rescheduled)"

    r = await client.delete(f"/api/v1/calendar/events/{event_id}", headers=auth_headers(bob))
    assert r.status_code == 204

    r = await client.get(f"/api/v1/calendar/events/{event_id}", headers=auth_headers(alice))
    assert r.status_code == 404


async def test_wipe_clears_calendar_for_either_partner(client, paired):
    alice, bob = paired
    r = await client.post(
        "/api/v1/calendar/events",
        json={"type": "planned_date", "title": "Movie night", "start_at": "2026-08-05T19:00:00Z"},
        headers=auth_headers(alice),
    )
    assert r.status_code == 201

    r = await client.post(
        "/api/v1/calendar/events",
        json={
            "type": "custom",
            "title": "Anniversary",
            "start_at": datetime.datetime(2020, 8, 5, tzinfo=datetime.UTC).isoformat(),
            "all_day": True,
        },
        headers=auth_headers(bob),
    )
    assert r.status_code == 201

    # bob wipes it — no ownership check, matching single-item delete today
    r = await client.delete("/api/v1/calendar", headers=auth_headers(bob))
    assert r.status_code == 204

    r = await client.get(
        "/api/v1/calendar/events",
        params={"from": "2019-01-01T00:00:00Z", "to": "2027-01-01T00:00:00Z"},
        headers=auth_headers(alice),
    )
    assert r.json() == []


async def test_wedding_anniversary_and_unplanned_date(client, paired):
    alice, _bob = paired

    r = await client.post(
        "/api/v1/calendar/events",
        json={
            "type": "wedding_anniversary",
            "title": "Our anniversary",
            "start_at": "2020-06-15T00:00:00Z",
            "all_day": True,
            "recurrence_rule": "FREQ=YEARLY",
        },
        headers=auth_headers(alice),
    )
    assert r.status_code == 201

    r = await client.post(
        "/api/v1/calendar/events",
        json={
            "type": "unplanned_date",
            "title": "Spontaneous dinner",
            "start_at": "2026-08-01T19:00:00Z",
        },
        headers=auth_headers(alice),
    )
    assert r.status_code == 201


async def test_create_planned_drive_reminder_trip(client, paired):
    alice, _bob = paired

    r = await client.post(
        "/api/v1/calendar/events",
        json={"type": "planned_drive", "title": "Coastal drive", "start_at": "2026-09-05T09:00:00Z"},
        headers=auth_headers(alice),
    )
    assert r.status_code == 201

    # REMINDER allows either — both should succeed.
    for recurrence_rule in ("FREQ=YEARLY", None):
        r = await client.post(
            "/api/v1/calendar/events",
            json={
                "type": "reminder",
                "title": "Renew passport",
                "start_at": "2026-10-01T09:00:00Z",
                "recurrence_rule": recurrence_rule,
            },
            headers=auth_headers(alice),
        )
        assert r.status_code == 201, recurrence_rule

    # PLANNED_TRIP is a multi-day range but, like VACATION, is never recurring.
    r = await client.post(
        "/api/v1/calendar/events",
        json={
            "type": "planned_trip",
            "title": "Ski trip",
            "start_at": "2026-01-10T00:00:00Z",
            "end_at": "2026-01-17T00:00:00Z",
            "all_day": True,
        },
        headers=auth_headers(alice),
    )
    assert r.status_code == 201


async def test_non_recurring_type_rejects_recurrence_rule(client, paired):
    alice, _bob = paired

    event_types = (
        "vacation",
        "planned_trip",
        "unplanned_date",
        "planned_drive",
        "unplanned_drive",
        "planned_date",
    )
    for event_type in event_types:
        r = await client.post(
            "/api/v1/calendar/events",
            json={
                "type": event_type,
                "title": "Should fail",
                "start_at": "2026-09-01T00:00:00Z",
                "recurrence_rule": "FREQ=YEARLY",
            },
            headers=auth_headers(alice),
        )
        assert r.status_code == 422, event_type


async def test_non_recurring_type_rejects_recurrence_rule_on_update(client, paired):
    alice, _bob = paired
    r = await client.post(
        "/api/v1/calendar/events",
        json={"type": "vacation", "title": "Trip", "start_at": "2026-09-10T00:00:00Z"},
        headers=auth_headers(alice),
    )
    event_id = r.json()["id"]

    r = await client.patch(
        f"/api/v1/calendar/events/{event_id}",
        json={"recurrence_rule": "FREQ=YEARLY"},
        headers=auth_headers(alice),
    )
    assert r.status_code == 422


async def test_intimacy_log_round_trip_on_past_eligible_event(client, paired):
    alice, _bob = paired
    intimacy = {
        "rating": 5,
        "duration_minutes": 45,
        "initiated_by": "both",
        "protection_used": True,
        "positions": ["Missionary", "Spooning"],
        "locations": ["Bedroom"],
    }
    r = await client.post(
        "/api/v1/calendar/events",
        json={
            "type": "custom",
            "title": "Date night",
            "start_at": "2020-01-01T20:00:00Z",
            "intimacy": intimacy,
        },
        headers=auth_headers(alice),
    )
    assert r.status_code == 201, r.text
    event = r.json()
    assert event["intimacy"]["rating"] == 5
    assert event["intimacy"]["initiated_by"] == "both"
    assert sorted(event["intimacy"]["positions"]) == ["Missionary", "Spooning"]

    r = await client.get(f"/api/v1/calendar/events/{event['id']}", headers=auth_headers(alice))
    assert r.status_code == 200
    assert r.json()["intimacy"]["duration_minutes"] == 45


async def test_intimacy_log_rejected_for_future_event(client, paired):
    alice, _bob = paired
    r = await client.post(
        "/api/v1/calendar/events",
        json={
            "type": "custom",
            "title": "Should fail",
            "start_at": "2027-01-01T20:00:00Z",
            "intimacy": {"rating": 3},
        },
        headers=auth_headers(alice),
    )
    assert r.status_code == 422


async def test_intimacy_log_rejected_for_ineligible_type(client, paired):
    alice, _bob = paired
    r = await client.post(
        "/api/v1/calendar/events",
        json={
            "type": "birthday",
            "title": "Should fail",
            "start_at": "2020-01-01T20:00:00Z",
            "intimacy": {"rating": 3},
        },
        headers=auth_headers(alice),
    )
    assert r.status_code == 422


async def test_intimacy_log_rejects_unknown_initiator(client, paired):
    alice, _bob = paired
    r = await client.post(
        "/api/v1/calendar/events",
        json={
            "type": "custom",
            "title": "Should fail",
            "start_at": "2020-01-01T20:00:00Z",
            "intimacy": {"initiated_by": "00000000-0000-0000-0000-000000000000"},
        },
        headers=auth_headers(alice),
    )
    assert r.status_code == 422


async def test_intimacy_log_rejects_unknown_position(client, paired):
    alice, _bob = paired
    r = await client.post(
        "/api/v1/calendar/events",
        json={
            "type": "custom",
            "title": "Should fail",
            "start_at": "2020-01-01T20:00:00Z",
            "intimacy": {"positions": ["Not A Real Position"]},
        },
        headers=auth_headers(alice),
    )
    assert r.status_code == 422


async def test_cancelled_allowed_for_planned_date_drive_trip_and_custom(client, paired):
    alice, _bob = paired

    for event_type in ("planned_date", "planned_drive", "planned_trip", "custom"):
        r = await client.post(
            "/api/v1/calendar/events",
            json={
                "type": event_type,
                "title": "Cancel me",
                "start_at": "2026-09-01T18:00:00Z",
                "cancelled": True,
            },
            headers=auth_headers(alice),
        )
        assert r.status_code == 201, event_type
        assert r.json()["cancelled"] is True


async def test_cancelled_rejected_for_ineligible_type(client, paired):
    alice, _bob = paired
    r = await client.post(
        "/api/v1/calendar/events",
        json={
            "type": "birthday",
            "title": "Should fail",
            "start_at": "2026-09-01T18:00:00Z",
            "cancelled": True,
        },
        headers=auth_headers(alice),
    )
    assert r.status_code == 422


async def test_cancelled_toggleable_via_update(client, paired):
    alice, bob = paired
    r = await client.post(
        "/api/v1/calendar/events",
        json={"type": "planned_date", "title": "Movie night", "start_at": "2026-08-05T19:00:00Z"},
        headers=auth_headers(alice),
    )
    event_id = r.json()["id"]
    assert r.json()["cancelled"] is False

    r = await client.patch(
        f"/api/v1/calendar/events/{event_id}", json={"cancelled": True}, headers=auth_headers(bob)
    )
    assert r.status_code == 200
    assert r.json()["cancelled"] is True

    r = await client.patch(
        f"/api/v1/calendar/events/{event_id}", json={"cancelled": False}, headers=auth_headers(bob)
    )
    assert r.status_code == 200
    assert r.json()["cancelled"] is False


async def test_cancellation_reason_round_trips_when_cancelled(client, paired):
    alice, _bob = paired
    r = await client.post(
        "/api/v1/calendar/events",
        json={
            "type": "planned_date",
            "title": "Cancel me",
            "start_at": "2026-09-01T18:00:00Z",
            "cancelled": True,
            "cancellation_reason": "Partner is sick",
        },
        headers=auth_headers(alice),
    )
    assert r.status_code == 201, r.text
    assert r.json()["cancellation_reason"] == "Partner is sick"


async def test_cancellation_reason_rejected_without_cancelled(client, paired):
    alice, _bob = paired
    r = await client.post(
        "/api/v1/calendar/events",
        json={
            "type": "planned_date",
            "title": "Should fail",
            "start_at": "2026-09-01T18:00:00Z",
            "cancellation_reason": "Partner is sick",
        },
        headers=auth_headers(alice),
    )
    assert r.status_code == 422


async def test_cancellation_reason_cleared_when_uncancelled_via_update(client, paired):
    alice, bob = paired
    r = await client.post(
        "/api/v1/calendar/events",
        json={
            "type": "custom",
            "title": "Cancel me",
            "start_at": "2026-09-01T18:00:00Z",
            "cancelled": True,
            "cancellation_reason": "Weather",
        },
        headers=auth_headers(alice),
    )
    event_id = r.json()["id"]

    r = await client.patch(
        f"/api/v1/calendar/events/{event_id}",
        json={"cancelled": False, "cancellation_reason": None},
        headers=auth_headers(bob),
    )
    assert r.status_code == 200
    assert r.json()["cancelled"] is False
    assert r.json()["cancellation_reason"] is None


async def test_cancelled_rejected_for_ineligible_type_on_update(client, paired):
    alice, _bob = paired
    r = await client.post(
        "/api/v1/calendar/events",
        json={"type": "vacation", "title": "Trip", "start_at": "2026-09-10T00:00:00Z"},
        headers=auth_headers(alice),
    )
    event_id = r.json()["id"]

    r = await client.patch(
        f"/api/v1/calendar/events/{event_id}",
        json={"cancelled": True},
        headers=auth_headers(alice),
    )
    assert r.status_code == 422


async def test_intimacy_log_addable_via_update(client, paired):
    alice, bob = paired
    r = await client.post(
        "/api/v1/calendar/events",
        json={"type": "unplanned_date", "title": "Impromptu dinner", "start_at": "2020-01-01T20:00:00Z"},
        headers=auth_headers(alice),
    )
    event_id = r.json()["id"]
    assert r.json()["intimacy"] is None

    r = await client.patch(
        f"/api/v1/calendar/events/{event_id}",
        json={"intimacy": {"rating": 4, "initiated_by": bob["id"]}},
        headers=auth_headers(bob),
    )
    assert r.status_code == 200
    assert r.json()["intimacy"]["rating"] == 4
    assert r.json()["intimacy"]["initiated_by"] == bob["id"]
