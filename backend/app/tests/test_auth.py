from fastapi.testclient import TestClient


def test_demo_account_can_login_and_read_profile(client: TestClient, login_as) -> None:
    login_data = login_as("admin", "Admin@123456")

    assert login_data["token_type"] == "bearer"
    assert login_data["refresh_token"]
    assert login_data["user"]["username"] == "admin"
    assert login_data["user"]["roles"][0]["code"] == "ADMIN"

    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {login_data['access_token']}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["display_name"] == "系统管理员"


def test_wrong_password_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "WrongPassword123"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == 40103


def test_refresh_token_issues_new_tokens(client: TestClient, login_as) -> None:
    login_data = login_as("viewer", "Viewer@123456")
    response = client.post(
        "/api/auth/refresh",
        json={"refresh_token": login_data["refresh_token"]},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["user"]["username"] == "viewer"


def test_access_token_cannot_be_used_as_refresh_token(client: TestClient, login_as) -> None:
    login_data = login_as("operator", "Operator@123456")
    response = client.post(
        "/api/auth/refresh",
        json={"refresh_token": login_data["access_token"]},
    )

    assert response.status_code == 401
    assert response.json()["code"] == 40101


def test_anonymous_user_cannot_read_profile(client: TestClient) -> None:
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["message"] == "请先登录"
