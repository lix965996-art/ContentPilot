"""Real, optional Toutiao creator publishing through a local Chrome profile.

The implementation follows the same boundary used by mature community tools:
the first login is completed by scanning Toutiao's QR code and the resulting
browser profile remains on this computer.  ContentPilot never serializes
cookies into its database and never reports success unless the creator page
shows a success signal after the final confirmation.

Browser-session lifecycle (launch / QR login / logout) is handled by
:class:`~app.publishers.browser_session.BrowserSessionManager`; this module
only contains Toutiao-specific page automation and the publisher.
"""

from __future__ import annotations

import asyncio
import re
import tempfile
import time
from pathlib import Path
from typing import Any

from playwright.async_api import Page

from app.publishers.base import PublishResult
from app.publishers.browser_session import BrowserSessionManager, LoginSession
from app.publishers.wechat_browser import _materialize_images

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


async def _toutiao_logged_in(page: Page) -> bool:
    url = page.url.lower()
    if "/profile_v4" in url and "/auth/" not in url:
        return True
    for selector in _ACCOUNT_NAME_SELECTORS:
        if await page.locator(selector).count():
            return True
    return False


_manager = BrowserSessionManager(
    home_url=TOUTIAO_HOME,
    qr_selectors=_QR_SELECTORS,
    account_name_selectors=_ACCOUNT_NAME_SELECTORS,
    profile_root_setting="toutiao_browser_profile_root",
    headless_setting="toutiao_browser_headless",
    platform_label="今日头条",
    logged_in_check=_toutiao_logged_in,
    login_timeout=45_000,
)

# Public API – re-exported so existing callers are unchanged.
get_login_qrcode = _manager.get_login_qrcode
check_login = _manager.check_login
logout = _manager.logout

# Internal helpers used by ToutiaoBrowserPublisher below.
_launch = _manager._launch  # noqa: SLF001
_close = _manager._close  # noqa: SLF001
_logged_in = _manager._logged_in  # noqa: SLF001


async def _append_article_images(page: Page, paths: list[Path]) -> int:
    if not paths:
        return 0
    editor = page.locator(
        ".ProseMirror[contenteditable='true'], .ql-editor[contenteditable='true'], "
        "[contenteditable='true'][class*='editor'], [contenteditable='true']"
    ).first
    before = await editor.locator("img").count()
    await editor.focus()
    await editor.evaluate(
        """element => {
          const selection = window.getSelection();
          const range = document.createRange();
          range.selectNodeContents(element);
          range.collapse(false);
          selection.removeAllRanges();
          selection.addRange(range);
        }"""
    )
    image_tool = page.locator(".syl-toolbar-tool.image button").first
    if not await image_tool.count():
        raise RuntimeError("未找到今日头条正文图片入口，页面结构可能已经更新")
    # Toutiao places a transparent editor layer above the toolbar while it is
    # autosaving. A normal Playwright click can therefore wait forever even
    # though the button itself is visible. Trigger the button's own handler
    # directly, then upload through the file input created by that handler.
    await image_tool.evaluate("element => element.click()")
    file_input = page.locator("input[type='file'][accept*='image']").first
    await file_input.wait_for(state="attached", timeout=10_000)
    await file_input.set_input_files([str(path) for path in paths])
    uploaded_items = page.locator(".upload-image-wrapper .pic-select-image-item-wrap")
    successful_items = page.locator(".upload-image-wrapper .pic-select-image-item-wrap .success")
    for _ in range(90):
        await page.wait_for_timeout(500)
        if await uploaded_items.count() >= len(paths) and await successful_items.count() >= len(
            paths
        ):
            break
    else:
        raise RuntimeError("今日头条图片上传没有完成，请检查图片格式或网络")

    confirm = page.get_by_role("button", name="确定", exact=True).last
    if not await confirm.count():
        raise RuntimeError("未找到今日头条图片上传确认按钮，页面结构可能已经更新")
    await confirm.evaluate("element => element.click()")
    expected = before + len(paths)
    for _ in range(90):
        await page.wait_for_timeout(500)
        if await editor.locator("img").count() >= expected:
            return len(paths)
    raise RuntimeError("今日头条图片上传超时，请检查图片格式或平台页面")


