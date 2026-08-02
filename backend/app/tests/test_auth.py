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


def test_user_can_register_and_is_logged_in_as_operator(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register",
        json={
            "username": "new_operator",
            "password": "Content123",
            "display_name": "新注册运营者",
            "email": "new-operator@example.com",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["access_token"]
    assert data["user"]["username"] == "new_operator"
    assert data["user"]["display_name"] == "新注册运营者"
    assert data["user"]["roles"][0]["code"] == "OPERATOR"
    profile = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {data['access_token']}"},
    )
    assert profile.status_code == 200
    assert profile.json()["data"]["username"] == "new_operator"


def test_registration_rejects_duplicate_username_and_email(client: TestClient) -> None:
    payload = {
        "username": "duplicate_user",
        "password": "Content123",
        "display_name": "第一位用户",
        "email": "duplicate@example.com",
    }
    assert client.post("/api/auth/register", json=payload).status_code == 200

    duplicate_username = client.post(
        "/api/auth/register",
        json={**payload, "email": "another@example.com"},
    )
    assert duplicate_username.status_code == 409
    assert duplicate_username.json()["code"] == 40921

    duplicate_email = client.post(
        "/api/auth/register",
        json={
            **payload,
            "username": "another_user",
        },
    )
    assert duplicate_email.status_code == 409
    assert duplicate_email.json()["code"] == 40922


def test_registration_rejects_weak_password(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register",
        json={
            "username": "weak_password_user",
            "password": "onlyletters",
            "display_name": "弱密码用户",
            "email": "weak-password@example.com",
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == 40001


def test_registration_requires_email(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register",
        json={
            "username": "no_email_user",
            "password": "Content123",
            "display_name": "无邮箱用户",
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == 40001


def test_login_username_is_case_insensitive(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "ADMIN", "password": "Admin@123456"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["user"]["username"] == "admin"


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
