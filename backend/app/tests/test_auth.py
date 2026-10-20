from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import create_token


def _register_session_user(client: TestClient, username: str) -> dict:
    response = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": "Content123",
            "display_name": "会话回归用户",
            "email": f"{username}@example.com",
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


def _assert_tokens_revoked(client: TestClient, tokens: dict) -> None:
    profile = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    refresh = client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert profile.status_code == refresh.status_code == 401
    assert profile.json()["code"] == refresh.json()["code"] == 40104


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


def test_logout_revokes_access_and_refresh_across_sessions(client: TestClient, login_as) -> None:
    first = _register_session_user(client, "logout_sessions")
    second = login_as("logout_sessions", "Content123")
    response = client.post(
        "/api/auth/logout", headers={"Authorization": f"Bearer {second['access_token']}"}
    )
    assert response.status_code == 200
    assert "全部登录会话已撤销" in response.json()["message"]
    _assert_tokens_revoked(client, first)
    _assert_tokens_revoked(client, second)

    new_session = login_as("logout_sessions", "Content123")
    assert (
        client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {new_session['access_token']}"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/auth/refresh", json={"refresh_token": new_session["refresh_token"]}
        ).status_code
        == 200
    )


def test_password_change_revokes_old_tokens_and_requires_new_password(
    client: TestClient, login_as
) -> None:
    original = _register_session_user(client, "password_sessions")
    renewed = client.post(
        "/api/auth/refresh", json={"refresh_token": original["refresh_token"]}
    ).json()["data"]
    response = client.put(
        "/api/auth/password",
        headers={"Authorization": f"Bearer {renewed['access_token']}"},
        json={"current_password": "Content123", "new_password": "Changed456"},
    )
    assert response.status_code == 200
    _assert_tokens_revoked(client, original)
    _assert_tokens_revoked(client, renewed)
    assert (
        client.post(
            "/api/auth/login", json={"username": "password_sessions", "password": "Content123"}
        ).status_code
        == 401
    )
    new_session = login_as("password_sessions", "Changed456")
    assert (
        client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {new_session['access_token']}"}
        ).status_code
        == 200
    )


def test_incorrect_password_change_does_not_revoke_session(client: TestClient) -> None:
    tokens = _register_session_user(client, "invalid_password_session")
    response = client.put(
        "/api/auth/password",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        json={"current_password": "Incorrect123", "new_password": "Changed456"},
    )
    assert response.status_code == 400
    assert (
        client.post(
            "/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        ).status_code
        == 200
    )


def test_expired_access_can_be_renewed_with_valid_refresh(client: TestClient) -> None:
    from datetime import timedelta

    tokens = _register_session_user(client, "expired_access_session")
    expired = create_token(str(tokens["user"]["id"]), "access", timedelta(seconds=-1))
    assert (
        client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code
        == 401
    )
    renewed = client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert renewed.status_code == 200
    assert (
        client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {renewed.json()['data']['access_token']}"},
        ).status_code
        == 200
    )


def test_malformed_subject_and_legacy_tokens_are_rejected(client: TestClient) -> None:
    from datetime import UTC, datetime, timedelta

    import jwt

    payload = {
        "sub": "not-an-id",
        "type": "refresh",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(minutes=5),
        "ver": 0,
    }
    malformed = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    response = client.post("/api/auth/refresh", json={"refresh_token": malformed})
    assert response.status_code == 401
    assert response.json()["code"] == 40101

    del payload["ver"]
    payload["sub"] = "1"
    legacy = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    assert client.post("/api/auth/refresh", json={"refresh_token": legacy}).status_code == 401


def test_token_version_migration_preserves_users_credentials_and_roles() -> None:
    import importlib.util
    from pathlib import Path

    from sqlalchemy import MetaData, create_engine, inspect, select

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from app.db.base import Base

    engine = create_engine("sqlite://")
    old = MetaData()
    for table in Base.metadata.sorted_tables:
        table.to_metadata(old)
    users = old.tables["sys_user"]
    users._columns.remove(users.c.token_version)
    old.create_all(engine)
    account = {
        "id": 41,
        "username": "migration_user",
        "password_hash": "unchanged-hashed-password",
        "display_name": "迁移保留用户",
        "email": "migration@example.com",
        "status": "ACTIVE",
    }
    with engine.begin() as connection:
        connection.execute(users.insert().values(**account))
        connection.execute(
            old.tables["sys_role"].insert().values(id=7, code="OPERATOR", name="运营")
        )
        connection.execute(old.tables["sys_user_role"].insert().values(user_id=41, role_id=7))

    path = Path(__file__).resolve().parents[2] / "alembic/versions/20261011_0016_auth_sessions.py"
    spec = importlib.util.spec_from_file_location("auth_sessions_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        current = MetaData()
        current.reflect(connection)
        migrated_users = current.tables["sys_user"]
        migrated = connection.execute(select(migrated_users)).mappings().one()
        assert all(migrated[key] == value for key, value in account.items())
        assert migrated["token_version"] == 0
        assert connection.execute(select(current.tables["sys_user_role"])).one() == (41, 7)

        connection.execute(
            migrated_users.insert().values(
                username="after_migration",
                password_hash="new-hashed-password",
                display_name="迁移后注册",
                status="ACTIVE",
            )
        )
        assert (
            connection.execute(
                select(migrated_users.c.token_version).where(
                    migrated_users.c.username == "after_migration"
                )
            ).scalar_one()
            == 0
        )
        migration.downgrade()
        assert "token_version" not in {
            column["name"] for column in inspect(connection).get_columns("sys_user")
        }
        remaining = connection.execute(select(users)).mappings().all()
        assert len(remaining) == 2
        assert remaining[0]["password_hash"] == account["password_hash"]
        assert connection.execute(select(old.tables["sys_user_role"])).one() == (41, 7)
    engine.dispose()
