from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.credentials import decrypt_json, decrypt_secret, encrypt_secret
from app.models.business import PlatformAccount
from app.publishers.base import PublishResult
from app.publishers.official import OfficialPublisher
from app.services.platform_content import build_x_post


def _token_headers(account: PlatformAccount) -> dict[str, str]:
    secret = str(decrypt_json(account.credentials_encrypted).get("app_secret") or "")
    if not secret:
        return {}
    raw = f"{account.client_id or ''}:{secret}".encode()
    return {"Authorization": f"Basic {base64.b64encode(raw).decode('ascii')}"}


def store_x_token_response(account: PlatformAccount, data: dict[str, Any]) -> None:
    access_token = str(data.get("access_token") or "")
    if not access_token:
        raise ValueError("X OAuth 响应没有 access_token")
    account.access_token_encrypted = encrypt_secret(access_token)
    if data.get("refresh_token"):
        account.refresh_token_encrypted = encrypt_secret(str(data["refresh_token"]))
    if data.get("expires_in"):
        account.token_expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
            seconds=int(data["expires_in"])
        )
    else:
        account.token_expires_at = None
    account.status = "CONNECTED"
    account.last_error = None
    account.capabilities_json = ["TEXT_PUBLISH", "STATUS_READ"]


async def exchange_x_authorization_code(
    account: PlatformAccount,
    *,
    code: str,
    code_verifier: str,
    redirect_uri: str,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            settings.x_oauth_token_url,
            headers=_token_headers(account),
            data={
                "code": code,
                "grant_type": "authorization_code",
                "client_id": account.client_id,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            },
        )
    data = response.json()
    if not response.is_success or not data.get("access_token"):
        detail = data.get("error_description") or data.get("error") or response.status_code
        raise ValueError(f"X OAuth 授权失败：{detail}")
    return data


