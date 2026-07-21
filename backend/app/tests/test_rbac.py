from fastapi.testclient import TestClient


def authorization_header(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def test_admin_can_list_users(client: TestClient, login_as) -> None:
    login_data = login_as("admin", "Admin@123456")
    response = client.get(
        "/api/admin/users",
        headers=authorization_header(login_data["access_token"]),
    )

    assert response.status_code == 200
    usernames = {user["username"] for user in response.json()["data"]}
    assert usernames == {"admin", "operator", "viewer"}


def test_operator_cannot_access_admin_endpoint(client: TestClient, login_as) -> None:
    login_data = login_as("operator", "Operator@123456")
    response = client.get(
        "/api/admin/users",
        headers=authorization_header(login_data["access_token"]),
    )

    assert response.status_code == 403
    assert response.json()["code"] == 40301


def test_all_roles_can_access_dashboard(client: TestClient, login_as) -> None:
    accounts = (
        ("admin", "Admin@123456"),
        ("operator", "Operator@123456"),
        ("viewer", "Viewer@123456"),
    )
    for username, password in accounts:
        login_data = login_as(username, password)
        response = client.get(
            "/api/dashboard/summary",
            headers=authorization_header(login_data["access_token"]),
        )
        assert response.status_code == 200
        assert response.json()["data"]["phase"] == 9
