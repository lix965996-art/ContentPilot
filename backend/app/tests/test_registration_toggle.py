"""Registration toggle behaviour for customer deployments."""

from fastapi.testclient import TestClient

from app.core.config import settings


def _payload(suffix: str) -> dict:
    return {
        "username": f"toggle_user_{suffix}",
        "password": "Content123",
        "display_name": f"开关测试用户{suffix}",
        "email": f"toggle-{suffix}@example.com",
    }


def test_auth_options_reports_registration_enabled(client: TestClient) -> None:
    response = client.get("/api/auth/options")

    assert response.status_code == 200
    assert response.json()["data"]["allowRegistration"] is True


def test_register_rejected_when_registration_disabled(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "allow_registration", False)

    response = client.post("/api/auth/register", json=_payload("closed"))

    assert response.status_code == 403
    assert response.json()["code"] == 40303

    options = client.get("/api/auth/options")
    assert options.json()["data"]["allowRegistration"] is False


def test_register_allowed_when_registration_enabled(client: TestClient) -> None:
    response = client.post("/api/auth/register", json=_payload("open"))

    assert response.status_code == 200
    assert response.json()["data"]["user"]["roles"][0]["code"] == "OPERATOR"
