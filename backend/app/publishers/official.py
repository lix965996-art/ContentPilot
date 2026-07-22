from __future__ import annotations

import html
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import BACKEND_DIR, settings
from app.core.credentials import decrypt_json, decrypt_secret, encrypt_secret
from app.models.business import PlatformAccount
from app.publishers.base import PublishResult


class OfficialPublisher:
    platform = "UNCONFIGURED"
    mode = "REAL_API"

    def __init__(self, db: Session, account: PlatformAccount) -> None:
        self.db = db
        self.account = account
        self.config = decrypt_json(account.credentials_encrypted)

    async def get_capabilities(self) -> list[str]:
        return list(self.account.capabilities_json or [])

    async def disconnect(self) -> PublishResult:
        self.account.access_token_encrypted = None
        self.account.refresh_token_encrypted = None
        self.account.token_expires_at = None
        self.account.status = "NOT_CONFIGURED"
        self.db.flush()
        return PublishResult(True, self.platform, self.mode, "DISCONNECTED")

    def failure(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        action: str = "检查平台账号配置后重试。",
    ) -> PublishResult:
        return PublishResult(
            False,
            self.platform,
            self.mode,
            "FAILED",
            retryable=retryable,
            error_code=code,
            error_message=message,
            suggested_action=action,
        )


class WeiboPublisher(OfficialPublisher):
    platform = "WEIBO"

    async def validate_credentials(self) -> PublishResult:
        token = decrypt_secret(self.account.access_token_encrypted)
        if not token:
            return self.failure(
                "TOKEN_MISSING", "微博 Access Token 未配置。", action="请完成 OAuth 授权。"
            )
        if self.account.token_expires_at and self.account.token_expires_at <= datetime.now():
            return self.failure("TOKEN_EXPIRED", "微博授权已过期。", action="请重新授权微博账号。")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    f"{settings.weibo_api_base_url}/2/account/get_uid.json",
                    params={"access_token": token},
                )
            data = response.json()
            if response.is_success and data.get("uid"):
                return PublishResult(
                    True,
                    self.platform,
                    self.mode,
                    "CONNECTED",
                    external_id=str(data["uid"]),
                )
            return self._api_failure(data, response.status_code)
        except (httpx.HTTPError, ValueError) as exc:
            return self.failure("NETWORK_ERROR", str(exc), retryable=True)

    async def get_capabilities(self) -> list[str]:
        return ["TEXT_PUBLISH", "IMAGE_PUBLISH", "STATUS_READ"]

    def _api_failure(self, data: dict[str, Any], status_code: int) -> PublishResult:
        code = str(data.get("error_code") or status_code)
        message = str(data.get("error") or "微博接口调用失败")
        token_error = code in {"21314", "21315", "21327", "21332"}
        permission_error = code in {"10014", "10022", "20016"}
        return self.failure(
            "TOKEN_EXPIRED" if token_error else "PERMISSION_DENIED" if permission_error else code,
            message,
            retryable=status_code >= 500,
            action="请重新授权微博账号。"
            if token_error
            else "请检查应用发布权限和微博开放平台审核状态。",
        )

    async def publish(self, request: dict[str, Any]) -> PublishResult:
        token = decrypt_secret(self.account.access_token_encrypted)
        if not token:
            return self.failure("TOKEN_MISSING", "微博 Access Token 未配置。")
        endpoint = "/2/statuses/upload.json" if request.get("images") else "/2/statuses/share.json"
        payload = {"access_token": token, "status": request["content"]}
        files = None
        image = _first_readable_image(request.get("images", []))
        if image:
            files = {"pic": (image.name, image.read_bytes(), "application/octet-stream")}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{settings.weibo_api_base_url}{endpoint}", data=payload, files=files
                )
            data = response.json()
            external_id = str(data.get("idstr") or data.get("id") or "")
            if response.is_success and external_id:
                user_id = str((data.get("user") or {}).get("idstr") or "")
                url = f"https://weibo.com/{user_id}/{external_id}" if user_id else ""
                return PublishResult(
                    True,
                    self.platform,
                    self.mode,
                    "SUCCESS",
                    external_id,
                    url,
                    detail={"real": True},
                )
            return self._api_failure(data, response.status_code)
        except (httpx.HTTPError, ValueError, OSError) as exc:
            return self.failure("NETWORK_ERROR", str(exc), retryable=True)

    async def query_status(self, task_id: str) -> dict[str, Any]:
        token = decrypt_secret(self.account.access_token_encrypted)
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"{settings.weibo_api_base_url}/2/statuses/show.json",
                params={"access_token": token, "id": task_id},
            )
        return response.json()