class XPublisher(OfficialPublisher):
    platform = "X"
    mode = "REAL_API"

    def __init__(self, db: Session, account: PlatformAccount) -> None:
        super().__init__(db, account)

    async def get_capabilities(self) -> list[str]:
        return ["TEXT_PUBLISH", "STATUS_READ"]

    async def disconnect(self) -> PublishResult:
        refresh_token = decrypt_secret(self.account.refresh_token_encrypted)
        access_token = decrypt_secret(self.account.access_token_encrypted)
        token = refresh_token or access_token
        if token:
            token_type_hint = "refresh_token" if refresh_token else "access_token"
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    response = await client.post(
                        f"{settings.x_api_base_url.rstrip('/')}/2/oauth2/revoke",
                        headers=_token_headers(self.account),
                        data={
                            "token": token,
                            "token_type_hint": token_type_hint,
                            "client_id": self.account.client_id,
                        },
                    )
                if not response.is_success:
                    try:
                        data = response.json()
                    except ValueError:
                        data = {}
                    detail = (
                        data.get("error_description") or data.get("error") or response.status_code
                    )
                    return self.failure(
                        "REVOKE_FAILED",
                        f"X 官方撤销授权失败：{detail}",
                        retryable=response.status_code >= 500,
                        action="请稍后重试；为避免遗留有效授权，本地凭证尚未删除。",
                    )
            except httpx.HTTPError as exc:
                return self.failure(
                    "NETWORK_ERROR",
                    f"X 官方撤销授权请求失败：{exc}",
                    retryable=True,
                    action="请稍后重试；为避免遗留有效授权，本地凭证尚未删除。",
                )
        self.account.access_token_encrypted = None
        self.account.refresh_token_encrypted = None
        self.account.token_expires_at = None
        self.account.status = "NOT_CONFIGURED"
        self.db.flush()
        return PublishResult(True, self.platform, self.mode, "DISCONNECTED")

    async def _refresh_access_token(self) -> tuple[str, PublishResult | None]:
        refresh_token = decrypt_secret(self.account.refresh_token_encrypted)
        if not refresh_token:
            return "", self.failure(
                "TOKEN_EXPIRED",
                "X 授权已过期，且没有可用的 Refresh Token。",
                action="请重新授权 X 账号。",
            )
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    settings.x_oauth_token_url,
                    headers=_token_headers(self.account),
                    data={
                        "refresh_token": refresh_token,
                        "grant_type": "refresh_token",
                        "client_id": self.account.client_id,
                    },
                )
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return "", self.failure("NETWORK_ERROR", str(exc), retryable=True)
        if not response.is_success or not data.get("access_token"):
            detail = str(data.get("error_description") or data.get("error") or response.status_code)
            return "", self.failure(
                "TOKEN_EXPIRED",
                f"X Token 刷新失败：{detail}",
                action="请重新授权 X 账号。",
            )
        store_x_token_response(self.account, data)
        self.db.flush()
        return str(data["access_token"]), None

    async def _access_token(
        self, *, force_refresh: bool = False
    ) -> tuple[str, PublishResult | None]:
        token = decrypt_secret(self.account.access_token_encrypted)
        expired = bool(
            self.account.token_expires_at
            and self.account.token_expires_at <= datetime.now(UTC).replace(tzinfo=None)
        )
        if force_refresh or expired or (not token and self.account.refresh_token_encrypted):
            return await self._refresh_access_token()
        if not token:
            return "", self.failure(
                "TOKEN_MISSING",
                "X Access Token 未配置。",
                action="请完成 X OAuth2 授权。",
            )
        return token, None

    def _api_failure(self, response: httpx.Response, data: dict[str, Any]) -> PublishResult:
        status_code = response.status_code
        detail = data.get("detail") or data.get("title") or data.get("error") or "X API 调用失败"
        if status_code == 401:
            code = "TOKEN_EXPIRED"
            action = "请重新授权 X 账号。"
        elif status_code == 403:
            code = "PERMISSION_DENIED"
            action = "请确认 X 应用已获得 tweet.write 权限且当前套餐允许发布。"
        elif status_code == 429:
            code = "RATE_LIMITED"
            action = "已触发 X 频率限制，请在限制解除后重试。"
        else:
            code = str(status_code)
            action = "请检查 X 开发者应用权限、套餐和网络后重试。"
        return self.failure(
            code,
            str(detail),
            retryable=status_code == 429,
            action=action,
        )

    async def _request_with_refresh(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> tuple[httpx.Response | None, dict[str, Any], PublishResult | None]:
        token, failure = await self._access_token()
        if failure:
            return None, {}, failure
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    response = await client.request(
                        method,
                        f"{settings.x_api_base_url.rstrip('/')}{path}",
                        headers={"Authorization": f"Bearer {token}"},
                        json=json,
                    )
                data = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                return (
                    None,
                    {},
                    self.failure(
                        "NETWORK_ERROR",
                        str(exc),
                        retryable=False,
                        action="请求结果不确定，请先在 X 账号中确认是否已发布，再决定是否重试。",
                    ),
                )
            if response.status_code != 401 or attempt == 1:
                return response, data, None
            token, failure = await self._access_token(force_refresh=True)
            if failure:
                return response, data, failure
        return response, data, None

    async def validate_credentials(self) -> PublishResult:
        response, data, failure = await self._request_with_refresh("GET", "/2/users/me")
        if failure:
            return failure
        if response and response.is_success and (data.get("data") or {}).get("id"):
            user = data["data"]
            return PublishResult(
                True,
                self.platform,
                self.mode,
                "CONNECTED",
                external_id=str(user["id"]),
                detail={"username": str(user.get("username") or "")},
            )
        assert response is not None
        return self._api_failure(response, data)

    async def publish(self, request: dict[str, Any]) -> PublishResult:
        text = build_x_post(
            request.get("title", ""),
            request.get("content", ""),
            request.get("hashtags", []),
        )
        if not text:
            return self.failure("CONTENT_EMPTY", "X 正文不能为空。")
        response, data, failure = await self._request_with_refresh(
            "POST", "/2/tweets", json={"text": text}
        )
        if failure:
            return failure
        external_id = str((data.get("data") or {}).get("id") or "")
        if response and response.is_success and external_id:
            return PublishResult(
                True,
                self.platform,
                self.mode,
                "PUBLISHED",
                external_id=external_id,
                published_url=f"https://x.com/i/web/status/{external_id}",
                detail={"real": True, "mediaUploaded": False},
            )
        assert response is not None
        return self._api_failure(response, data)

    async def query_status(self, task_id: str) -> dict[str, Any]:
        response, data, failure = await self._request_with_refresh("GET", f"/2/tweets/{task_id}")
        if failure:
            return {"error": failure.as_dict()}
        if response and response.is_success:
            return data
        assert response is not None
        return {"error": self._api_failure(response, data).as_dict()}
