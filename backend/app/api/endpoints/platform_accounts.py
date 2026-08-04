import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode, urlparse

import httpx
import jwt
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.config import settings
from app.core.credentials import decrypt_json, encrypt_json, encrypt_secret
from app.core.exceptions import AppException
from app.core.responses import success_response
from app.db.session import get_db
from app.models.business import PlatformAccount, PlatformAuthLog
from app.models.user import User
from app.publishers.toutiao_browser import get_login_qrcode
from app.publishers.toutiao_browser import logout as toutiao_logout
from app.publishers.wechat_browser import get_login_qrcode as get_wechat_login_qrcode
from app.publishers.wechat_browser import logout as wechat_logout
from app.publishers.x_official import (
    XPublisher,
    exchange_x_authorization_code,
    store_x_token_response,
)
from app.publishers.xhs_mcp import mcp_get_qrcode, mcp_logout
from app.schemas.platform_account import (
    Platform,
    PlatformAccountUpsert,
    WeiboOAuthStart,
    XOAuthStart,
)
from app.services.audit_service import record_audit
from app.services.platform_account_service import (
    PLATFORMS,
    clear_toutiao_session_metadata,
    clear_wechat_session_metadata,
    clear_xhs_session_metadata,
    disconnect_account,
    get_platform_account,
    public_account,
    record_toutiao_session,
    record_wechat_session,
    test_account,
    upsert_account,
)
from app.services.serializers import model_dict

router = APIRouter(prefix="/platform-accounts", tags=["平台账号"])


def _is_admin(user: User) -> bool:
    return any(role.code == "ADMIN" for role in user.roles)


def _allowed_redirect(uri: str) -> bool:
    parsed = urlparse(uri)
    allowed_hosts = {urlparse(origin).hostname for origin in settings.cors_origin_list}
    return parsed.scheme in {"http", "https"} and parsed.hostname in allowed_hosts


def _validate_return_origin(origin: str) -> str:
    parsed = urlparse(origin.strip())
    allowed_hosts = {urlparse(value).hostname for value in settings.cors_origin_list}
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.hostname not in allowed_hosts
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise AppException(40061, "前端返回地址不在系统允许的主机列表中")
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _return_origin(request: Request) -> str:
    return _validate_return_origin(
        request.headers.get("origin", "").strip() or settings.cors_origin_list[0]
    )


def _secret_is_available(account: PlatformAccount | None, submitted_secret: str | None) -> bool:
    return bool(
        submitted_secret
        or (account and decrypt_json(account.credentials_encrypted).get("app_secret"))
    )


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


@router.get("")
def list_accounts(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR", "VIEWER")),
) -> dict:
    accounts = {row.platform: row for row in db.scalars(select(PlatformAccount)).all()}
    return success_response(
        request,
        [
            public_account(
                accounts.get(platform),
                platform,
                include_configuration=_is_admin(user),
            )
            for platform in PLATFORMS
        ],
    )


