from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.exceptions import AppException
from app.core.responses import success_response
from app.db.session import get_db
from app.models.business import ContentArticle, ContentVariant, PublishSchedule
from app.models.user import User
from app.schemas.business import (
    ArticleCreate,
    ArticleUpdate,
    VariantUpdate,
    WechatFormatPreviewRequest,
    WechatFormatRequest,
)
from app.services.audit_service import record_audit
from app.services.generation_service import count_emoji, edit_ratio, markdown_to_safe_html
from app.services.serializers import model_dict
from app.services.wechat_formatting import (
    format_wechat_html,
    wechat_theme_profiles,
)

router = APIRouter(tags=["内容管理"])


def _article_data(article: ContentArticle, variant_count: int = 0) -> dict:
    data = model_dict(article, camel=True)
    data["keywords"] = data.pop("keywordsJson", [])
    data["variantCount"] = variant_count
    return data


@router.get("/articles")
def list_articles(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str = "",
    status: str = "",
    platform: str = "",
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    filters = []
    if keyword:
        filters.append(
            or_(
                ContentArticle.title.contains(keyword), ContentArticle.source_text.contains(keyword)
            )
        )
    if status:
        filters.append(ContentArticle.status == status)
    if platform:
        filters.append(ContentArticle.variants.any(ContentVariant.platform == platform))
    total = db.scalar(select(func.count()).select_from(ContentArticle).where(*filters)) or 0
    rows = db.execute(
        select(ContentArticle, func.count(ContentVariant.id))
        .outerjoin(ContentVariant)
        .where(*filters)
        .group_by(ContentArticle.id)
        .order_by(ContentArticle.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return success_response(
        request,
        {
            "items": [_article_data(article, count) for article, count in rows],
            "total": total,
            "page": page,
            "pageSize": page_size,
        },
    )


@router.post("/articles")
def create_article(
    payload: ArticleCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    article = ContentArticle(
        title=payload.title.strip(),
        source_text=payload.source_text.strip(),
        summary=payload.summary,
        topic=payload.topic,
        target_audience=payload.target_audience,
        tone=payload.tone,
        keywords_json=payload.keywords,
        status="DRAFT",
        created_by=user.id,
    )
    db.add(article)
    db.flush()
    record_audit(
        db, request, user, "CREATE", "CONTENT", "ARTICLE", article.id, {"title": article.title}
    )
    db.commit()
    db.refresh(article)
    return success_response(request, _article_data(article), "文章已创建")


@router.post("/articles/import")
async def import_article(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    if not file.filename or not file.filename.lower().endswith((".txt", ".md", ".markdown")):
        raise AppException(40011, "只支持 TXT 或 Markdown 文件")
    content = await file.read()
    if len(content) > 2 * 1024 * 1024:
        raise AppException(40012, "文件不能超过 2MB")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AppException(40013, "文件必须使用 UTF-8 编码") from exc
    title = next(
        (line.lstrip("# ").strip() for line in text.splitlines() if line.strip()), file.filename
    )
    article = ContentArticle(
        title=title[:255],
        source_text=text.strip(),
        status="DRAFT",
        created_by=user.id,
        keywords_json=[],
    )
    db.add(article)
    db.flush()
    record_audit(
        db, request, user, "IMPORT", "CONTENT", "ARTICLE", article.id, {"filename": file.filename}
    )
    db.commit()
    db.refresh(article)
    return success_response(request, _article_data(article), "文章导入成功")


@router.get("/articles/{article_id}")
def get_article(
    article_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    article = db.get(ContentArticle, article_id)
    if not article:
        raise AppException(40401, "文章不存在", 404)
    data = _article_data(article, len(article.variants))
    data["variants"] = [
        model_dict(item, camel=True)
        for item in sorted(article.variants, key=lambda x: (x.platform, -x.version_no))
    ]
    return success_response(request, data)


@router.put("/articles/{article_id}")
def update_article(
    article_id: int,
    payload: ArticleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    article = db.get(ContentArticle, article_id)
    if not article:
        raise AppException(40401, "文章不存在", 404)
    for key, value in payload.model_dump(exclude={"keywords"}).items():
        setattr(article, key, value)
    article.keywords_json = payload.keywords
    record_audit(db, request, user, "UPDATE", "CONTENT", "ARTICLE", article.id)
    db.commit()
    db.refresh(article)
    return success_response(request, _article_data(article), "文章已保存")


@router.delete("/articles/{article_id}")
def delete_article(
    article_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    article = db.get(ContentArticle, article_id)
    if not article:
        raise AppException(40401, "文章不存在", 404)
    record_audit(
        db, request, user, "DELETE", "CONTENT", "ARTICLE", article.id, {"title": article.title}
    )
    db.delete(article)
    db.commit()
    return success_response(request, {"id": article_id}, "文章已删除")


@router.post("/articles/{article_id}/archive")
def archive_article(
    article_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    article = db.get(ContentArticle, article_id)
    if not article:
        raise AppException(40401, "文章不存在", 404)
    article.status = "ARCHIVED"
    record_audit(db, request, user, "ARCHIVE", "CONTENT", "ARTICLE", article.id)
    db.commit()
    return success_response(request, _article_data(article), "文章已归档")


@router.get("/articles/{article_id}/variants")
def variants(
    article_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    items = db.scalars(
        select(ContentVariant)
        .where(ContentVariant.article_id == article_id)
        .order_by(ContentVariant.platform, ContentVariant.version_no.desc())
    ).all()
    return success_response(request, [model_dict(item, camel=True) for item in items])


@router.put("/variants/{variant_id}")
def update_variant(
    variant_id: int,
    payload: VariantUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    variant = db.get(ContentVariant, variant_id)
    if not variant:
        raise AppException(40402, "内容版本不存在", 404)
    variant.title = payload.title
    variant.content_text = payload.content_text
    if variant.platform == "WECHAT_OFFICIAL" and variant.format_profile_json:
        variant.content_html, variant.format_profile_json = format_wechat_html(
            payload.content_text, variant.format_profile_json
        )
    else:
        variant.content_html = markdown_to_safe_html(payload.content_text)
    variant.hashtags_json = payload.hashtags
    variant.emoji_count = count_emoji(payload.title + payload.content_text)
    variant.word_count = len(payload.content_text)
    variant.manual_edit_ratio = edit_ratio(variant.original_generated_text, payload.content_text)
    record_audit(db, request, user, "UPDATE", "CONTENT", "VARIANT", variant.id)
    db.commit()
    db.refresh(variant)
    return success_response(request, model_dict(variant, camel=True), "版本已保存")


@router.get("/formatting/wechat/profiles")
def wechat_format_profiles(
    request: Request,
    _: User = Depends(get_current_user),
) -> dict:
    return success_response(request, wechat_theme_profiles())


@router.post("/formatting/wechat/preview")
def preview_wechat_format(
    payload: WechatFormatPreviewRequest,
    request: Request,
    _: User = Depends(get_current_user),
) -> dict:
    data = payload.model_dump()
    content_text = data.pop("content_text")
    content_html, profile = format_wechat_html(content_text, data)
    return success_response(request, {"contentHtml": content_html, "profile": profile})


@router.put("/variants/{variant_id}/format")
def format_wechat_variant(
    variant_id: int,
    payload: WechatFormatRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    variant = db.get(ContentVariant, variant_id)
    if not variant:
        raise AppException(40402, "内容版本不存在", 404)
    if variant.platform != "WECHAT_OFFICIAL":
        raise AppException(40078, "排版助手当前仅适用于微信公众号版本")
    variant.content_html, variant.format_profile_json = format_wechat_html(
        variant.content_text, payload.model_dump()
    )
    record_audit(db, request, user, "FORMAT", "CONTENT", "VARIANT", variant.id)
    db.commit()
    db.refresh(variant)
    return success_response(request, model_dict(variant, camel=True), "公众号排版已保存")


@router.post("/variants/{variant_id}/approve")
def approve_variant(
    variant_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    variant = db.get(ContentVariant, variant_id)
    if not variant:
        raise AppException(40402, "内容版本不存在", 404)
    variant.review_status = "APPROVED"
    variant.article.status = "APPROVED"
    record_audit(db, request, user, "APPROVE", "CONTENT", "VARIANT", variant.id)
    db.commit()
    return success_response(request, model_dict(variant, camel=True), "审核通过")


@router.post("/variants/{variant_id}/reject")
def reject_variant(
    variant_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    variant = db.get(ContentVariant, variant_id)
    if not variant:
        raise AppException(40402, "内容版本不存在", 404)
    variant.review_status = "REJECTED"
    record_audit(db, request, user, "REJECT", "CONTENT", "VARIANT", variant.id)
    db.commit()
    return success_response(request, model_dict(variant, camel=True), "版本已拒绝")


@router.delete("/variants/{variant_id}")
def delete_variant(
    variant_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    variant = db.get(ContentVariant, variant_id)
    if not variant:
        raise AppException(40402, "内容版本不存在", 404)
    schedule_count = (
        db.query(PublishSchedule).filter(PublishSchedule.variant_id == variant_id).count()
    )
    if schedule_count:
        raise AppException(40921, "该版本已有发布任务，不能删除", 409)
    record_audit(db, request, user, "DELETE", "CONTENT", "VARIANT", variant.id)
    db.delete(variant)
    db.commit()
    return success_response(request, {"id": variant_id}, "版本已删除")
