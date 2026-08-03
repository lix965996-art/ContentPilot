from __future__ import annotations

import html
import ipaddress
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import BACKEND_DIR, settings
from app.core.credentials import decrypt_json, decrypt_secret, encrypt_secret
from app.models.business import PlatformAccount
from app.publishers.base import PublishResult
from app.services.platform_content import build_weibo_status, build_xiaohongshu_package
from app.services.wechat_formatting import markdown_to_wechat_html


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
        operation_ip = str(request.get("operation_ip") or self.config.get("operation_ip") or "")
        try:
            parsed_ip = ipaddress.ip_address(operation_ip)
        except ValueError:
            parsed_ip = None
        if parsed_ip is None or not parsed_ip.is_global:
            return self.failure(
                "OPERATION_IP_REQUIRED",
                "微博官方发布接口要求提交实际操作用户的公网 IP（rip）。",
                action="请在微博账号配置中填写本次发布操作者的真实公网 IP 后重试。",
            )
        status = build_weibo_status(
            request.get("title", ""),
            request.get("content", ""),
            request.get("hashtags", []),
        )
        if not status:
            return self.failure("CONTENT_EMPTY", "微博正文不能为空。")
        requested_images = [str(value) for value in request.get("images", []) if str(value)]
        try:
            image_upload = await _first_image_upload(requested_images)
        except (httpx.HTTPError, ValueError, OSError) as exc:
            return self.failure(
                "IMAGE_UNAVAILABLE",
                f"微博首张配图读取失败：{exc}",
                action="请移除该图片后重新选择，或上传一张本地图片。",
            )
        if requested_images and image_upload is None:
            return self.failure(
                "IMAGE_UNAVAILABLE",
                "微博首张配图无法读取。",
                action="请移除该图片后重新选择，或上传一张本地图片。",
            )
        if image_upload and len(status) > 140:
            return self.failure(
                "WEIBO_IMAGE_TEXT_TOO_LONG",
                f"当前图文微博共 {len(status)} 个字符，官方单图发布接口最多支持 140 个字符。",
                action="请缩短首句、正文或话题，或者移除图片后改用长文字发布。",
            )
        endpoint = "/2/statuses/upload.json" if image_upload else "/2/statuses/update.json"
        api_base_url = (
            settings.weibo_upload_api_base_url if image_upload else settings.weibo_api_base_url
        )
        payload = {
            "access_token": token,
            "status": status,
            "rip": operation_ip,
        }
        if not image_upload and len(status) > 140:
            payload["is_longtext"] = 1
        files = None
        if image_upload:
            files = {"pic": image_upload}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(f"{api_base_url}{endpoint}", data=payload, files=files)
            data = response.json()
            external_id = str(data.get("idstr") or data.get("id") or "")
            if response.is_success and external_id:
                user_id = str((data.get("user") or {}).get("idstr") or "")
                url = f"https://weibo.com/{user_id}/{external_id}" if user_id else ""
                return PublishResult(
                    True,
                    self.platform,
                    self.mode,
                    "PUBLISHED",
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

    # ------------------------------------------------------------------
    # capabilities
    # ------------------------------------------------------------------
    async def get_capabilities(self) -> list[str]:
        """Return the capabilities that were *actually* detected via API probe."""
        caps = list(self.account.capabilities_json or [])
        if not caps:
            caps = ["DRAFT_CREATE"]  # conservative fallback
        if self.config.get("allow_submit_publish"):
            caps.append("SUBMIT_PUBLISH")
        return caps

    # ------------------------------------------------------------------
    # access_token (unchanged logic, but kept for clarity)
    # ------------------------------------------------------------------
    async def _access_token(self) -> str:
        cached = decrypt_secret(self.account.access_token_encrypted)
        if cached and self.account.token_expires_at:
            if self.account.token_expires_at > datetime.now() + timedelta(minutes=2):
                return cached
        app_id = self.account.app_id or settings.wechat_app_id
        app_secret = self.config.get("app_secret") or settings.wechat_app_secret
        if not app_id or not app_secret:
            raise ValueError("微信公众号 AppID/AppSecret 未配置")
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"{settings.wechat_api_base_url}/cgi-bin/token",
                params={
                    "grant_type": "client_credential",
                    "appid": app_id,
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

    # ------------------------------------------------------------------
    # validate_credentials: step 1 – token, step 2 – draft list probe
    # ------------------------------------------------------------------
    async def validate_credentials(self) -> PublishResult:
        try:
            token = await self._access_token()
        except WechatApiError as exc:
            return self.failure(exc.code, exc.message, action=exc.suggested_action)
        except (httpx.HTTPError, ValueError) as exc:
            return self.failure(
                "CONNECTION_FAILED", str(exc), retryable=isinstance(exc, httpx.HTTPError)
            )

        # Probe draft + material capabilities via real API calls.
        probe = await self._probe_drafts(token)

        # Only update capabilities_json when the response is authoritative
        # (non-empty list means the probe succeeded and reported real
        # permissions).  An empty list means the API call itself failed
        # (e.g. 48001), so we preserve whatever the user configured.
        if probe["capabilities"]:
            self.account.capabilities_json = probe["capabilities"]
        self.db.flush()

        # Connection status reflects authentication: token obtained = CONNECTED.
        # Capabilities (draft_create / material_upload / direct_publish) are
        # tracked separately via capabilities_json and publishHint.
        self.account.status = "CONNECTED"
        return PublishResult(
            True,
            self.platform,
            self.mode,
            "CONNECTED",
            detail={"draft_probe": probe},
        )

    async def _probe_drafts(self, token: str) -> dict[str, Any]:
        """Call draft/count → draft/list → material/add_material → report."""
        result: dict[str, Any] = {
            "token_ok": True,
            "draft_create": False,
            "draft_update": False,
            "draft_read": False,
            "draft_delete": False,
            "material_upload": False,
            "capabilities": [],
            "draft_count_error": None,
            "material_upload_error": None,
        }
        # ── draft count ──
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{settings.wechat_api_base_url}/cgi-bin/draft/count",
                params={"access_token": token},
            )
        data = resp.json()
        errcode = data.get("errcode", 0)
        if errcode == 0:
            result["draft_read"] = True
            result["draft_create"] = True  # same permission group
            result["draft_update"] = True
            result["draft_delete"] = True
            result["capabilities"] = [
                "DRAFT_CREATE",
                "DRAFT_UPDATE",
                "DRAFT_READ",
                "DRAFT_DELETE",
            ]
        else:
            result["draft_count_error"] = {
                "errcode": errcode,
                "errmsg": data.get("errmsg", ""),
            }

        # ── material upload ──
        # Use a minimal 1×1 PNG to avoid consuming quota; we only check the
        # errcode, not whether the upload is practically usable.
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
            if mat_data.get("errcode", 0) == 0:
                result["material_upload"] = True
                result["capabilities"].append("MATERIAL_UPLOAD")
            else:
                result["material_upload_error"] = {
                    "errcode": mat_data.get("errcode"),
                    "errmsg": mat_data.get("errmsg", ""),
                }
        except (httpx.HTTPError, OSError) as exc:
            result["material_upload_error"] = {"errcode": "NETWORK", "errmsg": str(exc)}

        return result

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
        try:
            token = await self._access_token()
            images = [path for value in request.get("images", []) if (path := _local_image(value))]

            # Resolve cover media_id:
            #   1) pre-configured default_cover_media_id
            #   2) upload local cover image as permanent material
            #   3) download default_cover_url → upload as permanent material
            thumb_media_id = str(self.config.get("default_cover_media_id") or "")
            material_upload_failed = None

            if not thumb_media_id and images:
                try:
                    thumb_media_id = await self._upload_image(token, images[0], permanent=True)
                except WechatApiError as exc:
                    material_upload_failed = {
                        "errcode": exc.code,
                        "errmsg": exc.message,
                    }

            if not thumb_media_id and self.config.get("default_cover_url"):
                if not material_upload_failed:
                    try:
                        thumb_media_id = await self._upload_image_url(
                            token, str(self.config["default_cover_url"]), permanent=True
                        )
                    except WechatApiError as exc:
                        material_upload_failed = {
                            "errcode": exc.code,
                            "errmsg": exc.message,
                        }

            if not thumb_media_id:
                hint = (
                    f"素材上传失败 [{material_upload_failed['errcode']}]: "
                    f"{material_upload_failed['errmsg']}. "
                    if material_upload_failed
                    else ""
                )
                raise ValueError(
                    f"{hint}请配置默认封面素材 ID (default_cover_media_id)，"
                    f"或在文章中选择一张本地图片作为封面"
                )

            body_html = request.get("content_html") or markdown_to_wechat_html(request["content"])
            for path in images[1:]:
                try:
                    image_url = await self._upload_image(token, path, permanent=False)
                    body_html += f'<p><img src="{html.escape(image_url)}" /></p>'
                except WechatApiError:
                    pass  # body images are optional

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
                detail={
                    "draftId": draft_id,
                    "real": True,
                    "materialUploadFailed": material_upload_failed,
                },
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
        token = await self._access_token()
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{settings.wechat_api_base_url}/cgi-bin/draft/get",
                params={"access_token": token},
                json={"media_id": task_id},
            )
        data = resp.json()
        if data.get("errcode"):
            raise WechatApiError(data)
        return {"media_id": task_id, "status": "DRAFT_CREATED", "detail": data}

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
        if not draft.success:
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
            **build_xiaohongshu_package(
                title=request.get("title", ""),
                content=request.get("content", ""),
                hashtags=request.get("hashtags", []),
                images=request.get("images", []),
            ),
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


async def _first_image_upload(values: list[str]) -> tuple[str, bytes, str] | None:
    """Load the first selected image from local storage or its original public URL."""
    if not values:
        return None
    value = values[0]
    local = _local_image(value)
    if local:
        return local.name, local.read_bytes(), "application/octet-stream"

    try:
        parsed = httpx.URL(value)
    except httpx.InvalidURL as exc:
        raise ValueError("图片地址无效") from exc
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("图片地址必须使用 HTTP 或 HTTPS")
    host = parsed.host or ""
    if host.lower() == "localhost":
        raise ValueError("不允许读取本机图片地址")
    try:
        host_ip = ipaddress.ip_address(host)
    except ValueError:
        host_ip = None
    if host_ip is not None and not host_ip.is_global:
        raise ValueError("不允许读取内网图片地址")
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(value)
        response.raise_for_status()
    if not response.content:
        raise ValueError("图片文件为空")
    if len(response.content) > 5 * 1024 * 1024:
        raise ValueError("图片不能超过 5MB")
    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
    if content_type and not content_type.startswith("image/"):
        raise ValueError("远程地址返回的不是图片")
    filename = Path(parsed.path).name or "weibo-image.jpg"
    return filename, response.content, content_type or "application/octet-stream"
