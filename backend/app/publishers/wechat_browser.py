"""Local WeChat Official Account draft creation through an isolated Chrome profile.

The operator completes the normal QR login on mp.weixin.qq.com. Cookies stay in
the local browser profile and are never copied into ContentPilot's database.
This publisher only saves a draft; it never clicks the public publish action.
"""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import mimetypes
import os
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit

import httpx
from playwright.async_api import BrowserContext, Page, Playwright, async_playwright

from app.core.config import BACKEND_DIR, settings
from app.publishers.base import PublishResult

WECHAT_HOME = "https://mp.weixin.qq.com/"
BODY_EDITOR_SELECTOR = ".rich_media_content .ProseMirror"
QR_SELECTORS = (
    ".login__type__container__scan__qrcode",
    ".login__type__container__scan img",
    ".login_img img",
    "#login_container img",
    ".qrcode img",
    "img[src*='scanloginqrcode']",
    "img[src*='qrcode']",
)
ACCOUNT_NAME_SELECTORS = (
    ".weui-desktop-account__nickname",
    ".account_meta .nickname",
    ".account-info__name",
    "[class*='account'] [class*='nickname']",
)


@dataclass
class LoginSession:
    playwright: Playwright
    context: BrowserContext
    page: Page


_login_sessions: dict[int, LoginSession] = {}
_session_lock = asyncio.Lock()


def _profile_root() -> Path:
    configured = settings.wechat_browser_profile_root.strip()
    root = Path(configured).expanduser() if configured else Path.home() / ".contentpilot" / "wechat"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _profile_dir(account_id: int) -> Path:
    root = _profile_root()
    path = (root / f"account-{account_id}").resolve()
    if path.parent != root:
        raise RuntimeError("微信公众号浏览器会话目录无效")
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
        "headless": settings.wechat_browser_headless if headless is None else headless,
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
    if "/cgi-bin/home" in url and "token=" in url:
        return True
    if "token=" in url and "/cgi-bin/" in url and "login" not in url:
        return True
    return bool(await page.locator(".new-creation__menu").count())


async def _account_name(page: Page) -> str:
    for selector in ACCOUNT_NAME_SELECTORS:
        locator = page.locator(selector).first
        if await locator.count() and await locator.is_visible():
            value = (await locator.inner_text()).strip()
            if value:
                return value[:100]
    return ""


async def _qr_data_url(page: Page) -> str:
    for selector in QR_SELECTORS:
        locator = page.locator(selector).first
        if not await locator.count() or not await locator.is_visible():
            continue
        png = await locator.screenshot(type="png")
        return f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"
    return ""


