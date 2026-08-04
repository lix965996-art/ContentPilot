import uuid
from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.exceptions import AppException
from app.core.responses import success_response
from app.db.session import get_db
from app.models.business import ContentArticle, ContentVariant, MediaAsset, PublishSchedule
from app.models.user import User
from app.schemas.business import (
    ArticleCreate,
    ArticleUpdate,
    VariantUpdate,
    WechatFormatPreviewRequest,
    WechatFormatRequest,
)
from app.services.audit_service import record_audit
from app.services.generation_service import (
    compact_weibo_image_payload,
    count_emoji,
    edit_ratio,
    markdown_to_safe_html,
    normalize_visible_markdown,
)
from app.services.platform_account_service import get_platform_account
from app.services.platform_content import build_x_post, normalize_topics, x_weighted_length
from app.services.publish_service import execute_publish
from app.services.serializers import model_dict
from app.services.wechat_formatting import (
    format_wechat_html,
    wechat_theme_profiles,
)

router = APIRouter(tags=["内容管理"])


def _article_data(
    article: ContentArticle,
    variant_count: int = 0,
    cover_thumbnail_url: str | None = None,
) -> dict:
    data = model_dict(article, camel=True)
    data["keywords"] = data.pop("keywordsJson", [])
    data["variantCount"] = variant_count
    if cover_thumbnail_url:
        data["coverThumbnailUrl"] = cover_thumbnail_url
    return data


