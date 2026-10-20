from datetime import datetime, timedelta

from sqlalchemy import select

from app.api.endpoints import platform_accounts as platform_accounts_endpoint
from app.core.credentials import decrypt_json, encrypt_json, encrypt_secret
from app.db.session import SessionLocal
from app.models.business import PlatformAccount
from app.publishers.base import PublishResult
from app.services import platform_account_service


def _auth(login_as, username="admin", password="Admin@123456") -> dict[str, str]:
    return {"Authorization": f"Bearer {login_as(username, password)['access_token']}"}


def _payload(**overrides) -> dict:
    return {
        "account_name": "Bluesky 测试账号",
        "auth_type": "APP_PASSWORD",
        "publish_mode": "REAL_API",
        "identifier": "test-account.bsky.social",
        "app_password": "test-app-password-only",
        **overrides,
    }


def test_bluesky_configuration_is_encrypted_redacted_and_closed_by_default(client, login_as):
    auth = _auth(login_as)
    saved = client.put("/api/platform-accounts/BLUESKY", headers=auth, json=_payload())
    assert saved.status_code == 200, saved.text
    data = saved.json()["data"]
    assert data["status"] == "CONNECTING"
    assert data["authType"] == "APP_PASSWORD"
    assert data["appPasswordConfigured"] is True
    assert data["config"]["identifier"] == "test-account.bsky.social"
    assert data["publicPublishEnabled"] is False
    assert data["availablePublishModes"] == []
    assert "test-app-password-only" not in saved.text
    assert "应用密码" in data["publishHint"]
    assert set(data["capabilities"]) == {"TEXT_PUBLISH", "IMAGE_PUBLISH", "STATUS_READ"}

    with SessionLocal() as db:
        account = db.scalar(select(PlatformAccount).where(PlatformAccount.platform == "BLUESKY"))
        assert "test-app-password-only" not in account.credentials_encrypted
        config = decrypt_json(account.credentials_encrypted)
        assert config["app_password"] == "test-app-password-only"
        assert config["allow_public_publish"] is False
        assert account.access_token_encrypted is None

    operator_auth = _auth(login_as, "operator", "Operator@123456")
    rows = client.get("/api/platform-accounts", headers=operator_auth)
    public = next(row for row in rows.json()["data"] if row["platform"] == "BLUESKY")
    assert public["config"] == {}
    assert "test-app-password-only" not in rows.text
    forbidden = client.put("/api/platform-accounts/BLUESKY", headers=operator_auth, json=_payload())
    assert forbidden.status_code == 403


