from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.credentials import decrypt_json, encrypt_json, encrypt_secret, secret_hint
from app.models.business import PlatformAccount, PlatformAuthLog
from app.models.user import User
from app.publishers.base import PlatformPublisher, PublishResult
from app.publishers.official import (
    WechatDraftPublisher,
    WeiboPublisher,
    XiaohongshuManualPublisher,
)
from app.schemas.platform_account import PlatformAccountUpsert

PLATFORMS = ("WEIBO", "WECHAT_OFFICIAL", "XIAOHONGSHU")
PLATFORM_NAMES = {
    "WEIBO": "微博",
    "WECHAT_OFFICIAL": "微信公众号",
    "XIAOHONGSHU": "小红书",
}
DEFAULT_CAPABILITIES = {
    "WEIBO": ["TEXT_PUBLISH", "IMAGE_PUBLISH", "STATUS_READ"],
    "WECHAT_OFFICIAL": ["MATERIAL_UPLOAD", "DRAFT_CREATE", "SUBMIT_PUBLISH"],
    "XIAOHONGSHU": ["COPYWRITING", "IMAGE_PACKAGE", "MANUAL_CONFIRM"],
}
DEFAULT_PUBLISH_MODES = {
    "WEIBO": "REAL_API",
    "WECHAT_OFFICIAL": "DRAFT_ONLY",
    "XIAOHONGSHU": "MANUAL_CONFIRM",
}
CONNECTION_GUIDES = {
    "WEIBO": {
        "mode": "OFFICIAL_OAUTH",
        "consoleUrl": "https://open.weibo.com/apps",
        "callbackPath": "/api/platform-accounts/WEIBO/oauth/callback",
        "steps": [
            "在微博开放平台创建并通过审核的网页应用",
            "复制 App Key 和 App Secret",
            "将本系统回调地址原样加入应用的 OAuth2 回调地址",
            "保存配置后点击“前往微博授权”，用要发布内容的微博账号登录授权",
        ],
    },
    "WECHAT_OFFICIAL": {
        "mode": "APP_SECRET",
        "consoleUrl": "https://mp.weixin.qq.com/",
        "steps": [
            "在公众号后台的开发接口管理中获取 AppID 和 AppSecret",
            "将运行 ContentPilot 的服务器出口 IP 加入公众号 IP 白名单",
            "确认公众号具有草稿接口权限；自动发布还需要发布接口权限",
            "保存后点击“验证真实连接”，系统会向微信官方接口获取 Access Token",
        ],
    },
    "XIAOHONGSHU": {
        "mode": "MANUAL_ONLY",
        "consoleUrl": "https://creator.xiaohongshu.com/",
        "steps": [
            "当前不保存账号密码或 Cookie，也不伪造官方连接",
            "系统只生成文案和图片交付包",
            "运营人员在小红书创作中心完成真实发布后回填公开链接",
        ],
    },
}


def get_owned_account(db: Session, user: User, platform: str) -> PlatformAccount | None:
    return db.scalar(
        select(PlatformAccount).where(
            PlatformAccount.user_id == user.id, PlatformAccount.platform == platform
        )
    )


def require_owned_account(db: Session, user: User, account_id: int) -> PlatformAccount | None:
    return db.scalar(
        select(PlatformAccount).where(
            PlatformAccount.id == account_id, PlatformAccount.user_id == user.id
        )
    )


def public_account(account: PlatformAccount | None, platform: str) -> dict[str, Any]:
    if not account:
        return {
            "id": None,
            "platform": platform,
            "platformName": PLATFORM_NAMES[platform],
            "accountName": "未配置",
            "authType": "NONE",
            "publishMode": DEFAULT_PUBLISH_MODES[platform],
            "status": "MANUAL_ONLY" if platform == "XIAOHONGSHU" else "NOT_CONFIGURED",
            "capabilities": DEFAULT_CAPABILITIES[platform],
            "lastTestAt": None,
            "lastError": None,
            "appId": "",
            "clientId": "",
            "secretConfigured": False,
            "accessTokenConfigured": False,
            "refreshTokenConfigured": False,
            "tokenHint": "",
            "tokenExpiresAt": None,
            "config": {},
            "connectionGuide": CONNECTION_GUIDES[platform],
        }
    config = decrypt_json(account.credentials_encrypted)
    safe_config = {
        key: config.get(key)
        for key in (
            "redirect_uri",
            "default_author",
            "default_cover_media_id",
            "default_cover_url",
            "allow_submit_publish",
        )
        if config.get(key) not in (None, "")
    }
    return {
        "id": account.id,
        "platform": account.platform,
        "platformName": PLATFORM_NAMES.get(account.platform, account.platform),
        "accountName": account.account_name,
        "authType": account.auth_type,
        "publishMode": account.publish_mode,
        "status": effective_status(account),
        "capabilities": account.capabilities_json or DEFAULT_CAPABILITIES.get(platform, []),
        "lastTestAt": account.last_test_at.isoformat() if account.last_test_at else None,
        "lastError": account.last_error,
        "appId": account.app_id or "",
        "clientId": account.client_id or "",
        "secretConfigured": bool(config.get("app_secret")),
        "accessTokenConfigured": bool(account.access_token_encrypted),
        "refreshTokenConfigured": bool(account.refresh_token_encrypted),
        "tokenHint": secret_hint(account.access_token_encrypted),
        "tokenExpiresAt": account.token_expires_at.isoformat()
        if account.token_expires_at
        else None,
        "config": safe_config,
        "connectionGuide": CONNECTION_GUIDES[platform],
    }


