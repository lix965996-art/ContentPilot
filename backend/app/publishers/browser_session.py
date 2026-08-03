"""Shared browser-session management for platform publishers.

Extracts the common Playwright lifecycle (launch / close / QR login / logout)
that was previously duplicated between ``wechat_browser.py`` and
``toutiao_browser.py``.  Each platform module creates a
:class:`BrowserSessionManager` instance with its own selectors, URLs and
settings keys, then re-exports the public helpers so that existing callers
remain unchanged.
"""

from __future__ import annotations

import asyncio
import base64
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Coroutine

from playwright.async_api import BrowserContext, Page, Playwright, async_playwright

from app.core.config import settings


@dataclass
class LoginSession:
    playwright: Playwright
    context: BrowserContext
    page: Page


# Type alias for the platform-specific login-detection callback.
LoggedInCheck = Callable[[Page], Coroutine[Any, Any, bool]]


class BrowserSessionManager:
    """Manages isolated Chrome profiles and QR-login sessions for one platform.

    Parameters
    ----------
    home_url:
        The platform's creator / admin home page (e.g. ``https://mp.weixin.qq.com/``).
    qr_selectors:
        CSS selectors tried in order to locate the QR code image on the login page.
    account_name_selectors:
        CSS selectors tried in order to read the logged-in account's display name.
    profile_root_setting:
        Name of the ``settings`` attribute that holds the browser-profile root
        directory (e.g. ``"wechat_browser_profile_root"``).
    headless_setting:
        Name of the ``settings`` attribute that controls headless mode
        (e.g. ``"wechat_browser_headless"``).
    platform_label:
        Human-readable platform name used in log / error messages
        (e.g. ``"微信公众号"``).
    logged_in_check:
        Async callback ``(page) -> bool`` that returns ``True`` when the page
        reflects a logged-in session.  This is the main platform-specific hook.
    login_timeout:
        Navigation timeout in milliseconds for the login page (default 60 000).
    """

    def __init__(
        self,
        *,
        home_url: str,
        qr_selectors: tuple[str, ...],
        account_name_selectors: tuple[str, ...],
        profile_root_setting: str,
        headless_setting: str,
        platform_label: str,
        logged_in_check: LoggedInCheck,
        login_timeout: int = 60_000,
    ) -> None:
        self._home_url = home_url
        self._qr_selectors = qr_selectors
        self._account_name_selectors = account_name_selectors
        self._profile_root_setting = profile_root_setting
        self._headless_setting = headless_setting
        self._platform_label = platform_label
        self._logged_in_check = logged_in_check
        self._login_timeout = login_timeout

        self._sessions: dict[int, LoginSession] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # profile helpers
    # ------------------------------------------------------------------

    def _profile_root(self) -> Path:
        configured: str = getattr(settings, self._profile_root_setting, "").strip()
        default_dir = self._platform_label.lower().replace(" ", "-")
        root = (
            Path(configured).expanduser()
            if configured
            else Path.home() / ".contentpilot" / default_dir
        )
        root.mkdir(parents=True, exist_ok=True)
        return root.resolve()

    def _profile_dir(self, account_id: int) -> Path:
        root = self._profile_root()
        path = (root / f"account-{account_id}").resolve()
        if path.parent != root:
            raise RuntimeError(f"{self._platform_label}浏览器会话目录无效")
        path.mkdir(parents=True, exist_ok=True)
        return path

    # ------------------------------------------------------------------
    # browser lifecycle
    # ------------------------------------------------------------------

    @staticmethod
    def _chrome_path() -> str | None:
        configured = os.environ.get("CONTENTPILOT_CHROME_PATH", "").strip()
        candidates = (
            configured,
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        )
        return next((item for item in candidates if item and Path(item).is_file()), None)

    async def _launch(self, account_id: int, *, headless: bool | None = None) -> LoginSession:
        playwright = await async_playwright().start()
        resolved_headless = (
            getattr(settings, self._headless_setting, False) if headless is None else headless
        )
        launch_args: dict[str, Any] = {
            "headless": resolved_headless,
            "locale": "zh-CN",
            "timezone_id": "Asia/Shanghai",
            "viewport": {"width": 1440, "height": 900},
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-features=TranslateUI",
            ],
        }
        chrome = self._chrome_path()
        if chrome:
            launch_args["executable_path"] = chrome
        try:
            context = await playwright.chromium.launch_persistent_context(
                str(self._profile_dir(account_id)), **launch_args
            )
        except Exception:
            await playwright.stop()
            raise
        page = context.pages[0] if context.pages else await context.new_page()
        return LoginSession(playwright, context, page)

    @staticmethod
    async def _close(session: LoginSession) -> None:
        try:
            await session.context.close()
        finally:
            await session.playwright.stop()

    # ------------------------------------------------------------------
    # page-level helpers (use platform-specific selectors)
    # ------------------------------------------------------------------

    async def _logged_in(self, page: Page) -> bool:
        return await self._logged_in_check(page)

    async def _account_name(self, page: Page) -> str:
        for selector in self._account_name_selectors:
            locator = page.locator(selector).first
            if await locator.count() and await locator.is_visible():
                value = (await locator.inner_text()).strip()
                if value:
                    return value[:100]
        return ""

    async def _qr_data_url(self, page: Page) -> str:
        for selector in self._qr_selectors:
            locator = page.locator(selector).first
            if not await locator.count() or not await locator.is_visible():
                continue
            png = await locator.screenshot(type="png")
            return f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"
        return ""

    # ------------------------------------------------------------------
    # public API (re-exported by platform modules)
    # ------------------------------------------------------------------

    async def get_login_qrcode(
        self, account_id: int, *, force_refresh: bool = False
    ) -> dict[str, str | bool]:
        """Start or reuse a QR-login browser session for one local account."""
        async with self._lock:
            session = self._sessions.get(account_id)
            if session is None:
                try:
                    session = await self._launch(account_id)
                    await session.page.goto(
                        self._home_url,
                        wait_until="domcontentloaded",
                        timeout=self._login_timeout,
                    )
                    await session.page.wait_for_timeout(2_000)
                    self._sessions[account_id] = session
                except Exception as exc:
                    return {
                        "connected": False,
                        "image_data_url": "",
                        "message": f"无法启动{self._platform_label}本机 Chrome：{str(exc)[:300]}",
                    }
            try:
                if await self._logged_in(session.page):
                    return {
                        "connected": True,
                        "image_data_url": "",
                        "username": await self._account_name(session.page),
                        "message": f"{self._platform_label}账号已登录",
                    }
                if force_refresh:
                    await session.page.reload(
                        wait_until="domcontentloaded", timeout=self._login_timeout
                    )
                    await session.page.wait_for_timeout(1_500)
                image = await self._qr_data_url(session.page)
                if not image:
                    await session.page.reload(
                        wait_until="domcontentloaded", timeout=self._login_timeout
                    )
                    await session.page.wait_for_timeout(1_500)
                    image = await self._qr_data_url(session.page)
                return {
                    "connected": False,
                    "image_data_url": image,
                    "message": f"请使用{self._platform_label}管理员或运营者扫码，并在手机端确认登录"
                    if image
                    else f"{self._platform_label}登录页已打开，但没有识别到二维码；页面可能已更新，请重试。",
                }
            except Exception as exc:
                return {
                    "connected": False,
                    "image_data_url": "",
                    "message": f"读取{self._platform_label}登录页失败：{str(exc)[:300]}",
                }

    async def check_login(self, account_id: int) -> tuple[bool, str]:
        async with self._lock:
            active = self._sessions.get(account_id)
            if active:
                try:
                    if await self._logged_in(active.page):
                        name = await self._account_name(active.page)
                        self._sessions.pop(account_id, None)
                        await self._close(active)
                        return True, name or f"{self._platform_label}账号"
                    return False, "等待扫码确认"
                except Exception:
                    self._sessions.pop(account_id, None)
                    await self._close(active)
            try:
                session = await self._launch(account_id, headless=True)
                await session.page.goto(
                    self._home_url,
                    wait_until="domcontentloaded",
                    timeout=self._login_timeout,
                )
                await session.page.wait_for_timeout(1_500)
                logged = await self._logged_in(session.page)
                name = await self._account_name(session.page) if logged else ""
                await self._close(session)
                return logged, name or (
                    f"{self._platform_label}账号" if logged else "需要扫码登录"
                )
            except Exception as exc:
                return False, f"无法检测{self._platform_label}本机登录：{str(exc)[:300]}"

    async def logout(self, account_id: int) -> tuple[bool, str]:
        async with self._lock:
            session = self._sessions.pop(account_id, None)
            created = session is None
            try:
                session = session or await self._launch(account_id, headless=True)
                await session.context.clear_cookies()
                for page in session.context.pages:
                    try:
                        await page.evaluate(
                            "() => { localStorage.clear(); sessionStorage.clear(); }"
                        )
                    except Exception:
                        pass
                return True, f"{self._platform_label}本机登录会话已清除"
            except Exception as exc:
                return False, f"清除{self._platform_label}会话失败：{str(exc)[:300]}"
            finally:
                if session and (created or account_id not in self._sessions):
                    await self._close(session)
