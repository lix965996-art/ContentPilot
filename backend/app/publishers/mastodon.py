from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.core.credentials import decrypt_json, decrypt_secret, encrypt_json
from app.core.exceptions import AppException
from app.core.mastodon import ensure_public_instance, normalize_instance_url
from app.core.paths import local_media_path
from app.core.urls import PublicHTTPTransport
from app.models.business import PublishSchedule
from app.publishers.base import PublishResult
from app.publishers.bluesky import _image_mime
from app.publishers.official import OfficialPublisher
from app.services.platform_content import (
    build_mastodon_post,
    mastodon_text_length,
    normalize_image_alt_texts,
)
from app.services.thread_publishing import (
    THREAD_REPLY_FIELD,
    freeze_thread_reply,
    thread_request_context,
)

MAX_IMAGE_BYTES = 8 * 1024 * 1024
ATTEMPT_FIELD = "mastodonPublish"


def _request_fingerprint(
    text: str,
    uploads: list[tuple[str, bytes, str]],
    account_id: str,
    instance_url: Any,
    alt_texts: list[str],
    reply_to_id: str | None,
) -> str:
    payload = {
        "text": text,
        "images": [hashlib.sha256(item[1]).hexdigest() for item in uploads],
        "account_id": account_id,
        "instance_url": instance_url,
    }
    # Keep existing hashes compatible for legacy non-thread, empty-alt attempts.
    if any(alt_texts):
        payload["image_alt_texts"] = alt_texts
    if reply_to_id is not None:
        payload["in_reply_to_id"] = reply_to_id
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def _status_payload(text: str, media_ids: list[str], reply_to_id: str | None) -> dict:
    payload = {"status": text, "visibility": "public", "media_ids": media_ids}
    if reply_to_id is not None:
        payload["in_reply_to_id"] = reply_to_id
    return payload


def _json(response: httpx.Response) -> dict[str, Any]:
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Mastodon 响应格式无效")
    return data


def _positive(value: Any, default: int, maximum: int = 100_000) -> int:
    return value if type(value) is int and 0 < value <= maximum else default