def test_bluesky_password_reuse_and_rotation_reset_session(client, login_as):
    auth = _auth(login_as)
    saved = client.put("/api/platform-accounts/BLUESKY", headers=auth, json=_payload())
    account_id = saved.json()["data"]["id"]
    with SessionLocal() as db:
        account = db.get(PlatformAccount, account_id)
        config = decrypt_json(account.credentials_encrypted)
        config.update({"bluesky_did": "did:plc:old-account", "bluesky_handle": "old.bsky.social"})
        account.credentials_encrypted = encrypt_json(config)
        account.access_token_encrypted = encrypt_secret("old-access-jwt")
        account.refresh_token_encrypted = encrypt_secret("old-refresh-jwt")
        account.token_expires_at = datetime.now() + timedelta(minutes=5)
        db.commit()

    updated = client.put(
        "/api/platform-accounts/BLUESKY",
        headers=auth,
        json=_payload(app_password="", allow_public_publish=True),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["appPasswordConfigured"] is True
    assert updated.json()["data"]["publicPublishEnabled"] is True
    assert updated.json()["data"]["availablePublishModes"] == ["REAL_API"]
    with SessionLocal() as db:
        account = db.get(PlatformAccount, account_id)
        assert account.access_token_encrypted is not None
        assert account.refresh_token_encrypted is not None
        assert (
            decrypt_json(account.credentials_encrypted)["app_password"] == "test-app-password-only"
        )

    rotated = client.put(
        "/api/platform-accounts/BLUESKY",
        headers=auth,
        json=_payload(app_password="replacement-password"),
    )
    assert rotated.status_code == 200, rotated.text
    assert rotated.json()["data"]["status"] == "CONNECTING"
    assert "replacement-password" not in rotated.text
    with SessionLocal() as db:
        account = db.get(PlatformAccount, account_id)
        config = decrypt_json(account.credentials_encrypted)
        assert config["app_password"] == "replacement-password"
        assert "bluesky_did" not in config
        assert "bluesky_handle" not in config
        assert account.access_token_encrypted is None
        assert account.refresh_token_encrypted is None
        assert account.token_expires_at is None


def test_bluesky_connection_check_records_identity_without_enabling_publish(
    client, login_as, monkeypatch
):
    auth = _auth(login_as)
    client.put("/api/platform-accounts/BLUESKY", headers=auth, json=_payload())
    calls = []

    class IdentityValidator:
        async def validate_credentials(self):
            calls.append("validate")
            return PublishResult(
                True,
                "BLUESKY",
                "REAL_API",
                "CONNECTED",
                external_id="did:plc:validated-account",
                detail={"handle": "test-account.bsky.social", "did": "did:plc:validated-account"},
            )

    monkeypatch.setattr(
        platform_account_service, "BlueskyPublisher", lambda *_: IdentityValidator()
    )
    checked = client.post("/api/platform-accounts/BLUESKY/test", headers=auth)
    assert checked.status_code == 200, checked.text
    data = checked.json()["data"]
    assert data["status"] == "CONNECTED"
    assert data["loginUsername"] == "test-account.bsky.social"
    assert data["publicPublishEnabled"] is False
    assert data["availablePublishModes"] == []
    assert calls == ["validate"]
    with SessionLocal() as db:
        account = db.get(PlatformAccount, data["id"])
        config = decrypt_json(account.credentials_encrypted)
        assert config["bluesky_did"] == "did:plc:validated-account"
        assert config["bluesky_last_checked_at"]


def test_bluesky_requires_its_own_auth_method_and_first_password(client, login_as):
    auth = _auth(login_as)
    client.delete("/api/platform-accounts/BLUESKY", headers=auth)
    no_password = client.put(
        "/api/platform-accounts/BLUESKY", headers=auth, json=_payload(app_password=None)
    )
    assert no_password.status_code == 400
    assert no_password.json()["code"] == 40063
    no_identifier = client.put(
        "/api/platform-accounts/BLUESKY", headers=auth, json=_payload(identifier=None)
    )
    assert no_identifier.status_code == 422
    wrong_method = client.put(
        "/api/platform-accounts/BLUESKY",
        headers=auth,
        json=_payload(auth_type="APP_SECRET", client_id="unrelated-client"),
    )
    assert wrong_method.status_code == 400
    pasted_token = client.put(
        "/api/platform-accounts/BLUESKY",
        headers=auth,
        json=_payload(access_token="untrusted-pasted-token"),
    )
    assert pasted_token.status_code == 400
    other_platform = client.put("/api/platform-accounts/WEIBO", headers=auth, json=_payload())
    assert other_platform.status_code == 400


def test_bluesky_expired_session_can_refresh_but_missing_refresh_is_expired():
    account = PlatformAccount(
        platform="BLUESKY",
        status="CONNECTED",
        token_expires_at=datetime.now() - timedelta(seconds=5),
        refresh_token_encrypted="encrypted-refresh-token",
    )
    assert platform_account_service.effective_status(account) == "CONNECTED"
    account.refresh_token_encrypted = None
    assert platform_account_service.effective_status(account) == "TOKEN_EXPIRED"


def test_bluesky_delete_revokes_remote_session_before_removing_credentials(
    client, login_as, monkeypatch
):
    auth = _auth(login_as)
    saved = client.put("/api/platform-accounts/BLUESKY", headers=auth, json=_payload())
    account_id = saved.json()["data"]["id"]
    calls = []

    async def failed_revoke(publisher):
        calls.append(publisher.account.id)
        return PublishResult(
            False,
            "BLUESKY",
            "REAL_API",
            "FAILED",
            error_code="NETWORK_ERROR",
            error_message="Bluesky 会话撤销失败，请稍后重试",
        )

    monkeypatch.setattr(platform_accounts_endpoint.BlueskyPublisher, "disconnect", failed_revoke)
    refused = client.delete("/api/platform-accounts/BLUESKY", headers=auth)
    assert refused.status_code == 502, refused.text
    assert refused.json()["code"] == 50218
    assert calls == [account_id]
    with SessionLocal() as db:
        account = db.get(PlatformAccount, account_id)
        assert account is not None
        assert (
            decrypt_json(account.credentials_encrypted)["app_password"] == "test-app-password-only"
        )

    async def successful_revoke(publisher):
        calls.append(publisher.account.id)
        return PublishResult(True, "BLUESKY", "REAL_API", "DISCONNECTED")

    monkeypatch.setattr(
        platform_accounts_endpoint.BlueskyPublisher, "disconnect", successful_revoke
    )
    removed = client.delete("/api/platform-accounts/BLUESKY", headers=auth)
    assert removed.status_code == 200, removed.text
    assert removed.json()["data"]["id"] is None
    assert removed.json()["data"]["appPasswordConfigured"] is False
    assert calls == [account_id, account_id]
    with SessionLocal() as db:
        assert db.get(PlatformAccount, account_id) is None
