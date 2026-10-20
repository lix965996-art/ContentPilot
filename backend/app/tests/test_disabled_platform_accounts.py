import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest
from sqlalchemy import select

from app.api.endpoints import platform_accounts as endpoints
from app.core.config import settings
from app.core.credentials import decrypt_json, encrypt_json, encrypt_secret
from app.core.exceptions import AppException
from app.db.session import SessionLocal
from app.models.business import PlatformAccount
from app.models.user import User
from app.schemas.platform_account import PlatformAccountUpsert
from app.services import platform_account_service as accounts


class MemorySession:
    def add(self, _row):
        pass

    def flush(self):
        pass


def _account(platform, *, auth_type="OAUTH2", publish_mode="REAL_API"):
    return PlatformAccount(
        id=100,
        user_id=1,
        platform=platform,
        account_name="account-toggle-test",
        auth_type=auth_type,
        publish_mode=publish_mode,
        status="CONNECTED",
        credentials_encrypted=encrypt_json(
            {
                "app_secret": "test-secret",
                "identifier": "test.bsky.social",
                "app_password": "test-app-password",
                "instance_url": "https://mastodon.social",
                "x_oauth_pending": {"nonce": "old-pending-authorization"},
            }
        ),
    )


@pytest.mark.parametrize("platform", accounts.PLATFORMS)
def test_save_disabled_and_explicitly_reenable_account(platform, monkeypatch):
    monkeypatch.setattr(settings, "experimental_browser_publishing_enabled", True)
    monkeypatch.setattr(settings, "toutiao_browser_publishing_enabled", True)
    monkeypatch.setattr(settings, "wechat_browser_publishing_enabled", True)
    auth_type = {
        "BLUESKY": "APP_PASSWORD",
        "MASTODON": "ACCESS_TOKEN",
        "WECHAT_OFFICIAL": "APP_SECRET",
        "XIAOHONGSHU": "QR_LOGIN",
        "TOUTIAO": "QR_LOGIN",
    }.get(platform, "OAUTH2")
    publish_mode = {"XIAOHONGSHU": "MCP_PUBLISH", "TOUTIAO": "BROWSER_PUBLISH"}.get(
        platform, "REAL_API"
    )
    account = _account(platform, auth_type=auth_type, publish_mode=publish_mode)
    monkeypatch.setattr(accounts, "get_platform_account", lambda *_: account)
    payload = PlatformAccountUpsert(
        account_name="account-toggle-test",
        auth_type=auth_type,
        publish_mode=publish_mode,
        app_id="test-app-id",
        identifier="test.bsky.social" if platform == "BLUESKY" else None,
        instance_url="https://mastodon.social" if platform == "MASTODON" else None,
        access_token="test-access-token" if platform == "MASTODON" else None,
        enabled=False,
    )
    user = SimpleNamespace(id=1)
    accounts.upsert_account(MemorySession(), user, platform, payload)
    assert account.status == accounts.effective_status(account) == "DISABLED"
    assert "x_oauth_pending" not in decrypt_json(account.credentials_encrypted)

    payload.enabled = True
    accounts.upsert_account(MemorySession(), user, platform, payload)
    assert account.status == (
        "LOGIN_REQUIRED" if platform in {"TOUTIAO", "XIAOHONGSHU"} else "CONNECTING"
    )


@pytest.mark.parametrize(
    ("platform", "auth_type", "publish_mode"),
    [
        ("WEIBO", "OAUTH2", "REAL_API"),
        ("X", "OAUTH2", "REAL_API"),
        ("BLUESKY", "APP_PASSWORD", "REAL_API"),
        ("MASTODON", "ACCESS_TOKEN", "REAL_API"),
        ("WECHAT_OFFICIAL", "APP_SECRET", "DRAFT_ONLY"),
        ("WECHAT_OFFICIAL", "QR_LOGIN", "BROWSER_DRAFT"),
        ("TOUTIAO", "QR_LOGIN", "BROWSER_PUBLISH"),
        ("XIAOHONGSHU", "QR_LOGIN", "MCP_PUBLISH"),
        ("XIAOHONGSHU", "NONE", "MANUAL_CONFIRM"),
    ],
)
def test_disabled_connection_test_does_not_validate_or_change_state(
    platform, auth_type, publish_mode, monkeypatch
):
    def forbidden(*_args, **_kwargs):
        pytest.fail("a disabled account must not contact a platform")

    for name in (
        "account_validator",
        "wechat_check_login",
        "toutiao_check_login",
        "mcp_check_login",
    ):
        monkeypatch.setattr(accounts, name, forbidden)
    account = _account(platform, auth_type=auth_type, publish_mode=publish_mode)
    account.status = "DISABLED"
    with pytest.raises(AppException) as exc:
        asyncio.run(accounts.test_account(MemorySession(), account))
    assert exc.value.code == 40087
    assert account.status == accounts.effective_status(account) == "DISABLED"
    assert account.last_test_at is None


