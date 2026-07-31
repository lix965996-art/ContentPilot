from datetime import datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.api.endpoints import platform_accounts as platform_accounts_endpoint
from app.core.config import settings
from app.core.credentials import decrypt_json, decrypt_secret, encrypt_secret
from app.db.session import SessionLocal
from app.models.business import ContentVariant, MediaAsset, PlatformAccount
from app.models.user import User
from app.publishers.base import PublishResult
from app.publishers.official import WechatDraftPublisher
from app.services import platform_account_service, publish_service


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _operator_auth(client, login_as) -> dict[str, str]:
    token = login_as("operator", "Operator@123456")["access_token"]
    return headers(token)


def _admin_auth(client, login_as) -> dict[str, str]:
    token = login_as("admin", "Admin@123456")["access_token"]
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
    auth = _admin_auth(client, login_as)
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
            "operation_ip": "8.8.8.8",
        },
    )
    assert response.status_code == 200, response.text
    body = response.text
    assert secret not in body
    assert token not in body
    assert response.json()["data"]["tokenHint"] == "••••cret"
    assert response.json()["data"]["config"]["operation_ip"] == "8.8.8.8"

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "admin"))
        account = db.scalar(select(PlatformAccount).where(PlatformAccount.platform == "WEIBO"))
        assert account is not None
        assert account.updated_by == user.id
        assert secret not in (account.credentials_encrypted or "")
        assert token not in (account.access_token_encrypted or "")
        assert decrypt_json(account.credentials_encrypted)["app_secret"] == secret
        assert decrypt_json(account.credentials_encrypted)["operation_ip"] == "8.8.8.8"
        assert decrypt_secret(account.access_token_encrypted) == token


def test_operator_can_use_shared_account_but_cannot_manage_credentials(client, login_as) -> None:
    admin_auth = _admin_auth(client, login_as)
    operator_auth = _operator_auth(client, login_as)
    saved = client.put(
        "/api/platform-accounts/WEIBO",
        headers=admin_auth,
        json={
            "account_name": "团队共享微博",
            "auth_type": "OAUTH2",
            "publish_mode": "REAL_API",
            "client_id": "shared-client-id",
            "app_secret": "shared-client-secret",
            "access_token": "shared-access-token",
        },
    )
    assert saved.status_code == 200

    rows = client.get("/api/platform-accounts", headers=operator_auth)
    assert rows.status_code == 200
    account = next(item for item in rows.json()["data"] if item["platform"] == "WEIBO")
    assert account["id"] == saved.json()["data"]["id"]
    assert account["accountName"] == "团队共享微博"
    assert account["shared"] is True
    assert account["clientId"] == ""
    assert account["appId"] == ""
    assert account["tokenHint"] == ""
    assert account["config"] == {}
    assert "shared-client" not in rows.text
    assert "shared-access-token" not in rows.text

    forbidden_update = client.put(
        "/api/platform-accounts/WEIBO",
        headers=operator_auth,
        json={
            "account_name": "越权修改",
            "auth_type": "OAUTH2",
            "publish_mode": "REAL_API",
            "client_id": "forbidden",
            "app_secret": "forbidden",
        },
    )
    assert forbidden_update.status_code == 403
    assert client.delete("/api/platform-accounts/WEIBO", headers=operator_auth).status_code == 403
    assert (
        client.get(
            "/api/platform-accounts/WEIBO/auth-logs",
            headers=operator_auth,
        ).status_code
        == 403
    )


def test_simulated_platform_mode_is_rejected(client, login_as) -> None:
    auth = _admin_auth(client, login_as)
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
    auth = _admin_auth(client, login_as)
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
    auth = _admin_auth(client, login_as)
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
    assert published.status_code == 200, published.text
    data = published.json()["data"]
    assert data["status"] == "DRAFT_CREATED"
    assert data["resultMode"] == "DRAFT_ONLY"
    assert not data["publishedUrl"]
    assert data["externalId"] == "official-draft-media-id"


