from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.credentials import decrypt_json, encrypt_json, encrypt_secret, secret_hint
from app.models.business import PlatformAccount, PlatformAuthLog
from app.models.user import User
from app.publishers.base import PlatformPublisher, PublishResult
from app.publishers.official import (
    WechatDraftPublisher,
    WeiboPublisher,
    XiaohongshuManualPublisher,
)
from app.publishers.x_official import XPublisher
from app.publishers.xhs_mcp import XiaohongshuMCPPublisher, mcp_check_login
from app.schemas.platform_account import PlatformAccountUpsert

PLATFORMS = ("WEIBO", "WECHAT_OFFICIAL", "XIAOHONGSHU", "X")
PLATFORM_NAMES = {
    "WEIBO": "微博",
    "WECHAT_OFFICIAL": "微信公众号",
    "XIAOHONGSHU": "小红书",
    "X": "X",
}
DEFAULT_CAPABILITIES = {
    "WEIBO": ["TEXT_PUBLISH", "IMAGE_PUBLISH", "STATUS_READ"],
    "WECHAT_OFFICIAL": ["DRAFT_CREATE", "DRAFT_UPDATE", "DRAFT_READ", "DRAFT_DELETE"],
    "XIAOHONGSHU": ["COPYWRITING", "IMAGE_PACKAGE", "MANUAL_CONFIRM"],
    "X": ["TEXT_PUBLISH", "STATUS_READ"],
}

WECHAT_DRAFT_CAPABILITIES = {"DRAFT_CREATE", "DRAFT_UPDATE", "DRAFT_READ", "DRAFT_DELETE"}
WECHAT_PUBLISH_CAPABILITY = "SUBMIT_PUBLISH"
DEFAULT_PUBLISH_MODES = {
    "WEIBO": "REAL_API",
    "WECHAT_OFFICIAL": "DRAFT_ONLY",
    "XIAOHONGSHU": "MANUAL_CONFIRM",
    "X": "REAL_API",
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
        "mode": "MANUAL_DELIVERY",
        "consoleUrl": "https://creator.xiaohongshu.com/",
        "steps": [
            "系统在排期时间生成文案、标签和图片交付包",
            "运营人员打开小红书创作中心并人工发布",
            "发布完成后回到发布中心填写公开链接并确认完成",
            "系统不会保存 Cookie、密码或执行浏览器注入",
        ],
    },
    "X": {
        "mode": "OFFICIAL_OAUTH2_PKCE",
        "consoleUrl": "https://developer.x.com/en/portal/dashboard",
        "callbackPath": "/api/platform-accounts/X/oauth/callback",
        "steps": [
            "在 X Developer Portal 创建 Project 和 Web App，并启用 OAuth 2.0",
            "为应用申请 Read and write 权限，配置 tweet.read、tweet.write、"
            "users.read 和 offline.access",
            "将本系统显示的回调地址原样加入应用的 Callback URI / Redirect URL",
            "保存 Client ID 和 Client Secret 后，点击“前往 X 授权”并使用目标账号确认授权",
        ],
    },
}


def get_platform_account(db: Session, platform: str) -> PlatformAccount | None:
    """Return the single system-shared account for a platform."""
    return db.scalar(select(PlatformAccount).where(PlatformAccount.platform == platform))


def get_owned_account(db: Session, user: User, platform: str) -> PlatformAccount | None:
    """Backward-compatible alias; accounts are no longer owned by individual users."""
    del user
    return get_platform_account(db, platform)


def require_owned_account(db: Session, user: User, account_id: int) -> PlatformAccount | None:
    """Backward-compatible lookup for callers migrating from per-user accounts."""
    del user
    return db.get(PlatformAccount, account_id)


