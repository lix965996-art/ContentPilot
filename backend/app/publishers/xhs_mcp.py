"""Optional Xiaohongshu publisher using xpzouying/xiaohongshu-mcp.

The integration talks to a local Streamable HTTP MCP server. It never stores
Xiaohongshu cookies in ContentPilot and is disabled unless
``EXPERIMENTAL_BROWSER_PUBLISHING_ENABLED=true``.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

import httpx

from app.core.config import settings
from app.publishers.base import PublishResult
from app.services.platform_content import normalize_topics

XHS_MCP_URL = (
    settings.xhs_mcp_base_url.rstrip("/")
    if settings.xhs_mcp_base_url
    else "http://127.0.0.1:18060/mcp"
)

VISIBILITY_ALIASES = {
    "public": "公开可见",
    "public_visible": "公开可见",
    "公开可见": "公开可见",
    "only_self": "仅自己可见",
    "self_only": "仅自己可见",
    "仅自己可见": "仅自己可见",
    "friends_only": "仅互关好友可见",
    "mutual_friends": "仅互关好友可见",
    "仅互关好友可见": "仅互关好友可见",
}

_session: dict[str, Any] = {"id": None, "client": None}


def _get_client() -> httpx.AsyncClient:
    if _session["client"] is None:
        _session["client"] = httpx.AsyncClient(timeout=30)
    return _session["client"]


async def _ensure_session() -> str:
    """Initialize the MCP session and return the server-issued session id."""
    if _session["id"]:
        return str(_session["id"])

    client = _get_client()
    response = await client.post(
        XHS_MCP_URL,
        json={
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "contentpilot", "version": "1.0.0"},
            },
            "id": uuid.uuid4().hex[:8],
        },
    )
    response.raise_for_status()
    session_id = response.headers.get("Mcp-Session-Id") or response.headers.get("mcp-session-id")
    if not session_id:
        raise RuntimeError("xiaohongshu-mcp 未返回 Mcp-Session-Id")

    initialized = await client.post(
        XHS_MCP_URL,
        json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        headers={"Mcp-Session-Id": session_id},
    )
    initialized.raise_for_status()
    _session["id"] = session_id
    return session_id


async def _rpc_call(
    method: str, params: dict[str, Any] | None = None, timeout: float = 30
) -> dict[str, Any]:
    """Send one JSON-RPC request within an initialized MCP session."""
    session_id = await _ensure_session()
    try:
        response = await _get_client().post(
            XHS_MCP_URL,
            json={
                "jsonrpc": "2.0",
                "method": method,
                "params": params or {},
                "id": uuid.uuid4().hex[:8],
            },
            headers={"Mcp-Session-Id": session_id},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("xiaohongshu-mcp 返回内容不是 JSON 对象")
        return payload
    except (httpx.HTTPError, ValueError):
        # A local MCP restart invalidates its session id. Do not keep retrying
        # with stale state; the next request will perform a new handshake.
        _session["id"] = None
        raise


def _content_blocks(rpc_response: dict[str, Any]) -> list[dict[str, Any]]:
    result = rpc_response.get("result", {})
    content = result.get("content", []) if isinstance(result, dict) else []
    if not isinstance(content, list):
        return []
    return [item for item in content if isinstance(item, dict)]


def _extract_text(rpc_response: dict[str, Any]) -> str:
    """Join all text blocks instead of silently discarding later blocks."""
    if "error" in rpc_response:
        error = rpc_response["error"]
        if isinstance(error, dict):
            return f"MCP error {error.get('code', '?')}: {error.get('message', '?')}"
        return f"MCP error: {error}"
    texts = [
        str(item.get("text", "")).strip()
        for item in _content_blocks(rpc_response)
        if item.get("type") in (None, "text")
    ]
    texts = [item for item in texts if item]
    return "\n".join(texts) if texts else str(rpc_response.get("result", ""))


def _extract_image_data_url(rpc_response: dict[str, Any]) -> str:
    """Return the first MCP image block as a browser-safe data URL."""
    for item in _content_blocks(rpc_response):
        if item.get("type") != "image" or not item.get("data"):
            continue
        mime_type = str(item.get("mimeType") or item.get("mime_type") or "image/png")
        return f"data:{mime_type};base64,{item['data']}"
    return ""


def _tool_returned_error(rpc_response: dict[str, Any]) -> bool:
    if "error" in rpc_response:
        return True
    result = rpc_response.get("result", {})
    return bool(
        isinstance(result, dict)
        and (result.get("isError") is True or result.get("is_error") is True)
    )


def _safe_detail(value: str, max_length: int = 1200) -> str:
    """Redact session material before returning details to the UI or logs."""
    text = value
    for pattern in (
        r"(xsec_token[\"'=:\s]+)[^&\s\",}]+",
        r"(\ba1[\"'=:\s]+)[^;\s\",}]+",
        r"(web_session[\"'=:\s]+)[^;\s\",}]+",
    ):
        text = re.sub(pattern, r"\1[redacted]", text, flags=re.IGNORECASE)
    return text[:max_length]


async def mcp_check_login() -> tuple[bool, str]:
    try:
        response = await _rpc_call(
            "tools/call",
            {"name": "check_login_status", "arguments": {}},
        )
        text = _extract_text(response)
        lower_text = text.lower()
        logged_out_markers = ("未登录", "登录已失效", "not logged", "login required", "false")
        logged_in = not any(marker in lower_text for marker in logged_out_markers) and (
            "已登录" in text or "logged in" in lower_text or "true" in lower_text
        )
        return logged_in, _safe_detail(text)
    except Exception as exc:
        return False, _safe_detail(str(exc))


async def mcp_get_qrcode() -> dict[str, str]:
    """Return the QR image without exposing any local cookie material."""
    try:
        response = await _rpc_call(
            "tools/call",
            {"name": "get_login_qrcode", "arguments": {}},
        )
        return {
            "image_data_url": _extract_image_data_url(response),
            "message": _safe_detail(_extract_text(response)),
        }
    except Exception as exc:
        return {"image_data_url": "", "message": f"获取二维码失败: {_safe_detail(str(exc))}"}


async def mcp_logout() -> tuple[bool, str]:
    """Delete the local MCP cookies so the next login requires a fresh scan."""
    try:
        response = await _rpc_call(
            "tools/call",
            {"name": "delete_cookies", "arguments": {}},
        )
        text = _safe_detail(_extract_text(response))
        success = not _tool_returned_error(response) and any(
            marker in text.lower()
            for marker in ("成功", "已清除", "已删除", "success", "deleted", "cleared")
        )
        return success, text or ("本地登录会话已清除" if success else "未能清除本地登录会话")
    except Exception as exc:
        return False, _safe_detail(str(exc))
    finally:
        _session["id"] = None


class XiaohongshuMCPPublisher:
    platform = "XIAOHONGSHU"
    mode = "MCP_PUBLISH"

    async def check_login(self) -> tuple[bool, str]:
        return await mcp_check_login()

    async def get_qrcode(self) -> dict[str, str]:
        return await mcp_get_qrcode()

    async def publish(
        self,
        *,
        title: str,
        content: str,
        images: list[str] | None = None,
        tags: list[str] | None = None,
        visibility: str = "only_self",
        schedule_at: str | None = None,
        is_original: bool = False,
    ) -> PublishResult:
        """Publish one image note through the optional local MCP bridge."""
        title = title.strip()
        content = content.strip()
        images = [item.strip() for item in images or [] if item and item.strip()]
        topics = normalize_topics(tags)

        if not title:
            return self._validation_failure("标题不能为空")
        if len(title) > 20:
            return self._validation_failure("小红书标题不能超过 20 个字")
        if not content:
            return self._validation_failure("正文不能为空")
        if len(content) > 1000:
            return self._validation_failure("小红书正文不能超过 1000 个字")
        if not images:
            return self._validation_failure("小红书图文发布至少需要 1 张图片")

        normalized_visibility = VISIBILITY_ALIASES.get(visibility)
        if not normalized_visibility:
            return self._validation_failure("小红书可见范围参数无效")

        arguments: dict[str, Any] = {
            "title": title,
            "content": content,
            "images": images,
            "tags": topics,
            "visibility": normalized_visibility,
            "is_original": is_original,
        }
        if schedule_at:
            arguments["schedule_at"] = schedule_at

        try:
            response = await _rpc_call(
                "tools/call",
                {"name": "publish_content", "arguments": arguments},
                timeout=120,
            )
            detail_text = _extract_text(response)
            safe_text = _safe_detail(detail_text)

            if _tool_returned_error(response):
                error = response.get("error", {})
                error_code = error.get("code", "ERROR") if isinstance(error, dict) else "ERROR"
                error_message = (
                    error.get("message") if isinstance(error, dict) else str(error)
                ) or safe_text
                return self._classified_failure(
                    safe_text or str(error_message),
                    default_code=f"MCP_{error_code}",
                )

            lower_text = detail_text.lower()
            success_markers = ("成功", "success", "已发布", "note_id", "笔记id")
            if any(marker in lower_text for marker in success_markers):
                note_id, published_url = self._extract_identifier(detail_text)
                return PublishResult(
                    True,
                    self.platform,
                    self.mode,
                    "PUBLISHED",
                    external_id=note_id,
                    published_url=published_url,
                    detail={
                        "message": safe_text,
                        "method": "mcp",
                        "verified_identifier": bool(note_id or published_url),
                    },
                )

            return self._classified_failure(
                safe_text or "xiaohongshu-mcp 未返回明确发布结果",
                default_code="MCP_PUBLISH_FAILED",
            )
        except httpx.HTTPError as exc:
            return PublishResult(
                False,
                self.platform,
                self.mode,
                "FAILED",
                error_code="MCP_HTTP_ERROR",
                error_message=_safe_detail(str(exc)),
                suggested_action="请确认本机 xiaohongshu-mcp 已在 18060 端口启动。",
                retryable=True,
            )
        except Exception as exc:
            return PublishResult(
                False,
                self.platform,
                self.mode,
                "FAILED",
                error_code="MCP_ERROR",
                error_message=_safe_detail(str(exc)),
            )

    @staticmethod
    def _extract_identifier(detail_text: str) -> tuple[str, str]:
        for pattern in (
            r"(https?://www\.xiaohongshu\.com/\S+)",
            r"(https?://xhslink\.com/\S+)",
        ):
            match = re.search(pattern, detail_text)
            if not match:
                continue
            url = match.group(1).rstrip("，。),]}")
            explore_match = re.search(r"/explore/([A-Za-z0-9_-]+)", url)
            return (explore_match.group(1) if explore_match else ""), url

        for pattern in (
            r"note_id[：:=\s]+([A-Za-z0-9_-]+)",
            r"笔记\s*ID[：:=\s]+([A-Za-z0-9_-]+)",
        ):
            match = re.search(pattern, detail_text, flags=re.IGNORECASE)
            if match:
                note_id = match.group(1)
                return note_id, f"https://www.xiaohongshu.com/explore/{note_id}"
        return "", ""

    def _classified_failure(self, message: str, default_code: str) -> PublishResult:
        lower_message = message.lower()
        if any(marker in lower_message for marker in ("未登录", "登录失效", "login")):
            return PublishResult(
                False,
                self.platform,
                self.mode,
                "LOGIN_REQUIRED",
                error_code="LOGIN_REQUIRED",
                error_message=message[:500],
                suggested_action="请启动 xiaohongshu-mcp 并扫码登录。",
            )
        if any(marker in lower_message for marker in ("验证码", "captcha", "验证")):
            return PublishResult(
                False,
                self.platform,
                self.mode,
                "VERIFICATION_REQUIRED",
                error_code="VERIFICATION_REQUIRED",
                error_message=message[:500],
                suggested_action="请在小红书页面完成人工验证后重试。",
            )
        return PublishResult(
            False,
            self.platform,
            self.mode,
            "FAILED",
            error_code=default_code,
            error_message=message[:500],
            detail={"message": message, "method": "mcp"},
        )

    def _validation_failure(self, message: str) -> PublishResult:
        return PublishResult(
            False,
            self.platform,
            self.mode,
            "FAILED",
            error_code="INVALID_PUBLISH_PAYLOAD",
            error_message=message,
        )

    async def disconnect(self) -> PublishResult:
        _session["id"] = None
        return PublishResult(True, self.platform, self.mode, "DISCONNECTED")
