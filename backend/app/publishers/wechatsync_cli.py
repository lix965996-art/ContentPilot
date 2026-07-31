"""Optional browser-backed draft sync through the Wechatsync CLI.

This bridge is deliberately separate from official WeChat publishing. It is
disabled by default and only used as an explicit fallback when
``WECHATSYNC_CLI_ENABLED=true``.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from app.publishers.base import PublishResult


async def _run_cli(*args: str, timeout: float) -> tuple[int, str, str]:
    executable = shutil.which("wechatsync")
    if not executable:
        raise FileNotFoundError("wechatsync CLI 未安装")
    process = await asyncio.create_subprocess_exec(
        executable,
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        process.kill()
        await process.communicate()
        raise
    return (
        int(process.returncode or 0),
        stdout_bytes.decode("utf-8", errors="replace"),
        stderr_bytes.decode("utf-8", errors="replace"),
    )


async def _wechatsync_installed() -> bool:
    try:
        return_code, _, _ = await _run_cli("--version", timeout=10)
        return return_code == 0
    except (FileNotFoundError, TimeoutError):
        return False


async def _wechatsync_auth(platform: str) -> tuple[bool, str]:
    try:
        return_code, stdout, stderr = await _run_cli("auth", platform, timeout=20)
        detail = stdout.strip() or stderr.strip()
        lower_detail = detail.lower()
        logged_out = any(
            marker in lower_detail for marker in ("未登录", "not logged", "login required", "false")
        )
        logged_in = (
            return_code == 0
            and not logged_out
            and ("已登录" in detail or "logged" in lower_detail or "true" in lower_detail)
        )
        return logged_in, detail
    except TimeoutError:
        return False, "Wechatsync 登录检查超时，请确认 Chrome 扩展已连接"
    except FileNotFoundError:
        return False, "Wechatsync CLI 未安装。请运行: npm install -g @wechatsync/cli"


class WechatsyncPublisher:
    """Create a browser-backed WeChat draft through the local extension."""

    platform = "WECHAT_OFFICIAL"
    mode = "WECHATSYNC_CLI"
    target_platform = "weixin"

    async def check_login(self) -> tuple[bool, str]:
        if not await _wechatsync_installed():
            return False, "Wechatsync CLI 未安装。请运行: npm install -g @wechatsync/cli"
        return await _wechatsync_auth(self.target_platform)

    async def publish(
        self,
        title: str,
        content_md: str,
        author: str = "",
        summary: str = "",
        cover_url: str = "",
    ) -> PublishResult:
        if not await _wechatsync_installed():
            return PublishResult(
                False,
                self.platform,
                self.mode,
                "FAILED",
                error_code="CLI_NOT_FOUND",
                error_message="Wechatsync CLI 未安装。请运行: npm install -g @wechatsync/cli",
            )

        markdown = f"---\ntitle: {json.dumps(title, ensure_ascii=False)}\n"
        if author:
            markdown += f"author: {json.dumps(author, ensure_ascii=False)}\n"
        if summary:
            markdown += f"summary: {json.dumps(summary, ensure_ascii=False)}\n"
        markdown += f"---\n\n{content_md}"

        started = time.perf_counter()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", encoding="utf-8", delete=False
        ) as output:
            output.write(markdown)
            temporary_path = output.name

        command = ["sync", temporary_path, "-p", self.target_platform]
        if cover_url:
            command.extend(["--cover", cover_url])

        try:
            return_code, stdout, stderr = await _run_cli(*command, timeout=180)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            detail: dict[str, Any] = {
                "stdout": stdout[:2000],
                "stderr": stderr[:2000],
                "exit_code": return_code,
                "duration_ms": elapsed_ms,
                "method": "wechatsync_cli",
                "target_platform": self.target_platform,
            }
            if return_code == 0:
                # Wechatsync defaults to a platform draft. It does not provide
                # a stable platform draft id, so never invent one here.
                return PublishResult(
                    True,
                    self.platform,
                    self.mode,
                    "DRAFT_CREATED",
                    detail=detail,
                )
            return PublishResult(
                False,
                self.platform,
                self.mode,
                "FAILED",
                error_code="WECHATSYNC_FAILED",
                error_message=stderr.strip() or stdout.strip() or "同步草稿失败",
                detail=detail,
            )
        except TimeoutError:
            return PublishResult(
                False,
                self.platform,
                self.mode,
                "FAILED",
                error_code="WECHATSYNC_TIMEOUT",
                error_message="Wechatsync 同步超时，请检查 Chrome 扩展和登录状态。",
                retryable=True,
            )
        except FileNotFoundError:
            return PublishResult(
                False,
                self.platform,
                self.mode,
                "FAILED",
                error_code="CLI_NOT_FOUND",
                error_message="Wechatsync CLI 未安装",
            )
        finally:
            Path(temporary_path).unlink(missing_ok=True)

    async def disconnect(self) -> PublishResult:
        return PublishResult(True, self.platform, self.mode, "DISCONNECTED")
