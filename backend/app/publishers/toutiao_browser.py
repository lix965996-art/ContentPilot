"""Real, optional Toutiao creator publishing through a local Chrome profile.

The implementation follows the same boundary used by mature community tools:
the first login is completed by scanning Toutiao's QR code and the resulting
browser profile remains on this computer.  ContentPilot never serializes
cookies into its database and never reports success unless the creator page
shows a success signal after the final confirmation.
"""

from __future__ import annotations

import asyncio
import base64
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.async_api import BrowserContext, Page, Playwright, async_playwright

from app.core.config import settings
from app.publishers.base import PublishResult

TOUTIAO_HOME = "https://mp.toutiao.com/"
TOUTIAO_PUBLISH = "https://mp.toutiao.com/profile_v4/graphic/publish"
_QR_SELECTORS = (
    "img[class*='qrcode']",
    "[class*='qrcode'] img",
    "[class*='qr-code'] img",
    "[class*='login'] canvas",
    "[class*='scan'] img",
)
_ACCOUNT_NAME_SELECTORS = (
    ".auth-avator-name",
    "[class*='avatar-name']",
    "[class*='user-name']",
    "[class*='account-name']",
)


@dataclass
class LoginSession:
    playwright: Playwright
    context: BrowserContext
    page: Page


_login_sessions: dict[int, LoginSession] = {}
_session_lock = asyncio.Lock()


def _profile_root() -> Path:
    configured = settings.toutiao_browser_profile_root.strip()
    root = (
        Path(configured).expanduser() if configured else Path.home() / ".contentpilot" / "toutiao"
    )
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _profile_dir(account_id: int) -> Path:
    path = (_profile_root() / f"account-{account_id}").resolve()
    if path.parent != _profile_root():
        raise RuntimeError("今日头条浏览器会话目录无效")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _chrome_path() -> str | None:
    configured = os.environ.get("CONTENTPILOT_CHROME_PATH", "").strip()
    candidates = (
        configured,
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    )
    return next((item for item in candidates if item and Path(item).is_file()), None)


async def _launch(account_id: int, *, headless: bool | None = None) -> LoginSession:
    playwright = await async_playwright().start()
    launch_args: dict[str, Any] = {
        "headless": settings.toutiao_browser_headless if headless is None else headless,
        "locale": "zh-CN",
        "timezone_id": "Asia/Shanghai",
        "viewport": {"width": 1440, "height": 900},
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--disable-features=TranslateUI",
        ],
    }
    chrome = _chrome_path()
    if chrome:
        launch_args["executable_path"] = chrome
    try:
        context = await playwright.chromium.launch_persistent_context(
            str(_profile_dir(account_id)), **launch_args
        )
    except Exception:
        await playwright.stop()
        raise
    page = context.pages[0] if context.pages else await context.new_page()
    return LoginSession(playwright, context, page)


async def _close(session: LoginSession) -> None:
    try:
        await session.context.close()
    finally:
        await session.playwright.stop()


async def _logged_in(page: Page) -> bool:
    url = page.url.lower()
    if "/profile_v4" in url and "/auth/" not in url:
        return True
    for selector in _ACCOUNT_NAME_SELECTORS:
        if await page.locator(selector).count():
            return True
    return False


async def _account_name(page: Page) -> str:
    for selector in _ACCOUNT_NAME_SELECTORS:
        locator = page.locator(selector).first
        if await locator.count():
            value = (await locator.inner_text()).strip()
            if value:
                return value[:100]
    return ""


async def _qr_data_url(page: Page) -> str:
    for selector in _QR_SELECTORS:
        locator = page.locator(selector).first
        if not await locator.count() or not await locator.is_visible():
            continue
        png = await locator.screenshot(type="png")
        return f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"
    return ""


