from pathlib import Path

import pytest

from app.publishers import wechatsync_cli, xhs_mcp
from app.publishers.wechatsync_cli import WechatsyncPublisher
from app.publishers.xhs_mcp import XiaohongshuMCPPublisher


@pytest.mark.asyncio
async def test_xiaohongshu_mcp_retries_once_after_stale_session(monkeypatch) -> None:
    calls = 0

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"result": {"content": []}}

    class FakeClient:
        async def post(self, *_args, **_kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ValueError("stale session")
            return FakeResponse()

    async def fake_session() -> str:
        return "session-id"

    monkeypatch.setattr(xhs_mcp, "_ensure_session", fake_session)
    monkeypatch.setattr(xhs_mcp, "_get_client", lambda: FakeClient())

    result = await xhs_mcp._rpc_call("tools/list")

    assert result == {"result": {"content": []}}
    assert calls == 2


@pytest.mark.asyncio
async def test_xiaohongshu_mcp_uses_upstream_argument_contract(monkeypatch) -> None:
    captured: dict = {}

    async def fake_rpc(method: str, params: dict | None = None, timeout: float = 30) -> dict:
        captured.update({"method": method, "params": params, "timeout": timeout})
        return {
            "result": {
                "content": [
                    {"type": "text", "text": "发布成功"},
                ]
            }
        }

    monkeypatch.setattr(xhs_mcp, "_rpc_call", fake_rpc)
    result = await XiaohongshuMCPPublisher().publish(
        title="真实标题",
        content="真实正文",
        images=["https://example.com/cover.jpg"],
        tags=["#AI 创作", "AI 创作", "内容运营"],
        visibility="only_self",
        is_original=True,
    )

    assert result.success is True
    assert result.status == "PUBLISHED"
    assert result.external_id == ""
    assert result.published_url == ""
    assert result.detail["verified_identifier"] is False
    assert captured["method"] == "tools/call"
    assert captured["timeout"] == 120
    assert captured["params"]["name"] == "publish_content"
    arguments = captured["params"]["arguments"]
    assert arguments["visibility"] == "仅自己可见"
    assert arguments["images"] == ["https://example.com/cover.jpg"]
    assert arguments["tags"] == ["AI创作", "内容运营"]
    assert arguments["is_original"] is True


@pytest.mark.asyncio
async def test_xiaohongshu_mcp_rejects_missing_image_without_calling_server(
    monkeypatch,
) -> None:
    async def unexpected_rpc(*_args, **_kwargs):
        raise AssertionError("invalid payload must not call the MCP server")

    monkeypatch.setattr(xhs_mcp, "_rpc_call", unexpected_rpc)
    result = await XiaohongshuMCPPublisher().publish(
        title="标题",
        content="正文",
        images=[],
    )

    assert result.success is False
    assert result.error_code == "INVALID_PUBLISH_PAYLOAD"
    assert "至少需要 1 张图片" in result.error_message


@pytest.mark.asyncio
async def test_xiaohongshu_login_qrcode_keeps_image_and_redacts_session(
    monkeypatch,
) -> None:
    async def fake_rpc(*_args, **_kwargs) -> dict:
        return {
            "result": {
                "content": [
                    {"type": "text", "text": "请扫码 xsec_token=secret-token"},
                    {"type": "image", "mimeType": "image/png", "data": "aW1hZ2U="},
                ]
            }
        }

    monkeypatch.setattr(xhs_mcp, "_rpc_call", fake_rpc)
    result = await xhs_mcp.mcp_get_qrcode()

    assert result["image_data_url"] == "data:image/png;base64,aW1hZ2U="
    assert "secret-token" not in result["message"]
    assert "[redacted]" in result["message"]


@pytest.mark.asyncio
async def test_xiaohongshu_mcp_classifies_login_required(monkeypatch) -> None:
    async def fake_rpc(*_args, **_kwargs) -> dict:
        return {
            "result": {
                "isError": True,
                "content": [{"type": "text", "text": "未登录，请先扫码登录"}],
            }
        }

    monkeypatch.setattr(xhs_mcp, "_rpc_call", fake_rpc)
    result = await XiaohongshuMCPPublisher().publish(
        title="标题",
        content="正文",
        images=["https://example.com/cover.jpg"],
    )

    assert result.success is False
    assert result.status == "LOGIN_REQUIRED"
    assert result.error_code == "LOGIN_REQUIRED"


@pytest.mark.asyncio
async def test_xiaohongshu_mcp_logout_deletes_local_cookies(monkeypatch) -> None:
    captured: dict = {}

    async def fake_rpc(method: str, params: dict | None = None, timeout: float = 30) -> dict:
        captured.update({"method": method, "params": params, "timeout": timeout})
        return {
            "result": {
                "content": [{"type": "text", "text": "Cookies 删除成功"}],
            }
        }

    monkeypatch.setattr(xhs_mcp, "_rpc_call", fake_rpc)
    success, detail = await xhs_mcp.mcp_logout()

    assert success is True
    assert "成功" in detail
    assert captured["method"] == "tools/call"
    assert captured["params"] == {"name": "delete_cookies", "arguments": {}}


@pytest.mark.asyncio
async def test_wechatsync_creates_draft_without_inventing_external_id(
    monkeypatch,
) -> None:
    captured: dict = {}

    async def installed() -> bool:
        return True

    async def fake_cli(*args: str, timeout: float) -> tuple[int, str, str]:
        captured["args"] = args
        captured["timeout"] = timeout
        markdown_path = Path(args[1])
        captured["path"] = markdown_path
        captured["markdown"] = markdown_path.read_text(encoding="utf-8")
        return 0, "同步完成", ""

    monkeypatch.setattr(wechatsync_cli, "_wechatsync_installed", installed)
    monkeypatch.setattr(wechatsync_cli, "_run_cli", fake_cli)
    result = await WechatsyncPublisher().publish(
        title='标题: "安全"',
        content_md="# 正文",
        author="ContentPilot",
        summary="摘要",
    )

    assert result.success is True
    assert result.status == "DRAFT_CREATED"
    assert result.external_id == ""
    assert result.published_url == ""
    assert captured["args"][0] == "sync"
    assert captured["args"][-2:] == ("-p", "weixin")
    assert captured["timeout"] == 180
    assert 'title: "标题: \\"安全\\""' in captured["markdown"]
    assert not captured["path"].exists()


@pytest.mark.asyncio
async def test_wechatsync_timeout_is_retryable_and_cleans_temp_file(
    monkeypatch,
) -> None:
    captured: dict = {}

    async def installed() -> bool:
        return True

    async def timeout_cli(*args: str, timeout: float) -> tuple[int, str, str]:
        captured["path"] = Path(args[1])
        raise TimeoutError

    monkeypatch.setattr(wechatsync_cli, "_wechatsync_installed", installed)
    monkeypatch.setattr(wechatsync_cli, "_run_cli", timeout_cli)
    result = await WechatsyncPublisher().publish(title="标题", content_md="正文")

    assert result.success is False
    assert result.error_code == "WECHATSYNC_TIMEOUT"
    assert result.retryable is True
    assert not captured["path"].exists()
