"""Shared pytest fixtures.

Tests run against a REAL Postgres instance (see README.md "Running tests")
— there is no sqlite fallback, since the schema uses Postgres-specific
features (arrays, JSONB, generated tsvector columns, native enums) that
sqlite can't represent. `docker compose up -d db` before running pytest.

WARNING: the `_prepare_schema` fixture drops and recreates every table in
whatever database POSTGRES_DB points at, once per test session. Never run
this suite against a database that holds real data.

Scope: these fixtures exercise the REST API through FastAPI's dependency
override mechanism (each test gets its own DB transaction, rolled back via
a SAVEPOINT at teardown). Code paths that open their own session directly
(app.services.presence_service, app.integrations.fcm, app.ws.router's
message.read handler) use a separate connection and are intentionally out
of scope here — they're exercised manually per the verification notes in
each feature's commit message instead.
"""

import os
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-do-not-use-in-prod-aaaaaaaaaaaaaaaa")
os.environ.setdefault("SERVER_SETUP_TOKEN", "test-setup-token")
os.environ.setdefault("ENABLE_DOCS", "false")

import app.core.deps as deps_module  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.rate_limit import login_rate_limiter, register_rate_limiter  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402

TEST_PASSWORD = "correct horse battery staple"


@pytest.fixture(autouse=True)
def _reset_rate_limiters() -> None:
    # login/register rate limiters are process-local singletons keyed by
    # client IP (app/core/rate_limit.py) — every test shares the same IP
    # under ASGITransport, so without a reset the whole session drains one
    # shared bucket instead of each test getting a clean slate.
    login_rate_limiter.reset()
    register_rate_limiter.reset()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _prepare_schema() -> AsyncGenerator[None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession]:
    """One connection + outer transaction per test; the app's services
    commit freely (each commit becomes a SAVEPOINT release, not a real
    commit) and everything is rolled back at teardown."""
    connection = await engine.connect()
    outer_txn = await connection.begin()
    session = AsyncSession(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)

    async def override_get_db() -> AsyncGenerator[AsyncSession]:
        yield session

    app.dependency_overrides[deps_module.get_db] = override_get_db
    try:
        yield session
    finally:
        app.dependency_overrides.pop(deps_module.get_db, None)
        await session.close()
        await outer_txn.rollback()
        await connection.close()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def auth_headers(user: dict) -> dict:
    return {"Authorization": f"Bearer {user['access_token']}"}


async def register_and_login(
    client: AsyncClient,
    username: str,
    display_name: str,
    first_name: str = "Test",
    last_name: str = "User",
    birthday_date: str = "1990-01-01",
) -> dict:
    settings = get_settings()
    r = await client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "password": TEST_PASSWORD,
            "display_name": display_name,
            "first_name": first_name,
            "last_name": last_name,
            "birthday_date": birthday_date,
            "setup_token": settings.server_setup_token,
        },
    )
    assert r.status_code == 201, r.text
    user = r.json()

    r = await client.post("/api/v1/auth/login", json={"username": username, "password": TEST_PASSWORD})
    assert r.status_code == 200, r.text
    tokens = r.json()

    return {**user, **tokens}


@pytest_asyncio.fixture
async def alice(client: AsyncClient) -> dict:
    return await register_and_login(client, f"alice-{uuid.uuid4().hex[:8]}", "Alice")


@pytest_asyncio.fixture
async def bob(client: AsyncClient) -> dict:
    return await register_and_login(client, f"bob-{uuid.uuid4().hex[:8]}", "Bob")


@pytest_asyncio.fixture
async def paired(client: AsyncClient, alice: dict, bob: dict) -> tuple[dict, dict]:
    r = await client.post("/api/v1/pairing/code", headers=auth_headers(alice))
    assert r.status_code == 200, r.text
    code = r.json()["code"]

    r = await client.post("/api/v1/pairing/pair", json={"code": code}, headers=auth_headers(bob))
    assert r.status_code == 200, r.text

    return alice, bob