async def get_login_qrcode(account_id: int) -> dict[str, str | bool]:
    """Start or reuse one QR-login browser session for this account."""
    async with _session_lock:
        session = _login_sessions.get(account_id)
        if session is None:
            try:
                session = await _launch(account_id)
                await session.page.goto(TOUTIAO_HOME, wait_until="domcontentloaded", timeout=45_000)
                await session.page.wait_for_timeout(2_000)
                _login_sessions[account_id] = session
            except Exception as exc:
                return {
                    "connected": False,
                    "image_data_url": "",
                    "message": f"无法启动本机 Chrome：{str(exc)[:300]}",
                }
        try:
            if await _logged_in(session.page):
                return {
                    "connected": True,
                    "image_data_url": "",
                    "username": await _account_name(session.page),
                    "message": "今日头条账号已登录",
                }
            image = await _qr_data_url(session.page)
            if not image:
                await session.page.reload(wait_until="domcontentloaded", timeout=45_000)
                await session.page.wait_for_timeout(1_500)
                image = await _qr_data_url(session.page)
            return {
                "connected": False,
                "image_data_url": image,
                "message": "请使用抖音或今日头条 App 扫码，并在手机端确认登录"
                if image
                else "登录页已打开，但没有识别到二维码；平台页面可能已更新，请重试。",
            }
        except Exception as exc:
            return {
                "connected": False,
                "image_data_url": "",
                "message": f"读取今日头条登录页失败：{str(exc)[:300]}",
            }


async def check_login(account_id: int) -> tuple[bool, str]:
    async with _session_lock:
        active = _login_sessions.get(account_id)
        if active:
            try:
                if await _logged_in(active.page):
                    name = await _account_name(active.page)
                    _login_sessions.pop(account_id, None)
                    await _close(active)
                    return True, name
                return False, "等待扫码确认"
            except Exception:
                _login_sessions.pop(account_id, None)
                await _close(active)
        try:
            session = await _launch(account_id, headless=True)
            await session.page.goto(TOUTIAO_HOME, wait_until="domcontentloaded", timeout=45_000)
            await session.page.wait_for_timeout(1_500)
            logged = await _logged_in(session.page)
            name = await _account_name(session.page) if logged else ""
            await _close(session)
            return logged, name or ("账号已登录" if logged else "需要扫码登录")
        except Exception as exc:
            return False, f"无法检测本机登录：{str(exc)[:300]}"


async def logout(account_id: int) -> tuple[bool, str]:
    async with _session_lock:
        session = _login_sessions.pop(account_id, None)
        created = session is None
        try:
            session = session or await _launch(account_id, headless=True)
            await session.context.clear_cookies()
            for page in session.context.pages:
                try:
                    await page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
                except Exception:
                    pass
            return True, "本机今日头条登录会话已清除"
        except Exception as exc:
            return False, f"清除今日头条会话失败：{str(exc)[:300]}"
        finally:
            if session and (created or account_id not in _login_sessions):
                await _close(session)


