from datetime import datetime

import pytest
from sqlalchemy import select

from app.api.endpoints import platform_accounts as platform_accounts_endpoint
from app.core.credentials import decrypt_json, decrypt_secret, encrypt_json
from app.db.session import SessionLocal
from app.models.business import PlatformAccount
from app.publishers.base import PublishResult
from app.services import platform_account_service


def _auth(login_as, username="admin", password="Admin@123456") -> dict[str, str]:
    return {"Authorization": f"Bearer {login_as(username, password)['access_token']}"}


def _payload(**overrides) -> dict:
    return {
        "account_name": "Mastodon 测试账号",
        "auth_type": "ACCESS_TOKEN",
        "publish_mode": "REAL_API",
        "instance_url": "https://mastodon.social",
        "access_token": "test-mastodon-access-token-only",
        **overrides,
    }


@pytest.fixture(autouse=True)
def reset_mastodon_account(database):
    with SessionLocal() as db:
        account = db.scalar(select(PlatformAccount).where(PlatformAccount.platform == "MASTODON"))
        if account:
            db.delete(account)
            db.commit()
    yield
    with SessionLocal() as db:
        account = db.scalar(select(PlatformAccount).where(PlatformAccount.platform == "MASTODON"))
        if account:
            db.delete(account)
            db.commit()


def test_mastodon_configuration_encrypted_redacted_and_closed_by_default(client, login_as):
    auth = _auth(login_as)
    saved = client.put("/api/platform-accounts/MASTODON", headers=auth, json=_payload())
    assert saved.status_code == 200, saved.text
    data = saved.json()["data"]
    assert data["status"] == "CONNECTING"
    assert data["authType"] == "ACCESS_TOKEN"
    assert data["instanceUrl"] == "https://mastodon.social"
    assert data["config"]["instanceUrl"] == "https://mastodon.social"
    assert data["accessTokenConfigured"] is True
    assert data["tokenHint"] == ""
    assert data["publicPublishEnabled"] is False
    assert data["availablePublishModes"] == []
    assert "test-mastodon-access-token-only" not in saved.text
    assert "write:statuses" in str(data["connectionGuide"])
    with SessionLocal() as db:
        account = db.get(PlatformAccount, data["id"])
        assert account.access_token_encrypted != "test-mastodon-access-token-only"
        assert decrypt_secret(account.access_token_encrypted) == "test-mastodon-access-token-only"
        config = decrypt_json(account.credentials_encrypted)
        assert config["instance_url"] == "https://mastodon.social"
        assert "access_token" not in config

    operator_auth = _auth(login_as, "operator", "Operator@123456")
    rows = client.get("/api/platform-accounts", headers=operator_auth)
    public = next(row for row in rows.json()["data"] if row["platform"] == "MASTODON")
    assert public["config"] == {}
    assert public["instanceUrl"] == "https://mastodon.social"
    assert public["accessTokenConfigured"] is True
    assert "test-mastodon-access-token-only" not in rows.text
    forbidden = client.put(
        "/api/platform-accounts/MASTODON", headers=operator_auth, json=_payload()
    )
    assert forbidden.status_code == 403


def test_mastodon_only_gate_or_name_change_keeps_verified_connection(client, login_as):
    auth = _auth(login_as)
    saved = client.put("/api/platform-accounts/MASTODON", headers=auth, json=_payload())
    account_id = saved.json()["data"]["id"]
    verified_at = datetime.now()
    with SessionLocal() as db:
        account = db.get(PlatformAccount, account_id)
        config = decrypt_json(account.credentials_encrypted)
        config.update({"mastodon_account_id": "42", "mastodon_acct": "test-user"})
        account.credentials_encrypted = encrypt_json(config)
        account.status = "CONNECTED"
        account.last_test_at = verified_at
        token_before = account.access_token_encrypted
        db.commit()

    updated = client.put(
        "/api/platform-accounts/MASTODON",
        headers=auth,
        json=_payload(access_token=" ", account_name="我的服务器", allow_public_publish=True),
    )
    assert updated.status_code == 200, updated.text
    data = updated.json()["data"]
    assert data["status"] == "CONNECTED"
    assert data["loginUsername"] == "test-user"
    assert data["publicPublishEnabled"] is True
    assert data["availablePublishModes"] == ["REAL_API"]
    with SessionLocal() as db:
        account = db.get(PlatformAccount, account_id)
        assert account.access_token_encrypted == token_before
        assert account.last_test_at == verified_at


