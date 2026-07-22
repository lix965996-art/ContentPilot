from datetime import datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.core.credentials import decrypt_json, decrypt_secret, encrypt_secret
from app.db.session import SessionLocal
from app.models.business import PlatformAccount
from app.models.user import User
from app.publishers.base import PublishResult
from app.publishers.official import WechatDraftPublisher


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _operator_auth(client, login_as) -> dict[str, str]:
    token = login_as("operator", "Operator@123456")["access_token"]
    return headers(token)


def _variant_for(client, auth: dict[str, str], platform: str) -> tuple[int, int]:
    articles = client.get("/api/articles?page_size=100", headers=auth).json()["data"]["items"]
    for article in articles:
        variants = client.get(f"/api/articles/{article['id']}/variants", headers=auth).json()[
            "data"
        ]
        variant = next((item for item in variants if item["platform"] == platform), None)
        if variant:
            return article["id"], variant["id"]
    raise AssertionError(f"missing seeded variant for {platform}")


def _account_id(client, auth: dict[str, str], platform: str) -> int:
    rows = client.get("/api/platform-accounts", headers=auth).json()["data"]
    return next(int(item["id"]) for item in rows if item["platform"] == platform)


def test_credentials_are_encrypted_and_api_is_redacted(client, login_as) -> None:
    auth = _operator_auth(client, login_as)
    secret = "weibo-super-secret-value"
    token = "weibo-access-token-secret"
    response = client.put(
        "/api/platform-accounts/WEIBO",
        headers=auth,
        json={
            "account_name": "官方微博",
            "auth_type": "OAUTH2",
            "publish_mode": "REAL_API",
            "client_id": "client-123",
            "app_secret": secret,
            "access_token": token,
            "redirect_uri": ("http://127.0.0.1:8000/api/platform-accounts/WEIBO/oauth/callback"),
        },
    )
    assert response.status_code == 200, response.text
    body = response.text
    assert secret not in body
    assert token not in body
    assert response.json()["data"]["tokenHint"] == "••••cret"

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "operator"))
        account = db.scalar(
            select(PlatformAccount).where(
                PlatformAccount.user_id == user.id, PlatformAccount.platform == "WEIBO"
            )
        )
        assert account is not None
        assert secret not in (account.credentials_encrypted or "")
        assert token not in (account.access_token_encrypted or "")
        assert decrypt_json(account.credentials_encrypted)["app_secret"] == secret
        assert decrypt_secret(account.access_token_encrypted) == token


def test_simulated_platform_mode_is_rejected(client, login_as) -> None:
    auth = _operator_auth(client, login_as)
    response = client.put(
        "/api/platform-accounts/WEIBO",
        headers=auth,
        json={
            "account_name": "不应保存的模拟账号",
            "auth_type": "OAUTH2",
            "publish_mode": "MOCK",
            "client_id": "client-id",
            "app_secret": "client-secret",
        },
    )
    assert response.status_code == 422


def test_real_connection_and_oauth_state(client, login_as, monkeypatch) -> None:
    auth = _operator_auth(client, login_as)
    saved = client.put(
        "/api/platform-accounts/WEIBO",
        headers=auth,
        json={
            "account_name": "官方微博",
            "auth_type": "OAUTH2",
            "publish_mode": "REAL_API",
            "client_id": "client-123",
            "app_secret": "weibo-real-secret",
            "access_token": "weibo-real-access-token",
            "redirect_uri": ("http://127.0.0.1:8000/api/platform-accounts/WEIBO/oauth/callback"),
        },
    )
    assert saved.status_code == 200

    async def official_uid_response(_self, url, **_kwargs):
        return httpx.Response(200, json={"uid": "123456"}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", official_uid_response)
    tested = client.post("/api/platform-accounts/WEIBO/test", headers=auth)
    assert tested.status_code == 200
    assert tested.json()["data"]["status"] == "CONNECTED"
    assert tested.json()["data"]["result"]["external_id"] == "123456"
    oauth = client.post(
        "/api/platform-accounts/WEIBO/oauth/start",
        headers=auth,
        json={"redirect_uri": ("http://127.0.0.1:8000/api/platform-accounts/WEIBO/oauth/callback")},
    )
    assert oauth.status_code == 200
    assert "oauth2/authorize" in oauth.json()["data"]["authorizationUrl"]


@pytest.mark.asyncio
async def test_wechat_token_cache_does_not_require_network() -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "operator"))
        account = db.scalar(
            select(PlatformAccount).where(
                PlatformAccount.user_id == user.id,
                PlatformAccount.platform == "WECHAT_OFFICIAL",
            )
        )
        assert account is not None
        account.app_id = "wx-test"
        account.access_token_encrypted = encrypt_secret("cached-wechat-token")
        account.token_expires_at = datetime.now() + timedelta(hours=1)
        db.commit()
        publisher = WechatDraftPublisher(db, account)
        assert await publisher._access_token() == "cached-wechat-token"