class ToutiaoBrowserPublisher:
    platform = "TOUTIAO"
    mode = "BROWSER_PUBLISH"

    def __init__(self, account_id: int) -> None:
        self.account_id = account_id

    async def validate_credentials(self) -> PublishResult:
        logged, info = await check_login(self.account_id)
        return PublishResult(
            logged,
            self.platform,
            self.mode,
            "CONNECTED" if logged else "LOGIN_REQUIRED",
            error_code="" if logged else "LOGIN_REQUIRED",
            error_message="" if logged else "今日头条创作中心尚未登录",
            suggested_action="请获取二维码并完成扫码登录。" if not logged else "",
            detail={"username": info if logged else "", "method": "local_browser"},
        )

    async def get_capabilities(self) -> list[str]:
        return ["ARTICLE_PUBLISH", "STATUS_READ"]

    async def publish(self, request: dict[str, Any]) -> PublishResult:
        title = str(request.get("title") or "").strip()
        content = str(request.get("content") or "").strip()
        content_html = str(request.get("content_html") or "").strip()
        if not 2 <= len(title) <= 30:
            return self._failure("VALIDATION_ERROR", "今日头条标题必须为 2～30 个字符")
        if not content:
            return self._failure("VALIDATION_ERROR", "今日头条正文不能为空")

        started = time.perf_counter()
        try:
            session = await _launch(self.account_id, headless=settings.toutiao_browser_headless)
            page = session.page
            await page.goto(TOUTIAO_PUBLISH, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(2_000)
            if not await _logged_in(page):
                await _close(session)
                return self._failure(
                    "LOGIN_REQUIRED", "今日头条登录已失效，请重新扫码", status="LOGIN_REQUIRED"
                )

            title_input = page.locator(
                "textarea[placeholder*='标题'], input[placeholder*='标题'], "
                "[data-testid='title'] input"
            ).first
            if not await title_input.count():
                await _close(session)
                return self._failure("PAGE_CHANGED", "未找到标题输入框，今日头条页面可能已更新")
            await title_input.fill(title)

            editor = page.locator(
                ".ProseMirror[contenteditable='true'], .ql-editor[contenteditable='true'], "
                "[contenteditable='true'][class*='editor'], [contenteditable='true']"
            ).first
            if not await editor.count():
                await _close(session)
                return self._failure("PAGE_CHANGED", "未找到正文编辑器，今日头条页面可能已更新")
            safe_html = content_html or "".join(
                f"<p>{line}</p>" for line in content.splitlines() if line.strip()
            )
            await editor.evaluate(
                "(el, html) => { el.innerHTML = html; el.dispatchEvent(new InputEvent('input', "
                "{ bubbles: true, inputType: 'insertText', data: null })); }",
                safe_html,
            )

            no_cover = page.get_by_text(re.compile("无封面")).first
            if await no_cover.count() and await no_cover.is_visible():
                await no_cover.click()

            preview = page.get_by_role("button", name=re.compile("预览并发布|发布")).first
            if not await preview.count():
                await _close(session)
                return self._failure("PAGE_CHANGED", "未找到“预览并发布”按钮")
            await preview.click()
            await page.wait_for_timeout(1_500)
            confirm = page.get_by_role("button", name=re.compile("确认发布|发布")).last
            if await confirm.count() and await confirm.is_visible():
                await confirm.click()
            await page.wait_for_timeout(4_000)

            challenge = page.get_by_text(re.compile("验证码|安全验证|操作频繁|滑块")).first
            if await challenge.count() and await challenge.is_visible():
                await _close(session)
                return self._failure(
                    "CAPTCHA_REQUIRED",
                    "今日头条要求人工安全验证",
                    status="NEED_USER_ACTION",
                )
            success = page.get_by_text(re.compile("发布成功|已发布|审核中")).first
            success_visible = bool(await success.count() and await success.is_visible())
            current_url = page.url
            await _close(session)
            if success_visible or "/manage" in current_url or "/content" in current_url:
                return PublishResult(
                    True,
                    self.platform,
                    self.mode,
                    "PUBLISHED",
                    published_url=current_url if current_url.startswith("http") else "",
                    detail={
                        "method": "local_browser",
                        "durationMs": int((time.perf_counter() - started) * 1000),
                    },
                )
            return self._failure("PUBLISH_UNCONFIRMED", "页面没有返回明确的发布成功状态")
        except Exception as exc:
            return self._failure("BROWSER_ERROR", f"今日头条浏览器发布失败：{str(exc)[:400]}")

    async def query_status(self, task_id: str) -> dict[str, Any]:
        return {"taskId": task_id, "status": "UNKNOWN", "source": "local_browser"}

    async def disconnect(self) -> PublishResult:
        ok, message = await logout(self.account_id)
        return PublishResult(
            ok,
            self.platform,
            self.mode,
            "DISCONNECTED" if ok else "FAILED",
            error_message="" if ok else message,
        )

    def _failure(self, code: str, message: str, *, status: str = "FAILED") -> PublishResult:
        return PublishResult(
            False,
            self.platform,
            self.mode,
            status,
            retryable=code in {"BROWSER_ERROR", "PUBLISH_UNCONFIRMED"},
            error_code=code,
            error_message=message,
            suggested_action="请检查账号登录状态和今日头条创作页面后重试。",
        )