class WechatDraftPublisher(OfficialPublisher):
    platform = "WECHAT_OFFICIAL"
    mode = "DRAFT_ONLY"

    async def get_capabilities(self) -> list[str]:
        base = ["MATERIAL_UPLOAD", "DRAFT_CREATE"]
        if self.config.get("allow_submit_publish"):
            base.append("SUBMIT_PUBLISH")
        return base

    async def _access_token(self) -> str:
        cached = decrypt_secret(self.account.access_token_encrypted)
        if cached and self.account.token_expires_at:
            if self.account.token_expires_at > datetime.now() + timedelta(minutes=2):
                return cached
        app_secret = self.config.get("app_secret")
        if not self.account.app_id or not app_secret:
            raise ValueError("微信公众号 AppID/AppSecret 未配置")
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"{settings.wechat_api_base_url}/cgi-bin/token",
                params={
                    "grant_type": "client_credential",
                    "appid": self.account.app_id,
                    "secret": app_secret,
                },
            )
        data = response.json()
        if data.get("errcode"):
            raise WechatApiError(data)
        token = str(data["access_token"])
        self.account.access_token_encrypted = encrypt_secret(token)
        self.account.token_expires_at = datetime.now() + timedelta(
            seconds=max(60, int(data.get("expires_in", 7200)) - 120)
        )
        self.db.flush()
        return token

    async def validate_credentials(self) -> PublishResult:
        try:
            await self._access_token()
            return PublishResult(True, self.platform, self.mode, "CONNECTED")
        except WechatApiError as exc:
            return self.failure(exc.code, exc.message, action=exc.suggested_action)
        except (httpx.HTTPError, ValueError) as exc:
            return self.failure(
                "CONNECTION_FAILED", str(exc), retryable=isinstance(exc, httpx.HTTPError)
            )

    async def _upload_image(self, token: str, path: Path, *, permanent: bool) -> str:
        endpoint = "/cgi-bin/material/add_material" if permanent else "/cgi-bin/media/uploadimg"
        params = {"access_token": token}
        if permanent:
            params["type"] = "thumb"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{settings.wechat_api_base_url}{endpoint}",
                params=params,
                files={"media": (path.name, path.read_bytes(), "application/octet-stream")},
            )
        data = response.json()
        if data.get("errcode"):
            raise WechatApiError(data)
        value = data.get("media_id") if permanent else data.get("url")
        if not value:
            raise ValueError("微信图片上传未返回素材标识")
        return str(value)

    async def publish(self, request: dict[str, Any]) -> PublishResult:
        if self.account.publish_mode == "MOCK" or request.get("dry_run"):
            draft_id = f"mock-draft-{request['schedule_id']}"
            return PublishResult(
                True,
                self.platform,
                "MOCK",
                "MOCK_DRAFT_CREATED",
                external_id=draft_id,
                detail={"draftId": draft_id, "simulated": True},
            )
        try:
            token = await self._access_token()
            images = [path for value in request.get("images", []) if (path := _local_image(value))]
            thumb_media_id = str(self.config.get("default_cover_media_id") or "")
            if not thumb_media_id and images:
                thumb_media_id = await self._upload_image(token, images[0], permanent=True)
            if not thumb_media_id and self.config.get("default_cover_url"):
                thumb_media_id = await self._upload_image_url(
                    token, str(self.config["default_cover_url"]), permanent=True
                )
            if not thumb_media_id:
                raise ValueError("请配置默认封面素材 ID，或为文章选择一张本地图片")
            body_html = markdown_to_wechat_html(request["content"])
            for path in images[1:]:
                image_url = await self._upload_image(token, path, permanent=False)
                body_html += f'<p><img src="{html.escape(image_url)}" /></p>'
            article = {
                "title": request["title"][:64],
                "author": self.config.get("default_author", "")[:16],
                "digest": request.get("summary", "")[:120],
                "content": body_html,
                "content_source_url": request.get("source_url", ""),
                "thumb_media_id": thumb_media_id,
                "need_open_comment": 0,
                "only_fans_can_comment": 0,
            }
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{settings.wechat_api_base_url}/cgi-bin/draft/add",
                    params={"access_token": token},
                    json={"articles": [article]},
                )
            data = response.json()
            if data.get("errcode"):
                raise WechatApiError(data)
            draft_id = str(data.get("media_id") or "")
            if not draft_id:
                raise ValueError("微信草稿接口未返回 media_id")
            return PublishResult(
                True,
                self.platform,
                self.mode,
                "DRAFT_CREATED",
                external_id=draft_id,
                detail={"draftId": draft_id, "real": True},
            )
        except WechatApiError as exc:
            return self.failure(
                exc.code, exc.message, retryable=exc.retryable, action=exc.suggested_action
            )
        except (httpx.HTTPError, ValueError, OSError) as exc:
            return self.failure(
                "WECHAT_DRAFT_FAILED", str(exc), retryable=isinstance(exc, httpx.HTTPError)
            )

    async def query_status(self, task_id: str) -> dict[str, Any]:
        return {"media_id": task_id, "status": "DRAFT_CREATED"}

    async def _upload_image_url(self, token: str, url: str, *, permanent: bool) -> str:
        local = _local_image(url)
        if local:
            return await self._upload_image(token, local, permanent=permanent)
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("image/") or len(response.content) > 10 * 1024 * 1024:
            raise ValueError("默认封面 URL 必须返回不超过 10MB 的图片")
        endpoint = "/cgi-bin/material/add_material" if permanent else "/cgi-bin/media/uploadimg"
        params = {"access_token": token}
        if permanent:
            params["type"] = "thumb"
        async with httpx.AsyncClient(timeout=30) as client:
            upload = await client.post(
                f"{settings.wechat_api_base_url}{endpoint}",
                params=params,
                files={"media": ("cover.jpg", response.content, content_type)},
            )
        data = upload.json()
        if data.get("errcode"):
            raise WechatApiError(data)
        value = data.get("media_id") if permanent else data.get("url")
        if not value:
            raise ValueError("微信图片上传未返回素材标识")
        return str(value)


