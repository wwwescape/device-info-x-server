async def test_liveness(client):
    r = await client.get("/api/v1/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_readiness_reaches_the_database(client):
    r = await client.get("/api/v1/health/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