def effective_status(account: PlatformAccount) -> str:
    if account.status == "DISABLED":
        return "DISABLED"
    if account.token_expires_at and account.token_expires_at <= datetime.now():
        return "TOKEN_EXPIRED"
    if account.platform == "XIAOHONGSHU":
        return "MANUAL_ONLY"
    return account.status


def upsert_account(
    db: Session, user: User, platform: str, payload: PlatformAccountUpsert
) -> PlatformAccount:
    account = get_owned_account(db, user, platform)
    if not account:
        account = PlatformAccount(
            user_id=user.id, platform=platform, account_name=payload.account_name
        )
        db.add(account)
    config = decrypt_json(account.credentials_encrypted)
    config.update(
        {
            "redirect_uri": str(payload.redirect_uri)
            if payload.redirect_uri
            else config.get("redirect_uri"),
            "default_author": payload.default_author,
            "default_cover_media_id": payload.default_cover_media_id,
            "default_cover_url": str(payload.default_cover_url)
            if payload.default_cover_url
            else None,
            "allow_submit_publish": payload.allow_submit_publish,
        }
    )
    if payload.app_secret:
        config["app_secret"] = payload.app_secret
    account.account_name = payload.account_name
    account.auth_type = payload.auth_type
    account.publish_mode = payload.publish_mode
    account.app_id = payload.app_id
    account.client_id = payload.client_id or payload.app_id
    account.credentials_encrypted = encrypt_json(config)
    if payload.access_token:
        account.access_token_encrypted = encrypt_secret(payload.access_token)
    if payload.refresh_token:
        account.refresh_token_encrypted = encrypt_secret(payload.refresh_token)
    if payload.token_expires_at:
        expires = payload.token_expires_at
        account.token_expires_at = (
            expires.astimezone(UTC).replace(tzinfo=None) if expires.tzinfo else expires
        )
    account.capabilities_json = DEFAULT_CAPABILITIES[platform]
    account.status = "NOT_CONFIGURED" if not payload.enabled else _configured_status(account)
    account.last_error = None
    db.flush()
    log_auth(db, account, "CONFIGURE", "SUCCESS", "平台账号配置已保存")
    return account


def _configured_status(account: PlatformAccount) -> str:
    if account.platform == "XIAOHONGSHU":
        return "MANUAL_ONLY"
    if account.platform == "WECHAT_OFFICIAL" and account.app_id:
        return "CONNECTING"
    if account.platform == "WEIBO" and account.client_id:
        return "CONNECTING"
    return "NOT_CONFIGURED"


def account_validator(db: Session, account: PlatformAccount) -> PlatformPublisher:
    if account.platform == "WEIBO":
        return WeiboPublisher(db, account)
    if account.platform == "WECHAT_OFFICIAL":
        return WechatDraftPublisher(db, account)
    return XiaohongshuManualPublisher(account)


async def test_account(db: Session, account: PlatformAccount) -> PublishResult:
    if account.platform == "XIAOHONGSHU":
        account.status = "MANUAL_ONLY"
        result = PublishResult(
            False,
            account.platform,
            "MANUAL_CONFIRM",
            "MANUAL_ONLY",
            error_code="OFFICIAL_PUBLISH_API_UNAVAILABLE",
            error_message="当前未配置可供本系统使用的小红书官方内容发布接口。",
            suggested_action="请使用文案与图片交付包，在小红书创作中心人工发布。",
        )
        log_auth(db, account, "TEST_CONNECTION", "SKIPPED", result.error_message)
        return result
    account.status = "CONNECTING"
    db.flush()
    result = await account_validator(db, account).validate_credentials()
    account.last_test_at = datetime.now()
    account.last_error = result.error_message or None
    if result.success:
        account.status = "CONNECTED"
    elif result.error_code == "TOKEN_EXPIRED":
        account.status = "TOKEN_EXPIRED"
    else:
        account.status = "INVALID"
    log_auth(
        db,
        account,
        "TEST_CONNECTION",
        "SUCCESS" if result.success else "FAILED",
        result.error_message or "连接测试通过",
        {"errorCode": result.error_code, "retryable": result.retryable},
    )
    return result


def disconnect_account(db: Session, account: PlatformAccount) -> None:
    account.credentials_encrypted = None
    account.credential_encrypted = None
    account.access_token_encrypted = None
    account.refresh_token_encrypted = None
    account.token_expires_at = None
    account.status = "NOT_CONFIGURED"
    account.last_error = None
    log_auth(db, account, "DISCONNECT", "SUCCESS", "平台授权和敏感凭证已清除")


def log_auth(
    db: Session,
    account: PlatformAccount,
    action: str,
    status: str,
    message: str,
    detail: dict[str, Any] | None = None,
) -> None:
    db.add(
        PlatformAuthLog(
            platform_account_id=account.id,
            action=action,
            status=status,
            message=message[:500],
            detail_json=detail or {},
        )
    )