def test_xiaohongshu_package_download_and_manual_confirmation(
    client, login_as, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "experimental_browser_publishing_enabled", False)
    auth = _admin_auth(client, login_as)
    experimental = client.put(
        "/api/platform-accounts/XIAOHONGSHU",
        headers=auth,
        json={
            "account_name": "小红书本地 MCP 账号",
            "auth_type": "NONE",
            "publish_mode": "MCP_PUBLISH",
        },
    )
    assert experimental.status_code == 400
    assert "本地 MCP 发布默认关闭" in experimental.json()["message"]

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
    article_id, variant_id = _variant_for(client, auth, "XIAOHONGSHU")
    with SessionLocal() as db:
        variant = db.get(ContentVariant, variant_id)
        assert variant is not None
        variant.title = "合规的小红书标题"
        variant.content_text = "这是一篇用于验证人工交付包的小红书正文。"
        db.add(
            MediaAsset(
                article_id=article_id,
                source="TEST",
                image_url="https://example.com/cover.jpg",
                thumbnail_url="https://example.com/cover.jpg",
                usage_type="COVER",
                selected=True,
            )
        )
        db.commit()
    scheduled = client.post(
        "/api/schedules",
        headers=auth,
        json={
            "article_id": article_id,
            "variant_id": variant_id,
            "platform": "XIAOHONGSHU",
            "scheduled_at": (datetime.now() + timedelta(days=32)).isoformat(),
            "publish_mode": "MANUAL_CONFIRM",
        },
    )
    assert scheduled.status_code == 200, scheduled.text
    schedule_id = scheduled.json()["data"]["id"]
    published = client.post(f"/api/schedules/{schedule_id}/publish-now", headers=auth)
    assert published.status_code == 200, published.text
    assert published.json()["data"]["status"] == "WAITING_MANUAL_CONFIRM"
    assert published.json()["data"]["publishPackageJson"]["creatorUrl"].startswith("https://")


def test_xiaohongshu_mcp_qrcode_is_optional_and_returns_real_image(
    client, login_as, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "experimental_browser_publishing_enabled", False)
    auth = _admin_auth(client, login_as)
    disabled = client.post(
        "/api/platform-accounts/XIAOHONGSHU/login-qrcode",
        headers=auth,
    )
    assert disabled.status_code == 400
    assert disabled.json()["code"] == 40064

    async def qrcode() -> dict[str, str]:
        return {
            "image_data_url": "data:image/png;base64,aW1hZ2U=",
            "message": "二维码有效期 5 分钟",
        }

    monkeypatch.setattr(settings, "experimental_browser_publishing_enabled", True)
    monkeypatch.setattr(platform_accounts_endpoint, "mcp_get_qrcode", qrcode)
    enabled = client.post(
        "/api/platform-accounts/XIAOHONGSHU/login-qrcode",
        headers=auth,
    )

    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["data"]["imageDataUrl"] == "data:image/png;base64,aW1hZ2U="
    assert enabled.json()["data"]["message"] == "二维码有效期 5 分钟"


