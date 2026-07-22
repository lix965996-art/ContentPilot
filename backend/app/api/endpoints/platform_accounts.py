from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode, urlparse

import httpx
import jwt
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.config import settings
from app.core.credentials import encrypt_secret
from app.core.exceptions import AppException
from app.core.responses import success_response
from app.db.session import get_db
from app.models.business import PlatformAccount, PlatformAuthLog
from app.models.user import User
from app.schemas.platform_account import Platform, PlatformAccountUpsert, WeiboOAuthStart
from app.services.audit_service import record_audit
from app.services.platform_account_service import (
    PLATFORMS,
    disconnect_account,
    get_owned_account,
    public_account,
    test_account,
    upsert_account,
)
from app.services.serializers import model_dict

router = APIRouter(prefix="/platform-accounts", tags=["平台账号"])


def _allowed_redirect(uri: str) -> bool:
    parsed = urlparse(uri)
    allowed_hosts = {urlparse(origin).hostname for origin in settings.cors_origin_list}
    return parsed.scheme in {"http", "https"} and parsed.hostname in allowed_hosts


@router.get("")
def list_accounts(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    accounts = {
        row.platform: row
        for row in db.scalars(
            select(PlatformAccount).where(PlatformAccount.user_id == user.id)
        ).all()
    }
    return success_response(
        request, [public_account(accounts.get(platform), platform) for platform in PLATFORMS]
    )


@router.put("/{platform}")
def save_account(
    platform: Platform,
    payload: PlatformAccountUpsert,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    if payload.redirect_uri and not _allowed_redirect(str(payload.redirect_uri)):
        raise AppException(40061, "Redirect URI 必须属于当前系统允许的前端来源")
    if platform == "XIAOHONGSHU" and payload.publish_mode not in {"MANUAL_CONFIRM", "MOCK"}:
        raise AppException(40062, "小红书仅允许人工确认或 Mock 模式")
    if platform == "WECHAT_OFFICIAL" and payload.publish_mode == "REAL_API":
        payload.publish_mode = "SUBMIT_PUBLISH"
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
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    account = get_owned_account(db, user, platform)
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
        request, {**public_account(account, platform), "result": result.as_dict()}
    )


@router.delete("/{platform}")
def disconnect(
    platform: Platform,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    account = get_owned_account(db, user, platform)
    if not account:
        raise AppException(40411, "平台账号尚未配置", 404)
    disconnect_account(db, account)
    record_audit(db, request, user, "DISCONNECT", "PLATFORM_ACCOUNT", "ACCOUNT", account.id)
    db.commit()
    return success_response(
        request, public_account(account, platform), "连接已解除，敏感凭证已清除"
    )


@router.get("/{platform}/auth-logs")
def auth_logs(
    platform: Platform,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    account = get_owned_account(db, user, platform)
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
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    redirect_uri = str(payload.redirect_uri)
    if not _allowed_redirect(redirect_uri):
        raise AppException(40061, "Redirect URI 不在允许列表中")
    account = get_owned_account(db, user, "WEIBO")
    if not account or not account.client_id:
        raise AppException(40063, "请先保存微博 App Key / Client ID")
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
) -> dict:
    try:
        payload = jwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.InvalidTokenError as exc:
        raise AppException(40064, "OAuth state 无效或已过期") from exc
    if payload.get("type") != "weibo_oauth_state" or not _allowed_redirect(payload["redirect_uri"]):
        raise AppException(40064, "OAuth state 校验失败")
    account = db.get(PlatformAccount, int(payload["account_id"]))
    if not account or account.user_id != int(payload["sub"]) or account.platform != "WEIBO":
        raise AppException(40302, "平台账号归属校验失败", 403)
    from app.core.credentials import decrypt_json

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
    return success_response(request, public_account(account, "WEIBO"), "微博授权成功")