def public_account(
    account: PlatformAccount | None,
    platform: str,
    *,
    include_configuration: bool = True,
) -> dict[str, Any]:
    local_publishing_enabled = (
        platform == "XIAOHONGSHU" and settings.experimental_browser_publishing_enabled
    )
    available_publish_modes = (
        []
        if platform == "X"
        else ["MANUAL_CONFIRM", "MCP_PUBLISH"]
        if local_publishing_enabled
        else ["MANUAL_CONFIRM"]
        if platform == "XIAOHONGSHU"
        else ["DRAFT_ONLY", "SUBMIT_PUBLISH"]
        if platform == "WECHAT_OFFICIAL"
        else ["REAL_API"]
    )
    if not account:
        return {
            "id": None,
            "platform": platform,
            "platformName": PLATFORM_NAMES[platform],
            "accountName": "未配置",
            "authType": "NONE",
            "publishMode": DEFAULT_PUBLISH_MODES[platform],
            "publishHint": _build_publish_hint(platform, DEFAULT_CAPABILITIES[platform], {}),
            "status": "MANUAL_ONLY" if platform == "XIAOHONGSHU" else "NOT_CONFIGURED",
            "capabilities": DEFAULT_CAPABILITIES[platform],
            "lastTestAt": None,
            "lastError": None,
            "loginUsername": "",
            "lastLoginAt": None,
            "sessionDurationSeconds": 0,
            "appId": "",
            "clientId": "",
            "secretConfigured": False,
            "accessTokenConfigured": False,
            "refreshTokenConfigured": False,
            "tokenHint": "",
            "tokenExpiresAt": None,
            "config": {},
            "publicPublishEnabled": False,
            "shared": True,
            "localPublishingEnabled": local_publishing_enabled,
            "availablePublishModes": available_publish_modes,
            "connectionGuide": CONNECTION_GUIDES[platform],
        }
    config = decrypt_json(account.credentials_encrypted)
    safe_config = {
        key: config.get(key)
        for key in (
            "redirect_uri",
            "operation_ip",
            "default_author",
            "default_cover_media_id",
            "default_cover_url",
            "allow_submit_publish",
            "allow_public_publish",
        )
        if config.get(key) not in (None, "")
    }
    browser_mode_disabled = (
        platform == "XIAOHONGSHU"
        and not settings.experimental_browser_publishing_enabled
        and account.publish_mode in {"CDP_PUBLISH", "MCP_PUBLISH"}
    )
    public_publish_enabled = bool(platform == "X" and config.get("allow_public_publish") is True)
    if platform == "X":
        available_publish_modes = ["REAL_API"] if public_publish_enabled else []
    caps = (
        DEFAULT_CAPABILITIES["XIAOHONGSHU"]
        if browser_mode_disabled
        else account.capabilities_json or DEFAULT_CAPABILITIES.get(platform, [])
    )
    # Build a human-readable hint about what the account can actually do.
    publish_hint = _build_publish_hint(account.platform, caps, safe_config)
    last_login_at = _parse_datetime(
        config.get("xhs_last_login_at")
        if platform == "XIAOHONGSHU"
        else config.get("x_authorized_at")
        if platform == "X"
        else None
    )
    session_duration_seconds = (
        max(0, int((datetime.now() - last_login_at).total_seconds()))
        if platform == "XIAOHONGSHU" and effective_status(account) == "CONNECTED" and last_login_at
        else 0
    )
    return {
        "id": account.id,
        "platform": account.platform,
        "platformName": PLATFORM_NAMES.get(account.platform, account.platform),
        "accountName": account.account_name,
        "authType": account.auth_type,
        "publishMode": "MANUAL_CONFIRM" if browser_mode_disabled else account.publish_mode,
        "status": "MANUAL_ONLY" if browser_mode_disabled else effective_status(account),
        "capabilities": caps,
        "publishHint": publish_hint,
        "lastTestAt": account.last_test_at.isoformat() if account.last_test_at else None,
        "lastError": account.last_error,
        "loginUsername": (
            config.get("xhs_login_username", "")
            if platform == "XIAOHONGSHU"
            else config.get("x_username", "")
            if platform == "X"
            else ""
        ),
        "lastLoginAt": last_login_at.isoformat() if last_login_at else None,
        "sessionDurationSeconds": session_duration_seconds,
        "appId": account.app_id or "" if include_configuration else "",
        "clientId": account.client_id or "" if include_configuration else "",
        "secretConfigured": bool(config.get("app_secret")),
        "accessTokenConfigured": bool(account.access_token_encrypted),
        "refreshTokenConfigured": bool(account.refresh_token_encrypted),
        "tokenHint": secret_hint(account.access_token_encrypted) if include_configuration else "",
        "tokenExpiresAt": account.token_expires_at.isoformat()
        if account.token_expires_at
        else None,
        "config": safe_config if include_configuration else {},
        "publicPublishEnabled": public_publish_enabled,
        "shared": True,
        "localPublishingEnabled": local_publishing_enabled,
        "availablePublishModes": available_publish_modes,
        "connectionGuide": CONNECTION_GUIDES[platform],
    }