async def get_login_qrcode(account_id: int) -> dict[str, str | bool]:
    """Start or reuse a QR-login browser session for one local account."""
    async with _session_lock:
        session = _login_sessions.get(account_id)
        if session is None:
            try:
                session = await _launch(account_id)
                await session.page.goto(WECHAT_HOME, wait_until="domcontentloaded", timeout=60_000)
                await session.page.wait_for_timeout(2_000)
                _login_sessions[account_id] = session
            except Exception as exc:
                return {
                    "connected": False,
                    "image_data_url": "",
                    "message": f"无法启动微信公众号本机 Chrome：{str(exc)[:300]}",
                }
        try:
            if await _logged_in(session.page):
                return {
                    "connected": True,
                    "image_data_url": "",
                    "username": await _account_name(session.page),
                    "message": "微信公众号账号已登录",
                }
            image = await _qr_data_url(session.page)
            if not image:
                await session.page.reload(wait_until="domcontentloaded", timeout=60_000)
                await session.page.wait_for_timeout(1_500)
                image = await _qr_data_url(session.page)
            return {
                "connected": False,
                "image_data_url": image,
                "message": "请使用公众号管理员或运营者微信扫码，并在手机端确认登录"
                if image
                else "微信登录页已打开，但没有识别到二维码；页面可能已更新，请重试。",
            }
        except Exception as exc:
            return {
                "connected": False,
                "image_data_url": "",
                "message": f"读取微信公众号登录页失败：{str(exc)[:300]}",
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
                    return True, name or "公众号账号"
                return False, "等待扫码确认"
            except Exception:
                _login_sessions.pop(account_id, None)
                await _close(active)
        try:
            session = await _launch(account_id, headless=True)
            await session.page.goto(WECHAT_HOME, wait_until="domcontentloaded", timeout=60_000)
            await session.page.wait_for_timeout(1_500)
            logged = await _logged_in(session.page)
            name = await _account_name(session.page) if logged else ""
            await _close(session)
            return logged, name or ("公众号账号" if logged else "需要扫码登录")
        except Exception as exc:
            return False, f"无法检测微信公众号本机登录：{str(exc)[:300]}"


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
            return True, "微信公众号本机登录会话已清除"
        except Exception as exc:
            return False, f"清除微信公众号会话失败：{str(exc)[:300]}"
        finally:
            if session and (created or account_id not in _login_sessions):
                await _close(session)


def _local_image(value: str) -> Path | None:
    if not value:
        return None
    direct = Path(value)
    if direct.is_file():
        return direct.resolve()
    parsed = urlsplit(value)
    if parsed.scheme in {"http", "https"}:
        if (parsed.hostname or "").lower() not in {"127.0.0.1", "localhost", "::1"}:
            return None
        path_only = unquote(parsed.path)
    else:
        path_only = unquote(value.split("?", 1)[0])
    if path_only.startswith("/uploads/"):
        candidate = BACKEND_DIR.parent / path_only.lstrip("/")
        return candidate.resolve() if candidate.is_file() else None
    if path_only.startswith("/media/"):
        candidate = BACKEND_DIR.parent / "frontend" / "public" / path_only.lstrip("/")
        return candidate.resolve() if candidate.is_file() else None
    return None


def _ensure_public_image_url(value: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("远程图片必须使用有效的 HTTPS 地址")
    host = parsed.hostname.lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
        raise ValueError("不允许从本机或内网地址下载远程图片")
    try:
        host_ip = ipaddress.ip_address(host)
    except ValueError:
        host_ip = None
    if host_ip is not None and not host_ip.is_global:
        raise ValueError("不允许从本机或内网地址下载远程图片")


async def _download_image(value: str, target_dir: Path, index: int) -> Path:
    current_url = value
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        for _ in range(5):
            _ensure_public_image_url(current_url)
            response = await client.get(
                current_url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/138.0 Safari/537.36"
                    ),
                    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                    "Referer": f"{urlsplit(current_url).scheme}://{urlsplit(current_url).netloc}/",
                },
            )
            if response.is_redirect:
                location = response.headers.get("location", "")
                if not location:
                    raise ValueError("远程图片重定向地址为空")
                current_url = urljoin(current_url, location)
                continue
            response.raise_for_status()
            break
        else:
            raise ValueError("远程图片重定向次数过多")

    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
    if not content_type.startswith("image/"):
        raise ValueError("远程地址返回的内容不是图片")
    if not response.content:
        raise ValueError("远程图片文件为空")
    if len(response.content) > 10 * 1024 * 1024:
        raise ValueError("单张图片不能超过 10MB")

    suffix = Path(urlsplit(current_url).path).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}:
        suffix = mimetypes.guess_extension(content_type) or ".jpg"
    target = target_dir / f"wechat-image-{index}{suffix}"
    target.write_bytes(response.content)
    return target


