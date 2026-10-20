import asyncio
import base64
import binascii
import logging
import mimetypes
import uuid
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.paths import MEDIA_UPLOAD_DIR, local_media_path
from app.core.urls import fetch_public_image
from app.models.business import MediaAsset
from app.services.generation_service import LlmRuntime
from app.services.llm_usage_service import begin_usage, finish_usage

MAX_IMAGE_BYTES = 12 * 1024 * 1024
logger = logging.getLogger(__name__)


def image_content_suffix(content: bytes, *, max_bytes: int = MAX_IMAGE_BYTES) -> str:
    """Validate supported binary image signatures before storing provider/network bytes."""
    if not content or len(content) > max_bytes:
        raise AppException(50221, "图片为空或超过大小限制", 502)
    if content.startswith(b"\x89PNG\r\n\x1a\n") and len(content) >= 24:
        return ".png"
    if content.startswith(b"\xff\xd8\xff") and len(content) >= 4:
        return ".jpg"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP" and len(content) >= 16:
        return ".webp"
    if content[:6] in {b"GIF87a", b"GIF89a"} and len(content) >= 13:
        return ".gif"
    raise AppException(50221, "图片内容不是受支持的 PNG、JPEG、WebP 或 GIF 文件", 502)


def _siliconflow_protocol(runtime: LlmRuntime) -> bool:
    return runtime.provider.lower() == "siliconflow" or (
        urlparse(runtime.base_url).hostname or ""
    ).lower() in {"api.siliconflow.cn", "api.siliconflow.com"}


async def list_image_models(runtime: LlmRuntime) -> list[str]:
    if not all([runtime.api_key, runtime.base_url]):
        raise AppException(50301, "请先在设置中配置支持图片模型的服务商", 503)
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{runtime.base_url.rstrip('/')}/models",
            params={"type": "image"} if _siliconflow_protocol(runtime) else None,
            headers={"Authorization": f"Bearer {runtime.api_key}"},
        )
        response.raise_for_status()
    try:
        body = response.json()
    except ValueError as exc:
        raise AppException(50220, "图片模型列表响应不是有效 JSON", 502) from exc
    rows = body.get("data", []) if isinstance(body, dict) else None
    if not isinstance(rows, list):
        raise AppException(50220, "图片模型列表响应格式无效", 502)
    return [
        str(item["id"])
        for item in rows
        if isinstance(item, dict)
        and item.get("id")
        and (
            _siliconflow_protocol(runtime)
            or item.get("type") == "image"
            or any(
                marker in str(item["id"]).lower()
                for marker in (
                    "image",
                    "dall-e",
                    "flux",
                    "kolors",
                    "stable-diffusion",
                    "sdxl",
                    "imagen",
                )
            )
        )
    ]


def image_model_capabilities(model: str) -> tuple[bool, bool]:
    """Known common model families; do not advertise generation-only models as editors."""
    name = model.lower()
    if name.startswith("gpt-image-") or name == "dall-e-2":
        return True, True
    if "edit" in name:
        return False, True
    return True, False


def _asset_image_input(asset: MediaAsset) -> str:
    parsed = urlparse(asset.image_url)
    path = local_media_path(asset.image_url, local_hosts_only=True)
    if path:
        if path.stat().st_size > MAX_IMAGE_BYTES:
            raise AppException(40045, "原始图片超过 12MB，无法用于图片编辑")
        content = path.read_bytes()
        suffix = image_content_suffix(content)
        mime = mimetypes.guess_type("image" + suffix)[0] or "image/png"
        return f"data:{mime};base64,{base64.b64encode(content).decode()}"
    if not parsed.scheme or (parsed.hostname or "").lower() in {"localhost", "127.0.0.1", "::1"}:
        raise AppException(40404, "原始图片文件不存在", 404)
    if parsed.scheme in {"http", "https"}:
        return asset.image_url
    raise AppException(40045, "该图片地址不能用于 AI 改造")