def _cover_thumbnails(db: Session, article_ids: list[int]) -> dict[int, str]:
    if not article_ids:
        return {}
    assets = db.scalars(
        select(MediaAsset)
        .where(
            MediaAsset.article_id.in_(article_ids),
            MediaAsset.selected.is_(True),
        )
        .order_by(
            MediaAsset.article_id,
            case((MediaAsset.usage_type == "COVER", 0), else_=1),
            MediaAsset.created_at.desc(),
        )
    ).all()
    covers: dict[int, str] = {}
    for asset in assets:
        if asset.article_id is None or asset.article_id in covers:
            continue
        covers[asset.article_id] = asset.thumbnail_url or asset.image_url
    return covers


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
        # ``updated_at`` has only second-level precision on SQLite, so ties are
        # broken by id to keep pagination and "most recent" ordering stable
        # when several articles are updated within the same second.
        .order_by(ContentArticle.updated_at.desc(), ContentArticle.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    article_ids = [article.id for article, _ in rows]
    cover_map = _cover_thumbnails(db, article_ids)
    return success_response(
        request,
        {
            "items": [
                _article_data(article, count, cover_map.get(article.id))
                for article, count in rows
            ],
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
    user: User = Depends(require_roles("OPERATOR")),
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
    user: User = Depends(require_roles("OPERATOR")),
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
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    article = db.get(ContentArticle, article_id)
    if not article:
        raise AppException(40401, "文章不存在", 404)
    for key, value in payload.model_dump(exclude={"keywords"}, exclude_unset=True).items():
        if value is not None or key != "status":
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
    user: User = Depends(require_roles("OPERATOR")),
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
    user: User = Depends(require_roles("OPERATOR")),
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
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    variant = db.get(ContentVariant, variant_id)
    if not variant:
        raise AppException(40402, "内容版本不存在", 404)
    clean_title = normalize_visible_markdown(payload.title)
    clean_content = normalize_visible_markdown(payload.content_text)
    tag_limits = {"WEIBO": 5, "X": 4, "XIAOHONGSHU": 10, "WECHAT_OFFICIAL": 8, "TOUTIAO": 8}
    normalized_hashtags = normalize_topics(
        payload.hashtags, limit=tag_limits.get(variant.platform, 10)
    )
    has_selected_media = bool(
        variant.platform == "WEIBO"
        and db.scalar(
            select(func.count(MediaAsset.id)).where(
                MediaAsset.article_id == variant.article_id,
                MediaAsset.selected.is_(True),
            )
        )
    )
    if has_selected_media:
        fitted = compact_weibo_image_payload(
            {
                "title": clean_title,
                "content": clean_content,
                "hashtags": normalized_hashtags,
            }
        )
        clean_title = fitted["title"]
        clean_content = fitted["content"]
        normalized_hashtags = fitted["hashtags"]
    title_limits = {"WEIBO": 60, "X": 80, "XIAOHONGSHU": 20, "WECHAT_OFFICIAL": 64, "TOUTIAO": 30}
    title_limit = title_limits.get(variant.platform, 255)
    if not clean_title:
        raise AppException(40029, "标题不能为空")
    if len(clean_title) > title_limit:
        raise AppException(40029, f"{variant.platform} 标题最多 {title_limit} 个字符")
    if not clean_content:
        raise AppException(40030, "正文不能为空")
    content_limits = {"XIAOHONGSHU": 1000}
    content_limit = content_limits.get(variant.platform)
    if content_limit and len(clean_content) > content_limit:
        raise AppException(40030, f"{variant.platform} 正文最多 {content_limit} 个字符")
    variant.title = clean_title
    variant.content_text = clean_content
    if variant.platform == "WECHAT_OFFICIAL":
        variant.content_html, variant.format_profile_json = format_wechat_html(
            clean_content, variant.format_profile_json or None
        )
    else:
        variant.content_html = markdown_to_safe_html(clean_content)
    if variant.platform == "X":
        weighted_length = x_weighted_length(
            build_x_post(clean_title, clean_content, normalized_hashtags)
        )
        if weighted_length > 280:
            raise AppException(40030, f"X 帖子最多 280 个加权字符，当前为 {weighted_length}")
    variant.hashtags_json = normalized_hashtags
    variant.emoji_count = count_emoji(clean_title + clean_content)
    variant.word_count = len(clean_content)
    variant.manual_edit_ratio = edit_ratio(variant.original_generated_text, clean_content)
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
    content_text = normalize_visible_markdown(data.pop("content_text"))
    content_html, profile = format_wechat_html(content_text, data)
    return success_response(request, {"contentHtml": content_html, "profile": profile})


@router.put("/variants/{variant_id}/format")
def format_wechat_variant(
    variant_id: int,
    payload: WechatFormatRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
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


async def _save_variant_to_draft(
    variant_id: int,
    request: Request,
    db: Session,
    user: User,
    *,
    platform: str,
    error_code: int,
    success_message: str,
    platform_check_message: str,
    account_missing_message: str,
    publish_mode_resolver: Callable | None = None,
    pre_publish: Callable | None = None,
) -> dict:
    """Shared logic for saving a variant to a platform draft box.

    ``publish_mode_resolver`` receives the account and returns the publish mode
    string (defaults to ``"BROWSER_DRAFT"``).  ``pre_publish`` receives
    ``(variant, account)`` for platform-specific preprocessing (e.g. HTML
    rendering) before the schedule row is created.
    """
    variant = db.get(ContentVariant, variant_id)
    if not variant:
        raise AppException(40402, "内容版本不存在", 404)
    if variant.platform != platform:
        raise AppException(40078, platform_check_message)
    account = get_platform_account(db, platform)
    if not account:
        raise AppException(40411, account_missing_message, 404)

    publish_mode = (
        publish_mode_resolver(account) if publish_mode_resolver else "BROWSER_DRAFT"
    )
    if pre_publish:
        pre_publish(variant, account)

    row = PublishSchedule(
        article_id=variant.article_id,
        variant_id=variant.id,
        account_id=account.id,
        platform=platform,
        scheduled_at=datetime.now(),
        publish_mode=publish_mode,
        status="PENDING",
        publish_package_json={"trigger": "studio_save_draft"},
        idempotency_key=str(uuid.uuid4()),
        created_by=user.id,
    )
    db.add(row)
    db.flush()
    record_audit(db, request, user, "CREATE_DRAFT", "CONTENT", "VARIANT", variant.id)
    db.commit()

    result = await execute_publish(db, row.id)
    if result.status != "DRAFT_CREATED":
        raise AppException(
            error_code,
            result.error_message or f"{platform}草稿保存失败，请查看发布中心详情",
            502,
        )
    return success_response(
        request,
        {
            "scheduleId": result.id,
            "status": result.status,
            "draftId": result.external_id or "",
            "draftUrl": result.published_url or "",
            "resultMode": result.result_mode or publish_mode,
        },
        success_message,
    )


def _resolve_wechat_publish_mode(account) -> str:
    if account.publish_mode == "BROWSER_DRAFT":
        return "BROWSER_DRAFT"
    if account.publish_mode in {"DRAFT_ONLY", "SUBMIT_PUBLISH"}:
        return "DRAFT_ONLY"
    raise AppException(40075, "微信公众号账号没有启用可用的草稿保存方式")


def _render_wechat_html(variant: ContentVariant, _account) -> None:
    variant.content_html, variant.format_profile_json = format_wechat_html(
        variant.content_text,
        variant.format_profile_json or {},
    )


@router.post("/variants/{variant_id}/wechat-draft")
async def save_wechat_variant_to_draft(
    variant_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    """Save the current edited WeChat variant to the real account draft box now."""
    return await _save_variant_to_draft(
        variant_id,
        request,
        db,
        user,
        platform="WECHAT_OFFICIAL",
        error_code=50218,
        success_message="文章已保存到微信公众号草稿箱",
        platform_check_message="只有微信公众号版本可以保存到公众号草稿箱",
        account_missing_message="请先连接微信公众号账号",
        publish_mode_resolver=_resolve_wechat_publish_mode,
        pre_publish=_render_wechat_html,
    )


@router.post("/variants/{variant_id}/toutiao-draft")
async def save_toutiao_variant_to_draft(
    variant_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    """Save the current edited Toutiao variant to the real account draft box now."""
    return await _save_variant_to_draft(
        variant_id,
        request,
        db,
        user,
        platform="TOUTIAO",
        error_code=50219,
        success_message="文章已保存到今日头条草稿箱",
        platform_check_message="只有今日头条版本可以保存到头条草稿箱",
        account_missing_message="请先连接今日头条账号",
    )


@router.post("/variants/{variant_id}/approve")
def approve_variant(
    variant_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    variant = db.get(ContentVariant, variant_id)
    if not variant:
        raise AppException(40402, "内容版本不存在", 404)
    if variant.review_status == "APPROVED":
        raise AppException(40906, "该版本已经是审核通过状态", 409)
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
    user: User = Depends(require_roles("OPERATOR")),
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
    user: User = Depends(require_roles("OPERATOR")),
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