class MastodonPublisher(OfficialPublisher):
    platform = "MASTODON"
    mode = "REAL_API"

    async def get_capabilities(self) -> list[str]:
        return ["TEXT_PUBLISH", "IMAGE_PUBLISH", "STATUS_READ"]

    async def _request(self, method: str, path: str, *, auth: bool = True, **kwargs):
        config = decrypt_json(self.account.credentials_encrypted)
        proxy = settings.outbound_http_proxy.strip() or None
        instance_options = (
            {"dns_over_https": True, "proxy": proxy} if settings.outbound_dns_over_https else {}
        )
        origin = await ensure_public_instance(
            str(config.get("instance_url") or ""), **instance_options
        )
        headers = dict(kwargs.pop("headers", {}))
        if auth:
            token = decrypt_secret(self.account.access_token_encrypted)
            if not token:
                raise ValueError("Mastodon 访问令牌未配置")
            headers["Authorization"] = f"Bearer {token}"
        transport = PublicHTTPTransport(
            proxy=proxy, require_https=True, dns_over_https=settings.outbound_dns_over_https
        )
        async with httpx.AsyncClient(
            timeout=30, follow_redirects=False, transport=transport, trust_env=False
        ) as client:
            return await client.request(method, f"{origin}{path}", headers=headers, **kwargs)

    def _api_failure(self, response: httpx.Response) -> PublishResult:
        code, message, action = (
            "API_ERROR",
            f"Mastodon 接口返回 HTTP {response.status_code}",
            "请核对服务器规则、内容限制和令牌权限后重试同一任务。",
        )
        if response.status_code == 401:
            code, message = "TOKEN_EXPIRED", "Mastodon 令牌无效或已撤销，请重新配置"
        elif response.status_code == 403:
            code, message = (
                "PERMISSION_DENIED",
                "Mastodon 账号或令牌缺少权限，请确认邮箱、审核及应用权限",
            )
        elif response.status_code == 422:
            code, message = "CONTENT_INVALID", "Mastodon 拒绝了内容，请检查字数、媒体及实例规则"
        elif response.status_code == 429:
            code, message, action = "RATE_LIMITED", "Mastodon 请求频率超限", "请稍后重试同一任务。"
        return self.failure(code, message, retryable=response.status_code == 429, action=action)

    async def validate_credentials(self) -> PublishResult:
        if not decrypt_secret(self.account.access_token_encrypted):
            return self.failure("TOKEN_MISSING", "请填写 Mastodon 访问令牌")
        try:
            response = await self._request("GET", "/api/v1/accounts/verify_credentials")
            if not response.is_success:
                return self._api_failure(response)
            data = _json(response)
            account_id = data.get("id")
            acct = data.get("acct")
            if (
                not isinstance(account_id, str)
                or not re.fullmatch(r"[0-9]+", account_id)
                or not isinstance(acct, str)
                or not acct
                or data.get("suspended") is True
                or data.get("disabled") is True
            ):
                return self.failure("INVALID_IDENTITY", "Mastodon 账号响应无效或账号不可用")
            response = await self._request("GET", "/api/v2/instance", auth=False)
            if response.status_code == 404:
                response = await self._request("GET", "/api/v1/instance", auth=False)
            if not response.is_success:
                return self._api_failure(response)
            instance = _json(response)
            configuration = instance.get("configuration") or {}
            if not isinstance(configuration, dict):
                raise ValueError
            limits = configuration.get("statuses") or {}
            media = configuration.get("media_attachments") or {}
            if not isinstance(limits, dict) or not isinstance(media, dict):
                raise ValueError
            return PublishResult(
                True,
                self.platform,
                self.mode,
                "CONNECTED",
                external_id=account_id,
                detail={
                    "account_id": account_id,
                    "acct": acct,
                    "max_characters": _positive(limits.get("max_characters"), 500),
                    "characters_reserved_per_url": _positive(
                        limits.get("characters_reserved_per_url"), 23
                    ),
                    "max_media_attachments": _positive(limits.get("max_media_attachments"), 4),
                    "image_size_limit": _positive(
                        media.get("image_size_limit"), MAX_IMAGE_BYTES, 100_000_000
                    ),
                },
            )
        except httpx.HTTPError:
            return self.failure(
                "NETWORK_ERROR", "无法连接 Mastodon 服务器，请检查网络", retryable=True
            )
        except (ValueError, OSError):
            return self.failure("INVALID_INSTANCE", "Mastodon 服务器地址或响应无效，请检查账号配置")

    def _save_attempt(self, schedule: PublishSchedule, attempt: dict[str, Any]) -> None:
        context = dict(schedule.publish_package_json or {})
        context[ATTEMPT_FIELD] = dict(attempt)
        schedule.publish_package_json = context
        self.db.commit()

    def _receipt(
        self,
        data: dict[str, Any],
        account_id: str,
        *,
        reply_to_id: str | None = None,
        check_reply: bool = False,
    ) -> PublishResult:
        status_id = data.get("id")
        url = data.get("url")
        account = data.get("account") or {}
        origin = normalize_instance_url(
            str(decrypt_json(self.account.credentials_encrypted).get("instance_url") or "")
        )
        parsed = urlsplit(url) if isinstance(url, str) else None
        if (
            not isinstance(status_id, str)
            or not re.fullmatch(r"[0-9]+", status_id)
            or not isinstance(account, dict)
            or not isinstance(url, str)
            or account.get("id") != account_id
            or data.get("visibility") != "public"
            or parsed is None
            or parsed.scheme != "https"
            or parsed.netloc != urlsplit(origin).netloc
            or parsed.username is not None
            or not parsed.path.rstrip("/").endswith(f"/{status_id}")
            or (check_reply and data.get("in_reply_to_id") != reply_to_id)
        ):
            return self.failure(
                "INVALID_RECEIPT", "Mastodon 未返回有效的公开帖子回执，请先核对个人主页"
            )
        return PublishResult(
            True,
            self.platform,
            self.mode,
            "PUBLISHED",
            status_id,
            url,
            detail={"real": True, "publishedAtUTC": data.get("created_at")},
        )

    async def _read_receipt(
        self,
        status_id: str,
        account_id: str,
        *,
        reply_to_id: str | None = None,
        check_reply: bool = False,
    ) -> PublishResult:
        response = await self._request("GET", f"/api/v1/statuses/{status_id}", auth=False)
        if response.is_success:
            data = _json(response)
            if data.get("id") == status_id:
                return self._receipt(
                    data, account_id, reply_to_id=reply_to_id, check_reply=check_reply
                )
        return self.failure(
            "PUBLISH_UNCERTAIN",
            "已有发布记录，但目前无法核实该帖子；不会自动重发",
            action="请核对 Mastodon 个人主页和任务回执。",
        )

    async def _thread_reply(self, request: dict, account_id: str) -> str | PublishResult | None:
        schedule, context = thread_request_context(self.db, self.account.id, self.platform, request)
        if schedule is None or context is None or not context.is_reply:
            return None
        assert context.root is not None and context.parent is not None
        checked = set()
        for peer in (context.root, context.parent):
            if peer.id in checked:
                continue
            expected = (peer.publish_package_json or {}).get(THREAD_REPLY_FIELD) or {}
            result = await self._read_receipt(
                str(peer.external_id),
                account_id,
                reply_to_id=expected.get("inReplyToId"),
                check_reply=True,
            )
            if not result.success:
                return result
            checked.add(peer.id)
        frozen = freeze_thread_reply(
            self.db, schedule, {"inReplyToId": str(context.parent.external_id)}
        )
        return frozen["inReplyToId"]

    def _content_inputs(
        self, request: dict, config: dict
    ) -> tuple[str, list[str], list[str]] | PublishResult:
        text = build_mastodon_post(
            request.get("title", ""), request.get("content", ""), request.get("hashtags", [])
        )
        max_characters = min(500, _positive(config.get("mastodon_max_characters"), 500))
        reserved = _positive(config.get("mastodon_characters_reserved_per_url"), 23)
        images = [str(value) for value in request.get("images", []) if str(value)]
        try:
            alt_texts = normalize_image_alt_texts(request.get("image_alt_texts"), len(images))
        except ValueError as exc:
            return self.failure("CONTENT_INVALID", str(exc))
        max_images = min(4, _positive(config.get("mastodon_max_media_attachments"), 4))
        if (
            not text
            or mastodon_text_length(text, reserved) > max_characters
            or len(images) > max_images
        ):
            return self.failure(
                "CONTENT_INVALID",
                f"Mastodon 正文须为 1–{max_characters} 字符，"
                f"配图最多 {max_images} 张（标题与标签计入）",
            )
        return text, images, alt_texts

    async def _upload(
        self,
        filename: str,
        content: bytes,
        mime: str,
        media_id=None,
        on_upload=None,
        description: str = "",
    ) -> str | PublishResult:
        response = (
            await self._request("GET", f"/api/v1/media/{media_id}")
            if media_id
            else await self._request(
                "POST",
                "/api/v2/media",
                files={"file": (filename, content, mime)},
                data={"description": description},
            )
        )
        if not response.is_success:
            return self._api_failure(response)
        media = _json(response) if response.status_code != 206 else {"id": media_id}
        received_id = media.get("id")
        if (
            not isinstance(received_id, str)
            or not re.fullmatch(r"[0-9]+", received_id)
            or (media_id and received_id != media_id)
        ):
            return self.failure("INVALID_IMAGE_RECEIPT", "Mastodon 未返回有效的媒体标识")
        media_id = received_id
        if on_upload:
            on_upload(media_id)
        for _ in range(5):
            if media.get("url"):
                return media_id
            await asyncio.sleep(1)
            response = await self._request("GET", f"/api/v1/media/{media_id}")
            if response.status_code == 206:
                continue
            if not response.is_success:
                return self._api_failure(response)
            media = _json(response)
            if media.get("id") != media_id:
                return self.failure("INVALID_IMAGE_RECEIPT", "Mastodon 返回了不一致的媒体处理回执")
        if media.get("url"):
            return media_id
        return self.failure(
            "MEDIA_PROCESSING", "Mastodon 图片仍在处理，请稍后重试同一任务", retryable=True
        )

    async def publish(self, request: dict[str, Any]) -> PublishResult:
        config = decrypt_json(self.account.credentials_encrypted)
        if config.get("allow_public_publish") is not True:
            return self.failure("PUBLIC_PUBLISH_DISABLED", "Mastodon 真实发布开关未开启")
        account_id = str(config.get("mastodon_account_id") or "")
        if not account_id:
            return self.failure("IDENTITY_MISSING", "请先在账号设置中检测 Mastodon 连接")
        schedule = (
            self.db.get(PublishSchedule, request.get("schedule_id"))
            if request.get("schedule_id")
            else None
        )
        if (
            schedule is None
            or schedule.platform != self.platform
            or schedule.account_id != self.account.id
            or schedule.idempotency_key != request.get("idempotency_key")
        ):
            return self.failure("TASK_REQUIRED", "Mastodon 发布需要有效的排期任务")
        try:
            reply_to_id = await self._thread_reply(request, account_id)
            if isinstance(reply_to_id, PublishResult):
                return reply_to_id
            inputs = self._content_inputs(request, config)
            if isinstance(inputs, PublishResult):
                return inputs
            text, images, alt_texts = inputs
            uploads = []
            for image in images:
                path = local_media_path(image, local_hosts_only=True)
                if path is None:
                    return self.failure("IMAGE_UNAVAILABLE", "Mastodon 配图需先上传到本项目")
                size_limit = min(
                    MAX_IMAGE_BYTES,
                    _positive(
                        config.get("mastodon_image_size_limit"), MAX_IMAGE_BYTES, 100_000_000
                    ),
                )
                if path.stat().st_size > size_limit:
                    return self.failure(
                        "IMAGE_TOO_LARGE", f"Mastodon 配图须不超过 {size_limit // 1024} KB"
                    )
                content = path.read_bytes()
                mime = _image_mime(content)
                if not mime:
                    return self.failure("IMAGE_FORMAT", "Mastodon 配图目前支持 JPEG、PNG、WebP")
                uploads.append((path.name, content, mime))
            fingerprint = _request_fingerprint(
                text, uploads, account_id, config.get("instance_url"), alt_texts, reply_to_id
            )
            attempt = dict((schedule.publish_package_json or {}).get(ATTEMPT_FIELD) or {})
            if attempt.get("requestHash") and attempt["requestHash"] != fingerprint:
                return self.failure(
                    "TASK_CONTENT_CHANGED",
                    "此任务已尝试发布其他内容或账号，不能覆盖；请先核对平台结果",
                )
            attempt.update(
                requestHash=fingerprint,
                key="cp-" + hashlib.sha256(schedule.idempotency_key.encode()).hexdigest(),
            )
            self._save_attempt(schedule, attempt)
            if attempt.get("statusId"):
                return await self._read_receipt(
                    str(attempt["statusId"]),
                    account_id,
                    reply_to_id=reply_to_id,
                    check_reply=True,
                )
            if attempt.get("uncertain"):
                sent_at = datetime.fromisoformat(str(attempt["sentAt"]))
                if datetime.now(UTC) - sent_at >= timedelta(minutes=55):
                    return self.failure(
                        "PUBLISH_UNCERTAIN",
                        "上次发布结果未确认，已超出安全重试窗口；不会自动重发",
                        action="请先检查 Mastodon 个人主页，确认后再决定是否创建新任务。",
                    )
            saved_media = list(attempt.get("mediaIds") or [])
            media_ids = []
            for index, upload in enumerate(uploads):

                def remember_media(media_id, index=index):
                    while len(saved_media) <= index:
                        saved_media.append(None)
                    saved_media[index] = media_id
                    attempt["mediaIds"] = list(saved_media)
                    self._save_attempt(schedule, attempt)

                media_id = await self._upload(
                    *upload,
                    media_id=saved_media[index] if index < len(saved_media) else None,
                    on_upload=remember_media,
                    description=alt_texts[index],
                )
                if isinstance(media_id, PublishResult):
                    return media_id
                media_ids.append(media_id)
            previously_uncertain = bool(attempt.get("uncertain"))
            # Media processing can cross the server's idempotency-cache window.
            if previously_uncertain and datetime.now(UTC) - datetime.fromisoformat(
                str(attempt["sentAt"])
            ) >= timedelta(minutes=55):
                return self.failure(
                    "PUBLISH_UNCERTAIN",
                    "上次发布结果未确认，已超出安全重试窗口；不会自动重发",
                    action="请先检查 Mastodon 个人主页，再决定是否创建新任务。",
                )
            attempt.setdefault("sentAt", datetime.now(UTC).isoformat())
            attempt["uncertain"] = True
            self._save_attempt(schedule, attempt)
            response = await self._request(
                "POST",
                "/api/v1/statuses",
                headers={"Idempotency-Key": attempt["key"]},
                json=_status_payload(text, media_ids, reply_to_id),
            )
            if not response.is_success:
                if (
                    400 <= response.status_code < 500
                    and response.status_code != 408
                    and not previously_uncertain
                ):
                    attempt["uncertain"] = False
                    attempt.pop("sentAt", None)
                    self._save_attempt(schedule, attempt)
                return self._api_failure(response)
            data = _json(response)
            result = self._receipt(data, account_id, reply_to_id=reply_to_id, check_reply=True)
            if result.success:
                attempt.update(
                    statusId=result.external_id, statusUrl=result.published_url, uncertain=False
                )
                self._save_attempt(schedule, attempt)
            return result
        except AppException as exc:
            return self.failure("THREAD_INVALID", exc.message)
        except httpx.HTTPError:
            return self.failure(
                "PUBLISH_UNCERTAIN",
                "Mastodon 请求中断，尚未确认发布结果",
                action="请核对个人主页后重试同一任务，勿新建重复任务。",
            )
        except (ValueError, OSError, TypeError):
            return self.failure(
                "REQUEST_FAILED", "Mastodon 请求、响应或素材无效，请检查配置并核对个人主页"
            )

    async def query_status(self, task_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"[0-9]+", task_id):
            return {"status": "UNKNOWN", "error": "INVALID_POST_ID"}
        try:
            account_id = str(
                decrypt_json(self.account.credentials_encrypted).get("mastodon_account_id") or ""
            )
            schedule = self.db.scalar(
                select(PublishSchedule).where(
                    PublishSchedule.account_id == self.account.id,
                    PublishSchedule.platform == self.platform,
                    PublishSchedule.external_id == task_id,
                )
            )
            package = schedule.publish_package_json or {} if schedule is not None else {}
            reply = package.get(THREAD_REPLY_FIELD) or {}
            result = await self._read_receipt(
                task_id,
                account_id,
                reply_to_id=reply.get("inReplyToId"),
                check_reply="thread" in package,
            )
            return {
                "status": result.status if result.success else "UNKNOWN",
                "externalId": result.external_id,
                "error": result.error_code,
            }
        except (httpx.HTTPError, ValueError, OSError):
            return {"status": "UNKNOWN", "error": "STATUS_UNAVAILABLE"}

    async def read_metrics(self, post_id: str):
        from app.publishers.metrics import (
            MetricReadResult,
            counter,
            parse_utc,
            response_failure,
        )

        config = decrypt_json(self.account.credentials_encrypted)
        owner = str(config.get("mastodon_account_id") or "")
        if not owner or not re.fullmatch(r"[0-9]+", post_id):
            return MetricReadResult("FAILED", error_code="POST_IDENTITY_MISMATCH")
        try:
            response = await self._request("GET", f"/api/v1/statuses/{post_id}")
            if not response.is_success:
                return response_failure(response)
            post = _json(response)
            if post.get("id") != post_id or (post.get("account") or {}).get("id") != owner:
                return MetricReadResult("FAILED", error_code="POST_IDENTITY_MISMATCH")
            return MetricReadResult(
                "SUCCEEDED",
                http_status=200,
                published_at=parse_utc(post.get("created_at")),
                counts={
                    key: counter(post.get(field))
                    for key, field in (
                        ("likes", "favourites_count"),
                        ("replies", "replies_count"),
                        ("reposts", "reblogs_count"),
                        ("quotes", "quotes_count"),
                    )
                },
            )
        except httpx.HTTPError:
            return MetricReadResult("FAILED", error_code="NETWORK_ERROR", retryable=True)
        except (ValueError, TypeError, AttributeError, OSError):
            return MetricReadResult("FAILED", error_code="INVALID_RESPONSE")

    async def disconnect(self) -> PublishResult:
        config = decrypt_json(self.account.credentials_encrypted)
        for key in list(config):
            if key.startswith("mastodon_"):
                config.pop(key)
        config["allow_public_publish"] = False
        self.account.credentials_encrypted = encrypt_json(config)
        return await super().disconnect()