async def _download_generated_image(url: str) -> tuple[str, bytes]:
    try:
        image = await fetch_public_image(
            url,
            max_bytes=MAX_IMAGE_BYTES,
            timeout=45,
            proxy=settings.outbound_http_proxy.strip() or None,
        )
    except ValueError as exc:
        raise AppException(50221, f"图片服务返回的图片无法安全下载：{exc}", 502) from exc
    except httpx.HTTPError as exc:
        raise AppException(50221, "图片服务下载失败，请稍后重试", 502) from exc
    suffix = image_content_suffix(image.content, max_bytes=MAX_IMAGE_BYTES)
    return suffix, image.content


def _provider_error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:500]
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("code") or error)[:500]
        return str(body.get("message") or body.get("code") or body)[:500]
    return str(body)[:500]


async def _post_image_request(runtime: LlmRuntime, payload: dict) -> httpx.Response:
    ticket = begin_usage(
        runtime, "IMAGE_GENERATION", model=str(payload.get("model") or ""), token_priced=False
    )
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(
                f"{runtime.base_url.rstrip('/')}/images/generations",
                headers={"Authorization": f"Bearer {runtime.api_key}"},
                json=payload,
            )
    except BaseException as exc:
        finish_usage(ticket, status="FAILED", error_code=type(exc).__name__)
        raise
    finish_usage(
        ticket,
        status="SUCCEEDED" if response.is_success else "FAILED",
        error_code=None if response.is_success else f"HTTP_{response.status_code}",
    )
    return response


async def _post_image_edit_request(
    runtime: LlmRuntime, payload: dict, source_asset: MediaAsset
) -> httpx.Response:
    path = local_media_path(source_asset.image_url, local_hosts_only=True)
    if path:
        if path.stat().st_size > MAX_IMAGE_BYTES:
            raise AppException(40045, "原始图片超过 12MB，无法用于图片编辑")
        content = path.read_bytes()
        suffix = image_content_suffix(content)
    else:
        suffix, content = await _download_generated_image(source_asset.image_url)
    mime = mimetypes.guess_type("image" + suffix)[0] or "image/png"
    ticket = begin_usage(
        runtime, "IMAGE_EDIT", model=str(payload.get("model") or ""), token_priced=False
    )
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(
                f"{runtime.base_url.rstrip('/')}/images/edits",
                headers={"Authorization": f"Bearer {runtime.api_key}"},
                data={key: str(value) for key, value in payload.items()},
                files={"image": ("source" + suffix, content, mime)},
            )
    except BaseException as exc:
        finish_usage(ticket, status="FAILED", error_code=type(exc).__name__)
        raise
    finish_usage(
        ticket,
        status="SUCCEEDED" if response.is_success else "FAILED",
        error_code=None if response.is_success else f"HTTP_{response.status_code}",
    )
    return response


def _image_payload(
    runtime: LlmRuntime,
    prompt: str,
    model: str,
    image_size: str | None,
    source_asset: MediaAsset | None,
) -> dict:
    payload: dict = {"model": model, "prompt": prompt}
    if _siliconflow_protocol(runtime):
        if source_asset:
            payload["image"] = _asset_image_input(source_asset)
        elif image_size:
            payload["image_size"] = image_size
        if model == "Kwai-Kolors/Kolors":
            payload.update(batch_size=1, num_inference_steps=20, guidance_scale=7.5)
    elif image_size:
        size = image_size
        if runtime.provider.lower() == "openai" or model.startswith(("gpt-image-", "dall-e-")):
            width, height = (int(part) for part in image_size.split("x"))
            if model == "dall-e-2" or width == height:
                size = "1024x1024"
            elif model == "dall-e-3":
                size = "1792x1024" if width > height else "1024x1792"
            else:
                size = "1536x1024" if width > height else "1024x1536"
        payload["size"] = size
    return payload