@pytest.mark.parametrize(
    "clear_session",
    [
        accounts.clear_xhs_session_metadata,
        accounts.clear_toutiao_session_metadata,
        accounts.clear_wechat_session_metadata,
    ],
)
def test_logout_cleanup_does_not_reenable_disabled_account(clear_session):
    account = _account("WECHAT_OFFICIAL", auth_type="QR_LOGIN", publish_mode="BROWSER_DRAFT")
    account.status = "DISABLED"
    clear_session(account)
    assert account.status == accounts.effective_status(account) == "DISABLED"


def test_recording_wechat_session_does_not_reenable_disabled_account():
    account = _account("WECHAT_OFFICIAL", auth_type="QR_LOGIN", publish_mode="BROWSER_DRAFT")
    account.status = "DISABLED"
    accounts.record_wechat_session(account, "test-user", datetime.now())
    assert account.status == "DISABLED"


@pytest.fixture
def disabled_account(database):
    restored = []

    def create(platform):
        with SessionLocal() as db:
            account = accounts.get_platform_account(db, platform)
            original = (
                {column.name: getattr(account, column.name) for column in account.__table__.columns}
                if account
                else None
            )
            if account is None:
                actor = db.scalar(select(User).where(User.username == "admin"))
                account = PlatformAccount(
                    user_id=actor.id, platform=platform, account_name="account-toggle-test"
                )
                db.add(account)
            account.status = "DISABLED"
            account.auth_type = "QR_LOGIN" if platform == "WECHAT_OFFICIAL" else "OAUTH2"
            account.publish_mode = "BROWSER_DRAFT" if platform == "WECHAT_OFFICIAL" else "REAL_API"
            account.client_id = "test-client-id"
            account.credentials_encrypted = encrypt_json({"app_secret": "test-app-secret"})
            account.access_token_encrypted = encrypt_secret("test-access-token")
            db.commit()
            restored.append((account.id, original))
            return account.id

    yield create
    with SessionLocal() as db:
        for account_id, original in restored:
            account = db.get(PlatformAccount, account_id)
            if original is None:
                db.delete(account)
            else:
                for key, value in original.items():
                    setattr(account, key, value)
        db.commit()


@pytest.mark.parametrize(
    ("platform", "endpoint"),
    [
        ("XIAOHONGSHU", "login-qrcode"),
        ("TOUTIAO", "login-qrcode?refresh=true"),
        ("WECHAT_OFFICIAL", "login-qrcode?refresh=true"),
        ("WEIBO", "oauth/start"),
        ("X", "oauth/start"),
    ],
)
def test_disabled_qr_and_oauth_start_do_not_contact_platform(
    client, login_as, disabled_account, monkeypatch, platform, endpoint
):
    def forbidden(*_args, **_kwargs):
        pytest.fail("disabled account must not start login or authorization")

    for name in ("mcp_get_qrcode", "get_login_qrcode", "get_wechat_login_qrcode"):
        monkeypatch.setattr(endpoints, name, forbidden)
    monkeypatch.setattr(settings, "experimental_browser_publishing_enabled", True)
    monkeypatch.setattr(settings, "toutiao_browser_publishing_enabled", True)
    monkeypatch.setattr(settings, "wechat_browser_publishing_enabled", True)
    account_id = disabled_account(platform)
    auth = {"Authorization": f"Bearer {login_as('admin', 'Admin@123456')['access_token']}"}
    response = client.post(
        f"/api/platform-accounts/{platform}/{endpoint}",
        headers=auth,
        json={"redirect_uri": "http://127.0.0.1:8000/api/callback"},
    )
    assert response.status_code == 400, response.text
    assert response.json()["code"] == 40087
    with SessionLocal() as db:
        assert db.get(PlatformAccount, account_id).status == "DISABLED"


@pytest.mark.parametrize("platform", ["WEIBO", "X"])
def test_disabled_oauth_callback_does_not_exchange_tokens(
    client, disabled_account, monkeypatch, platform
):
    def forbidden(*_args, **_kwargs):
        pytest.fail("disabled account must not exchange OAuth tokens")

    monkeypatch.setattr(endpoints, "exchange_x_authorization_code", forbidden)
    monkeypatch.setattr(endpoints.httpx, "AsyncClient", forbidden)
    account_id = disabled_account(platform)
    with SessionLocal() as db:
        actor = db.scalar(select(User).where(User.username == "admin"))
        actor_id = actor.id
    state = jwt.encode(
        {
            "sub": str(actor_id),
            "account_id": account_id,
            "type": "weibo_oauth_state" if platform == "WEIBO" else "x_oauth_state",
            "redirect_uri": "http://127.0.0.1:8000/api/callback",
            "exp": datetime.now(UTC) + timedelta(minutes=10),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    response = client.get(
        f"/api/platform-accounts/{platform}/oauth/callback",
        params={"code": "fake-authorization-code", "state": state},
        follow_redirects=False,
    )
    assert response.status_code == 400, response.text
    assert response.json()["code"] == 40087
    with SessionLocal() as db:
        assert db.get(PlatformAccount, account_id).status == "DISABLED"
