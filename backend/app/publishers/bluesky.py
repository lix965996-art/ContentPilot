from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx
import regex

from app.core.config import settings
from app.core.credentials import decrypt_json, decrypt_secret, encrypt_json, encrypt_secret
from app.core.paths import local_media_path
from app.models.business import PlatformAccount
from app.publishers.base import PublishResult
from app.publishers.official import OfficialPublisher
from app.services.platform_content import build_bluesky_post, validate_platform_publish

COLLECTION = "app.bsky.feed.post"
MAX_IMAGE_BYTES = 1_000_000
TID_ALPHABET = "234567abcdefghijklmnopqrstuvwxyz"
TID_PATTERN = re.compile(r"[234567abcdefghij][234567abcdefghijklmnopqrstuvwxyz]{12}")
_tid_lock = Lock()
_last_tid_microseconds = 0


def new_bluesky_record_key(idempotency_key: str) -> str:
    """Generate a valid TID once; callers must persist it before network writes."""
    global _last_tid_microseconds
    with _tid_lock:
        microseconds = max(time.time_ns() // 1000, _last_tid_microseconds + 1)
        _last_tid_microseconds = microseconds
    clock_id = int.from_bytes(hashlib.sha256(idempotency_key.encode()).digest()[:2]) & 1023
    value = (microseconds << 10) | clock_id
    if value >= 1 << 63:
        raise ValueError("Bluesky TID timestamp is outside its supported range")
    encoded = ""
    for _ in range(13):
        encoded = TID_ALPHABET[value & 31] + encoded
        value >>= 5
    return encoded


def _now() -> datetime:
    return datetime.now(ZoneInfo(settings.app_timezone)).replace(tzinfo=None)


def store_bluesky_session(account: PlatformAccount, data: dict[str, Any]) -> None:
    if not isinstance(data, dict) or not all(
        isinstance(data.get(key), str) and data[key]
        for key in ("accessJwt", "refreshJwt", "did", "handle")
    ):
        raise ValueError("Bluesky 登录响应不完整")
    if not data["did"].startswith("did:"):
        raise ValueError("Bluesky 登录身份无效")
    if data.get("active") is False:
        raise ValueError("Bluesky 账号当前不可用")
    config = decrypt_json(account.credentials_encrypted)
    if config.get("bluesky_did") and config["bluesky_did"] != data["did"]:
        raise ValueError("Bluesky 登录身份与已连接账号不一致，请重新保存账号配置")
    account.access_token_encrypted = encrypt_secret(str(data["accessJwt"]))
    account.refresh_token_encrypted = encrypt_secret(str(data["refreshJwt"]))
    try:
        payload = str(data["accessJwt"]).split(".")[1]
        expiry = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))["exp"]
        account.token_expires_at = datetime.fromtimestamp(
            float(expiry), ZoneInfo(settings.app_timezone)
        ).replace(tzinfo=None)
    except (IndexError, KeyError, TypeError, ValueError):
        account.token_expires_at = _now() + timedelta(minutes=5)
    config.update(bluesky_did=str(data["did"]), bluesky_handle=str(data["handle"]))
    account.credentials_encrypted = encrypt_json(config)


def _json(response: httpx.Response) -> dict[str, Any]:
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Bluesky 响应格式无效")
    return data


def _facets(text: str) -> list[dict[str, Any]]:
    facets: list[dict[str, Any]] = []
    occupied: list[tuple[int, int]] = []
    for match in re.finditer(r"https?://[^\s<>]+", text):
        url = match.group().rstrip(".,!?;:)]}。，！？；：）】")
        if not url:
            continue
        start, end = match.start(), match.start() + len(url)
        occupied.append((start, end))
        facets.append(
            {
                "index": {
                    "byteStart": len(text[:start].encode("utf-8")),
                    "byteEnd": len(text[:end].encode("utf-8")),
                },
                "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url}],
            }
        )
    for match in regex.finditer(r"(?<![\w/#])#([\p{L}\p{M}\p{N}_]+)", text):
        if any(start <= match.start() < end for start, end in occupied):
            continue
        tag = match.group(1)
        if len(regex.findall(r"\X", tag)) > 64:
            continue
        facets.append(
            {
                "index": {
                    "byteStart": len(text[: match.start()].encode("utf-8")),
                    "byteEnd": len(text[: match.end()].encode("utf-8")),
                },
                "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": tag}],
            }
        )
    return sorted(facets, key=lambda facet: facet["index"]["byteStart"])


