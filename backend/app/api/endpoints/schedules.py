import io
import ipaddress
import json
import uuid
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, require_roles
from app.core.config import settings
from app.core.credentials import decrypt_json
from app.core.exceptions import AppException
from app.core.responses import success_response
from app.db.session import get_db
from app.models.business import (
    ContentArticle,
    ContentVariant,
    MediaAsset,
    PlatformAccount,
    PublishLog,
    PublishRecommendation,
    PublishSchedule,
)
from app.models.user import User
from app.scheduler.runtime import add_schedule_job, remove_schedule_job
from app.schemas.business import ScheduleCreate, ScheduleUpdate
from app.schemas.platform_account import ManualConfirmRequest
from app.services.activity_service import classify_content_type, content_type_name
from app.services.audit_service import record_audit
from app.services.platform_account_service import effective_status
from app.services.publish_service import (
    TEXT_REAL_API_PLATFORMS,
    execute_publish,
    toutiao_public_publish_enabled,
    validate_schedule_account,
    x_public_publish_enabled,
)
from app.services.serializers import model_dict

router = APIRouter(tags=["排期与发布"])

CONFLICT_WINDOW_MINUTES = 30
DENSITY_WINDOW_MINUTES = 120
ACTIVE_SCHEDULE_STATUSES = ("PENDING", "RUNNING", "WAITING_MANUAL_CONFIRM")


def _local_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)


def _public_client_ip(request: Request) -> str:
    """Return the direct client's public IP without trusting spoofable forwarding headers."""
    host = request.client.host if request.client else ""
    try:
        parsed = ipaddress.ip_address(host)
    except ValueError:
        return ""
    return str(parsed) if parsed.is_global else ""


def _ensure_schedule_owner(row: PublishSchedule, user: User) -> None:
    if row.created_by != user.id:
        raise AppException(40303, "无权操作其他用户的平台排期", 403)


