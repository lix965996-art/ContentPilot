from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import select

from app.api.endpoints import platform_accounts as platform_accounts_endpoint
from app.core.config import settings
from app.core.credentials import decrypt_json, decrypt_secret, encrypt_secret
from app.db.session import SessionLocal
from app.models.business import ContentVariant, PlatformAccount
from app.publishers.base import PublishResult
from app.publishers.x_official import XPublisher


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin_auth(login_as) -> dict[str, str]:
    return _headers(login_as("admin", "Admin@123456")["access_token"])


def _operator_auth(login_as) -> dict[str, str]:
    return _headers(login_as("operator", "Operator@123456")["access_token"])


def _save_x_account(client, auth: dict[str, str], *, allow_public_publish: bool = False) -> dict:
    response = client.put(
        "/api/platform-accounts/X",
        headers=auth,
        json={
            "account_name": "ContentPilot X",
            "auth_type": "OAUTH2",
            "publish_mode": "REAL_API",
            "client_id": "x-client-id",
            "app_secret": "x-client-secret",
            "allow_public_publish": allow_public_publish,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_x_shared_account_is_admin_managed_and_operator_redacted(client, login_as) -> None:
    admin_auth = _admin_auth(login_as)
    operator_auth = _operator_auth(login_as)
    saved = _save_x_account(client, admin_auth)

    operator_rows = client.get("/api/platform-accounts", headers=operator_auth)
    assert operator_rows.status_code == 200
    x_account = next(row for row in operator_rows.json()["data"] if row["platform"] == "X")
    assert x_account["id"] == saved["id"]
    assert x_account["shared"] is True
    assert x_account["clientId"] == ""
    assert x_account["tokenHint"] == ""
    assert x_account["config"] == {}
    assert x_account["capabilities"] == ["TEXT_PUBLISH", "STATUS_READ"]
    assert x_account["publicPublishEnabled"] is False
    assert x_account["availablePublishModes"] == []

    forbidden = client.put(
        "/api/platform-accounts/X",
        headers=operator_auth,
        json={
            "account_name": "forbidden",
            "auth_type": "OAUTH2",
            "publish_mode": "REAL_API",
            "client_id": "forbidden",
            "app_secret": "forbidden",
        },
    )
    assert forbidden.status_code == 403


def test_x_oauth_pkce_callback_is_one_time_and_stores_encrypted_tokens(
    client, login_as, monkeypatch
) -> None:
    admin_auth = _admin_auth(login_as)
    saved = _save_x_account(client, admin_auth)
    redirect_uri = "http://127.0.0.1:8000/api/platform-accounts/X/oauth/callback"

    started = client.post(
        "/api/platform-accounts/X/oauth/start",
        json={"redirect_uri": redirect_uri},
        headers={**admin_auth, "Origin": "http://127.0.0.1:5174"},
    )
    assert started.status_code == 200, started.text
    authorization_url = started.json()["data"]["authorizationUrl"]
    query = parse_qs(urlparse(authorization_url).query)
    assert query["code_challenge_method"] == ["S256"]
    assert set(query["scope"][0].split()) == {
        "tweet.read",
        "tweet.write",
        "users.read",
        "offline.access",
    }
    state = query["state"][0]

    with SessionLocal() as db:
        account = db.get(PlatformAccount, saved["id"])
        encrypted = account.credentials_encrypted or ""
        pending = decrypt_json(encrypted)["x_oauth_pending"]
        assert pending["nonce"]
        assert pending["code_verifier"]
        assert pending["nonce"] not in encrypted
        assert pending["code_verifier"] not in encrypted

    async def fake_exchange(_account, *, code, code_verifier, redirect_uri):
        assert code == "oauth-code"
        assert code_verifier
        assert redirect_uri.endswith("/api/platform-accounts/X/oauth/callback")
        return {
            "access_token": "x-access-token",
            "refresh_token": "x-refresh-token",
            "expires_in": 7200,
            "scope": "tweet.read tweet.write users.read offline.access",
            "token_type": "bearer",
        }

    monkeypatch.setattr(
        platform_accounts_endpoint,
        "exchange_x_authorization_code",
        fake_exchange,
    )
    callback = client.get(
        "/api/platform-accounts/X/oauth/callback",
        params={"code": "oauth-code", "state": state},
        follow_redirects=False,
    )
    assert callback.status_code == 302
    assert callback.headers["location"] == (
        "http://127.0.0.1:5174/platform-accounts?oauth=x_success"
    )

    with SessionLocal() as db:
        account = db.get(PlatformAccount, saved["id"])
        assert decrypt_secret(account.access_token_encrypted) == "x-access-token"
        assert decrypt_secret(account.refresh_token_encrypted) == "x-refresh-token"
        assert account.status == "CONNECTED"
        assert "x_oauth_pending" not in decrypt_json(account.credentials_encrypted)

    replay = client.get(
        "/api/platform-accounts/X/oauth/callback",
        params={"code": "oauth-code", "state": state},
        follow_redirects=False,
    )
    assert replay.status_code == 400


def test_x_connection_test_only_reads_current_user(client, login_as, monkeypatch) -> None:
    admin_auth = _admin_auth(login_as)
    saved = _save_x_account(client, admin_auth, allow_public_publish=True)
    with SessionLocal() as db:
        account = db.get(PlatformAccount, saved["id"])
        account.access_token_encrypted = encrypt_secret("x-access-token")
        account.refresh_token_encrypted = encrypt_secret("x-refresh-token")
        account.token_expires_at = datetime.now() + timedelta(hours=1)
        db.commit()

    calls: list[tuple[str, str]] = []

    async def fake_request(_self, method, url, **kwargs):
        calls.append((method, url))
        assert kwargs["headers"]["Authorization"] == "Bearer x-access-token"
        return httpx.Response(
            200,
            json={"data": {"id": "x-user-id", "username": "contentpilot"}},
            request=httpx.Request(method, url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)
    tested = client.post("/api/platform-accounts/X/test", headers=admin_auth)
    assert tested.status_code == 200, tested.text
    result = tested.json()["data"]["result"]
    assert result["status"] == "CONNECTED"
    assert result["external_id"] == "x-user-id"
    assert tested.json()["data"]["loginUsername"] == "contentpilot"
    assert calls == [("GET", f"{settings.x_api_base_url}/2/users/me")]


@pytest.mark.asyncio
async def test_x_publisher_refreshes_then_publishes_text(monkeypatch) -> None:
    with SessionLocal() as db:
        account = db.scalar(select(PlatformAccount).where(PlatformAccount.platform == "X"))
        assert account is not None
        account.access_token_encrypted = None
        account.refresh_token_encrypted = encrypt_secret("refresh-token")
        account.token_expires_at = datetime.now() - timedelta(minutes=1)
        db.commit()

        async def fake_post(_self, url, **kwargs):
            assert url == settings.x_oauth_token_url
            assert kwargs["data"]["grant_type"] == "refresh_token"
            return httpx.Response(
                200,
                json={
                    "access_token": "fresh-access",
                    "refresh_token": "fresh-refresh",
                    "expires_in": 7200,
                },
                request=httpx.Request("POST", url),
            )

        async def fake_request(_self, method, url, **kwargs):
            assert method == "POST"
            assert url == f"{settings.x_api_base_url}/2/tweets"
            assert kwargs["headers"]["Authorization"] == "Bearer fresh-access"
            assert kwargs["json"]["text"]
            return httpx.Response(
                201,
                json={"data": {"id": "tweet-123", "text": kwargs["json"]["text"]}},
                request=httpx.Request(method, url),
            )

        monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
        monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)
        result = await XPublisher(db, account).publish(
            {
                "title": "X 发布测试",
                "content": "这是通过 X 官方 API 自动发布的测试正文。",
                "hashtags": ["ContentPilot"],
            }
        )
        assert result.success is True
        assert result.status == "PUBLISHED"
        assert result.external_id == "tweet-123"
        assert result.published_url == "https://x.com/i/web/status/tweet-123"
        assert result.detail["mediaUploaded"] is False
        assert decrypt_secret(account.access_token_encrypted) == "fresh-access"


def test_x_schedule_requires_authorization_and_uses_shared_account(
    client, login_as, monkeypatch
) -> None:
    admin_auth = _admin_auth(login_as)
    operator_auth = _operator_auth(login_as)
    saved = _save_x_account(client, admin_auth)

    created = client.post(
        "/api/articles",
        headers=operator_auth,
        json={
            "title": "X 排期测试",
            "source_text": "这是一篇用于验证 X 官方自动发布排期和共享账号权限的测试文章。",
        },
    )
    assert created.status_code == 200
    article_id = created.json()["data"]["id"]
    with SessionLocal() as db:
        variant = ContentVariant(
            article_id=article_id,
            platform="X",
            version_no=1,
            title="X 排期测试",
            content_text="运营者可以使用管理员授权的共享 X 账号进行自动发布。",
            hashtags_json=["ContentPilot"],
            review_status="APPROVED",
        )
        db.add(variant)
        account = db.get(PlatformAccount, saved["id"])
        account.status = "CONNECTED"
        account.access_token_encrypted = encrypt_secret("x-access-token")
        account.capabilities_json = ["TEXT_PUBLISH", "STATUS_READ"]
        db.commit()
        db.refresh(variant)
        variant_id = variant.id

    payload = {
        "article_id": article_id,
        "variant_id": variant_id,
        "platform": "X",
        "account_id": saved["id"],
        "scheduled_at": (datetime.now() + timedelta(days=10)).isoformat(timespec="seconds"),
        "publish_mode": "REAL_API",
    }
    disabled = client.post("/api/schedules", headers=operator_auth, json=payload)
    assert disabled.status_code == 400
    assert disabled.json()["code"] == 40080

    enabled = _save_x_account(client, admin_auth, allow_public_publish=True)
    assert enabled["id"] == saved["id"]
    unauthorized = client.post("/api/schedules", headers=operator_auth, json=payload)
    assert unauthorized.status_code == 400
    assert unauthorized.json()["code"] == 40075

    with SessionLocal() as db:
        account = db.get(PlatformAccount, saved["id"])
        account.status = "CONNECTED"
        account.access_token_encrypted = encrypt_secret("x-access-token")
        account.token_expires_at = datetime.now() + timedelta(hours=1)
        db.commit()

    scheduled = client.post("/api/schedules", headers=operator_auth, json=payload)
    assert scheduled.status_code == 200, scheduled.text

    async def fake_publish(_self, _request):
        return PublishResult(
            True,
            "X",
            "REAL_API",
            "PUBLISHED",
            external_id="tweet-scheduled",
            published_url="https://x.com/i/web/status/tweet-scheduled",
        )

    monkeypatch.setattr(XPublisher, "publish", fake_publish)
    schedule_id = scheduled.json()["data"]["id"]
    published = client.post(
        f"/api/schedules/{schedule_id}/publish-now",
        headers=operator_auth,
    )
    assert published.status_code == 200, published.text
    assert published.json()["data"]["status"] == "PUBLISHED"
    assert published.json()["data"]["externalId"] == "tweet-scheduled"


def test_x_disconnect_revokes_official_token_before_deleting(client, login_as, monkeypatch) -> None:
    admin_auth = _admin_auth(login_as)
    saved = _save_x_account(client, admin_auth)
    with SessionLocal() as db:
        account = db.get(PlatformAccount, saved["id"])
        account.access_token_encrypted = encrypt_secret("x-access-token")
        account.refresh_token_encrypted = encrypt_secret("x-refresh-token")
        account.status = "CONNECTED"
        db.commit()

    revoked: list[str] = []

    async def fake_post(_self, url, **kwargs):
        revoked.append(url)
        assert kwargs["data"]["token"] == "x-refresh-token"
        assert kwargs["data"]["token_type_hint"] == "refresh_token"
        return httpx.Response(200, json={}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    response = client.delete("/api/platform-accounts/X", headers=admin_auth)
    assert response.status_code == 200, response.text
    assert revoked == [f"{settings.x_api_base_url}/2/oauth2/revoke"]
    with SessionLocal() as db:
        assert db.get(PlatformAccount, saved["id"]) is None