@pytest.mark.parametrize(
    "overrides",
    [
        {"access_token": "replacement-token"},
        {"instance_url": "https://mstdn.social", "access_token": "new-instance-token"},
    ],
)
def test_mastodon_credential_changes_clear_verified_identity(client, login_as, overrides):
    auth = _auth(login_as)
    saved = client.put("/api/platform-accounts/MASTODON", headers=auth, json=_payload())
    account_id = saved.json()["data"]["id"]
    with SessionLocal() as db:
        account = db.get(PlatformAccount, account_id)
        config = decrypt_json(account.credentials_encrypted)
        config.update(
            {
                "mastodon_account_id": "42",
                "mastodon_acct": "old-user",
                "mastodon_max_characters": 500,
                "mastodon_image_size_limit": 8_388_608,
                "mastodon_last_checked_at": datetime.now().isoformat(),
            }
        )
        account.credentials_encrypted = encrypt_json(config)
        account.status = "CONNECTED"
        account.last_test_at = datetime.now()
        db.commit()
    updated = client.put(
        "/api/platform-accounts/MASTODON", headers=auth, json=_payload(**overrides)
    )
    assert updated.status_code == 200, updated.text
    data = updated.json()["data"]
    assert data["status"] == "CONNECTING"
    assert data["loginUsername"] == ""
    assert data["lastTestAt"] is None
    with SessionLocal() as db:
        account = db.get(PlatformAccount, account_id)
        config = decrypt_json(account.credentials_encrypted)
        assert not any(key.startswith("mastodon_") for key in config)
        assert decrypt_secret(account.access_token_encrypted) == overrides["access_token"]


def test_mastodon_connection_check_records_identity_and_server_limits(
    client, login_as, monkeypatch
):
    auth = _auth(login_as)
    client.put("/api/platform-accounts/MASTODON", headers=auth, json=_payload())
    calls = []

    class IdentityValidator:
        async def validate_credentials(self):
            calls.append("validate")
            return PublishResult(
                True,
                "MASTODON",
                "REAL_API",
                "CONNECTED",
                external_id="42",
                detail={
                    "account_id": "42",
                    "acct": "test-user",
                    "max_characters": 500,
                    "characters_reserved_per_url": 23,
                    "max_media_attachments": 4,
                    "image_size_limit": 8_388_608,
                },
            )

    monkeypatch.setattr(
        platform_account_service, "MastodonPublisher", lambda *_: IdentityValidator()
    )
    checked = client.post("/api/platform-accounts/MASTODON/test", headers=auth)
    assert checked.status_code == 200, checked.text
    data = checked.json()["data"]
    assert data["status"] == "CONNECTED"
    assert data["loginUsername"] == "test-user"
    assert data["config"]["accountId"] == "42"
    assert data["config"]["maxCharacters"] == 500
    assert data["config"]["charactersReservedPerUrl"] == 23
    assert data["config"]["maxMediaAttachments"] == 4
    assert data["publicPublishEnabled"] is False
    assert calls == ["validate"]
    with SessionLocal() as db:
        account = db.get(PlatformAccount, data["id"])
        config = decrypt_json(account.credentials_encrypted)
        assert config["mastodon_last_checked_at"]
        assert config["mastodon_image_size_limit"] == 8_388_608