def test_wechat_real_draft_uses_official_publisher(client, login_as, monkeypatch) -> None:
    auth = _operator_auth(client, login_as)
    configured = client.put(
        "/api/platform-accounts/WECHAT_OFFICIAL",
        headers=auth,
        json={
            "account_name": "真实公众号",
            "auth_type": "APP_SECRET",
            "publish_mode": "DRAFT_ONLY",
            "app_id": "wx-real",
            "app_secret": "wechat-real-secret",
        },
    )
    assert configured.status_code == 200
    account_id = configured.json()["data"]["id"]
    with SessionLocal() as db:
        account = db.get(PlatformAccount, account_id)
        account.status = "CONNECTED"
        account.access_token_encrypted = encrypt_secret("cached-real-wechat-token")
        account.token_expires_at = datetime.now() + timedelta(hours=1)
        db.commit()

    async def official_draft(_self, _request):
        return PublishResult(
            True,
            "WECHAT_OFFICIAL",
            "DRAFT_ONLY",
            "DRAFT_CREATED",
            external_id="official-draft-media-id",
            detail={"real": True},
        )

    monkeypatch.setattr(WechatDraftPublisher, "publish", official_draft)
    article_id, variant_id = _variant_for(client, auth, "WECHAT_OFFICIAL")
    scheduled = client.post(
        "/api/schedules",
        headers=auth,
        json={
            "article_id": article_id,
            "variant_id": variant_id,
            "account_id": account_id,
            "platform": "WECHAT_OFFICIAL",
            "scheduled_at": (datetime.now() + timedelta(days=31)).isoformat(),
            "publish_mode": "DRAFT_ONLY",
        },
    )
    assert scheduled.status_code == 200, scheduled.text
    published = client.post(
        f"/api/schedules/{scheduled.json()['data']['id']}/publish-now", headers=auth
    )
    assert published.status_code == 200
    data = published.json()["data"]
    assert data["status"] == "DRAFT_CREATED"
    assert data["resultMode"] == "DRAFT_ONLY"
    assert not data["publishedUrl"]
    assert data["externalId"] == "official-draft-media-id"


def test_xiaohongshu_package_download_and_manual_confirmation(client, login_as) -> None:
    auth = _operator_auth(client, login_as)
    configured = client.put(
        "/api/platform-accounts/XIAOHONGSHU",
        headers=auth,
        json={
            "account_name": "小红书人工账号",
            "auth_type": "NONE",
            "publish_mode": "MANUAL_CONFIRM",
        },
    )
    assert configured.status_code == 200
    assert configured.json()["data"]["status"] == "MANUAL_ONLY"
    account_id = _account_id(client, auth, "XIAOHONGSHU")
    article_id, variant_id = _variant_for(client, auth, "XIAOHONGSHU")
    scheduled = client.post(
        "/api/schedules",
        headers=auth,
        json={
            "article_id": article_id,
            "variant_id": variant_id,
            "account_id": account_id,
            "platform": "XIAOHONGSHU",
            "scheduled_at": (datetime.now() + timedelta(days=32)).isoformat(),
            "publish_mode": "MANUAL_CONFIRM",
        },
    )
    assert scheduled.status_code == 200, scheduled.text
    schedule_id = scheduled.json()["data"]["id"]
    published = client.post(f"/api/schedules/{schedule_id}/publish-now", headers=auth)
    assert published.status_code == 200
    assert published.json()["data"]["status"] == "WAITING_MANUAL_CONFIRM"

    package = client.get(f"/api/schedules/{schedule_id}/publish-package", headers=auth)
    assert package.status_code == 200
    assert package.json()["data"]["creatorUrl"].startswith("https://creator.xiaohongshu.com")
    archive = client.get(f"/api/schedules/{schedule_id}/publish-package/download", headers=auth)
    assert archive.status_code == 200
    assert archive.headers["content-type"] == "application/zip"

    missing_url = client.post(f"/api/schedules/{schedule_id}/manual-confirm", headers=auth, json={})
    assert missing_url.status_code == 400
    confirmed = client.post(
        f"/api/schedules/{schedule_id}/manual-confirm",
        headers=auth,
        json={"published_url": "https://www.xiaohongshu.com/explore/example"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["data"]["status"] == "MANUAL_PUBLISHED"


def test_expired_token_is_reported_without_exposing_it(client, login_as) -> None:
    auth = _operator_auth(client, login_as)
    client.put(
        "/api/platform-accounts/WEIBO",
        headers=auth,
        json={
            "account_name": "过期微博",
            "auth_type": "OAUTH2",
            "publish_mode": "REAL_API",
            "client_id": "client-123",
            "app_secret": "weibo-real-secret",
            "access_token": "expired-sensitive-token",
            "token_expires_at": (datetime.now() - timedelta(minutes=1)).isoformat(),
        },
    )
    rows = client.get("/api/platform-accounts", headers=auth)
    assert rows.status_code == 200
    weibo = next(item for item in rows.json()["data"] if item["platform"] == "WEIBO")
    assert weibo["status"] == "TOKEN_EXPIRED"
    assert "expired-sensitive-token" not in rows.text


def test_real_publish_is_forbidden_until_official_connection_passes(client, login_as) -> None:
    auth = _operator_auth(client, login_as)
    configured = client.put(
        "/api/platform-accounts/WECHAT_OFFICIAL",
        headers=auth,
        json={
            "account_name": "尚未验证公众号",
            "auth_type": "APP_SECRET",
            "publish_mode": "DRAFT_ONLY",
            "app_id": "wx-unverified",
            "app_secret": "wechat-unverified-secret",
        },
    )
    account_id = configured.json()["data"]["id"]
    article_id, variant_id = _variant_for(client, auth, "WECHAT_OFFICIAL")
    response = client.post(
        "/api/schedules",
        headers=auth,
        json={
            "article_id": article_id,
            "variant_id": variant_id,
            "account_id": account_id,
            "platform": "WECHAT_OFFICIAL",
            "scheduled_at": (datetime.now() + timedelta(days=33)).isoformat(),
            "publish_mode": "REAL_API",
        },
    )
    assert response.status_code == 400
    assert response.json()["code"] == 40075
