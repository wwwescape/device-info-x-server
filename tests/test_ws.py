"""WebSocket coverage is intentionally light here — see the conftest.py
module docstring for why the deeper realtime-delivery paths aren't covered
by this suite. These two tests don't touch any data (the session-scoped
schema fixture still runs, like for every test in this suite, but neither
test queries through it) — they just confirm the handshake actually
rejects unauthenticated clients before a connection is ever accepted.
"""

from fastapi.testclient import TestClient

from app.main import app


def test_ws_rejects_missing_auth_header():
    client = TestClient(app)
    try:
        with client.websocket_connect("/ws"):
            raise AssertionError("connection should have been rejected")
    except Exception as exc:
        assert type(exc).__name__ == "WebSocketDisconnect"


def test_ws_rejects_garbage_token():
    client = TestClient(app)
    try:
        with client.websocket_connect("/ws", headers={"Authorization": "Bearer garbage"}):
            raise AssertionError("connection should have been rejected")
    except Exception as exc:
        assert type(exc).__name__ == "WebSocketDisconnect"