def effective_status(account: PlatformAccount) -> str:
    if account.status == "DISABLED":
        return "DISABLED"
    if account.token_expires_at and account.token_expires_at <= datetime.now():
        return "TOKEN_EXPIRED"
    if account.platform == "XIAOHONGSHU":
        if not settings.experimental_browser_publishing_enabled:
            return "MANUAL_ONLY"
        return account.status or "LOGIN_REQUIRED"
    return account.status


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError:
        return None


def _xhs_login_username(info: str) -> str:
    match = re.search(
        r"(?:用户名|账号|user(?:name)?)\s*[:：]\s*([^\r\n]+)",
        info,
        flags=re.IGNORECASE,
    )
    return match.group(1).strip()[:100] if match else ""


def _record_xhs_session(account: PlatformAccount, info: str, checked_at: datetime) -> None:
    config = decrypt_json(account.credentials_encrypted)
    username = _xhs_login_username(info)
    previous_username = str(config.get("xhs_login_username") or "")
    if username:
        config["xhs_login_username"] = username
    if not config.get("xhs_last_login_at") or (username and username != previous_username):
        config["xhs_last_login_at"] = checked_at.isoformat()
    config["xhs_last_seen_at"] = checked_at.isoformat()
    account.credentials_encrypted = encrypt_json(config)


def clear_xhs_session_metadata(account: PlatformAccount) -> None:
    config = decrypt_json(account.credentials_encrypted)
    for key in ("xhs_login_username", "xhs_last_login_at", "xhs_last_seen_at"):
        config.pop(key, None)
    account.credentials_encrypted = encrypt_json(config)
    account.status = "LOGIN_REQUIRED"
    account.last_error = None


def _build_publish_hint(platform: str, caps: list[str], config: dict) -> str:
    """Return a short note describing what the connected platform can actually do."""
    if platform == "WEIBO":
        return "支持调用微博开放 API 自动发布图文内容。"
    if platform == "X":
        return "支持通过 X 官方 API 自动发布文字内容；图片上传尚未启用。"
    if platform == "XIAOHONGSHU":
        if not settings.experimental_browser_publishing_enabled:
            return "到点生成文案与图片交付包，由运营人员前往小红书创作中心人工发布。"
        return "实验性浏览器发布已启用；会话仅限本机使用，失败时回退人工交付。"
    if platform == "WECHAT_OFFICIAL":
        caps_set = set(caps)
        has_draft = bool(caps_set & WECHAT_DRAFT_CAPABILITIES)
        has_publish = WECHAT_PUBLISH_CAPABILITY in caps_set or config.get("allow_submit_publish")
        has_material = "MATERIAL_UPLOAD" in caps_set
        parts: list[str] = []
        if has_draft:
            parts.append("支持通过 API 同步到公众号草稿箱")
            if not has_material:
                parts.append("需预先配置默认封面素材 ID（素材上传接口无权限）")
        if has_publish:
            parts.append("支持通过 API 直接公开发布")
        if not has_draft and not has_publish:
            parts.append("当前账号 API 权限不足，无法创建草稿或提交发布")
        if has_draft and not has_publish:
            parts.append("不支持 API 直接公开发布")
        return "；".join(parts) if parts else "暂无可用发布能力"
    return ""


