import uuid

import httpx
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.config import settings
from app.core.exceptions import AppException
from app.core.responses import success_response
from app.db.session import get_db
from app.models.business import ContentArticle, MediaAsset
from app.models.user import User
from app.schemas.business import (
    KeywordRequest,
    MediaImageGenerateRequest,
    MediaImageTransformRequest,
    MediaSelectRequest,
)
from app.services.audit_service import record_audit
from app.services.generation_service import extract_keywords_with_llm, load_llm_runtime
from app.services.image_service import (
    MEDIA_UPLOAD_DIR,
    generate_provider_image,
    list_image_models,
    save_generated_asset,
)
from app.services.media_search_service import search_unsplash, search_wikimedia_commons
from app.services.serializers import model_dict
from app.services.setting_service import setting_value

router = APIRouter(tags=["素材管理"])

UPLOAD_DIR = MEDIA_UPLOAD_DIR


def _select_generated_asset(db: Session, asset: MediaAsset) -> None:
    if asset.usage_type == "COVER":
        db.query(MediaAsset).filter(
            MediaAsset.article_id == asset.article_id, MediaAsset.usage_type == "COVER"
        ).update({"selected": False})
    db.add(asset)
    db.flush()


@router.get("/media/image-models")
async def image_models(
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    runtime = load_llm_runtime(db)
    try:
        models = await list_image_models(runtime)
    except httpx.HTTPError as exc:
        raise AppException(50220, f"读取图片模型失败：{exc}", 502) from exc
    return success_response(
        request,
        {
            "models": models,
            "textToImage": [model for model in models if "Edit" not in model],
            "imageToImage": [model for model in models if "Edit" in model],
            "provider": runtime.provider,
        },
    )


@router.post("/media/generate")
async def generate_media_image(
    payload: MediaImageGenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    if not db.get(ContentArticle, payload.article_id):
        raise AppException(40401, "文章不存在", 404)
    runtime = load_llm_runtime(db)
    suffix, content, metadata = await generate_provider_image(
        runtime,
        prompt=payload.prompt,
        model=payload.model,
        image_size=payload.image_size,
    )
    asset = save_generated_asset(
        article_id=payload.article_id,
        variant_id=None,
        prompt=payload.prompt,
        model=payload.model,
        usage_type=payload.usage_type,
        source="AI_GENERATED",
        suffix=suffix,
        content=content,
        base_url=str(request.base_url),
    )
    _select_generated_asset(db, asset)
    record_audit(db, request, user, "GENERATE", "MEDIA", "MEDIA_ASSET", asset.id, metadata)
    db.commit()
    db.refresh(asset)
    data = model_dict(asset, camel=True)
    data["generationMetadata"] = metadata
    return success_response(request, data, "AI 图片已生成并保存")


@router.post("/media/transform")
async def transform_media_image(
    payload: MediaImageTransformRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    source_asset = db.get(MediaAsset, payload.asset_id)
    if not source_asset or source_asset.article_id != payload.article_id:
        raise AppException(40404, "待改造图片不存在", 404)
    runtime = load_llm_runtime(db)
    suffix, content, metadata = await generate_provider_image(
        runtime,
        prompt=payload.prompt,
        model=payload.model,
        source_asset=source_asset,
    )
    asset = save_generated_asset(
        article_id=payload.article_id,
        variant_id=source_asset.variant_id,
        prompt=payload.prompt,
        model=payload.model,
        usage_type=payload.usage_type,
        source="AI_TRANSFORMED",
        suffix=suffix,
        content=content,
        base_url=str(request.base_url),
    )
    _select_generated_asset(db, asset)
    record_audit(
        db,
        request,
        user,
        "TRANSFORM",
        "MEDIA",
        "MEDIA_ASSET",
        asset.id,
        {**metadata, "sourceAssetId": source_asset.id},
    )
    db.commit()
    db.refresh(asset)
    data = model_dict(asset, camel=True)
    data["generationMetadata"] = metadata
    return success_response(request, data, "AI 图片改造完成并保存")


@router.get("/media/search")
async def search_media(
    request: Request,
    keyword: str = Query(min_length=1, max_length=100),
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    access_key = setting_value(db, "media.unsplash_key", settings.unsplash_access_key)
    providers: list[str] = []
    warnings: list[str] = []
    try:
        items = await search_wikimedia_commons(keyword)
        providers.append("Wikimedia Commons")
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        items = []
        warnings.append(f"Wikimedia Commons 搜索失败：{type(exc).__name__}")

    if access_key:
        try:
            items.extend(await search_unsplash(keyword, access_key, page=page))
            providers.append("Unsplash")
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            warnings.append(f"Unsplash 搜索失败：{type(exc).__name__}")

    if not providers:
        raise AppException(50222, "联网图片搜索失败，请检查网络后重试", 502)

    source = (
        "MIXED"
        if len(providers) > 1
        else ("UNSPLASH" if providers[0] == "Unsplash" else "WIKIMEDIA_COMMONS")
    )
    notice = f"已联网搜索 {' + '.join(providers)} · {len(items)} 张图片"
    if warnings:
        notice += f"；{'；'.join(warnings)}"
    return success_response(
        request,
        {"items": items, "page": page, "source": source, "notice": notice, "online": True},
    )


@router.post("/media/extract-keywords")
async def media_keywords(
    payload: KeywordRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    article = db.get(ContentArticle, payload.article_id)
    if not article:
        raise AppException(40401, "文章不存在", 404)
    keywords, provider = await extract_keywords_with_llm(
        db, article.title + "\n" + article.source_text
    )
    return success_response(request, {"keywords": keywords, "provider": provider})


@router.post("/media/upload")
async def upload_media(
    request: Request,
    article_id: int = Form(...),
    usage_type: str = Form("BODY"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    if not db.get(ContentArticle, article_id):
        raise AppException(40401, "文章不存在", 404)
    if usage_type not in {"COVER", "BODY"}:
        raise AppException(40041, "素材用途只能是封面或正文")
    allowed = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    suffix = allowed.get(file.content_type or "")
    if not suffix:
        raise AppException(40042, "仅支持 JPG、PNG、WebP 和 GIF 图片")
    content = await file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise AppException(40043, "图片不能超过 5MB")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{suffix}"
    (UPLOAD_DIR / filename).write_bytes(content)
    relative_url = f"/uploads/media/{filename}"
    image_url = str(request.base_url).rstrip("/") + relative_url
    if usage_type == "COVER":
        db.query(MediaAsset).filter(
            MediaAsset.article_id == article_id, MediaAsset.usage_type == "COVER"
        ).update({"selected": False})
    asset = MediaAsset(
        article_id=article_id,
        source="LOCAL_UPLOAD",
        source_id=filename,
        image_url=image_url,
        thumbnail_url=image_url,
        alt_text=file.filename or "本地上传素材",
        usage_type=usage_type,
        selected=True,
    )
    db.add(asset)
    db.flush()
    record_audit(db, request, user, "UPLOAD", "MEDIA", "MEDIA_ASSET", asset.id)
    db.commit()
    db.refresh(asset)
    return success_response(request, model_dict(asset, camel=True), "图片已上传")


@router.post("/media/select")
def select_media(
    payload: MediaSelectRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    if not db.get(ContentArticle, payload.article_id):
        raise AppException(40401, "文章不存在", 404)
    if payload.usage_type == "COVER":
        db.query(MediaAsset).filter(
            MediaAsset.article_id == payload.article_id, MediaAsset.usage_type == "COVER"
        ).update({"selected": False})
    asset = MediaAsset(**payload.model_dump(), selected=True)
    db.add(asset)
    db.flush()
    record_audit(
        db, request, user, "SELECT", "MEDIA", "MEDIA_ASSET", asset.id, {"source": asset.source}
    )
    db.commit()
    db.refresh(asset)
    return success_response(request, model_dict(asset, camel=True), "图片已选择")


@router.delete("/media/{asset_id}")
def delete_media(
    asset_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    asset = db.get(MediaAsset, asset_id)
    if not asset:
        raise AppException(40404, "图片资源不存在", 404)
    record_audit(db, request, user, "DELETE", "MEDIA", "MEDIA_ASSET", asset.id)
    db.delete(asset)
    db.commit()
    return success_response(request, {"id": asset_id}, "图片已移除")


@router.get("/articles/{article_id}/media")
def article_media(
    article_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    items = db.scalars(
        select(MediaAsset)
        .where(MediaAsset.article_id == article_id)
        .order_by(MediaAsset.created_at.desc())
    ).all()
    return success_response(request, [model_dict(item, camel=True) for item in items])