class WechatPublishPublisher(WechatDraftPublisher):
    mode = "REAL_API"

    async def publish(self, request: dict[str, Any]) -> PublishResult:
        if not self.config.get("allow_submit_publish"):
            return self.failure(
                "PUBLISH_NOT_ALLOWED",
                "该公众号配置未允许自动提交发布。",
                action="在账号设置中确认接口权限后启用“允许提交发布”。",
            )
        draft = await super().publish(request)
        if not draft.success or draft.mode == "MOCK":
            return draft
        try:
            token = await self._access_token()
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    f"{settings.wechat_api_base_url}/cgi-bin/freepublish/submit",
                    params={"access_token": token},
                    json={"media_id": draft.external_id},
                )
            data = response.json()
            if data.get("errcode"):
                raise WechatApiError(data)
            publish_id = str(data.get("publish_id") or "")
            return PublishResult(
                True,
                self.platform,
                self.mode,
                "PUBLISH_SUBMITTED",
                external_id=publish_id,
                detail={"draftId": draft.external_id, "publishId": publish_id, "real": True},
            )
        except WechatApiError as exc:
            return self.failure(
                exc.code, exc.message, retryable=exc.retryable, action=exc.suggested_action
            )
        except (httpx.HTTPError, ValueError) as exc:
            return self.failure("WECHAT_SUBMIT_FAILED", str(exc), retryable=True)

    async def query_status(self, task_id: str) -> dict[str, Any]:
        token = await self._access_token()
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{settings.wechat_api_base_url}/cgi-bin/freepublish/get",
                params={"access_token": token},
                json={"publish_id": task_id},
            )
        return response.json()