async def _materialize_images(values: list[str], target_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for index, value in enumerate(values, start=1):
        local = _local_image(value)
        if local:
            paths.append(local)
            continue
        try:
            paths.append(await _download_image(value, target_dir, index))
        except Exception as exc:
            raise ValueError(f"第 {index} 张图片准备失败：{str(exc)[:200]}") from exc
    return paths


async def _open_article_editor(session: LoginSession) -> Page:
    home = session.page
    await home.goto(WECHAT_HOME, wait_until="domcontentloaded", timeout=60_000)
    await home.wait_for_timeout(2_000)
    if not await _logged_in(home):
        raise PermissionError("微信公众号登录已失效，请重新扫码")

    existing_pages = set(session.context.pages)
    menu = (
        home.locator(".new-creation__menu .new-creation__menu-item")
        .filter(has_text=re.compile(r"^\s*文章\s*$"))
        .first
    )
    if not await menu.count():
        menu = home.get_by_text("文章", exact=True).first
    if not await menu.count():
        raise RuntimeError("未找到公众号“文章”创作入口，微信页面可能已更新")
    await menu.click()

    for _ in range(30):
        for page in session.context.pages:
            if page not in existing_pages and "mp.weixin.qq.com" in page.url:
                return page
        if "appmsg" in home.url or await home.locator("#title").count():
            return home
        await asyncio.sleep(0.5)
    raise RuntimeError("公众号文章编辑器没有打开")


async def _insert_html(page: Page, content_html: str) -> None:
    editor = page.locator(BODY_EDITOR_SELECTOR).first
    await editor.wait_for(state="visible", timeout=30_000)
    result = await editor.evaluate(
        """(el, html) => {
          const template = document.createElement('template');
          template.innerHTML = html;
          el.focus();
          const selection = window.getSelection();
          const range = document.createRange();
          range.selectNodeContents(el);
          range.deleteContents();
          range.collapse(true);
          selection.removeAllRanges();
          selection.addRange(range);
          const inserted = document.execCommand('insertHTML', false, template.innerHTML);
          el.dispatchEvent(new InputEvent('input', {
            bubbles: true, inputType: 'insertHTML', data: template.content.textContent || ''
          }));
          return inserted || (el.innerText || '').trim().length > 0;
        }""",
        content_html,
    )
    if not result:
        raise RuntimeError("公众号正文写入失败")


async def _set_form_field(page: Page, selector: str, value: str, field_name: str) -> None:
    """Set WeChat's proxy form fields even when its textarea is visually overlaid."""
    field = page.locator(selector).first
    await field.wait_for(state="attached", timeout=30_000)
    actual = await field.evaluate(
        """(el, nextValue) => {
          el.focus();
          el.value = nextValue;
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
          el.dispatchEvent(new Event('blur', { bubbles: true }));
          return el.value;
        }""",
        value,
    )
    if actual != value:
        raise RuntimeError(f"公众号{field_name}写入失败")


async def _append_images(page: Page, paths: list[Path]) -> int:
    if not paths:
        return 0
    editor = page.locator(BODY_EDITOR_SELECTOR).first
    file_input = page.locator("input[type='file'][accept*='image']").first
    if not await file_input.count():
        raise RuntimeError("未找到微信公众号图片上传入口，页面结构可能已经更新")

    inserted = 0
    for index, path in enumerate(paths, start=1):
        await editor.focus()
        await editor.evaluate(
            """el => {
              const selection = window.getSelection();
              const range = document.createRange();
              range.selectNodeContents(el);
              range.collapse(false);
              selection.removeAllRanges();
              selection.addRange(range);
            }"""
        )
        before = await editor.locator("img").count()
        await file_input.set_input_files(str(path))
        for _ in range(60):
            await page.wait_for_timeout(500)
            if await editor.locator("img").count() > before:
                inserted += 1
                break
        else:
            raise RuntimeError(f"第 {index} 张图片上传后没有出现在正文中：{path.name}")
    return inserted


class WechatBrowserDraftPublisher:
    platform = "WECHAT_OFFICIAL"
    mode = "BROWSER_DRAFT"

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
            error_message="" if logged else "微信公众号后台尚未登录",
            suggested_action="请获取二维码并完成扫码登录。" if not logged else "",
            detail={"username": info if logged else "", "method": "local_browser"},
        )

    async def get_capabilities(self) -> list[str]:
        return ["DRAFT_CREATE", "DRAFT_UPDATE", "DRAFT_READ"]

    async def publish(self, request: dict[str, Any]) -> PublishResult:
        title = str(request.get("title") or "").strip()
        content = str(request.get("content") or "").strip()
        content_html = str(request.get("content_html") or "").strip()
        if not title or len(title) > 64:
            return self._failure("VALIDATION_ERROR", "公众号标题必须为 1～64 个字符")
        if not content and not content_html:
            return self._failure("VALIDATION_ERROR", "公众号正文不能为空")

        started = time.perf_counter()
        session: LoginSession | None = None
        image_temp_dir: tempfile.TemporaryDirectory[str] | None = None
        try:
            image_values = [str(value) for value in request.get("images", []) if value]
            image_temp_dir = tempfile.TemporaryDirectory(prefix="contentpilot-wechat-images-")
            image_paths = await _materialize_images(image_values, Path(image_temp_dir.name))
            session = await _launch(self.account_id, headless=settings.wechat_browser_headless)
            page = await _open_article_editor(session)
            await page.locator(BODY_EDITOR_SELECTOR).first.wait_for(state="visible", timeout=30_000)
            await _set_form_field(page, "#title", title, "标题")

            author = str(request.get("author") or "")[:16]
            if author and await page.locator("#author").count():
                await _set_form_field(page, "#author", author, "作者")

            safe_html = content_html or "".join(
                f"<p>{line}</p>" for line in content.splitlines() if line.strip()
            )
            await _insert_html(page, safe_html)
            image_inserted_count = await _append_images(page, image_paths)
            if image_inserted_count != len(image_values):
                raise RuntimeError(
                    "图片插入数量不一致："
                    f"选择 {len(image_values)} 张，实际插入 {image_inserted_count} 张"
                )

            digest = str(request.get("summary") or "")[:120]
            if digest and await page.locator("#js_description").count():
                await _set_form_field(page, "#js_description", digest, "摘要")

            save_button = page.locator("#js_submit button").first
            if not await save_button.count():
                save_button = page.get_by_role("button", name=re.compile("保存为草稿|保存")).first
            if not await save_button.count():
                return self._failure("PAGE_CHANGED", "未找到公众号“保存为草稿”按钮")
            await save_button.click()

            draft_id = ""
            failure_message = ""
            for _ in range(60):
                await page.wait_for_timeout(1_000)
                match = re.search(r"(?:appmsgid|msgid)=([^&#]+)", page.url)
                if match:
                    draft_id = match.group(1)
                messages = await page.locator(
                    ".weui-desktop-toast, .weui-desktop-toptips, .js_tips"
                ).all_inner_texts()
                failure_message = next(
                    (
                        value.strip()
                        for value in messages
                        if re.search("保存.*失败|草稿.*失败", value)
                    ),
                    "",
                )
                loading = await page.locator(
                    "#js_submit.btn_loading, #js_submit button:disabled"
                ).count()
                if draft_id and not loading:
                    break
                if failure_message:
                    break

            if failure_message:
                return self._failure("DRAFT_SAVE_FAILED", failure_message)
            if not draft_id:
                challenge = page.get_by_text(re.compile("验证码|安全验证|管理员确认")).first
                if await challenge.count() and await challenge.is_visible():
                    return self._failure(
                        "USER_CONFIRMATION_REQUIRED",
                        "微信要求在页面或手机端完成人工确认",
                        status="NEED_USER_ACTION",
                    )
                return self._failure("DRAFT_SAVE_UNCONFIRMED", "页面没有返回明确的草稿保存结果")

            return PublishResult(
                True,
                self.platform,
                self.mode,
                "DRAFT_CREATED",
                external_id=draft_id,
                published_url=(
                    "https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2"
                    f"&action=edit&appmsgid={draft_id}"
                ),
                detail={
                    "draftId": draft_id,
                    "method": "local_browser",
                    "imageRequestedCount": len(image_values),
                    "imageInsertedCount": image_inserted_count,
                    "publishPackage": {
                        "imageRequestedCount": len(image_values),
                        "imageInsertedCount": image_inserted_count,
                    },
                    "durationMs": int((time.perf_counter() - started) * 1000),
                },
            )
        except PermissionError as exc:
            return self._failure("LOGIN_REQUIRED", str(exc), status="LOGIN_REQUIRED")
        except Exception as exc:
            return self._failure("BROWSER_ERROR", f"公众号草稿保存失败：{str(exc)[:400]}")
        finally:
            if session:
                await _close(session)
            if image_temp_dir:
                image_temp_dir.cleanup()

    async def query_status(self, task_id: str) -> dict[str, Any]:
        return {"media_id": task_id, "status": "DRAFT_CREATED", "source": "local_browser"}

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
            retryable=code in {"BROWSER_ERROR", "DRAFT_SAVE_UNCONFIRMED"},
            error_code=code,
            error_message=message,
            suggested_action="请检查公众号登录状态和微信公众平台编辑页面后重试。",
        )
