from app.repositories import user_repo
from app.services import auth_service
from tests.conftest import TEST_PASSWORD, auth_headers, register_and_login


async def test_register_and_login(client):
    user = await register_and_login(client, "alice", "Alice")
    assert user["username"] == "alice"
    assert "access_token" in user
    assert "refresh_token" in user


async def test_register_rejects_wrong_setup_token(client):
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "eve",
            "password": TEST_PASSWORD,
            "display_name": "Eve",
            "first_name": "Eve",
            "last_name": "Test",
            "birthday_date": "1990-01-01",
            "setup_token": "not-the-real-token",
        },
    )
    assert r.status_code == 401


async def test_registration_cap_of_two(client):
    await register_and_login(client, "alice", "Alice")
    await register_and_login(client, "bob", "Bob")

    from app.core.config import get_settings

    settings = get_settings()
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "username": "carol",
            "password": TEST_PASSWORD,
            "display_name": "Carol",
            "first_name": "Carol",
            "last_name": "Test",
            "birthday_date": "1990-01-01",
            "setup_token": settings.server_setup_token,
        },
    )
    assert r.status_code == 403


async def test_login_wrong_password_rejected(client):
    await register_and_login(client, "alice", "Alice")
    r = await client.post("/api/v1/auth/login", json={"username": "alice", "password": "wrong"})
    assert r.status_code == 401


async def test_me_requires_valid_token(client, alice):
    r = await client.get("/api/v1/auth/me", headers=auth_headers(alice))
    assert r.status_code == 200
    assert r.json()["id"] == alice["id"]

    r = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


async def test_refresh_token_rotates_and_old_one_dies(client, alice):
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": alice["refresh_token"]})
    assert r.status_code == 200
    new_tokens = r.json()
    assert new_tokens["refresh_token"] != alice["refresh_token"]

    # the old refresh token was rotated out and must no longer work
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": alice["refresh_token"]})
    assert r.status_code == 401

    # the new one does
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": new_tokens["refresh_token"]})
    assert r.status_code == 200


async def test_logout_revokes_refresh_token(client, alice):
    r = await client.post("/api/v1/auth/logout", json={"refresh_token": alice["refresh_token"]})
    assert r.status_code == 204

    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": alice["refresh_token"]})
    assert r.status_code == 401


async def test_verify_password_endpoint(client, alice):
    r = await client.post(
        "/api/v1/auth/verify-password", json={"password": TEST_PASSWORD}, headers=auth_headers(alice)
    )
    assert r.status_code == 204

    r = await client.post(
        "/api/v1/auth/verify-password", json={"password": "wrong"}, headers=auth_headers(alice)
    )
    assert r.status_code == 401


async def test_change_password_success_signs_in_with_new_password(client, alice):
    r = await client.post(
        "/api/v1/users/me/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": "a brand new password"},
        headers=auth_headers(alice),
    )
    assert r.status_code == 200
    assert r.json()["must_change_password"] is False

    r = await client.post("/api/v1/auth/login", json={"username": alice["username"], "password": TEST_PASSWORD})
    assert r.status_code == 401

    r = await client.post(
        "/api/v1/auth/login", json={"username": alice["username"], "password": "a brand new password"}
    )
    assert r.status_code == 200


async def test_change_password_wrong_current_rejected(client, alice):
    r = await client.post(
        "/api/v1/users/me/change-password",
        json={"current_password": "not it", "new_password": "a brand new password"},
        headers=auth_headers(alice),
    )
    assert r.status_code == 401


async def test_admin_reset_password_forces_change_and_revokes_sessions(client, db_session, alice):
    user = await user_repo.get_by_username(db_session, alice["username"])
    otp = await auth_service.admin_reset_password(db_session, user)

    # the old password no longer works
    r = await client.post("/api/v1/auth/login", json={"username": alice["username"], "password": TEST_PASSWORD})
    assert r.status_code == 401

    # every session that predates the reset is dead
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": alice["refresh_token"]})
    assert r.status_code == 401

    # the OTP logs in, and the account is flagged to force a real password next
    r = await client.post("/api/v1/auth/login", json={"username": alice["username"], "password": otp})
    assert r.status_code == 200
    tokens = r.json()

    r = await client.get("/api/v1/users/me", headers=auth_headers(tokens))
    assert r.status_code == 200
    assert r.json()["must_change_password"] is True

    # changing the password (as the app forces after an OTP login) clears the flag
    r = await client.post(
        "/api/v1/users/me/change-password",
        json={"current_password": otp, "new_password": "a brand new password"},
        headers=auth_headers(tokens),
    )
    assert r.status_code == 200
    assert r.json()["must_change_password"] is False


async def test_registration_creates_recurring_birthday_event(client):
    user = await register_and_login(
        client, "dana", "Dana", first_name="Dana", last_name="Smith", birthday_date="1995-03-14"
    )

    r = await client.get(
        "/api/v1/calendar/events",
        params={"from": "2020-01-01T00:00:00Z", "to": "2030-01-01T00:00:00Z"},
        headers=auth_headers(user),
    )
    assert r.status_code == 200
    events = r.json()
    birthday_events = [e for e in events if e["type"] == "birthday"]
    assert len(birthday_events) == 1
    assert birthday_events[0]["title"] == "Dana's Birthday"
    assert birthday_events[0]["recurrence_rule"] == "FREQ=YEARLY"
    assert birthday_events[0]["start_at"].startswith("1995-03-14")
    assert birthday_events[0]["all_day"] is True
