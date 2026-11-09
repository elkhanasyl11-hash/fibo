"""Every error uses one JSON shape: {"error": {code, message, details, request_id}}."""


def assert_error_shape(response, status: int, code: str) -> dict:
    assert response.status_code == status
    error = response.json()["error"]
    assert set(error) == {"code", "message", "details", "request_id"}
    assert error["code"] == code
    assert error["request_id"] == response.headers["x-request-id"]
    return error


async def test_unknown_route_is_404(client):
    response = await client.get("/api/v1/does-not-exist")
    assert_error_shape(response, 404, "not_found")


async def test_app_error_404_keeps_message_and_details(client):
    response = await client.get("/api/v1/_test/not-found")
    error = assert_error_shape(response, 404, "not_found")
    assert error["message"] == "Machine 42 not found"
    assert error["details"] == {"machine_id": 42}


async def test_validation_error_is_422_with_fields(client):
    response = await client.get("/api/v1/_test/needs-int", params={"count": "abc"})
    error = assert_error_shape(response, 422, "validation_failed")
    assert error["details"]["fields"][0]["loc"] == ["query", "count"]


async def test_wrong_method_is_405(client):
    response = await client.post("/api/v1/health")
    assert_error_shape(response, 405, "method_not_allowed")


async def test_unexpected_error_is_generic_500(client):
    response = await client.get("/api/v1/_test/crash")
    error = assert_error_shape(response, 500, "internal_error")
    assert error["message"] == "Internal server error"
    assert "secret" not in response.text  # no internal details or traceback leak


async def test_client_request_id_is_echoed(client):
    response = await client.get("/api/v1/_test/not-found", headers={"X-Request-ID": "demo-123"})
    assert response.headers["x-request-id"] == "demo-123"
    assert response.json()["error"]["request_id"] == "demo-123"


async def test_unsafe_request_id_is_replaced(client):
    response = await client.get("/api/v1/health", headers={"X-Request-ID": "bad id\nwith newline"})
    assert response.headers["x-request-id"] != "bad id\nwith newline"
    assert len(response.headers["x-request-id"]) == 32  # uuid4 hex