class ToutiaoBrowserPublisher:
    platform = "TOUTIAO"
    mode = "BROWSER_PUBLISH"

    def __init__(self, account_id: int, mode: str = "BROWSER_PUBLISH") -> None:
        self.account_id = account_id
        self.mode = mode

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
        return ["ARTICLE_PUBLISH", "DRAFT_CREATE", "DRAFT_UPDATE", "STATUS_READ"]

    async def publish(self, request: dict[str, Any]) -> PublishResult:
        title = str(request.get("title") or "").strip()
        content = str(request.get("content") or "").strip()
        content_html = str(request.get("content_html") or "").strip()
        if not 2 <= len(title) <= 30:
            return self._failure("VALIDATION_ERROR", "今日头条标题必须为 2～30 个字符")
        if not content:
            return self._failure("VALIDATION_ERROR", "今日头条正文不能为空")

        started = time.perf_counter()
        session: LoginSession | None = None
        try:
            # Toutiao currently returns business error 7050 for cloud-draft
            # writes from headless Chrome, while the same authenticated profile
            # succeeds in a normal Chrome window. Keep publishing headful so the
            # platform receives an ordinary creator-browser environment.
            session = await _launch(self.account_id, headless=False)
            page = session.page
            await page.goto(TOUTIAO_PUBLISH, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(2_000)
            if not await _logged_in(page):
                await _close(session)
                return self._failure(
                    "LOGIN_REQUIRED", "今日头条登录已失效，请重新扫码", status="LOGIN_REQUIRED"
                )

            draft_future: asyncio.Future[tuple[bool, str]] | None = None
            if self.mode == "BROWSER_DRAFT":
                draft_future = asyncio.get_running_loop().create_future()

                async def capture_draft_id(response) -> None:
                    if (
                        response.request.method != "POST"
                        or "/mp/agw/article/publish" not in response.url
                    ):
                        return
                    try:
                        payload = await response.json()
                        data = payload.get("data") or {}
                        draft_id = str(data.get("pgcId") or data.get("pgc_id") or "")
                        if draft_future.done():
                            return
                        if payload.get("code") == 0 and draft_id:
                            draft_future.set_result((True, draft_id))
                        elif payload.get("code") != 0:
                            message = str(
                                payload.get("reason")
                                or payload.get("message")
                                or "今日头条拒绝保存草稿"
                            )
                            draft_future.set_result((False, message))
                    except Exception:
                        return

                page.on(
                    "response", lambda response: asyncio.create_task(capture_draft_id(response))
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
            if self.mode == "BROWSER_DRAFT":
                # Playwright's contenteditable fill emits the native events used
                # by Toutiao's editor state and cloud-draft debounce. Replacing
                # innerHTML alone changes what is visible but does not reliably
                # update the React/editor model, so no cloud draft is created.
                await editor.fill(content)
            else:
                safe_html = content_html or "".join(
                    f"<p>{line}</p>" for line in content.splitlines() if line.strip()
                )
                await editor.evaluate(
                    "(el, html) => { el.innerHTML = html; el.dispatchEvent(new InputEvent('input', "
                    "{ bubbles: true, inputType: 'insertText', data: null })); }",
                    safe_html,
                )

            image_values = [str(value) for value in request.get("images", []) if value]
            image_inserted_count = 0
            if self.mode == "BROWSER_DRAFT" and image_values:
                with tempfile.TemporaryDirectory(prefix="contentpilot-toutiao-images-") as temp_dir:
                    image_paths = await _materialize_images(image_values, Path(temp_dir))
                    image_inserted_count = await _append_article_images(page, image_paths)

            if self.mode == "BROWSER_DRAFT":
                # Ignore any intermediate autosave caused by the title alone.
                # The next successful publish response is the one scheduled
                # after the final body/image change.
                draft_future = asyncio.get_running_loop().create_future()
                try:
                    draft_saved, draft_result = await asyncio.wait_for(
                        asyncio.shield(draft_future), timeout=60
                    )
                except TimeoutError:
                    messages = await page.locator(
                        ".byte-message, [class*='toast'], [class*='message']"
                    ).all_inner_texts()
                    detail = next(
                        (value.strip() for value in messages if "失败" in value),
                        "页面没有返回明确的草稿保存结果",
                    )
                    await _close(session)
                    return self._failure("DRAFT_SAVE_UNCONFIRMED", detail)
                if not draft_saved:
                    await _close(session)
                    return self._failure("DRAFT_SAVE_FAILED", draft_result)
                draft_id = draft_result

                try:
                    await page.wait_for_function(
                        """() => Array.from(document.querySelectorAll('.footer-draft-save'))
                          .some((el) => (el.textContent || '').includes('草稿已保存'))""",
                        timeout=10_000,
                    )
                except Exception:
                    # The successful cloud response with pgcId is authoritative;
                    # the status label can lag or be hidden by another panel.
                    pass
                await _close(session)
                return PublishResult(
                    True,
                    self.platform,
                    self.mode,
                    "DRAFT_CREATED",
                    external_id=draft_id,
                    published_url="https://mp.toutiao.com/profile_v4/manage/draft?from=creation",
                    detail={
                        "draftId": draft_id,
                        "method": "local_browser_autosave",
                        "imageRequestedCount": len(image_values),
                        "imageInsertedCount": image_inserted_count,
                        "publishPackage": {
                            "imageRequestedCount": len(image_values),
                            "imageInsertedCount": image_inserted_count,
                        },
                        "durationMs": int((time.perf_counter() - started) * 1000),
                    },
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
            if session:
                await _close(session)
            detail = str(exc)
            if "Locator." in detail or "Call log:" in detail or "Timeout" in detail:
                detail = "今日头条编辑器响应超时，请重试；若持续失败，请检查头条页面是否弹出提示"
            return self._failure("BROWSER_ERROR", f"今日头条浏览器发布失败：{detail[:400]}")

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