def upsert_account(
    db: Session, user: User, platform: str, payload: PlatformAccountUpsert
) -> PlatformAccount:
    account = get_platform_account(db, platform)
    if not account:
        account = PlatformAccount(
            user_id=user.id,
            updated_by=user.id,
            platform=platform,
            account_name=payload.account_name,
        )
        db.add(account)
    else:
        account.updated_by = user.id
    credentials_changed = bool(
        payload.app_secret
        or payload.app_id != account.app_id
        or (payload.client_id or payload.app_id) != account.client_id
        or payload.auth_type != account.auth_type
    )
    config = decrypt_json(account.credentials_encrypted)
    if platform == "X" and credentials_changed:
        config.pop("x_oauth_pending", None)
    config.update(
        {
            "redirect_uri": str(payload.redirect_uri)
            if payload.redirect_uri
            else config.get("redirect_uri"),
            "operation_ip": str(payload.operation_ip) if payload.operation_ip else None,
            "default_author": payload.default_author,
            "default_cover_media_id": payload.default_cover_media_id,
            "default_cover_url": str(payload.default_cover_url)
            if payload.default_cover_url
            else None,
            "allow_submit_publish": payload.allow_submit_publish,
            "allow_public_publish": payload.allow_public_publish,
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
        account.token_expires_at = None
        if credentials_changed and not payload.refresh_token:
            account.refresh_token_encrypted = None
    elif credentials_changed:
        account.access_token_encrypted = None
        account.refresh_token_encrypted = None
        account.token_expires_at = None
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
        if account.publish_mode == "MANUAL_CONFIRM":
            return "MANUAL_ONLY"
        if not settings.experimental_browser_publishing_enabled:
            return "MANUAL_ONLY"
        return "LOGIN_REQUIRED"  # must pass the local MCP login check before READY
    if account.platform == "WECHAT_OFFICIAL" and account.app_id:
        return "CONNECTING"
    if account.platform == "WEIBO" and account.client_id:
        return "CONNECTING"
    if account.platform == "X" and account.client_id:
        return "CONNECTING"
    return "NOT_CONFIGURED"


def account_validator(db: Session, account: PlatformAccount) -> PlatformPublisher:
    if account.platform == "WEIBO":
        return WeiboPublisher(db, account)
    if account.platform == "WECHAT_OFFICIAL":
        return WechatDraftPublisher(db, account)
    if account.platform == "X":
        return XPublisher(db, account)
    if not settings.experimental_browser_publishing_enabled:
        return XiaohongshuManualPublisher(account)
    return XiaohongshuMCPPublisher()  # type: ignore[return-value]


async def test_account(db: Session, account: PlatformAccount) -> PublishResult:
    if account.platform == "XIAOHONGSHU":
        checked_at = datetime.now()
        account.last_test_at = checked_at
        if (
            account.publish_mode == "MANUAL_CONFIRM"
            or not settings.experimental_browser_publishing_enabled
        ):
            account.status = "MANUAL_ONLY"
            account.publish_mode = "MANUAL_CONFIRM"
            account.capabilities_json = DEFAULT_CAPABILITIES["XIAOHONGSHU"]
            account.last_error = None
            result = PublishResult(
                True,
                account.platform,
                "MANUAL_CONFIRM",
                "MANUAL_ONLY",
                detail={"method": "manual_delivery"},
            )
            log_auth(db, account, "TEST_CONNECTION", "SUCCESS", "小红书人工交付已启用")
            db.flush()
            return result
        logged, info = await mcp_check_login()
        if logged:
            account.status = "CONNECTED"
            account.capabilities_json = ["COPYWRITING", "IMAGE_PACKAGE", "MCP_PUBLISH"]
            account.last_error = None
            _record_xhs_session(account, info, checked_at)
            result = PublishResult(
                True,
                account.platform,
                "MCP_PUBLISH",
                "CONNECTED",
                detail={"method": "mcp", "info": info},
            )
            log_auth(db, account, "TEST_CONNECTION", "SUCCESS", "xiaohongshu-mcp 连接正常")
            db.flush()
            return result
        account.status = "LOGIN_REQUIRED"
        account.last_error = f"xiaohongshu-mcp 未登录: {info}"
        result = PublishResult(
            False,
            account.platform,
            "MCP_PUBLISH",
            "LOGIN_REQUIRED",
            error_code="LOGIN_REQUIRED",
            error_message=f"xiaohongshu-mcp 未登录。{info}",
            suggested_action="启动 xiaohongshu-mcp 并完成扫码登录。",
        )
        log_auth(db, account, "TEST_CONNECTION", "FAILED", result.error_message)
        db.flush()
        return result
    account.status = "CONNECTING"
    db.flush()
    result = await account_validator(db, account).validate_credentials()
    account.last_test_at = datetime.now()
    account.last_error = result.error_message or None
    if result.success:
        account.status = "CONNECTED"
        if account.platform == "X":
            config = decrypt_json(account.credentials_encrypted)
            if result.external_id:
                config["x_user_id"] = result.external_id
            username = str(result.detail.get("username") or "")
            if username:
                config["x_username"] = username
            config["x_last_checked_at"] = account.last_test_at.isoformat()
            account.credentials_encrypted = encrypt_json(config)
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