@router.put("/{platform}")
def save_account(
    platform: Platform,
    payload: PlatformAccountUpsert,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> dict:
    if payload.redirect_uri and not _allowed_redirect(str(payload.redirect_uri)):
        raise AppException(40061, "Redirect URI 必须属于当前系统允许的前端来源")
    existing = get_platform_account(db, platform)
    xhs_modes = {"MANUAL_CONFIRM", "MCP_PUBLISH"}
    if platform == "XIAOHONGSHU" and payload.publish_mode not in xhs_modes:
        raise AppException(40062, "小红书仅支持本地 MCP 发布或人工确认")
    if (
        platform == "XIAOHONGSHU"
        and payload.publish_mode == "MCP_PUBLISH"
        and not settings.experimental_browser_publishing_enabled
    ):
        raise AppException(40064, "本地 MCP 发布默认关闭，请使用人工交付模式")
    if platform == "WEIBO":
        if payload.publish_mode != "REAL_API":
            raise AppException(40062, "微博只允许使用真实 OAuth 官方接口")
        if not payload.client_id or not _secret_is_available(existing, payload.app_secret):
            raise AppException(40063, "请填写微博开放平台真实 App Key 和 App Secret")
    if platform == "X":
        if payload.auth_type != "OAUTH2" or payload.publish_mode != "REAL_API":
            raise AppException(40062, "X 只允许使用 OAuth2 官方接口")
        if not payload.client_id or not _secret_is_available(existing, payload.app_secret):
            raise AppException(40063, "请填写 X Developer Portal 的 Client ID 和 Client Secret")
    if platform == "TOUTIAO":
        if payload.auth_type != "QR_LOGIN" or payload.publish_mode != "BROWSER_PUBLISH":
            raise AppException(40062, "今日头条只支持本机扫码登录与浏览器发布")
        if not settings.toutiao_browser_publishing_enabled:
            raise AppException(40064, "今日头条本机浏览器发布功能已关闭")
    if platform == "WECHAT_OFFICIAL" and payload.publish_mode == "REAL_API":
        payload.publish_mode = "SUBMIT_PUBLISH"
    if platform == "WECHAT_OFFICIAL":
        if payload.publish_mode == "BROWSER_DRAFT":
            if payload.auth_type != "QR_LOGIN":
                raise AppException(40062, "公众号本机草稿模式必须使用扫码登录")
            if not settings.wechat_browser_publishing_enabled:
                raise AppException(40064, "微信公众号本机扫码登录功能已关闭")
        else:
            if payload.publish_mode not in {"DRAFT_ONLY", "SUBMIT_PUBLISH"}:
                raise AppException(40062, "微信公众号只允许真实草稿或真实提交发布")
            if payload.auth_type != "APP_SECRET":
                raise AppException(40062, "公众号官方 API 必须使用 AppID/AppSecret")
            if not payload.app_id or not _secret_is_available(existing, payload.app_secret):
                raise AppException(40063, "请填写微信公众号后台真实 AppID 和 AppSecret")
    account = upsert_account(db, user, platform, payload)
    record_audit(db, request, user, "CONFIGURE", "PLATFORM_ACCOUNT", "ACCOUNT", account.id)
    db.commit()
    db.refresh(account)
    return success_response(request, public_account(account, platform), "平台账号配置已保存")


@router.post("/{platform}/test")
async def test_connection(
    platform: Platform,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> dict:
    account = get_platform_account(db, platform)
    if not account:
        raise AppException(40411, "平台账号尚未配置", 404)
    result = await test_account(db, account)
    record_audit(
        db,
        request,
        user,
        "TEST_CONNECTION",
        "PLATFORM_ACCOUNT",
        "ACCOUNT",
        account.id,
        {"success": result.success, "errorCode": result.error_code},
    )
    db.commit()
    return success_response(
        request,
        {
            **public_account(
                account,
                platform,
                include_configuration=_is_admin(user),
            ),
            "result": result.as_dict(),
        },
    )


@router.post("/XIAOHONGSHU/login-qrcode")
async def xiaohongshu_login_qrcode(
    request: Request,
    _: User = Depends(require_roles("ADMIN")),
) -> dict:
    if not settings.experimental_browser_publishing_enabled:
        raise AppException(40064, "小红书本地 MCP 发布未启用")
    result = await mcp_get_qrcode()
    image_data_url = result.get("image_data_url", "")
    if not image_data_url:
        raise AppException(
            50211,
            result.get("message") or "xiaohongshu-mcp 未返回登录二维码",
            502,
        )
    return success_response(
        request,
        {
            "imageDataUrl": image_data_url,
            "message": result.get("message", ""),
            "expiresInSeconds": 240,
        },
        "请使用小红书 App 扫码登录",
    )


@router.post("/XIAOHONGSHU/logout")
async def xiaohongshu_logout(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> dict:
    if not settings.experimental_browser_publishing_enabled:
        raise AppException(40064, "小红书本地 MCP 发布未启用")
    success, detail = await mcp_logout()
    if not success:
        raise AppException(50212, f"退出小红书登录失败：{detail}", 502)
    account = get_platform_account(db, "XIAOHONGSHU")
    if account:
        clear_xhs_session_metadata(account)
        record_audit(
            db,
            request,
            user,
            "LOGOUT",
            "PLATFORM_ACCOUNT",
            "ACCOUNT",
            account.id,
        )
        db.commit()
        db.refresh(account)
    return success_response(
        request,
        public_account(account, "XIAOHONGSHU"),
        "小红书本地登录已退出，可以重新扫码登录",
    )


@router.post("/TOUTIAO/login-qrcode")
async def toutiao_login_qrcode(
    request: Request,
    refresh: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> dict:
    if not settings.toutiao_browser_publishing_enabled:
        raise AppException(40064, "今日头条本机浏览器发布功能已关闭")
    account = get_platform_account(db, "TOUTIAO")
    if not account:
        raise AppException(40411, "请先保存今日头条账号配置", 404)
    result = await get_login_qrcode(account.id, force_refresh=refresh)
    if result.get("connected"):
        checked_at = datetime.now()
        account.status = "CONNECTED"
        account.last_test_at = checked_at
        account.last_error = None
        record_toutiao_session(account, str(result.get("username") or ""), checked_at)
        db.commit()
        return success_response(
            request,
            {
                "connected": True,
                "imageDataUrl": "",
                "message": result.get("message", ""),
                "expiresInSeconds": 0,
            },
            "今日头条账号已登录",
        )
    image_data_url = str(result.get("image_data_url") or "")
    if not image_data_url:
        raise AppException(50214, str(result.get("message") or "未获取到登录二维码"), 502)
    return success_response(
        request,
        {
            "connected": False,
            "imageDataUrl": image_data_url,
            "message": result.get("message", ""),
            "expiresInSeconds": 120,
        },
        "请扫码登录今日头条",
    )


@router.post("/WECHAT_OFFICIAL/login-qrcode")
async def wechat_login_qrcode(
    request: Request,
    refresh: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> dict:
    if not settings.wechat_browser_publishing_enabled:
        raise AppException(40064, "微信公众号本机扫码登录功能已关闭")
    account = get_platform_account(db, "WECHAT_OFFICIAL")
    if not account or account.publish_mode != "BROWSER_DRAFT":
        raise AppException(40411, "请先保存微信公众号本机扫码配置", 404)
    result = await get_wechat_login_qrcode(account.id, force_refresh=refresh)
    if result.get("connected"):
        checked_at = datetime.now()
        account.status = "CONNECTED"
        account.last_test_at = checked_at
        account.last_error = None
        record_wechat_session(account, str(result.get("username") or ""), checked_at)
        db.commit()
        return success_response(
            request,
            {
                "connected": True,
                "imageDataUrl": "",
                "message": result.get("message", ""),
                "expiresInSeconds": 0,
            },
            "微信公众号账号已登录",
        )
    image_data_url = str(result.get("image_data_url") or "")
    if not image_data_url:
        raise AppException(50216, str(result.get("message") or "未获取到登录二维码"), 502)
    return success_response(
        request,
        {
            "connected": False,
            "imageDataUrl": image_data_url,
            "message": result.get("message", ""),
            "expiresInSeconds": 240,
        },
        "请扫码登录微信公众号",
    )


@router.post("/WECHAT_OFFICIAL/logout")
async def wechat_account_logout(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> dict:
    account = get_platform_account(db, "WECHAT_OFFICIAL")
    if not account:
        raise AppException(40411, "微信公众号账号尚未配置", 404)
    ok, detail = await wechat_logout(account.id)
    if not ok:
        raise AppException(50217, detail, 502)
    clear_wechat_session_metadata(account)
    record_audit(db, request, user, "LOGOUT", "PLATFORM_ACCOUNT", "ACCOUNT", account.id)
    db.commit()
    db.refresh(account)
    return success_response(
        request,
        public_account(account, "WECHAT_OFFICIAL"),
        "微信公众号本机登录已退出，可以重新扫码",
    )


@router.post("/TOUTIAO/logout")
async def toutiao_account_logout(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> dict:
    account = get_platform_account(db, "TOUTIAO")
    if not account:
        raise AppException(40411, "今日头条账号尚未配置", 404)
    ok, detail = await toutiao_logout(account.id)
    if not ok:
        raise AppException(50215, detail, 502)
    clear_toutiao_session_metadata(account)
    record_audit(db, request, user, "LOGOUT", "PLATFORM_ACCOUNT", "ACCOUNT", account.id)
    db.commit()
    db.refresh(account)
    return success_response(
        request,
        public_account(account, "TOUTIAO"),
        "今日头条本机登录已退出，可以重新扫码",
    )


@router.delete("/{platform}")
async def disconnect(
    platform: Platform,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> dict:
    account = get_platform_account(db, platform)
    if not account:
        raise AppException(40411, "平台账号尚未配置", 404)
    if platform == "XIAOHONGSHU" and settings.experimental_browser_publishing_enabled:
        logged_out, detail = await mcp_logout()
        if not logged_out:
            raise AppException(50212, f"无法清除小红书本地登录：{detail}", 502)
    if platform == "TOUTIAO" and settings.toutiao_browser_publishing_enabled:
        logged_out, detail = await toutiao_logout(account.id)
        if not logged_out:
            raise AppException(50215, detail, 502)
    if platform == "WECHAT_OFFICIAL" and account.publish_mode == "BROWSER_DRAFT":
        logged_out, detail = await wechat_logout(account.id)
        if not logged_out:
            raise AppException(50217, detail, 502)
    if platform == "X":
        revoked = await XPublisher(db, account).disconnect()
        if not revoked.success:
            raise AppException(50213, revoked.error_message or "X 官方撤销授权失败", 502)
    account_id = account.id
    disconnect_account(db, account)
    record_audit(db, request, user, "DISCONNECT", "PLATFORM_ACCOUNT", "ACCOUNT", account_id)
    db.delete(account)
    db.commit()
    return success_response(
        request, public_account(None, platform), "连接与账号配置已删除，敏感凭证已清除"
    )


@router.get("/{platform}/auth-logs")
def auth_logs(
    platform: Platform,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> dict:
    account = get_platform_account(db, platform)
    if not account:
        return success_response(request, [])
    rows = db.scalars(
        select(PlatformAuthLog)
        .where(PlatformAuthLog.platform_account_id == account.id)
        .order_by(PlatformAuthLog.created_at.desc())
        .limit(100)
    ).all()
    return success_response(request, [model_dict(row, camel=True) for row in rows])


@router.post("/WEIBO/oauth/start")
def weibo_oauth_start(
    payload: WeiboOAuthStart,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> dict:
    redirect_uri = str(payload.redirect_uri)
    if not _allowed_redirect(redirect_uri):
        raise AppException(40061, "Redirect URI 不在允许列表中")
    account = get_platform_account(db, "WEIBO")
    if not account or not account.client_id:
        raise AppException(40063, "请先保存微博开放平台 App Key")
    if not decrypt_json(account.credentials_encrypted).get("app_secret"):
        raise AppException(40063, "请先保存微博开放平台 App Secret")
    now = datetime.now(UTC)
    state = jwt.encode(
        {
            "sub": str(user.id),
            "type": "weibo_oauth_state",
            "account_id": account.id,
            "redirect_uri": redirect_uri,
            "iat": now,
            "exp": now + timedelta(minutes=10),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    query = urlencode(
        {
            "client_id": account.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "state": state,
        }
    )
    return success_response(
        request, {"authorizationUrl": f"{settings.weibo_api_base_url}/oauth2/authorize?{query}"}
    )


@router.get("/WEIBO/oauth/callback")
async def weibo_oauth_callback(
    request: Request,
    code: str = Query(min_length=1),
    state: str = Query(min_length=20),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        payload = jwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.InvalidTokenError as exc:
        raise AppException(40064, "OAuth state 无效或已过期") from exc
    if payload.get("type") != "weibo_oauth_state" or not _allowed_redirect(payload["redirect_uri"]):
        raise AppException(40064, "OAuth state 校验失败")
    account = db.get(PlatformAccount, int(payload["account_id"]))
    actor = db.get(User, int(payload["sub"]))
    if (
        not account
        or account.platform != "WEIBO"
        or not actor
        or actor.status != "ACTIVE"
        or not _is_admin(actor)
    ):
        raise AppException(40302, "平台账号授权人校验失败", 403)
    config = decrypt_json(account.credentials_encrypted)
    secret = config.get("app_secret")
    if not secret:
        raise AppException(40063, "微博 App Secret 未配置")
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{settings.weibo_api_base_url}/oauth2/access_token",
            data={
                "client_id": account.client_id,
                "client_secret": secret,
                "grant_type": "authorization_code",
                "redirect_uri": payload["redirect_uri"],
                "code": code,
            },
        )
    data = response.json()
    if not response.is_success or not data.get("access_token"):
        raise AppException(40065, str(data.get("error_description") or "微博 OAuth 授权失败"))
    account.access_token_encrypted = encrypt_secret(str(data["access_token"]))
    if data.get("refresh_token"):
        account.refresh_token_encrypted = encrypt_secret(str(data["refresh_token"]))
    if data.get("expires_in"):
        account.token_expires_at = datetime.now() + timedelta(seconds=int(data["expires_in"]))
    account.status = "CONNECTED"
    account.last_error = None
    db.add(
        PlatformAuthLog(
            platform_account_id=account.id,
            action="OAUTH_CALLBACK",
            status="SUCCESS",
            message="微博 OAuth 授权成功",
            detail_json={"uid": str(data.get("uid", ""))},
        )
    )
    db.commit()
    frontend_origin = settings.cors_origin_list[0].rstrip("/")
    return RedirectResponse(
        f"{frontend_origin}/platform-accounts?oauth=weibo_success", status_code=302
    )


@router.post("/X/oauth/start")
def x_oauth_start(
    payload: XOAuthStart,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> dict:
    redirect_uri = str(payload.redirect_uri)
    if not _allowed_redirect(redirect_uri):
        raise AppException(40061, "Redirect URI 不在系统允许列表中")
    account = get_platform_account(db, "X")
    if not account or not account.client_id:
        raise AppException(40063, "请先保存 X Client ID")
    config = decrypt_json(account.credentials_encrypted)
    if not config.get("app_secret"):
        raise AppException(40063, "请先保存 X Client Secret")

    now = datetime.now(UTC)
    return_origin = _return_origin(request)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    config["x_oauth_pending"] = {
        "nonce": nonce,
        "code_verifier": verifier,
        "redirect_uri": redirect_uri,
        "return_origin": return_origin,
        "expires_at": (now + timedelta(minutes=10)).isoformat(),
    }
    account.credentials_encrypted = encrypt_json(config)

    state = jwt.encode(
        {
            "sub": str(user.id),
            "type": "x_oauth_state",
            "account_id": account.id,
            "nonce": nonce,
            "redirect_uri": redirect_uri,
            "return_origin": return_origin,
            "iat": now,
            "exp": now + timedelta(minutes=10),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    query = urlencode(
        {
            "response_type": "code",
            "client_id": account.client_id,
            "redirect_uri": redirect_uri,
            "scope": "tweet.read tweet.write users.read offline.access",
            "state": state,
            "code_challenge": _pkce_challenge(verifier),
            "code_challenge_method": "S256",
        }
    )
    log = PlatformAuthLog(
        platform_account_id=account.id,
        action="OAUTH_START",
        status="SUCCESS",
        message="X OAuth2 + PKCE 授权已开始",
    )
    db.add(log)
    db.commit()
    return success_response(
        request,
        {"authorizationUrl": f"{settings.x_oauth_authorize_url}?{query}"},
    )


@router.get("/X/oauth/callback")
async def x_oauth_callback(
    request: Request,
    code: str = Query(min_length=1),
    state: str = Query(min_length=20),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        payload = jwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.InvalidTokenError as exc:
        raise AppException(40064, "X OAuth state 无效或已过期") from exc
    if payload.get("type") != "x_oauth_state":
        raise AppException(40064, "X OAuth state 校验失败")

    redirect_uri = str(payload.get("redirect_uri") or "")
    if not _allowed_redirect(redirect_uri):
        raise AppException(40064, "X OAuth 回调地址校验失败")
    account = db.get(PlatformAccount, int(payload["account_id"]))
    actor = db.get(User, int(payload["sub"]))
    if (
        not account
        or account.platform != "X"
        or not actor
        or actor.status != "ACTIVE"
        or not _is_admin(actor)
    ):
        raise AppException(40302, "X 平台账号授权人校验失败", 403)

    config = decrypt_json(account.credentials_encrypted)
    pending = config.get("x_oauth_pending")
    if not isinstance(pending, dict):
        raise AppException(40064, "X OAuth 请求已使用或不存在")
    try:
        pending_expiry = datetime.fromisoformat(str(pending["expires_at"]))
        if pending_expiry.tzinfo is None:
            pending_expiry = pending_expiry.replace(tzinfo=UTC)
    except (KeyError, TypeError, ValueError) as exc:
        raise AppException(40064, "X OAuth 临时状态无效") from exc
    if (
        pending.get("nonce") != payload.get("nonce")
        or pending.get("redirect_uri") != redirect_uri
        or pending.get("return_origin") != payload.get("return_origin")
        or pending_expiry <= datetime.now(UTC)
    ):
        raise AppException(40064, "X OAuth 临时状态不匹配或已过期")
    verifier = str(pending.get("code_verifier") or "")
    if not verifier:
        raise AppException(40064, "X OAuth PKCE verifier 不存在")

    # Consume the nonce before exchanging the code. A callback cannot be replayed,
    # even if the provider request fails after this point.
    config.pop("x_oauth_pending", None)
    account.credentials_encrypted = encrypt_json(config)
    db.commit()
    try:
        token_data = await exchange_x_authorization_code(
            account,
            code=code,
            code_verifier=verifier,
            redirect_uri=redirect_uri,
        )
    except (httpx.HTTPError, ValueError) as exc:
        db.add(
            PlatformAuthLog(
                platform_account_id=account.id,
                action="OAUTH_CALLBACK",
                status="FAILED",
                message=str(exc)[:500],
            )
        )
        db.commit()
        raise AppException(40065, str(exc)) from exc

    store_x_token_response(account, token_data)
    config = decrypt_json(account.credentials_encrypted)
    config["x_authorized_at"] = datetime.now(UTC).replace(tzinfo=None).isoformat()
    account.credentials_encrypted = encrypt_json(config)
    db.add(
        PlatformAuthLog(
            platform_account_id=account.id,
            action="OAUTH_CALLBACK",
            status="SUCCESS",
            message="X OAuth2 授权成功",
            detail_json={
                "scope": str(token_data.get("scope") or ""),
                "tokenType": str(token_data.get("token_type") or ""),
            },
        )
    )
    db.commit()
    return_origin = _validate_return_origin(str(payload.get("return_origin") or ""))
    return RedirectResponse(f"{return_origin}/platform-accounts?oauth=x_success", status_code=302)


# ── WeChat diagnostic probe ────────────────────────────────────────────
@router.post("/diagnostic/wechat")
async def wechat_diagnostic_test(
    request: Request,
    _: User = Depends(require_roles("ADMIN")),
) -> dict:
    """Probe every WeChat API dependency and report what works.

    Reads credentials from the JSON body (preferred) or falls back to
    ``WECHAT_APP_ID`` / ``WECHAT_APP_SECRET`` environment variables.
    """
    body: dict[str, object] = {}
    try:
        body = await request.json() or {}
    except Exception:
        pass

    app_id = str(body.get("app_id") or settings.wechat_app_id or "")
    app_secret = str(body.get("app_secret") or settings.wechat_app_secret or "")

    result: dict[str, object] = {
        "app_id_provided": bool(app_id),
        "app_secret_provided": bool(app_secret),
        "public_ip": "",
        "token": {"ok": False, "errcode": None, "errmsg": None, "access_token_hint": ""},
        "drafts": {"ok": False, "errcode": None, "errmsg": None, "total_count": 0},
        "material_upload": {"ok": False, "errcode": None, "errmsg": None},
        "final_capabilities": {
            "draft_create": False,
            "draft_update": False,
            "draft_read": False,
            "draft_delete": False,
            "direct_publish": False,
        },
    }

    # ── public IP ──
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            ip_resp = await client.get("https://api.ipify.org")
            result["public_ip"] = ip_resp.text.strip()
    except Exception:
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                ip_resp = await client.get("https://ip.sb")
                result["public_ip"] = ip_resp.text.strip()
        except Exception:
            result["public_ip"] = "unknown"

    if not app_id or not app_secret:
        result["token"]["errmsg"] = "未提供 AppID 或 AppSecret"
        return success_response(request, result, "缺少公众号凭证，无法执行诊断")

    # ── token ──
    token: str = ""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{settings.wechat_api_base_url}/cgi-bin/token",
                params={
                    "grant_type": "client_credential",
                    "appid": app_id,
                    "secret": app_secret,
                },
            )
        data = resp.json()
        errcode = data.get("errcode", 0)
        result["token"]["errcode"] = errcode
        result["token"]["errmsg"] = data.get("errmsg", "")
        if errcode == 0:
            token = str(data.get("access_token", ""))
            result["token"]["ok"] = True
            result["token"]["access_token_hint"] = token[:6] + "****" + token[-4:]
        else:
            return success_response(request, result, "Access Token 获取失败，无法继续诊断")
    except Exception as exc:
        result["token"]["errmsg"] = str(exc)
        return success_response(request, result, "Access Token 请求网络异常")

    # ── drafts ──
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{settings.wechat_api_base_url}/cgi-bin/draft/count",
                params={"access_token": token},
            )
        draft_data = resp.json()
        draft_errcode = draft_data.get("errcode", 0)
        result["drafts"]["errcode"] = draft_errcode
        result["drafts"]["errmsg"] = draft_data.get("errmsg", "")
        if draft_errcode == 0:
            result["drafts"]["ok"] = True
            result["drafts"]["total_count"] = draft_data.get("total_count", 0)
            result["final_capabilities"]["draft_create"] = True
            result["final_capabilities"]["draft_update"] = True
            result["final_capabilities"]["draft_read"] = True
            result["final_capabilities"]["draft_delete"] = True
    except Exception as exc:
        result["drafts"]["errmsg"] = str(exc)

    # ── material upload ──
    minimal_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
        b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{settings.wechat_api_base_url}/cgi-bin/material/add_material",
                params={"access_token": token, "type": "thumb"},
                files={"media": ("_probe.png", minimal_png, "image/png")},
            )
        mat_data = resp.json()
        mat_errcode = mat_data.get("errcode", 0)
        result["material_upload"]["errcode"] = mat_errcode
        result["material_upload"]["errmsg"] = mat_data.get("errmsg", "")
        if mat_errcode == 0:
            result["material_upload"]["ok"] = True
    except Exception as exc:
        result["material_upload"]["errmsg"] = str(exc)

    return success_response(request, result, "微信诊断完成")
