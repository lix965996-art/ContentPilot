from fastapi.testclient import TestClient


def test_health_uses_unified_response(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "healthy"
    assert body["data"]["database"] == "connected"
    assert body["traceId"]
    assert response.headers["X-Trace-Id"] == body["traceId"]


def test_validation_error_uses_unified_response(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={"username": "a", "password": "x"})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == 40001
    assert body["data"]
    assert body["traceId"]