def _recommendation_meta(row: PublishSchedule) -> dict:
    return {
        "contentTypeName": content_type_name(row.content_type),
        "timeDeviationMinutes": (
            int((row.scheduled_at - row.recommended_at).total_seconds() // 60)
            if row.recommended_at
            else None
        ),
        "usedRecommendedTime": row.time_source in {"RECOMMENDED", "ALTERNATIVE"},
    }


def _data(db: Session, row: PublishSchedule, include_logs: bool = False) -> dict:
    data = model_dict(row, camel=True)
    article = db.get(ContentArticle, row.article_id)
    variant = db.get(ContentVariant, row.variant_id)
    account = db.get(PlatformAccount, row.account_id) if row.account_id else None
    data.update(
        {
            "articleTitle": article.title if article else "",
            "variantTitle": variant.title if variant else "",
            "accountName": account.account_name if account else "",
            **_recommendation_meta(row),
        }
    )
    if include_logs:
        data["logs"] = [model_dict(log, camel=True) for log in row.logs]
    return data


@router.get("/schedules")
def list_schedules(
    request: Request,
    start: datetime | None = None,
    end: datetime | None = None,
    platform: str = "",
    status: str = "",
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    filters = []
    if start:
        filters.append(PublishSchedule.scheduled_at >= start)
    if end:
        filters.append(PublishSchedule.scheduled_at <= end)
    if platform:
        filters.append(PublishSchedule.platform == platform)
    if status:
        if "," in status:
            filters.append(PublishSchedule.status.in_(status.split(",")))
        else:
            filters.append(PublishSchedule.status == status)
    items = db.scalars(
        select(PublishSchedule)
        .options(selectinload(PublishSchedule.logs))
        .where(*filters)
        .order_by(PublishSchedule.scheduled_at)
    ).all()

    # Batch-prefetch related objects to avoid N+1 queries.
    article_ids = {row.article_id for row in items}
    variant_ids = {row.variant_id for row in items}
    account_ids = {row.account_id for row in items if row.account_id}
    articles = {a.id: a for a in db.scalars(select(ContentArticle).where(ContentArticle.id.in_(article_ids)))} if article_ids else {}
    variants = {v.id: v for v in db.scalars(select(ContentVariant).where(ContentVariant.id.in_(variant_ids)))} if variant_ids else {}
    accounts = {a.id: a for a in db.scalars(select(PlatformAccount).where(PlatformAccount.id.in_(account_ids)))} if account_ids else {}

    def serialize(row: PublishSchedule) -> dict:
        data = model_dict(row, camel=True)
        article = articles.get(row.article_id)
        variant = variants.get(row.variant_id)
        account = accounts.get(row.account_id) if row.account_id else None
        data.update(
            {
                "articleTitle": article.title if article else "",
                "variantTitle": variant.title if variant else "",
                "accountName": account.account_name if account else "",
                **_recommendation_meta(row),
            }
        )
        return data

    return success_response(request, [serialize(item) for item in items])


@router.get("/schedules/backlog")
def schedule_backlog(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    active_variant_ids = select(PublishSchedule.variant_id).where(
        PublishSchedule.status.notin_(["CANCELLED"])
    )
    variants = db.scalars(
        select(ContentVariant)
        .where(
            ContentVariant.review_status == "APPROVED",
            ContentVariant.id.notin_(active_variant_ids),
        )
        .order_by(ContentVariant.updated_at.desc(), ContentVariant.id.desc())
    ).all()
    items = []
    for variant in variants:
        article = db.get(ContentArticle, variant.article_id)
        cover_ready = (
            db.scalar(
                select(MediaAsset.id).where(
                    MediaAsset.article_id == variant.article_id,
                    MediaAsset.usage_type == "COVER",
                    MediaAsset.selected.is_(True),
                )
            )
            is not None
        )
        account = db.scalar(
            select(PlatformAccount).where(
                PlatformAccount.platform == variant.platform,
            )
        )
        account_ready = variant.platform == "XIAOHONGSHU" or (
            account is not None and effective_status(account) == "CONNECTED"
        )
        blockers = []
        if not cover_ready:
            blockers.append("缺少封面")
        if not account_ready:
            blockers.append("账号未连接")
        items.append(
            {
                "articleId": variant.article_id,
                "variantId": variant.id,
                "articleTitle": article.title if article else "",
                "variantTitle": variant.title,
                "platform": variant.platform,
                "reviewStatus": variant.review_status,
                "coverReady": cover_ready,
                "accountReady": account_ready,
                "ready": not blockers,
                "blockers": blockers,
                "updatedAt": variant.updated_at,
            }
        )
    return success_response(request, items)


@router.get("/schedules/conflict-check")
def conflict_check(
    request: Request,
    platform: str,
    scheduled_at: datetime,
    account_id: int | None = None,
    exclude_schedule_id: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    """Hard conflicts (same platform, <30 min) and same-account density warnings."""
    moment = _local_naive(scheduled_at)
    window = timedelta(minutes=DENSITY_WINDOW_MINUTES)
    rows = db.scalars(
        select(PublishSchedule).where(
            PublishSchedule.platform == platform,
            PublishSchedule.status.in_(ACTIVE_SCHEDULE_STATUSES),
            PublishSchedule.scheduled_at >= moment - window,
            PublishSchedule.scheduled_at <= moment + window,
        )
    ).all()
    conflicts = []
    for row in rows:
        if exclude_schedule_id and row.id == exclude_schedule_id:
            continue
        minutes = int(abs((row.scheduled_at - moment).total_seconds()) // 60)
        same_account = bool(account_id and row.account_id == account_id)
        if minutes < CONFLICT_WINDOW_MINUTES:
            level = "CONFLICT"
            message = f"该平台已有排期与所选时间相差 {minutes} 分钟"
        elif same_account:
            level = "DENSITY"
            message = f"同账号 {minutes} 分钟内已有排期，发布可能过密"
        else:
            continue
        conflicts.append(
            {
                "scheduleId": row.id,
                "articleTitle": (
                    article.title
                    if (article := db.get(ContentArticle, row.article_id)) is not None
                    else ""
                ),
                "scheduledAt": row.scheduled_at.isoformat(),
                "minutes": minutes,
                "sameAccount": same_account,
                "level": level,
                "message": message,
            }
        )
    return success_response(
        request,
        {
            "platform": platform,
            "scheduledAt": moment.isoformat(),
            "hasConflict": any(item["level"] == "CONFLICT" for item in conflicts),
            "hasDensityWarning": any(item["level"] == "DENSITY" for item in conflicts),
            "conflicts": conflicts,
        },
    )


@router.post("/schedules")
def create_schedule(
    payload: ScheduleCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    article = db.get(ContentArticle, payload.article_id)
    variant = db.get(ContentVariant, payload.variant_id)
    if not article or not variant or variant.article_id != article.id:
        raise AppException(40031, "文章与平台版本不匹配")
    if variant.platform != payload.platform:
        raise AppException(40033, "内容版本与目标平台不匹配")
    # Manual Xiaohongshu delivery may omit an account. Real local MCP
    # Publishing must use the system-shared account for the selected platform.
    account = None
    if payload.account_id:
        account = db.scalar(
            select(PlatformAccount).where(
                PlatformAccount.id == payload.account_id,
                PlatformAccount.platform == payload.platform,
            )
        )
        if not account:
            raise AppException(40073, "共享平台账号不存在或与目标平台不匹配")
        if account.platform != payload.platform:
            raise AppException(40073, "平台账号与目标平台不匹配")
    elif payload.platform != "XIAOHONGSHU" or payload.publish_mode == "MCP_PUBLISH":
        raise AppException(40072, "创建排期时必须选择平台账号")
    if payload.platform == "X" and not x_public_publish_enabled(account):
        raise AppException(40080, "X 公开发布安全开关未开启，请由管理员确认后启用")
    if payload.platform == "TOUTIAO":
        if payload.publish_mode != "BROWSER_PUBLISH":
            raise AppException(40081, "今日头条仅支持本机浏览器发布")
        if not account or account.publish_mode != "BROWSER_PUBLISH":
            raise AppException(40075, "今日头条账号未启用本机浏览器发布")
        if effective_status(account) != "CONNECTED":
            raise AppException(40075, "今日头条账号尚未扫码登录或登录已失效")
        if not toutiao_public_publish_enabled(account):
            raise AppException(40083, "今日头条真实发布开关未开启，请由管理员确认后启用")
    if payload.platform == "WECHAT_OFFICIAL" and payload.publish_mode == "BROWSER_DRAFT":
        if not settings.wechat_browser_publishing_enabled:
            raise AppException(40084, "微信公众号本机扫码草稿功能已关闭")
        if not account or account.publish_mode != "BROWSER_DRAFT":
            raise AppException(40075, "微信公众号账号未启用本机扫码草稿模式")
        if effective_status(account) != "CONNECTED":
            raise AppException(40075, "微信公众号后台尚未扫码登录或登录已失效")
    if payload.publish_mode in {"REAL_API", "DRAFT_ONLY"}:
        allowed_account_modes = (
            {"REAL_API"}
            if payload.platform in TEXT_REAL_API_PLATFORMS and payload.publish_mode == "REAL_API"
            else {"SUBMIT_PUBLISH"}
            if payload.publish_mode == "REAL_API"
            else {"DRAFT_ONLY", "SUBMIT_PUBLISH"}
        )
        if account.publish_mode not in allowed_account_modes:
            raise AppException(40075, "账号配置未启用所选真实发布方式")
        status = effective_status(account)
        x_can_refresh = bool(
            payload.platform == "X"
            and status == "TOKEN_EXPIRED"
            and account.refresh_token_encrypted
        )
        if status != "CONNECTED" and not x_can_refresh:
            raise AppException(40075, "真实发布前必须先通过平台账号连接测试")
        required = (
            "DRAFT_CREATE"
            if payload.publish_mode == "DRAFT_ONLY"
            else (
                "TEXT_PUBLISH" if payload.platform in TEXT_REAL_API_PLATFORMS else "SUBMIT_PUBLISH"
            )
        )
        if required not in set(account.capabilities_json or []):
            raise AppException(40076, f"平台账号缺少发布能力：{required}")
        if (
            payload.platform == "WECHAT_OFFICIAL"
            and payload.publish_mode == "REAL_API"
            and not decrypt_json(account.credentials_encrypted).get("allow_submit_publish")
        ):
            raise AppException(40076, "公众号配置未明确允许提交发布")
    xhs_modes = {"MANUAL_CONFIRM", "MCP_PUBLISH"}
    if payload.platform == "XIAOHONGSHU" and payload.publish_mode not in xhs_modes:
        raise AppException(40077, "小红书仅支持人工确认或本地 xiaohongshu-mcp 发布")
    if (
        payload.platform == "XIAOHONGSHU"
        and payload.publish_mode == "MCP_PUBLISH"
        and not settings.experimental_browser_publishing_enabled
    ):
        raise AppException(40078, "本地 MCP 发布默认关闭，请改用人工确认")
    if payload.platform == "XIAOHONGSHU" and payload.publish_mode == "MCP_PUBLISH":
        if not account or account.publish_mode != "MCP_PUBLISH":
            raise AppException(40075, "小红书账号未启用本地 MCP 发布")
        if effective_status(account) != "CONNECTED":
            raise AppException(40075, "小红书本地 MCP 尚未登录或连接检测未通过")
    if payload.platform != "XIAOHONGSHU" and payload.publish_mode == "MANUAL_CONFIRM":
        raise AppException(40077, "人工交付目前仅用于小红书")
    scheduled_at = _local_naive(payload.scheduled_at)
    if scheduled_at <= datetime.now():
        raise AppException(40032, "排期时间必须晚于当前时间")
    conflict = db.scalar(
        select(PublishSchedule).where(
            PublishSchedule.platform == payload.platform,
            PublishSchedule.scheduled_at.between(
                scheduled_at.replace(second=0), scheduled_at.replace(second=59)
            ),
            PublishSchedule.status.in_(["PENDING", "RUNNING"]),
        )
    )
    if conflict:
        raise AppException(40902, "该平台同一时间已有排期，请调整时间", 409)
    values = payload.model_dump()
    values["scheduled_at"] = scheduled_at
    publish_context: dict[str, str] = {}
    if payload.platform == "WEIBO":
        operation_ip = _public_client_ip(request)
        if operation_ip:
            publish_context["operationIp"] = operation_ip
    recommendation = (
        db.get(PublishRecommendation, payload.recommendation_id)
        if payload.recommendation_id
        else None
    )
    if payload.recommendation_id and not recommendation:
        raise AppException(40405, "推荐记录不存在", 404)
    values["content_type"] = (
        payload.content_type
        or (recommendation.content_type if recommendation else None)
        or classify_content_type(variant.title, variant.content_text)
    )
    values["recommended_at"] = recommendation.recommended_at if recommendation else None
    if recommendation:
        values["recommendation_snapshot_json"] = {
            "recommendedAt": recommendation.recommended_at.isoformat(),
            "score": recommendation.score,
            "confidence": recommendation.confidence,
            "algorithmVersion": recommendation.algorithm_version,
            "sampleCount": recommendation.sample_count,
            "accountSampleCount": recommendation.account_sample_count,
            "baselineSampleCount": recommendation.baseline_sample_count,
            "weights": recommendation.weights_json or {},
            "dataSource": recommendation.data_source_json or {},
            "reasons": recommendation.reason_json or [],
            "alternatives": recommendation.alternative_times_json or [],
            "warnings": recommendation.warnings_json or [],
            "narrative": recommendation.narrative,
            "narrativeProvider": recommendation.narrative_provider,
            "contentType": recommendation.content_type,
            "contentTypeName": content_type_name(recommendation.content_type),
        }
    row = PublishSchedule(
        **values,
        status="PENDING",
        publish_package_json=publish_context,
        idempotency_key=str(uuid.uuid4()),
        created_by=user.id,
    )
    db.add(row)
    db.flush()
    record_audit(db, request, user, "CREATE", "SCHEDULING", "SCHEDULE", row.id)
    db.commit()
    db.refresh(row)
    add_schedule_job(row.id, row.scheduled_at)
    return success_response(request, _data(db, row), "排期已创建")


@router.get("/schedules/{schedule_id}")
def get_schedule(
    schedule_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    row = db.get(PublishSchedule, schedule_id)
    if not row:
        raise AppException(40407, "排期任务不存在", 404)
    return success_response(request, _data(db, row, True))


@router.put("/schedules/{schedule_id}")
def update_schedule(
    schedule_id: int,
    payload: ScheduleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    row = db.get(PublishSchedule, schedule_id)
    if not row:
        raise AppException(40407, "排期任务不存在", 404)
    _ensure_schedule_owner(row, user)
    if row.status not in {"PENDING", "FAILED", "WAITING_MANUAL_CONFIRM"}:
        raise AppException(40903, "当前状态不允许修改", 409)
    if payload.scheduled_at:
        scheduled_at = _local_naive(payload.scheduled_at)
        if scheduled_at <= datetime.now():
            raise AppException(40032, "排期时间必须晚于当前时间")
        row.scheduled_at = scheduled_at
        if payload.time_source is None and row.recommended_at:
            # Dragging a task on the calendar away from the recommended slot must
            # be reflected in the adoption statistics.
            row.time_source = "RECOMMENDED" if scheduled_at == row.recommended_at else "CUSTOM"
    if payload.time_source:
        row.time_source = payload.time_source
    if payload.publish_mode:
        row.publish_mode = payload.publish_mode
    if payload.account_id:
        account = db.scalar(
            select(PlatformAccount).where(
                PlatformAccount.id == payload.account_id,
                PlatformAccount.platform == row.platform,
            )
        )
        if not account:
            raise AppException(40073, "共享平台账号不存在或与排期平台不匹配")
        row.account_id = account.id
    account = db.get(PlatformAccount, row.account_id) if row.account_id else None
    validate_schedule_account(row, account)
    row.status = "PENDING"
    record_audit(db, request, user, "UPDATE", "SCHEDULING", "SCHEDULE", row.id)
    db.commit()
    add_schedule_job(row.id, row.scheduled_at)
    return success_response(request, _data(db, row), "排期已更新")


@router.delete("/schedules/{schedule_id}")
def delete_schedule(
    schedule_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    row = db.get(PublishSchedule, schedule_id)
    if not row:
        raise AppException(40407, "排期任务不存在", 404)
    _ensure_schedule_owner(row, user)
    if row.status in {"PUBLISHING", "PUBLISHED", "DRAFT_CREATED", "PUBLISH_SUBMITTED", "MANUAL_PUBLISHED"}:
        raise AppException(40903, "已执行任务不能删除", 409)
    remove_schedule_job(row.id)
    record_audit(db, request, user, "DELETE", "SCHEDULING", "SCHEDULE", row.id)
    db.delete(row)
    db.commit()
    return success_response(request, {"id": schedule_id}, "排期已删除")


@router.post("/schedules/{schedule_id}/cancel")
def cancel_schedule(
    schedule_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    row = db.get(PublishSchedule, schedule_id)
    if not row:
        raise AppException(40407, "排期任务不存在", 404)
    _ensure_schedule_owner(row, user)
    if row.status in {"PUBLISHING", "PUBLISHED", "DRAFT_CREATED", "PUBLISH_SUBMITTED", "MANUAL_PUBLISHED"}:
        raise AppException(40903, "已发布任务不能取消", 409)
    row.status = "CANCELLED"
    remove_schedule_job(row.id)
    record_audit(db, request, user, "CANCEL", "PUBLISH", "SCHEDULE", row.id)
    db.commit()
    return success_response(request, _data(db, row), "任务已取消")


@router.post("/schedules/{schedule_id}/publish-now")
async def publish_now(
    schedule_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    existing = db.get(PublishSchedule, schedule_id)
    if not existing:
        raise AppException(40407, "排期任务不存在", 404)
    _ensure_schedule_owner(existing, user)
    row = await execute_publish(db, schedule_id)
    record_audit(
        db, request, user, "PUBLISH_NOW", "PUBLISH", "SCHEDULE", row.id, {"status": row.status}
    )
    db.commit()
    return success_response(request, _data(db, row, True), "发布流程已执行")


@router.post("/schedules/{schedule_id}/retry")
async def retry(
    schedule_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    row = db.get(PublishSchedule, schedule_id)
    if row:
        _ensure_schedule_owner(row, user)
    if not row or row.status != "FAILED":
        raise AppException(40904, "只有失败任务可以重试", 409)
    if row.retry_count >= row.max_retry_count:
        raise AppException(40905, "已达到最大重试次数", 409)
    return await publish_now(schedule_id, request, db, user)


@router.post("/schedules/{schedule_id}/manual-confirm")
async def manual_confirm(
    schedule_id: int,
    payload: ManualConfirmRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    row = db.get(PublishSchedule, schedule_id)
    if row:
        _ensure_schedule_owner(row, user)
    if not row or row.status != "WAITING_MANUAL_CONFIRM":
        raise AppException(40906, "当前任务不在等待人工确认状态", 409)
    if row.platform == "XIAOHONGSHU" and not payload.published_url:
        raise AppException(40078, "请填写小红书真实发布链接")
    row.status = "MANUAL_PUBLISHED"
    row.result_mode = "MANUAL_CONFIRM"
    row.actual_publish_at = datetime.now()
    row.published_url = str(payload.published_url) if payload.published_url else None
    db.add(
        PublishLog(
            schedule_id=row.id,
            step="MANUAL_CONFIRM",
            response_summary="运营人员已确认平台发布",
            status="MANUAL_PUBLISHED",
        )
    )
    record_audit(db, request, user, "MANUAL_CONFIRM", "PUBLISH", "SCHEDULE", row.id)
    db.commit()
    return success_response(request, _data(db, row, True), "人工发布已确认")


@router.get("/schedules/{schedule_id}/publish-package")
def get_publish_package(
    schedule_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    row = db.get(PublishSchedule, schedule_id)
    if not row or row.created_by != user.id:
        raise AppException(40407, "发布任务不存在", 404)
    if row.platform != "XIAOHONGSHU":
        raise AppException(40079, "只有小红书人工任务提供发布包")
    return success_response(request, row.publish_package_json or {})


@router.get("/schedules/{schedule_id}/publish-package/download")
def download_publish_package(
    schedule_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> StreamingResponse:
    row = db.get(PublishSchedule, schedule_id)
    if not row or row.created_by != user.id:
        raise AppException(40407, "发布任务不存在", 404)
    if row.platform != "XIAOHONGSHU":
        raise AppException(40079, "只有小红书人工任务提供发布包")
    package = row.publish_package_json or {}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        text = f"{package.get('title', '')}\n\n{package.get('content', '')}\n\n"
        text += " ".join(package.get("hashtags", []))
        archive.writestr("发布文案.txt", text)
        archive.writestr("发布说明.json", json.dumps(package, ensure_ascii=False, indent=2))
        for index, image_url in enumerate(package.get("images", []), start=1):
            path = _package_image_path(str(image_url))
            if path and path.is_file():
                archive.writestr(f"images/{index:02d}{path.suffix.lower()}", path.read_bytes())
    stream.seek(0)
    return StreamingResponse(
        stream,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="xiaohongshu-{schedule_id}.zip"'},
    )


def _package_image_path(value: str) -> Path | None:
    parsed = urlparse(value)
    url_path = parsed.path if parsed.scheme else value
    project_root = Path(__file__).resolve().parents[4]
    if url_path.startswith("/uploads/"):
        return project_root / url_path.lstrip("/")
    if url_path.startswith("/media/"):
        return project_root / "frontend" / "public" / url_path.lstrip("/")
    return None
