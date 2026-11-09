"""GET /health reports DB, risk model (index-only mode without artifacts), AI mode, profiles."""


async def test_health_ok(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["risk_model_loaded"] is False  # no artifacts in tests -> index-only mode
    assert body["ai_mode"] == "mock"
    assert body["profiles_loaded"] == 5
    assert response.headers["x-request-id"]