class XiaohongshuManualPublisher:
    platform = "XIAOHONGSHU"
    mode = "MANUAL_CONFIRM"

    def __init__(self, account: PlatformAccount | None = None) -> None:
        self.account = account

    async def validate_credentials(self) -> PublishResult:
        return PublishResult(True, self.platform, self.mode, "CONNECTED")

    async def get_capabilities(self) -> list[str]:
        return ["COPYWRITING", "IMAGE_PACKAGE", "MANUAL_CONFIRM"]

    async def publish(self, request: dict[str, Any]) -> PublishResult:
        package = {
            "title": request["title"],
            "content": request["content"],
            "hashtags": request.get("hashtags", []),
            "coverImage": (request.get("images") or [""])[0],
            "images": request.get("images", []),
            "imageOrder": list(range(1, len(request.get("images", [])) + 1)),
            "creatorUrl": "https://creator.xiaohongshu.com/publish/publish",
            "notice": "小红书当前采用人工确认发布，不属于服务器无人值守自动发布。",
        }
        return PublishResult(
            False,
            self.platform,
            self.mode,
            "WAITING_MANUAL_CONFIRM",
            suggested_action="复制文案并下载图片包，在小红书创作中心发布后填写公开链接。",
            detail={"publishPackage": package},
        )

    async def query_status(self, task_id: str) -> dict[str, Any]:
        return {"taskId": task_id, "status": "WAITING_MANUAL_CONFIRM"}

    async def disconnect(self) -> PublishResult:
        return PublishResult(True, self.platform, self.mode, "DISCONNECTED")


class WechatApiError(Exception):
    def __init__(self, data: dict[str, Any]) -> None:
        self.code = str(data.get("errcode", "WECHAT_ERROR"))
        self.message = str(data.get("errmsg", "微信接口调用失败"))
        self.retryable = self.code in {"-1", "45009"}
        if self.code in {"40001", "40014", "42001"}:
            self.suggested_action = "Access Token 已失效，请测试连接并重新获取。"
        elif self.code == "40164":
            self.suggested_action = "请将当前服务器出口 IP 加入公众号 IP 白名单。"
        elif self.code in {"48001", "48002"}:
            self.suggested_action = "当前公众号没有此接口权限，请检查认证和接口权限。"
        else:
            self.suggested_action = "请根据微信错误码检查公众号配置。"
        super().__init__(self.message)


def markdown_to_wechat_html(value: str) -> str:
    lines: list[str] = []
    in_list = False
    for raw in value.splitlines():
        line = html.escape(raw.strip())
        line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
        if line.startswith("### "):
            lines.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("## "):
            lines.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "):
            lines.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith(("- ", "* ")):
            if not in_list:
                lines.append("<ul>")
                in_list = True
            lines.append(f"<li>{line[2:]}</li>")
        else:
            if in_list:
                lines.append("</ul>")
                in_list = False
            if line:
                lines.append(f"<p>{line}</p>")
    if in_list:
        lines.append("</ul>")
    return "".join(lines)


def _local_image(value: str) -> Path | None:
    if not value:
        return None
    direct = Path(value)
    if direct.is_file():
        return direct
    try:
        parsed = httpx.URL(value)
    except httpx.InvalidURL:
        return None
    url_path = parsed.path if parsed.scheme else value
    if url_path.startswith("/uploads/"):
        path = BACKEND_DIR.parent / url_path.lstrip("/")
    elif url_path.startswith("/media/"):
        path = BACKEND_DIR.parent / "frontend" / "public" / url_path.lstrip("/")
    else:
        path = Path(value)
    return path if path.is_file() else None


def _first_readable_image(values: list[str]) -> Path | None:
    return next((path for value in values if (path := _local_image(value))), None)
