import pytest
from sqlalchemy import select

from app.api.endpoints import platform_accounts as platform_accounts_endpoint
from app.core.credentials import decrypt_json
from app.db.session import SessionLocal
from app.models.business import ContentArticle, PlatformAccount
from app.prompts.profiles import PLATFORM_PROFILES, build_generation_prompt
from app.publishers.toutiao_browser import ToutiaoBrowserPublisher
from app.services import platform_account_service
from app.services.platform_content import validate_platform_publish
from app.services.publish_service import toutiao_public_publish_enabled


def _admin_headers(login_as) -> dict[str, str]:
    token = login_as("admin", "Admin@123456")["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_toutiao_prompt_profile_and_validation() -> None:
    article = ContentArticle(
        title="今日头条内容测试",
        source_text="项目持续八周，共有三百二十名参与者。项目方强调结果仍需独立复核。",
        target_audience="内容运营者",
        keywords_json=[],
        created_by=1,
    )
    prompt = build_generation_prompt(
        article,
        "TOUTIAO",
        {
            "style": "专业自然",
            "length": "LONG",
            "preserve_meaning": 95,
            "target_audience": "内容运营者",
            "include_emoji": False,
            "include_hashtags": True,
        },
    )
    assert "目标平台：今日头条" in prompt
    assert "标题为 2～30 个字符" in PLATFORM_PROFILES["TOUTIAO"].render()
    assert "preserve_meaning（原意保留程度）：95/100" in prompt
    assert not validate_platform_publish(
        platform="TOUTIAO",
        title="今日头条真实发布测试",
        content="这是一段用于验证今日头条发布边界的正文。" * 4,
        hashtags=[],
        images=[],
    )


@pytest.mark.asyncio
async def test_toutiao_publisher_rejects_invalid_title_without_opening_browser() -> None:
    result = await ToutiaoBrowserPublisher(1).publish(
        {"title": "一", "content": "正文" * 30, "content_html": "<p>正文</p>"}
    )
    assert not result.success
    assert result.error_code == "VALIDATION_ERROR"


def test_toutiao_account_qr_login_and_safe_metadata(client, login_as, monkeypatch) -> None:
    auth = _admin_headers(login_as)
    listed = client.get("/api/platform-accounts", headers=auth)
    assert any(item["platform"] == "TOUTIAO" for item in listed.json()["data"])

    saved = client.put(
        "/api/platform-accounts/TOUTIAO",
        headers=auth,
        json={
            "account_name": "我的头条号",
            "auth_type": "QR_LOGIN",
            "publish_mode": "BROWSER_PUBLISH",
            "allow_public_publish": True,
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["data"]["status"] == "LOGIN_REQUIRED"

    async def fake_qrcode(_account_id: int):
        return {
            "connected": False,
            "image_data_url": "data:image/png;base64,dGVzdA==",
            "message": "请扫码",
        }

    monkeypatch.setattr(platform_accounts_endpoint, "get_login_qrcode", fake_qrcode)
    qrcode = client.post("/api/platform-accounts/TOUTIAO/login-qrcode", headers=auth)
    assert qrcode.status_code == 200, qrcode.text
    assert qrcode.json()["data"]["imageDataUrl"].startswith("data:image/png;base64,")

    async def fake_check_login(_account_id: int):
        return True, "毕业设计头条号"

    monkeypatch.setattr(platform_account_service, "toutiao_check_login", fake_check_login)
    tested = client.post("/api/platform-accounts/TOUTIAO/test", headers=auth)
    assert tested.status_code == 200, tested.text
    data = tested.json()["data"]
    assert data["status"] == "CONNECTED"
    assert data["loginUsername"] == "毕业设计头条号"
    assert data["publicPublishEnabled"] is True

    with SessionLocal() as db:
        account = db.scalar(select(PlatformAccount).where(PlatformAccount.platform == "TOUTIAO"))
        assert account is not None
        config = decrypt_json(account.credentials_encrypted)
        assert config["toutiao_login_username"] == "毕业设计头条号"
        assert "cookie" not in " ".join(config).lower()
        assert toutiao_public_publish_enabled(account)