def test_mastodon_failed_connection_keeps_credentials_but_invalidates_status(
    client, login_as, monkeypatch
):
    auth = _auth(login_as)
    client.put("/api/platform-accounts/MASTODON", headers=auth, json=_payload())

    class InvalidValidator:
        async def validate_credentials(self):
            return PublishResult(
                False,
                "MASTODON",
                "REAL_API",
                "INVALID",
                error_code="UNAUTHORIZED",
                error_message="Mastodon 访问令牌无效或缺少权限",
            )

    monkeypatch.setattr(
        platform_account_service, "MastodonPublisher", lambda *_: InvalidValidator()
    )
    checked = client.post("/api/platform-accounts/MASTODON/test", headers=auth)
    assert checked.status_code == 200, checked.text
    data = checked.json()["data"]
    assert data["status"] == "INVALID"
    assert data["accessTokenConfigured"] is True
    assert "test-mastodon-access-token-only" not in checked.text


@pytest.mark.parametrize(
    "url",
    [
        "http://mastodon.social",
        "https://localhost",
        "https://127.0.0.1",
        "https://192.168.1.2",
        "https://[::1]",
        "https://user:password@mastodon.social",
        "https://mastodon.social:8443",
        "https://mastodon.social/api",
        "https://mastodon.social?query=1",
        "https://mastodon.social#fragment",
    ],
)
def test_mastodon_rejects_unsafe_instance_urls(client, login_as, url):
    saved = client.put(
        "/api/platform-accounts/MASTODON",
        headers=_auth(login_as),
        json=_payload(instance_url=url),
    )
    assert saved.status_code == 422, saved.text
    assert "test-mastodon-access-token-only" not in saved.text


def test_mastodon_requires_its_auth_method_and_matching_server_token(client, login_as):
    auth = _auth(login_as)
    missing_token = client.put(
        "/api/platform-accounts/MASTODON", headers=auth, json=_payload(access_token=None)
    )
    assert missing_token.status_code == 400
    assert missing_token.json()["code"] == 40063
    wrong_method = client.put(
        "/api/platform-accounts/MASTODON",
        headers=auth,
        json=_payload(auth_type="APP_SECRET", client_id="unrelated-client"),
    )
    assert wrong_method.status_code == 400
    other_platform = client.put("/api/platform-accounts/WEIBO", headers=auth, json=_payload())
    assert other_platform.status_code == 400
    pasted_refresh = client.put(
        "/api/platform-accounts/MASTODON",
        headers=auth,
        json=_payload(refresh_token="unsupported-refresh-token"),
    )
    assert pasted_refresh.status_code == 400
    client.put("/api/platform-accounts/MASTODON", headers=auth, json=_payload())
    changed_server = client.put(
        "/api/platform-accounts/MASTODON",
        headers=auth,
        json=_payload(instance_url="https://mstdn.social", access_token=""),
    )
    assert changed_server.status_code == 400
    assert changed_server.json()["code"] == 40063


def test_mastodon_disconnect_only_deletes_config_after_success(client, login_as, monkeypatch):
    auth = _auth(login_as)
    saved = client.put("/api/platform-accounts/MASTODON", headers=auth, json=_payload())
    account_id = saved.json()["data"]["id"]

    async def failed_disconnect(_publisher):
        return PublishResult(
            False,
            "MASTODON",
            "REAL_API",
            "FAILED",
            error_code="NETWORK_ERROR",
            error_message="Mastodon 断开连接失败，请稍后重试",
        )

    monkeypatch.setattr(
        platform_accounts_endpoint.MastodonPublisher, "disconnect", failed_disconnect
    )
    refused = client.delete("/api/platform-accounts/MASTODON", headers=auth)
    assert refused.status_code == 502, refused.text
    with SessionLocal() as db:
        account = db.get(PlatformAccount, account_id)
        assert decrypt_secret(account.access_token_encrypted) == "test-mastodon-access-token-only"

    async def successful_disconnect(_publisher):
        return PublishResult(True, "MASTODON", "REAL_API", "DISCONNECTED")

    monkeypatch.setattr(
        platform_accounts_endpoint.MastodonPublisher, "disconnect", successful_disconnect
    )
    removed = client.delete("/api/platform-accounts/MASTODON", headers=auth)
    assert removed.status_code == 200, removed.text
    assert removed.json()["data"]["id"] is None
    assert removed.json()["data"]["accessTokenConfigured"] is False
    with SessionLocal() as db:
        assert db.get(PlatformAccount, account_id) is None
