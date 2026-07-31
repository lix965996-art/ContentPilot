"""
CDP (Chrome DevTools Protocol) publishers for platforms without open APIs.

- WechatCDPPublisher: logs into mp.weixin.qq.com via a local Chrome profile,
  fills the draft editor and saves to draft box.
- XiaohongshuCDPPublisher: logs into creator.xiaohongshu.com via a local
  Chrome profile, fills the publish form and submits.

Cookies live exclusively in the local Chrome user-data directory and are
never written to the database.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.async_api import Browser, BrowserContext, async_playwright

from app.core.config import settings
from app.publishers.base import PublishResult

# ---------------------------------------------------------------------------
# shared browser helpers
# ---------------------------------------------------------------------------

USER_DATA_ROOT = Path.home() / ".contentpilot" / "chrome-profiles"
CHROME_PATH = os.environ.get("CONTENTPILOT_CHROME_PATH", "")
CDP_ENDPOINT = os.environ.get("CONTENTPILOT_CDP_ENDPOINT", "http://127.0.0.1:9222")
WECHAT_MP_URL = "https://mp.weixin.qq.com"
XIAOHONGSHU_CREATOR_URL = "https://creator.xiaohongshu.com"

_pw_instance = None


async def _get_playwright():
    global _pw_instance
    if _pw_instance is None:
        _pw_instance = await async_playwright().start()
    return _pw_instance


async def _launch_browser(channel: str, headless: bool) -> Browser:
    """Launch a persistent Chromium with the given profile sub-directory.

    If CONTENTPILOT_CDP_ENDPOINT is set, connect to an already-running
    Chrome with ``--remote-debugging-port=9222`` instead of launching a
    new browser.  This avoids losing the existing login session.
    """
    pw = await _get_playwright()
    cdp_endpoint = os.environ.get("CONTENTPILOT_CDP_ENDPOINT", "")
    if cdp_endpoint:
        browser = await pw.chromium.connect_over_cdp(cdp_endpoint)
        return browser  # type: ignore[return-value]

    profile_dir = USER_DATA_ROOT / channel
    profile_dir.mkdir(parents=True, exist_ok=True)
    launch_kwargs: dict[str, Any] = {
        "headless": headless,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--disable-features=TranslateUI",
        ],
    }
    if CHROME_PATH:
        launch_kwargs["executable_path"] = CHROME_PATH
    context = await pw.chromium.launch_persistent_context(str(profile_dir), **launch_kwargs)
    return context  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# WeChat Official Account CDP Publisher
# ---------------------------------------------------------------------------

WECHAT_LOGIN_URL = "https://mp.weixin.qq.com"
WECHAT_NEW_DRAFT_URL = (
    "https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2"
    "&action=edit&isNew=1&type=77&share=1"
)


@dataclass
class WechatDraftPayload:
    title: str
    author: str
    digest: str
    content_html: str
    content_source_url: str
    images: list[str]


class WechatCDPPublisher:
    platform = "WECHAT_OFFICIAL"
    mode = "CDP_DRAFT"

    def __init__(self) -> None:
        self._context: BrowserContext | None = None

    async def _ensure_context(self, headless: bool = True) -> BrowserContext:
        if self._context is None:
            self._context = await _launch_browser("wechat", headless=headless)
        return self._context

    async def login_with_qr(self) -> tuple[bool, str]:
        """Launch visible Chrome for QR login.  Returns (logged_in, message)."""
        # Close stale headless context if any
        if self._context is not None:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None
        ctx = await _launch_browser("wechat", headless=False)
        self._context = ctx
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(WECHAT_MP_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        if "/cgi-bin/home" in page.url or "token=" in page.url:
            return True, "已登录"

        # Screenshot for debugging
        screen_path = str(USER_DATA_ROOT / "wechat_login_screen.png")
        await page.screenshot(path=screen_path)
        print(f"登录页截图: {screen_path}")

        # WeChat MP login selectors (multiple variants)
        qr_selectors = [
            ".login_qrcode_img",
            ".qrcode img",
            "img.qrcode",
            "#login_qr_img",
            ".mp_qrcode_img img",
            ".wechat-qrcode img",
            "img[src*='qrcode']",
            "img[src*='qr']",
        ]
        for sel in qr_selectors:
            el = page.locator(sel)
            if await el.count() > 0:
                qr_src = await el.first.get_attribute("src") or ""
                if qr_src:
                    print(f"找到二维码: {sel} -> {qr_src[:80]}...")
                    print("请用微信扫描二维码（120 秒超时）")
                    for _ in range(60):
                        await asyncio.sleep(2)
                        try:
                            if "/cgi-bin/home" in page.url or "token=" in page.url:
                                return True, "扫码登录成功"
                            # Also check if title changed from login page
                            title = await page.title()
                            if "微信公众平台" not in title:
                                pass
                        except Exception:
                            pass
                    return False, "扫码超时（120 秒未完成）"

        # Try clicking the "account login" button if QR not visible
        login_btn = page.locator("a:has-text('登录'), button:has-text('登录'), .login-btn")
        if await login_btn.count() > 0:
            await login_btn.first.click()
            await asyncio.sleep(3)
            for sel in qr_selectors:
                el = page.locator(sel)
                if await el.count() > 0:
                    qr_src = await el.first.get_attribute("src") or ""
                    print(f"点击登录后找到二维码: {sel}")
                    print("请用微信扫描二维码（120 秒超时）")
                    for _ in range(60):
                        await asyncio.sleep(2)
                        if "/cgi-bin/home" in page.url or "token=" in page.url:
                            return True, "扫码登录成功"
                    return False, "扫码超时"

        return False, f"未检测到登录二维码。请查看截图 {screen_path}"

    async def check_login(self) -> tuple[bool, str]:
        """Return (logged_in, qr_url_or_error)."""
        try:
            ctx = await self._ensure_context()
            pages = ctx.pages or [await ctx.new_page()]
            page = pages[0]
            await page.goto(WECHAT_MP_URL, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(2)
            logged_in = "/cgi-bin/home" in page.url or "token=" in page.url
            if logged_in:
                return True, ""
            qr_el = page.locator(".login_qrcode_img, .qrcode, #login_qr_img")
            if await qr_el.count() > 0:
                qr_src = await qr_el.first.get_attribute("src") or "需要扫码登录"
                return False, qr_src
            return False, page.url
        except Exception as exc:
            return False, str(exc)

    async def publish(self, payload: WechatDraftPayload) -> PublishResult:
        """Open WeChat MP editor, fill fields, save as draft."""
        try:
            ctx = await self._ensure_context()
            page = await ctx.new_page()

            # Navigate to editor
            await page.goto(WECHAT_NEW_DRAFT_URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            # Check if we need login
            if "login" in page.url.lower() or "/cgi-bin/login" in page.url:
                return PublishResult(
                    False,
                    self.platform,
                    self.mode,
                    "LOGIN_REQUIRED",
                    error_code="LOGIN_REQUIRED",
                    error_message="微信后台需要登录。请先用 Chrome 登录 mp.weixin.qq.com。",
                    suggested_action="在 Chrome 中打开 mp.weixin.qq.com 并登录后重试。",
                )

            # Fill title
            title_input = page.locator("#title")
            if await title_input.count() > 0:
                await title_input.fill(payload.title)

            # Fill author
            author_input = page.locator("#author")
            if await author_input.count() > 0:
                await author_input.fill(payload.author)

            # Fill digest via JS (the editor is an iframe)
            try:
                await page.evaluate(
                    """(digest) => {
                        var el = document.querySelector('#js_description');
                        if (el) el.value = digest;
                    }""",
                    payload.digest,
                )
            except Exception:
                pass

            # Fill content body (the editor is in an iframe)
            frame = page.frame("ueditor_0") or page.main_frame
            try:
                await frame.evaluate(
                    """(html) => {
                        var ed = document.querySelector('#ueditor_0');
                        if (ed && ed.contentWindow && ed.contentWindow.document) {
                            ed.contentWindow.document.body.innerHTML = html;
                        } else {
                            var body = document.querySelector('body');
                            if (body) body.innerHTML = html;
                        }
                    }""",
                    payload.content_html,
                )
            except Exception:
                pass

            # Click save.  The WeChat editor sends an AJAX POST to one of:
            #   /cgi-bin/operate_appmsg?t=ajax-response&sub=save_draft
            #   /cgi-bin/appmsg?t=ajax-save
            # Capture the first JSON response that returns a media_id / msgid.
            draft_id = ""
            captured_responses: list[dict] = []

            async def _capture(resp):
                if resp.url and "/cgi-bin/" in resp.url:
                    try:
                        body = await resp.json()
                        captured_responses.append({"url": resp.url, "body": body})
                        mid = (
                            body.get("media_id")
                            or body.get("msgid")
                            or (body.get("data") or {}).get("media_id")
                        )
                        if mid:
                            nonlocal draft_id
                            draft_id = str(mid)
                    except Exception:
                        pass

            page.on("response", _capture)

            save_btn = page.locator("#js_submit, #save, button:has-text('保存')").first
            if await save_btn.count() > 0:
                await save_btn.click()
            else:
                await page.keyboard.press("Control+s")

            # Wait for the save AJAX to complete
            for _ in range(10):
                await asyncio.sleep(1.5)
                if draft_id:
                    break

            # Also check URL / page content as fallback
            if not draft_id and "msgid" in page.url:
                m = re.search(r"msgid=(\d+)", page.url)
                if m:
                    draft_id = m.group(1)

            if not draft_id:
                try:
                    page_text = await page.locator("body").inner_text()
                    m = re.search(r"media_id[：:=]+\\s*(\\d+)", page_text)
                    if m:
                        draft_id = m.group(1)
                except Exception:
                    pass

            if not draft_id and captured_responses:
                # Print captured responses for debugging
                print(f"[CDP] captured {len(captured_responses)} responses")
                for cr in captured_responses[:3]:
                    print(f"  {cr['url'][:100]}")
                    print(f"  body keys: {list(cr['body'].keys())[:10]}")

            if draft_id:
                return PublishResult(
                    True,
                    self.platform,
                    self.mode,
                    "DRAFT_CREATED",
                    external_id=draft_id,
                    published_url=f"https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit&msgid={draft_id}",
                    detail={"draftId": draft_id, "method": "cdp"},
                )

            # Might need user action
            captcha = page.locator("text=验证码, text=安全验证, text=需要验证")
            if await captcha.count() > 0:
                return PublishResult(
                    False,
                    self.platform,
                    self.mode,
                    "NEED_USER_ACTION",
                    error_code="CAPTCHA_REQUIRED",
                    error_message="微信后台要求验证码验证，需要人工处理。",
                    suggested_action="请在 Chrome 中手动完成验证码后重试。",
                )

            return PublishResult(
                False,
                self.platform,
                self.mode,
                "FAILED",
                error_code="DRAFT_SAVE_FAILED",
                error_message=f"草稿保存后未获取到 media_id。当前 URL: {page.url[:200]}",
            )
        except Exception as exc:
            return PublishResult(
                False,
                self.platform,
                self.mode,
                "FAILED",
                error_code="CDP_ERROR",
                error_message=str(exc),
                retryable=True,
            )

    async def disconnect(self) -> PublishResult:
        if self._context:
            await self._context.close()
            self._context = None
        return PublishResult(True, self.platform, self.mode, "DISCONNECTED")


# ---------------------------------------------------------------------------
# Xiaohongshu CDP Publisher
# ---------------------------------------------------------------------------

XHS_CREATOR_URL = "https://creator.xiaohongshu.com"
XHS_PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish"


class XiaohongshuCDPPublisher:
    platform = "XIAOHONGSHU"
    mode = "CDP_PUBLISH"

    def __init__(self) -> None:
        self._context: BrowserContext | None = None

    async def _ensure_context(self) -> BrowserContext:
        if self._context is None:
            self._context = await _launch_browser("xiaohongshu", headless=True)
        return self._context

    async def check_login(self) -> tuple[bool, str]:
        """Return (logged_in, qr_url_or_error)."""
        try:
            ctx = await self._ensure_context()
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            await page.goto(XHS_CREATOR_URL, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(2)
            if "/login" not in page.url and "login" not in page.url.lower():
                return True, ""
            qr_img = page.locator(".qrcode-img img, .login-qrcode img, img[src*='qrcode']")
            if await qr_img.count() > 0:
                qr_src = await qr_img.first.get_attribute("src") or "需要扫码"
                return False, qr_src
            return False, page.url
        except Exception as exc:
            return False, str(exc)

    async def publish(
        self, title: str, content: str, images: list[str], hashtags: list[str]
    ) -> PublishResult:
        """Open Xiaohongshu creator, fill publish form, submit."""
        started = time.perf_counter()
        try:
            ctx = await self._ensure_context()
            page = await ctx.new_page()
            await page.goto(XHS_PUBLISH_URL, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            if "/login" in page.url or "login" in page.url.lower():
                return PublishResult(
                    False,
                    self.platform,
                    self.mode,
                    "LOGIN_REQUIRED",
                    error_code="LOGIN_REQUIRED",
                    error_message="小红书创作中心需要登录。",
                    suggested_action="请在 Chrome 中打开 creator.xiaohongshu.com 并登录后重试。",
                )

            # Fill title
            title_el = page.locator('[placeholder*="标题"], #title, .title-input input').first
            if await title_el.count() > 0:
                await title_el.fill(title)
                await asyncio.sleep(0.5)

            # Fill content
            content_sel = '[placeholder*="正文"], #content, .ql-editor, [contenteditable="true"]'
            content_el = page.locator(content_sel).first
            if await content_el.count() > 0:
                await content_el.click()
                await content_el.fill(content)
                await asyncio.sleep(0.5)

            # Fill hashtags
            if hashtags:
                tag_sel = '[placeholder*="标签"], .tag-input input, input[placeholder*="搜索"]'
                tag_input = page.locator(tag_sel).first
                if await tag_input.count() > 0:
                    for tag in hashtags[:10]:
                        await tag_input.fill(tag)
                        await asyncio.sleep(0.5)
                        await page.keyboard.press("Enter")
                        await asyncio.sleep(0.3)

            # Upload images
            if images:
                upload_btn = page.locator('input[type="file"], .upload-input input').first
                if await upload_btn.count() > 0:
                    for img_path in images[:9]:
                        resolved = Path(img_path)
                        if resolved.is_file():
                            await upload_btn.set_input_files(str(resolved))
                            await asyncio.sleep(1)

            await asyncio.sleep(1)

            # Click publish
            pub_sel = (
                'button:has-text("发布"), button:has-text("发表"), '
                '.publish-btn, [data-testid="publish-btn"]'
            )
            publish_btn = page.locator(pub_sel).first
            if await publish_btn.count() > 0:
                await publish_btn.click()
                await asyncio.sleep(5)

            # Capture result
            note_id = ""
            published_url = ""
            if "/publish/success" in page.url or "success" in page.url.lower():
                note_id = f"xhs-cdp-{int(started)}"
                published_url = f"https://www.xiaohongshu.com/explore/{note_id}"

            captcha = page.locator("text=验证码, text=滑块, text=安全验证")
            if await captcha.count() > 0:
                return PublishResult(
                    False,
                    self.platform,
                    self.mode,
                    "NEED_USER_ACTION",
                    error_code="CAPTCHA_REQUIRED",
                    error_message="小红书要求验证，需要人工处理。",
                    suggested_action="请在浏览器中手动完成验证后重试。",
                )

            if note_id:
                return PublishResult(
                    True,
                    self.platform,
                    self.mode,
                    "PUBLISHED",
                    external_id=note_id,
                    published_url=published_url,
                    detail={"noteId": note_id, "method": "cdp"},
                )
            return PublishResult(
                False,
                self.platform,
                self.mode,
                "FAILED",
                error_code="PUBLISH_FAILED",
                error_message=f"发布后未检测到成功标识。URL: {page.url[:200]}",
            )
        except Exception as exc:
            return PublishResult(
                False,
                self.platform,
                self.mode,
                "FAILED",
                error_code="CDP_ERROR",
                error_message=str(exc),
                retryable=True,
            )

    async def disconnect(self) -> PublishResult:
        if self._context:
            await self._context.close()
            self._context = None
        return PublishResult(True, self.platform, self.mode, "DISCONNECTED")


# ---------------------------------------------------------------------------
# XiaohongshuMCPPublisher – bridges to a local xiaohongshu-mcp process
# ---------------------------------------------------------------------------

XHS_MCP_DEFAULT_PATH = str(USER_DATA_ROOT.parent / "xiaohongshu-mcp" / "xiaohongshu-mcp")


class XiaohongshuMCPPublisher:
    """Talk to a locally running xiaohongshu-mcp process via its JSON-RPC API.

    The MCP binary must be started separately (e.g. via ``./xiaohongshu-mcp serve``
    or the equivalent).  This publisher sends HTTP-style JSON-RPC calls to
    the MCP's HTTP endpoint.
    """

    platform = "XIAOHONGSHU"
    mode = "MCP_PUBLISH"

    def __init__(self, mcp_base: str = "") -> None:
        base = (mcp_base or settings.xhs_mcp_base_url or "http://127.0.0.1:3100").rstrip("/")
        self._base = base

    async def check_login(self) -> tuple[bool, str]:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.post(
                    f"{self._base}/tools/call",
                    json={"name": "check_login_status", "arguments": {}},
                )
            data = r.json()
            logged = bool(data.get("content", [{}])[0].get("text", "").lower().find("已登录") >= 0)
            return logged, ""
        except Exception as exc:
            return False, str(exc)

    async def publish(
        self, title: str, content: str, images: list[str], hashtags: list[str]
    ) -> PublishResult:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=60) as c:
                r = await c.post(
                    f"{self._base}/tools/call",
                    json={
                        "name": "publish_content",
                        "arguments": {
                            "title": title,
                            "content": content,
                            "images": images,
                            "hashtags": hashtags,
                        },
                    },
                )
            data = r.json()
            text = data.get("content", [{}])[0].get("text", "")
            if "成功" in text or "发布成功" in text:
                note_id = ""
                url = ""
                m = re.search(r"(?:链接|url|id)[：:]\s*(\S+)", text)
                if m:
                    url = m.group(1)
                    note_id = url.split("/")[-1]
                return PublishResult(
                    True,
                    self.platform,
                    self.mode,
                    "PUBLISHED",
                    external_id=note_id,
                    published_url=url,
                    detail={"raw": text, "method": "mcp"},
                )
            if "登录" in text:
                return PublishResult(
                    False,
                    self.platform,
                    self.mode,
                    "LOGIN_REQUIRED",
                    error_code="LOGIN_REQUIRED",
                    error_message=f"小红书 MCP: {text}",
                    suggested_action="启动 xiaohongshu-mcp 并完成扫码登录后重试。",
                )
            return PublishResult(
                False,
                self.platform,
                self.mode,
                "FAILED",
                error_code="MCP_FAILED",
                error_message=text[:500] or "xiaohongshu-mcp 返回空响应",
            )
        except Exception as exc:
            return PublishResult(
                False,
                self.platform,
                self.mode,
                "FAILED",
                error_code="MCP_ERROR",
                error_message=str(exc),
                retryable=True,
            )

    async def disconnect(self) -> PublishResult:
        return PublishResult(True, self.platform, self.mode, "DISCONNECTED")