async def _provider_image_content(result: dict) -> tuple[str, bytes]:
    rows = result.get("images") or result.get("data")
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        raise AppException(
            50221, "图片服务未返回可用图片，支持 images/data 中的 URL 或 Base64", 502
        )
    row = rows[0]
    encoded = row.get("b64_json")
    url = row.get("url")
    if isinstance(url, str) and url.startswith("data:"):
        header, separator, encoded = url.partition(",")
        if not separator or ";base64" not in header.lower():
            raise AppException(50221, "图片服务返回的图片编码格式无效", 502)
    if encoded is not None:
        if not isinstance(encoded, str) or len(encoded) > ((MAX_IMAGE_BYTES + 2) // 3) * 4:
            raise AppException(50221, "图片服务返回的 Base64 图片超过大小限制", 502)
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise AppException(50221, "图片服务返回的 Base64 图片编码无效", 502) from exc
        return image_content_suffix(content, max_bytes=MAX_IMAGE_BYTES), content
    if not isinstance(url, str) or urlparse(url).scheme.lower() not in {"http", "https"}:
        raise AppException(50221, "图片服务未返回有效的图片 URL 或 Base64", 502)
    return await _download_generated_image(url)


async def generate_provider_image(
    runtime: LlmRuntime,
    *,
    prompt: str,
    model: str,
    image_size: str | None = None,
    source_asset: MediaAsset | None = None,
) -> tuple[str, bytes, dict]:
    if not all([runtime.api_key, runtime.base_url]):
        raise AppException(50301, "请先在设置中配置支持图片生成的服务商", 503)
    if runtime.provider.lower() in {"deepseek", "moonshot"}:
        raise AppException(40046, "当前文本服务商未提供本项目支持的图片接口，请切换图片服务商")
    can_generate, can_edit = image_model_capabilities(model)
    if (source_asset and not can_edit) or (not source_asset and not can_generate):
        raise AppException(40046, "所选模型不支持当前图片操作，请选择对应的生图或改图模型")
    payload = _image_payload(runtime, prompt, model, image_size, source_asset)
    try:
        response: httpx.Response | None = None
        for attempt in range(2):
            try:
                response = (
                    await _post_image_edit_request(runtime, payload, source_asset)
                    if source_asset and not _siliconflow_protocol(runtime)
                    else await _post_image_request(runtime, payload)
                )
            except httpx.HTTPError:
                # A timed-out POST may have generated/billed an image already.
                raise
            if response.is_success:
                break
            detail = _provider_error_detail(response)
            logger.warning(
                "Image provider rejected request: status=%s trace_id=%s model=%s detail=%s",
                response.status_code,
                response.headers.get("x-siliconcloud-trace-id"),
                model,
                detail,
            )
            if attempt == 0 and response.status_code in {400, 429, 503, 504}:
                await asyncio.sleep(0.6)
                continue
            if response.status_code == 400:
                message = (
                    "图片改造服务连续两次拒绝了当前图片或描述，原图和现有封面均已保留"
                    if source_asset
                    else "图片生成服务连续两次拒绝了当前描述，请调整图片要求后重试"
                )
                raise AppException(50221, message, 502)
            if response.status_code == 429:
                raise AppException(50221, "图片模型当前请求较多，请稍后重试", 502)
            raise AppException(50221, "图片模型服务暂时不可用，原图和现有封面均已保留", 502)
        if response is None or not response.is_success:
            raise AppException(50221, "图片模型服务暂时不可用", 502)
        result = response.json()
        if not isinstance(result, dict):
            raise AppException(50221, "图片服务响应格式无效", 502)
        suffix, content = await _provider_image_content(result)
        return (
            suffix,
            content,
            {
                "seed": result.get("seed"),
                "inference": (
                    result["timings"].get("inference")
                    if isinstance(result.get("timings"), dict)
                    else None
                ),
                "usage": result.get("usage"),
                "requestedSize": image_size,
                "providerSize": payload.get("size") or payload.get("image_size"),
            },
        )
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise AppException(50221, f"图片模型生成失败：{exc}", 502) from exc


def save_generated_asset(
    *,
    article_id: int,
    variant_id: int | None,
    prompt: str,
    model: str,
    usage_type: str,
    source: str,
    suffix: str,
    content: bytes,
    base_url: str,
) -> MediaAsset:
    MEDIA_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{suffix}"
    (MEDIA_UPLOAD_DIR / filename).write_bytes(content)
    image_url = f"{base_url.rstrip('/')}/uploads/media/{filename}"
    return MediaAsset(
        article_id=article_id,
        variant_id=variant_id,
        source=source,
        source_id=filename,
        image_url=image_url,
        thumbnail_url=image_url,
        photographer_name=f"AI · {model}"[:100],
        alt_text=prompt[:500],
        search_keyword=prompt[:100],
        usage_type=usage_type,
        selected=True,
    )
