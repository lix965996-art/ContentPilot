import base64
import mimetypes
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.core.exceptions import AppException
from app.models.business import MediaAsset
from app.services.generation_service import LlmRuntime

MEDIA_UPLOAD_DIR = Path(__file__).resolve().parents[3] / "uploads" / "media"
MAX_IMAGE_BYTES = 12 * 1024 * 1024


async def list_image_models(runtime: LlmRuntime) -> list[str]:
    if not all([runtime.api_key, runtime.base_url]):
        raise AppException(50301, "请先在设置中配置支持图片模型的服务商", 503)
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{runtime.base_url.rstrip('/')}/models",
            params={"type": "image"},
            headers={"Authorization": f"Bearer {runtime.api_key}"},
        )
        response.raise_for_status()
    return [str(item["id"]) for item in response.json().get("data", []) if item.get("id")]


def _asset_image_input(asset: MediaAsset) -> str:
    parsed = urlparse(asset.image_url)
    if parsed.path.startswith("/uploads/media/"):
        filename = Path(parsed.path).name
        path = (MEDIA_UPLOAD_DIR / filename).resolve()
        if path.parent != MEDIA_UPLOAD_DIR.resolve() or not path.is_file():
            raise AppException(40404, "原始图片文件不存在", 404)
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"
    if parsed.scheme in {"http", "https"}:
        return asset.image_url
    raise AppException(40045, "该图片地址不能用于 AI 改造")


async def _download_generated_image(url: str) -> tuple[str, bytes]:
    async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
    content = response.content
    if not content or len(content) > MAX_IMAGE_BYTES:
        raise AppException(50221, "图片服务返回了空文件或超大文件", 502)
    content_type = response.headers.get("content-type", "").split(";")[0]
    suffix = {"image/jpeg": ".jpg", "image/webp": ".webp", "image/png": ".png"}.get(
        content_type, ".png"
    )
    return suffix, content


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
    payload: dict = {"model": model, "prompt": prompt}
    if source_asset:
        payload["image"] = _asset_image_input(source_asset)
    elif image_size:
        payload["image_size"] = image_size
    if model == "Kwai-Kolors/Kolors":
        payload.update(batch_size=1, num_inference_steps=20, guidance_scale=7.5)
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(
                f"{runtime.base_url.rstrip('/')}/images/generations",
                headers={"Authorization": f"Bearer {runtime.api_key}"},
                json=payload,
            )
            response.raise_for_status()
        result = response.json()
        image_url = result["images"][0]["url"]
        suffix, content = await _download_generated_image(image_url)
        return (
            suffix,
            content,
            {
                "seed": result.get("seed"),
                "inference": (result.get("timings") or {}).get("inference"),
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
