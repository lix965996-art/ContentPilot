import uuid
from pathlib import Path

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
from app.schemas.business import KeywordRequest, MediaSelectRequest
from app.services.audit_service import record_audit
from app.services.generation_service import extract_keywords_with_llm
from app.services.serializers import model_dict
from app.services.setting_service import setting_value

router = APIRouter(tags=["素材管理"])

UPLOAD_DIR = Path(__file__).resolve().parents[4] / "uploads" / "media"

FALLBACK_IMAGES = [
    {
        "id": f"local-{i}",
        "imageUrl": f"/media/fallback-{i}.svg",
        "thumbnailUrl": f"/media/fallback-{i}.svg",
        "source": "LOCAL",
        "photographerName": "ContentPilot",
        "photographerUrl": None,
    }
    for i in range(1, 11)
]

PROJECT_GENERATED_IMAGES = [
    ("content-adaptation", "content-adaptation.webp", "多平台内容适配与分发"),
    ("ai-brand-meaning", "ai-brand-meaning.webp", "AI 写作与品牌原意保护"),
    ("content-calendar", "content-calendar.webp", "内容日历与团队协作"),
    ("longform-reading", "longform-reading.webp", "长文章排版与阅读体验"),
    ("visual-selection", "visual-selection.webp", "内容配图选择与裁切"),
    ("team-workflow", "team-workflow.webp", "内容团队协作流程"),
    ("content-experiment", "content-experiment.webp", "内容策略对照实验"),
    ("publishing-schedule", "publishing-schedule.webp", "内容发布排期与时段规划"),
]


def _project_generated_items(keyword: str) -> list[dict]:
    return [
        {
            "id": item_id,
            "imageUrl": f"/media/generated/{filename}",
            "thumbnailUrl": f"/media/generated/{filename}",
            "source": "AI_GENERATED",
            "photographerName": "ContentPilot AI",
            "photographerUrl": None,
            "altText": alt_text,
            "searchKeyword": keyword,
        }
        for item_id, filename, alt_text in PROJECT_GENERATED_IMAGES
    ]


@router.get("/media/search")
async def search_media(
    request: Request,
    keyword: str = Query(min_length=1, max_length=100),
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    access_key = setting_value(db, "media.unsplash_key", settings.unsplash_access_key)
    if access_key:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    "https://api.unsplash.com/search/photos",
                    params={"query": keyword, "page": page, "per_page": 15},
                    headers={"Authorization": f"Client-ID {access_key}"},
                )
                response.raise_for_status()
                items = [
                    {
                        "id": item["id"],
                        "imageUrl": item["urls"]["regular"],
                        "thumbnailUrl": item["urls"]["small"],
                        "source": "UNSPLASH",
                        "photographerName": item["user"]["name"],
                        "photographerUrl": item["user"]["links"]["html"],
                        "altText": item.get("alt_description") or keyword,
                        "searchKeyword": keyword,
                    }
                    for item in response.json().get("results", [])
                ]
                if items:
                    return success_response(
                        request,
                        {
                            "items": [*_project_generated_items(keyword), *items],
                            "page": page,
                            "source": "MIXED",
                            "notice": "项目 AI 素材与 Unsplash 搜索结果",
                        },
                    )
        except (httpx.HTTPError, KeyError, ValueError):
            pass
    generated_items = _project_generated_items(keyword)
    if generated_items:
        return success_response(
            request,
            {
                "items": generated_items,
                "page": page,
                "source": "AI_GENERATED",
                "notice": "8 张项目内置 AI 生成素材",
            },
        )
    if not (settings.app_demo_mode and settings.media_fallback_enabled):
        return success_response(
            request,
            {
                "items": [],
                "page": page,
                "source": "UNCONFIGURED",
                "notice": "未配置 Unsplash，您仍可上传本地图片作为真实素材。",
            },
        )
    items = [
        {**item, "altText": f"{keyword} 配图", "searchKeyword": keyword} for item in FALLBACK_IMAGES
    ]
    return success_response(
        request,
        {
            "items": items,
            "page": page,
            "source": "LOCAL_FALLBACK",
            "notice": "演示模式：当前展示本地备用图库",
        },
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