def test_xiaohongshu_mcp_optional_publish_flow(client, login_as, monkeypatch) -> None:
    auth = _admin_auth(client, login_as)
    monkeypatch.setattr(settings, "experimental_browser_publishing_enabled", True)

    async def logged_in() -> tuple[bool, str]:
        return True, "✅ 已登录\n用户名: contentpilot-test"

    async def published(_variant, _assets) -> PublishResult:
        return PublishResult(
            True,
            "XIAOHONGSHU",
            "MCP_PUBLISH",
            "PUBLISHED",
            external_id="real-note-id-from-adapter",
            published_url="https://www.xiaohongshu.com/explore/real-note-id-from-adapter",
            detail={"method": "mcp", "verified_identifier": True},
        )

    monkeypatch.setattr(platform_account_service, "mcp_check_login", logged_in)
    monkeypatch.setattr(publish_service, "_publish_xiaohongshu", published)
    configured = client.put(
        "/api/platform-accounts/XIAOHONGSHU",
        headers=auth,
        json={
            "account_name": "本机小红书 MCP",
            "auth_type": "NONE",
            "publish_mode": "MCP_PUBLISH",
        },
    )
    assert configured.status_code == 200, configured.text
    account_id = configured.json()["data"]["id"]
    assert configured.json()["data"]["status"] == "LOGIN_REQUIRED"
    assert configured.json()["data"]["localPublishingEnabled"] is True
    with SessionLocal() as db:
        account = db.get(PlatformAccount, account_id)
        assert account is not None
        account.last_error = "此前未登录的旧错误"
        db.commit()

    tested = client.post("/api/platform-accounts/XIAOHONGSHU/test", headers=auth)
    assert tested.status_code == 200, tested.text
    assert tested.json()["data"]["status"] == "CONNECTED"
    assert tested.json()["data"]["result"]["mode"] == "MCP_PUBLISH"
    assert tested.json()["data"]["lastError"] is None
    assert tested.json()["data"]["lastTestAt"]
    assert tested.json()["data"]["loginUsername"] == "contentpilot-test"
    assert tested.json()["data"]["lastLoginAt"]
    assert tested.json()["data"]["sessionDurationSeconds"] >= 0

    article_id, variant_id = _variant_for(client, auth, "XIAOHONGSHU")
    with SessionLocal() as db:
        variant = db.get(ContentVariant, variant_id)
        assert variant is not None
        variant.title = "真实发布链路测试"
        variant.content_text = "验证可选 MCP 发布流程，不调用真实平台。"
        db.add(
            MediaAsset(
                article_id=article_id,
                source="TEST",
                image_url="https://example.com/mcp-cover.jpg",
                thumbnail_url="https://example.com/mcp-cover.jpg",
                usage_type="COVER",
                selected=True,
            )
        )
        db.commit()

    scheduled = client.post(
        "/api/schedules",
        headers=auth,
        json={
            "article_id": article_id,
            "variant_id": variant_id,
            "account_id": account_id,
            "platform": "XIAOHONGSHU",
            "scheduled_at": (datetime.now() + timedelta(days=33)).isoformat(),
            "publish_mode": "MCP_PUBLISH",
        },
    )
    assert scheduled.status_code == 200, scheduled.text
    published_response = client.post(
        f"/api/schedules/{scheduled.json()['data']['id']}/publish-now",
        headers=auth,
    )
    assert published_response.status_code == 200, published_response.text
    data = published_response.json()["data"]
    assert data["status"] == "PUBLISHED"
    assert data["resultMode"] == "MCP_PUBLISH"
    assert data["externalId"] == "real-note-id-from-adapter"

    async def logged_out() -> tuple[bool, str]:
        return True, "Cookies 删除成功"

    monkeypatch.setattr(platform_accounts_endpoint, "mcp_logout", logged_out)
    logout_response = client.post(
        "/api/platform-accounts/XIAOHONGSHU/logout",
        headers=auth,
    )
    assert logout_response.status_code == 200, logout_response.text
    logged_out_account = logout_response.json()["data"]
    assert logged_out_account["status"] == "LOGIN_REQUIRED"
    assert logged_out_account["loginUsername"] == ""
    assert logged_out_account["lastLoginAt"] is None
    assert logged_out_account["sessionDurationSeconds"] == 0


def test_expired_token_is_reported_without_exposing_it(client, login_as) -> None:
    auth = _admin_auth(client, login_as)
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


def test_new_credentials_clear_stale_expired_token(client, login_as) -> None:
    auth = _admin_auth(client, login_as)
    expired = client.put(
        "/api/platform-accounts/WECHAT_OFFICIAL",
        headers=auth,
        json={
            "account_name": "待更新公众号",
            "auth_type": "APP_SECRET",
            "publish_mode": "DRAFT_ONLY",
            "app_id": "wx-stale-token",
            "app_secret": "old-wechat-secret",
            "access_token": "expired-wechat-token",
            "token_expires_at": (datetime.now() - timedelta(minutes=1)).isoformat(),
        },
    )
    assert expired.status_code == 200
    assert expired.json()["data"]["status"] == "TOKEN_EXPIRED"

    updated = client.put(
        "/api/platform-accounts/WECHAT_OFFICIAL",
        headers=auth,
        json={
            "account_name": "已更新公众号",
            "auth_type": "APP_SECRET",
            "publish_mode": "DRAFT_ONLY",
            "app_id": "wx-stale-token",
            "app_secret": "new-wechat-secret",
        },
    )
    assert updated.status_code == 200
    data = updated.json()["data"]
    assert data["status"] == "CONNECTING"
    assert data["accessTokenConfigured"] is False
    assert data["refreshTokenConfigured"] is False
    assert data["tokenExpiresAt"] is None


def test_wechat_diagnostic_requires_admin(client, login_as) -> None:
    anonymous = client.post("/api/platform-accounts/diagnostic/wechat", json={})
    assert anonymous.status_code == 401
    assert anonymous.json()["code"] == 40101

    operator_auth = _operator_auth(client, login_as)
    operator = client.post(
        "/api/platform-accounts/diagnostic/wechat", headers=operator_auth, json={}
    )
    assert operator.status_code == 403
    assert operator.json()["code"] == 40301


def test_real_publish_is_forbidden_until_official_connection_passes(client, login_as) -> None:
    auth = _admin_auth(client, login_as)
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