class BlueskyPublisher(OfficialPublisher):
    platform = "BLUESKY"
    mode = "REAL_API"

    async def get_capabilities(self) -> list[str]:
        return ["TEXT_PUBLISH", "IMAGE_PUBLISH", "STATUS_READ"]

    async def _raw(self, method: str, nsid: str, *, token: str = "", **kwargs) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}))
        if token:
            headers["Authorization"] = f"Bearer {token}"
        # Use the same explicitly configured outbound route as Mastodon. A
        # working Mastodon proxy must not leave Bluesky on a blocked direct route.
        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=False,
            proxy=settings.outbound_http_proxy.strip() or None,
        ) as client:
            return await client.request(
                method,
                f"{settings.bluesky_api_base_url.rstrip('/')}/xrpc/{nsid}",
                headers=headers,
                **kwargs,
            )

    def _api_failure(self, response: httpx.Response) -> PublishResult:
        code, message, action = (
            "API_ERROR",
            f"Bluesky 接口返回 HTTP {response.status_code}",
            "请检查账号状态、内容格式及图片，再重试同一任务。",
        )
        if response.status_code == 401:
            code, message, action = (
                "TOKEN_EXPIRED",
                "Bluesky 授权无效或已过期",
                "请检查应用密码，并在账号设置中重新检测连接。",
            )
        elif response.status_code == 403:
            code, message = "PERMISSION_DENIED", "Bluesky 账号当前没有此操作权限"
        elif response.status_code == 429:
            code, message, action = "RATE_LIMITED", "Bluesky 请求频率超限", "请稍后重试。"
        upstream_error = ""
        try:
            error = _json(response).get("error")
            if isinstance(error, str) and re.fullmatch(r"[A-Za-z0-9_]{1,64}", error):
                upstream_error = error
        except (ValueError, TypeError):
            pass
        if code == "API_ERROR" and upstream_error:
            message += f"（{upstream_error}）"
        result = self.failure(code, message, retryable=response.status_code == 429, action=action)
        if upstream_error:
            result.detail["upstream_error"] = upstream_error
        return result

    async def _login(self) -> PublishResult | None:
        config = decrypt_json(self.account.credentials_encrypted)
        identifier = str(config.get("identifier") or "").strip().lstrip("@")
        password = str(config.get("app_password") or "")
        if not identifier or not password:
            return self.failure("CREDENTIALS_MISSING", "请填写 Bluesky 账号和应用密码")
        response = await self._raw(
            "POST",
            "com.atproto.server.createSession",
            json={"identifier": identifier, "password": password},
        )
        if not response.is_success:
            return self._api_failure(response)
        try:
            store_bluesky_session(self.account, _json(response))
        except (ValueError, TypeError):
            return self.failure("INVALID_SESSION", "Bluesky 登录响应无效或账号不可用")
        self.db.flush()
        return None

    async def _token(self, *, refresh: bool = False) -> tuple[str, PublishResult | None]:
        token = decrypt_secret(self.account.access_token_encrypted)
        expired = bool(
            self.account.token_expires_at
            and self.account.token_expires_at <= _now() + timedelta(seconds=30)
        )
        if token and not expired and not refresh:
            return token, None
        refresh_token = decrypt_secret(self.account.refresh_token_encrypted)
        if refresh_token:
            response = await self._raw(
                "POST", "com.atproto.server.refreshSession", token=refresh_token
            )
            if response.is_success:
                try:
                    store_bluesky_session(self.account, _json(response))
                except (ValueError, TypeError):
                    return "", self.failure("INVALID_SESSION", "Bluesky 会话刷新响应无效")
                self.db.flush()
                return decrypt_secret(self.account.access_token_encrypted) or "", None
            if response.status_code not in {400, 401}:
                return "", self._api_failure(response)
        failure = await self._login()
        return decrypt_secret(self.account.access_token_encrypted) or "", failure

    async def _request(self, method: str, nsid: str, **kwargs) -> httpx.Response:
        token, failure = await self._token()
        if failure:
            raise _SessionFailure(failure)
        response = await self._raw(method, nsid, token=token, **kwargs)
        if response.status_code == 401:
            token, failure = await self._token(refresh=True)
            if failure:
                raise _SessionFailure(failure)
            response = await self._raw(method, nsid, token=token, **kwargs)
        return response

    async def validate_credentials(self) -> PublishResult:
        try:
            failure = await self._login()
            if failure:
                return failure
            config = decrypt_json(self.account.credentials_encrypted)
            return PublishResult(
                True,
                self.platform,
                self.mode,
                "CONNECTED",
                external_id=str(config["bluesky_did"]),
                detail={"handle": config["bluesky_handle"], "did": config["bluesky_did"]},
            )
        except httpx.HTTPError:
            return self.failure(
                "NETWORK_ERROR", "无法连接 Bluesky 登录接口，请检查网络", retryable=True
            )

    def _published(
        self,
        data: dict[str, Any],
        did: str,
        rkey: str,
        *,
        replay: bool = False,
        published_at: str | None = None,
    ) -> PublishResult:
        uri = str(data.get("uri") or "")
        parts = uri.removeprefix("at://").split("/")
        if (
            uri != f"at://{did}/{COLLECTION}/{rkey}"
            or not isinstance(data.get("cid"), str)
            or not data["cid"]
        ):
            return self.failure("INVALID_RECEIPT", "Bluesky 未返回有效的帖子回执，请先核对个人主页")
        url = (
            f"https://bsky.app/profile/{quote(parts[0], safe=':')}/post/{quote(parts[2], safe='')}"
        )
        return PublishResult(
            True,
            self.platform,
            self.mode,
            "PUBLISHED",
            uri,
            url,
            detail={
                "real": True,
                "cid": str(data.get("cid") or ""),
                "idempotent_replay": replay,
                "publishedAtUTC": published_at,
            },
        )

    async def _existing(
        self, did: str, rkey: str, text: str, images: list[dict[str, Any]]
    ) -> PublishResult | None:
        response = await self._request(
            "GET",
            "com.atproto.repo.getRecord",
            params={"repo": did, "collection": COLLECTION, "rkey": rkey},
        )
        if response.is_success:
            data = _json(response)
            value = data.get("value")
            if not isinstance(value, dict):
                return self.failure("INVALID_RECEIPT", "Bluesky 帖子内容回执格式无效")
            existing_embed = value.get("embed") or {}
            existing_images = (
                existing_embed.get("images", []) if isinstance(existing_embed, dict) else []
            )
            if value.get("text") != text or existing_images != images:
                return self.failure(
                    "TASK_ALREADY_PUBLISHED",
                    "此任务已发布过不同内容，不能覆盖或重复发布",
                    action="请核对个人主页；如需发布新内容，请创建新的排期任务。",
                )
            return self._published(
                data, did, rkey, replay=True, published_at=value.get("createdAt")
            )
        if response.status_code == 400:
            if _json(response).get("error") == "RecordNotFound":
                return None
        if response.status_code == 404:
            return None
        return self._api_failure(response)

    async def publish(self, request: dict[str, Any]) -> PublishResult:
        if decrypt_json(self.account.credentials_encrypted).get("allow_public_publish") is not True:
            return self.failure("PUBLIC_PUBLISH_DISABLED", "Bluesky 真实发布开关未开启")
        images = [str(value) for value in request.get("images", []) if str(value)]
        errors = validate_platform_publish(
            platform=self.platform,
            title=str(request.get("title") or ""),
            content=str(request.get("content") or ""),
            hashtags=request.get("hashtags", []),
            images=images,
        )
        if errors:
            return self.failure("CONTENT_INVALID", "；".join(errors))
        text = build_bluesky_post(
            request.get("title", ""), request.get("content", ""), request.get("hashtags", [])
        )
        rkey = request.get("record_key")
        if not isinstance(rkey, str) or not TID_PATTERN.fullmatch(rkey):
            return self.failure(
                "INVALID_RECORD_KEY",
                "Bluesky 发布任务缺少有效的持久化 TID，请修复排期后重试同一任务",
            )
        try:
            _, failure = await self._token()
            if failure:
                return failure
            did = str(decrypt_json(self.account.credentials_encrypted).get("bluesky_did") or "")
            if not did.startswith("did:"):
                return self.failure("IDENTITY_MISSING", "请先在账号设置中检测 Bluesky 连接")
            embeds = []
            for value in images:
                path = local_media_path(value, local_hosts_only=True)
                if path is None:
                    return self.failure(
                        "IMAGE_UNAVAILABLE",
                        "Bluesky 配图需要先上传到本项目，远程图片不会被静默忽略",
                    )
                if path.stat().st_size > MAX_IMAGE_BYTES:
                    return self.failure(
                        "IMAGE_TOO_LARGE", "Bluesky 每张配图须不超过 1 MB，请压缩后重新上传"
                    )
                content = path.read_bytes()
                mime = _image_mime(content)
                if not mime:
                    return self.failure("IMAGE_FORMAT", "Bluesky 配图仅支持 JPEG、PNG、WebP")
                response = await self._request(
                    "POST",
                    "com.atproto.repo.uploadBlob",
                    content=content,
                    headers={"Content-Type": mime},
                )
                if not response.is_success:
                    return self._api_failure(response)
                blob = _json(response).get("blob")
                if not isinstance(blob, dict) or not blob.get("ref"):
                    return self.failure("INVALID_IMAGE_RECEIPT", "Bluesky 未返回有效的图片上传回执")
                embeds.append({"alt": "", "image": blob})
            existing = await self._existing(did, rkey, text, embeds)
            if existing:
                return existing
            record: dict[str, Any] = {
                "$type": COLLECTION,
                "text": text,
                "createdAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            }
            facets = _facets(text)
            if facets:
                record["facets"] = facets
            if embeds:
                record["embed"] = {"$type": "app.bsky.embed.images", "images": embeds}
            try:
                response = await self._request(
                    "POST",
                    "com.atproto.repo.createRecord",
                    json={"repo": did, "collection": COLLECTION, "rkey": rkey, "record": record},
                )
            except httpx.HTTPError:
                recovered = await self._existing(did, rkey, text, embeds)
                return recovered or self.failure(
                    "PUBLISH_UNCERTAIN",
                    "Bluesky 发布请求中断，尚未确认结果",
                    action="请核对个人主页后重试同一任务，系统会使用同一帖子标识避免重复。",
                )
            if response.is_success:
                return self._published(_json(response), did, rkey, published_at=record["createdAt"])
            if response.status_code >= 500 or response.status_code in {400, 409}:
                recovered = await self._existing(did, rkey, text, embeds)
                if recovered:
                    return recovered
            return self._api_failure(response)
        except _SessionFailure as exc:
            return exc.result
        except (httpx.HTTPError, ValueError, OSError):
            return self.failure(
                "REQUEST_FAILED",
                "Bluesky 请求或图片读取失败，请检查网络与素材",
                action="请核对个人主页后重试同一任务，避免重复创建排期。",
            )

    async def query_status(self, task_id: str) -> dict[str, Any]:
        try:
            parts = task_id.removeprefix("at://").split("/")
            if not task_id.startswith("at://did:") or len(parts) != 3 or parts[1] != COLLECTION:
                return {"status": "UNKNOWN", "error": "INVALID_POST_URI"}
            response = await self._request(
                "GET",
                "com.atproto.repo.getRecord",
                params={"repo": parts[0], "collection": COLLECTION, "rkey": parts[2]},
            )
            if response.is_success:
                return {"status": "PUBLISHED", "externalId": task_id}
            return {"status": "UNKNOWN", "error": self._api_failure(response).error_code}
        except (_SessionFailure, httpx.HTTPError, ValueError):
            return {"status": "UNKNOWN", "error": "STATUS_UNAVAILABLE"}

    async def read_metrics(self, post_id: str):
        from app.publishers.metrics import (
            MetricReadResult,
            counter,
            parse_utc,
            response_failure,
        )

        config = decrypt_json(self.account.credentials_encrypted)
        owner = str(config.get("bluesky_did") or "")
        if not owner or not post_id.startswith(f"at://{owner}/{COLLECTION}/"):
            return MetricReadResult("FAILED", error_code="POST_IDENTITY_MISMATCH")
        try:
            response = await self._request(
                "GET", "app.bsky.feed.getPosts", params={"uris": [post_id]}
            )
            if not response.is_success:
                return response_failure(response)
            posts = _json(response).get("posts", [])
            if not isinstance(posts, list) or not posts:
                return MetricReadResult("FAILED", http_status=404, error_code="POST_UNAVAILABLE")
            post = posts[0]
            if post.get("uri") != post_id or (post.get("author") or {}).get("did") != owner:
                return MetricReadResult("FAILED", error_code="POST_IDENTITY_MISMATCH")
            return MetricReadResult(
                "SUCCEEDED",
                http_status=200,
                published_at=parse_utc((post.get("record") or {}).get("createdAt")),
                counts={
                    key: counter(post.get(field))
                    for key, field in (
                        ("likes", "likeCount"),
                        ("replies", "replyCount"),
                        ("reposts", "repostCount"),
                        ("quotes", "quoteCount"),
                    )
                },
            )
        except _SessionFailure:
            return MetricReadResult("FAILED", error_code="AUTH_REQUIRED")
        except httpx.HTTPError:
            return MetricReadResult("FAILED", error_code="NETWORK_ERROR", retryable=True)
        except (ValueError, TypeError, AttributeError, IndexError):
            return MetricReadResult("FAILED", error_code="INVALID_RESPONSE")

    async def disconnect(self) -> PublishResult:
        refresh_token = decrypt_secret(self.account.refresh_token_encrypted)
        if refresh_token:
            try:
                response = await self._raw(
                    "POST", "com.atproto.server.deleteSession", token=refresh_token
                )
                if not response.is_success and response.status_code != 401:
                    return self._api_failure(response)
            except httpx.HTTPError:
                return self.failure("NETWORK_ERROR", "Bluesky 会话撤销失败，请稍后重试")
        config = decrypt_json(self.account.credentials_encrypted)
        for key in ("app_password", "bluesky_did", "bluesky_handle", "bluesky_last_checked_at"):
            config.pop(key, None)
        config["allow_public_publish"] = False
        self.account.credentials_encrypted = encrypt_json(config)
        return await super().disconnect()


def _image_mime(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return ""


class _SessionFailure(Exception):
    def __init__(self, result: PublishResult) -> None:
        self.result = result
