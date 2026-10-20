import hashlib
import io
import ipaddress
import json
import threading
import uuid
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, require_roles
from app.core.config import settings
from app.core.credentials import decrypt_json
from app.core.exceptions import AppException
from app.core.paths import local_media_path
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
from app.schemas.business import ScheduleBatchRequest, ScheduleCreate, ScheduleUpdate
from app.schemas.platform_account import ManualConfirmRequest
from app.services.activity_service import business_now, classify_content_type, content_type_name
from app.services.audit_service import record_audit
from app.services.image_service import _download_generated_image, image_content_suffix
from app.services.platform_account_service import effective_status
from app.services.publish_service import (
    SCHEDULE_REVISION_FIELD,
    TEXT_REAL_API_PLATFORMS,
    ScheduleState,
    bluesky_public_publish_enabled,
    execute_publish,
    mastodon_public_publish_enabled,
    schedule_state,
    schedule_state_conditions,
    toutiao_public_publish_enabled,
    validate_schedule_account,
    x_public_publish_enabled,
)
from app.services.review_fingerprint import require_current_approval
from app.services.serializers import model_dict
from app.services.task_dispatch_service import (
    TASK_TYPE_SCHEDULE,
    cancel_dispatch,
    upsert_dispatch,
)

router = APIRouter(tags=["排期与发布"])

CONFLICT_WINDOW_MINUTES = 30
DENSITY_WINDOW_MINUTES = 120
ACTIVE_SCHEDULE_STATUSES = ("PENDING", "RUNNING", "PUBLISHING", "WAITING_MANUAL_CONFIRM")
# Failures that did not produce a public post and can be retried after the
# operator fixes the account (re-scan QR, re-authorize, etc.).
RECOVERABLE_FAILURE_STATUSES = {
    "FAILED",
    "LOGIN_REQUIRED",
    "NEED_USER_ACTION",
    "VERIFICATION_REQUIRED",
    "TOKEN_EXPIRED",
}
# Serializes conflict-check + insert + commit inside this process. The unique
# idempotency key covers double-clicks; this lock also protects two different
# requests picking the same minute.
_SCHEDULE_CREATE_LOCK = threading.Lock()
CREATE_REQUEST_FINGERPRINT = "createRequestFingerprint"


def _local_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(ZoneInfo(settings.app_timezone)).replace(tzinfo=None)


def _forwarded_public_ip(direct_host: str, x_real_ip: str, x_forwarded_for: str) -> str:
    try:
        direct = ipaddress.ip_address(direct_host)
    except ValueError:
        return ""
    if direct.is_global:
        return str(direct)
    # The request came from a local reverse proxy (Docker Nginx). Trust its
    # forwarding headers only in that case; a directly exposed backend always
    # uses the real peer address above.
    candidates = [x_real_ip, *x_forwarded_for.split(",")]
    for candidate in candidates:
        try:
            parsed = ipaddress.ip_address(candidate.strip())
        except ValueError:
            continue
        if parsed.is_global:
            return str(parsed)
    return ""


def _public_client_ip(request: Request) -> str:
    """Return the public client IP without trusting spoofable headers directly."""
    host = request.client.host if request.client else ""
    return _forwarded_public_ip(
        host,
        request.headers.get("x-real-ip", ""),
        request.headers.get("x-forwarded-for", ""),
    )


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
    limit: int | None = Query(default=None, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
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
    statement = (
        select(PublishSchedule)
        .options(selectinload(PublishSchedule.logs))
        .where(*filters)
        .order_by(PublishSchedule.scheduled_at)
    )
    if limit is not None:
        statement = statement.offset(offset).limit(limit)
    items = db.scalars(statement).all()

    # Batch-prefetch related objects to avoid N+1 queries.
    article_ids = {row.article_id for row in items}
    variant_ids = {row.variant_id for row in items}
    account_ids = {row.account_id for row in items if row.account_id}
    articles = (
        {
            a.id: a
            for a in db.scalars(select(ContentArticle).where(ContentArticle.id.in_(article_ids)))
        }
        if article_ids
        else {}
    )
    variants = (
        {
            v.id: v
            for v in db.scalars(select(ContentVariant).where(ContentVariant.id.in_(variant_ids)))
        }
        if variant_ids
        else {}
    )
    accounts = (
        {
            a.id: a
            for a in db.scalars(select(PlatformAccount).where(PlatformAccount.id.in_(account_ids)))
        }
        if account_ids
        else {}
    )

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


def _create_fingerprint(
    payload: ScheduleCreate, recommended_at_override: datetime | None = None
) -> str:
    values = payload.model_dump(mode="json", exclude={"idempotency_key"})
    values["scheduled_at"] = _local_naive(payload.scheduled_at).isoformat(timespec="microseconds")
    values["recommended_at_override"] = (
        _local_naive(recommended_at_override).isoformat(timespec="microseconds")
        if recommended_at_override is not None
        else None
    )
    canonical = json.dumps(values, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _validate_create_replay(
    existing: PublishSchedule,
    user: User,
    payload: ScheduleCreate,
    recommended_at_override: datetime | None = None,
) -> None:
    if existing.created_by != user.id:
        raise AppException(40902, "幂等键已被其他排期使用", 409)
    fingerprint = (existing.publish_package_json or {}).get(CREATE_REQUEST_FINGERPRINT)
    if fingerprint:
        matches = fingerprint == _create_fingerprint(payload, recommended_at_override)
    else:
        # Existing installations have no original request fingerprint. Reuse a
        # legacy key only when every stored creation field still agrees.
        matches = all(
            getattr(existing, name) == getattr(payload, name)
            for name in (
                "article_id",
                "variant_id",
                "account_id",
                "platform",
                "publish_mode",
                "recommendation_id",
                "time_source",
            )
        ) and existing.scheduled_at == _local_naive(payload.scheduled_at)
        if payload.content_type is not None:
            matches = matches and existing.content_type == payload.content_type
        if recommended_at_override is not None:
            matches = matches and existing.recommended_at == _local_naive(recommended_at_override)
    if not matches:
        raise AppException(40902, "本次提交与原排期参数不同，请重新创建排期", 409)


def _ensure_schedule_dispatch(db: Session, row: PublishSchedule) -> None:
    if row.status != "PENDING":
        return
    state = schedule_state(row)
    upsert_dispatch(
        db,
        task_type=TASK_TYPE_SCHEDULE,
        task_id=str(row.id),
        revision=str(state.revision or ""),
        run_at=row.scheduled_at,
    )


def _resolve_schedule_targets(
    db: Session, payload: ScheduleCreate
) -> tuple[ContentArticle, ContentVariant, PlatformAccount | None]:
    article = db.get(ContentArticle, payload.article_id)
    variant = db.get(ContentVariant, payload.variant_id)
    if not article or not variant or variant.article_id != article.id:
        raise AppException(40031, "文章与平台版本不匹配")
    if variant.platform != payload.platform:
        raise AppException(40033, "内容版本与目标平台不匹配")
    require_current_approval(variant)
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
    elif payload.platform != "XIAOHONGSHU" or payload.publish_mode == "MCP_PUBLISH":
        raise AppException(40072, "创建排期时必须选择平台账号")
    return article, variant, account


def _validate_live_publish_switches(
    payload: ScheduleCreate, account: PlatformAccount | None, *, defer_live_connection: bool
) -> None:
    if defer_live_connection:
        return
    if payload.platform == "X" and not x_public_publish_enabled(account):
        raise AppException(40080, "X 公开发布安全开关未开启，请由管理员确认后启用")
    if payload.platform == "BLUESKY" and not bluesky_public_publish_enabled(account):
        raise AppException(40085, "Bluesky 真实发布开关未开启，请在账号设置中启用")
    if payload.platform == "MASTODON" and not mastodon_public_publish_enabled(account):
        raise AppException(40086, "Mastodon 真实发布开关未开启，请在账号设置中启用")


def _validate_toutiao_route(
    payload: ScheduleCreate, account: PlatformAccount | None, *, defer_live_connection: bool
) -> None:
    if payload.platform != "TOUTIAO":
        return
    if payload.publish_mode != "BROWSER_PUBLISH":
        raise AppException(40081, "今日头条仅支持本机浏览器发布")
    if not account or account.publish_mode != "BROWSER_PUBLISH":
        raise AppException(40075, "今日头条账号未启用本机浏览器发布")
    if defer_live_connection:
        return
    if effective_status(account) != "CONNECTED":
        raise AppException(40075, "今日头条账号尚未扫码登录或登录已失效")
    if not toutiao_public_publish_enabled(account):
        raise AppException(40083, "今日头条真实发布开关未开启，请由管理员确认后启用")


def _validate_wechat_browser_route(
    payload: ScheduleCreate, account: PlatformAccount | None, *, defer_live_connection: bool
) -> None:
    if payload.platform != "WECHAT_OFFICIAL" or payload.publish_mode != "BROWSER_DRAFT":
        return
    if not settings.wechat_browser_publishing_enabled:
        raise AppException(40084, "微信公众号本机扫码草稿功能已关闭")
    if not account or account.publish_mode != "BROWSER_DRAFT":
        raise AppException(40075, "微信公众号账号未启用本机扫码草稿模式")
    if not defer_live_connection and effective_status(account) != "CONNECTED":
        raise AppException(40075, "微信公众号后台尚未扫码登录或登录已失效")


def _validate_real_api_route(
    payload: ScheduleCreate, account: PlatformAccount | None, *, defer_live_connection: bool
) -> None:
    if payload.publish_mode not in {"REAL_API", "DRAFT_ONLY"}:
        return
    if account is None:
        raise AppException(40072, "创建排期时必须选择平台账号")
    if payload.platform in TEXT_REAL_API_PLATFORMS and payload.publish_mode == "REAL_API":
        allowed_account_modes = {"REAL_API"}
    elif payload.publish_mode == "REAL_API":
        allowed_account_modes = {"SUBMIT_PUBLISH"}
    else:
        allowed_account_modes = {"DRAFT_ONLY", "SUBMIT_PUBLISH"}
    if account.publish_mode not in allowed_account_modes:
        raise AppException(40075, "账号配置未启用所选真实发布方式")
    if defer_live_connection:
        return
    status = effective_status(account)
    can_refresh = bool(
        payload.platform in {"X", "BLUESKY"}
        and status == "TOKEN_EXPIRED"
        and account.refresh_token_encrypted
    )
    if status != "CONNECTED" and not can_refresh:
        raise AppException(40075, "真实发布前必须先通过平台账号连接测试")
    if payload.publish_mode == "DRAFT_ONLY":
        required = "DRAFT_CREATE"
    elif payload.platform in TEXT_REAL_API_PLATFORMS:
        required = "TEXT_PUBLISH"
    else:
        required = "SUBMIT_PUBLISH"
    if required not in set(account.capabilities_json or []):
        raise AppException(40076, f"平台账号缺少发布能力：{required}")
    if (
        payload.platform == "WECHAT_OFFICIAL"
        and payload.publish_mode == "REAL_API"
        and not decrypt_json(account.credentials_encrypted).get("allow_submit_publish")
    ):
        raise AppException(40076, "公众号配置未明确允许提交发布")


def _validate_xhs_route(
    payload: ScheduleCreate, account: PlatformAccount | None, *, defer_live_connection: bool
) -> None:
    if payload.platform != "XIAOHONGSHU":
        return
    if payload.publish_mode not in {"MANUAL_CONFIRM", "MCP_PUBLISH"}:
        raise AppException(40077, "小红书仅支持人工确认或本地 xiaohongshu-mcp 发布")
    if payload.publish_mode != "MCP_PUBLISH":
        return
    if not settings.experimental_browser_publishing_enabled:
        raise AppException(40078, "本地 MCP 发布默认关闭，请改用人工确认")
    if not account or account.publish_mode != "MCP_PUBLISH":
        raise AppException(40075, "小红书账号未启用本地 MCP 发布")
    if not defer_live_connection and effective_status(account) != "CONNECTED":
        raise AppException(40075, "小红书本地 MCP 尚未登录或连接检测未通过")


def _assert_schedule_slot_free(db: Session, platform: str, scheduled_at: datetime) -> None:
    conflict = db.scalar(
        select(PublishSchedule).where(
            PublishSchedule.platform == platform,
            PublishSchedule.scheduled_at.between(
                scheduled_at.replace(second=0), scheduled_at.replace(second=59)
            ),
            PublishSchedule.status.in_(["PENDING", "RUNNING"]),
        )
    )
    if conflict:
        raise AppException(40902, "该平台同一时间已有排期，请调整时间", 409)


def _build_schedule_values(
    db: Session,
    request: Request,
    payload: ScheduleCreate,
    variant: ContentVariant,
    recommended_at_override: datetime | None,
) -> tuple[dict[str, Any], dict[str, str]]:
    scheduled_at = _local_naive(payload.scheduled_at)
    values = payload.model_dump(exclude={"idempotency_key"})
    values["scheduled_at"] = scheduled_at
    publish_context: dict[str, str] = {
        CREATE_REQUEST_FINGERPRINT: _create_fingerprint(payload, recommended_at_override),
        SCHEDULE_REVISION_FIELD: uuid.uuid4().hex,
    }
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
    values["recommended_at"] = (
        _local_naive(recommended_at_override)
        if recommended_at_override
        else (recommendation.recommended_at if recommendation else None)
    )
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
    return values, publish_context


def _create_schedule_row(
    db: Session,
    request: Request,
    user: User,
    payload: ScheduleCreate,
    *,
    idempotency_key: str | None = None,
    recommended_at_override: datetime | None = None,
    defer_live_connection: bool = False,
) -> tuple[PublishSchedule, bool]:
    """Create a publish_schedule row.

    When ``defer_live_connection`` is True (batch cross-platform planning),
    structural publish-mode checks still apply, but live login / OAuth /
    public-publish gates are deferred to publish execution time. Single-create
    keeps the strict default.
    """
    request_key = idempotency_key or payload.idempotency_key
    if request_key:
        existing = db.scalar(
            select(PublishSchedule).where(PublishSchedule.idempotency_key == request_key)
        )
        if existing:
            _validate_create_replay(existing, user, payload, recommended_at_override)
            _ensure_schedule_dispatch(db, existing)
            return existing, False
    _, variant, account = _resolve_schedule_targets(db, payload)
    _validate_live_publish_switches(payload, account, defer_live_connection=defer_live_connection)
    _validate_toutiao_route(payload, account, defer_live_connection=defer_live_connection)
    _validate_wechat_browser_route(payload, account, defer_live_connection=defer_live_connection)
    _validate_real_api_route(payload, account, defer_live_connection=defer_live_connection)
    _validate_xhs_route(payload, account, defer_live_connection=defer_live_connection)
    if payload.platform != "XIAOHONGSHU" and payload.publish_mode == "MANUAL_CONFIRM":
        raise AppException(40077, "人工交付目前仅用于小红书")
    scheduled_at = _local_naive(payload.scheduled_at)
    if scheduled_at <= business_now():
        raise AppException(40032, "排期时间必须晚于当前时间")
    _assert_schedule_slot_free(db, payload.platform, scheduled_at)
    values, publish_context = _build_schedule_values(
        db, request, payload, variant, recommended_at_override
    )
    row = PublishSchedule(
        **values,
        status="PENDING",
        publish_package_json=publish_context,
        idempotency_key=request_key or str(uuid.uuid4()),
        created_by=user.id,
    )
    db.add(row)
    db.flush()
    _ensure_schedule_dispatch(db, row)
    record_audit(db, request, user, "CREATE", "SCHEDULING", "SCHEDULE", row.id)
    return row, True


@router.post("/schedules")
def create_schedule(
    payload: ScheduleCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    with _SCHEDULE_CREATE_LOCK:
        row, created = _create_schedule_row(db, request, user, payload)
        db.commit()
    db.refresh(row)
    if created:
        add_schedule_job(row.id, row.scheduled_at, schedule_state(row))
    return success_response(request, _data(db, row), "排期已创建" if created else "已返回原排期")


@router.post("/schedules/batch")
def create_schedules_batch(
    payload: ScheduleBatchRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    with _SCHEDULE_CREATE_LOCK:
        return _create_schedules_batch(payload, request, db, user)


def _create_schedules_batch(
    payload: ScheduleBatchRequest,
    request: Request,
    db: Session,
    user: User,
) -> dict:
    batch_key = payload.idempotency_key or str(uuid.uuid4())
    results: list[dict] = []
    created_rows: list[PublishSchedule] = []
    for item in payload.items:
        idempotency_key = f"{batch_key}:{item.platform}:{item.variant_id}"
        if len(idempotency_key) > 100:
            results.append(
                {
                    "platform": item.platform,
                    "success": False,
                    "message": "批量幂等键过长，请缩短 idempotency_key",
                    "code": 40032,
                }
            )
            continue
        try:
            schedule_payload = ScheduleCreate(
                article_id=payload.article_id,
                variant_id=item.variant_id,
                account_id=item.account_id,
                platform=item.platform,
                scheduled_at=item.scheduled_at,
                publish_mode=item.publish_mode,
                recommendation_id=item.recommendation_id,
                time_source=item.time_source,
                content_type=payload.content_type,
            )
            with db.begin_nested():
                row, created = _create_schedule_row(
                    db,
                    request,
                    user,
                    schedule_payload,
                    idempotency_key=idempotency_key,
                    recommended_at_override=item.recommended_at,
                    defer_live_connection=True,
                )
            if created:
                created_rows.append(row)
            results.append(
                {
                    "platform": item.platform,
                    "success": True,
                    "scheduleId": row.id,
                    "scheduledAt": row.scheduled_at.isoformat(),
                    **({"skipped": True, "message": "已返回原排期"} if not created else {}),
                }
            )
        except AppException as exc:
            results.append(
                {
                    "platform": item.platform,
                    "success": False,
                    "message": exc.message,
                    "code": exc.code,
                }
            )
        except IntegrityError:
            existing = db.scalar(
                select(PublishSchedule).where(PublishSchedule.idempotency_key == idempotency_key)
            )
            if existing:
                try:
                    _validate_create_replay(existing, user, schedule_payload, item.recommended_at)
                except AppException as exc:
                    results.append(
                        {
                            "platform": item.platform,
                            "success": False,
                            "message": exc.message,
                            "code": exc.code,
                        }
                    )
                else:
                    results.append(
                        {
                            "platform": item.platform,
                            "success": True,
                            "scheduleId": existing.id,
                            "message": "已返回原排期",
                            "skipped": True,
                        }
                    )
            else:
                results.append(
                    {
                        "platform": item.platform,
                        "success": False,
                        "message": "排期创建发生数据库冲突，请重试",
                        "code": 40902,
                    }
                )
    if created_rows:
        db.commit()
        for row in created_rows:
            db.refresh(row)
            add_schedule_job(row.id, row.scheduled_at, schedule_state(row))
    else:
        db.rollback()
    created_ids = [row.id for row in created_rows]
    return success_response(
        request,
        {
            "batchKey": batch_key,
            "items": results,
            "createdScheduleIds": created_ids,
            "successCount": sum(1 for item in results if item.get("success")),
            "failureCount": sum(1 for item in results if not item.get("success")),
        },
        "批量排期处理完成",
    )


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


def _schedule_for_change(db: Session, schedule_id: int, user: User) -> PublishSchedule:
    row = db.scalar(
        select(PublishSchedule)
        .where(PublishSchedule.id == schedule_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not row:
        raise AppException(40407, "排期任务不存在", 404)
    _ensure_schedule_owner(row, user)
    return row


def _change_schedule(
    db: Session, row: PublishSchedule, observed: ScheduleState, values: dict
) -> None:
    # Assigning ORM attributes before this comparison would allow autoflush
    # to persist an obsolete state before the conditional write.
    package = dict(row.publish_package_json or {})
    package[SCHEDULE_REVISION_FIELD] = uuid.uuid4().hex
    changed = db.execute(
        update(PublishSchedule)
        .where(PublishSchedule.id == row.id, *schedule_state_conditions(observed))
        .values(**values, publish_package_json=package)
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        db.rollback()
        raise AppException(40903, "排期状态已变更，请刷新后核对发布结果", 409)
    db.refresh(row)


@router.put("/schedules/{schedule_id}")
def update_schedule(
    schedule_id: int,
    payload: ScheduleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    row = _schedule_for_change(db, schedule_id, user)
    observed = schedule_state(row)
    if row.status not in {
        "PENDING",
        "WAITING_MANUAL_CONFIRM",
        "EXPIRED",
        "INTERRUPTED",
        *RECOVERABLE_FAILURE_STATUSES,
    }:
        raise AppException(40903, "当前状态不允许修改", 409)
    if row.status in {"EXPIRED", "INTERRUPTED"} and not payload.scheduled_at:
        raise AppException(40032, "错过或中断的任务必须重新指定未来的排期时间")
    values = {"status": "PENDING", "error_message": None}
    if payload.scheduled_at:
        scheduled_at = _local_naive(payload.scheduled_at)
        if scheduled_at <= business_now():
            raise AppException(40032, "排期时间必须晚于当前时间")
        values["scheduled_at"] = scheduled_at
        if payload.time_source is None and row.recommended_at:
            # Dragging a task on the calendar away from the recommended slot must
            # be reflected in the adoption statistics.
            values["time_source"] = (
                "RECOMMENDED" if scheduled_at == row.recommended_at else "CUSTOM"
            )
    if payload.time_source:
        values["time_source"] = payload.time_source
    if payload.publish_mode:
        values["publish_mode"] = payload.publish_mode
    if payload.account_id:
        account = db.scalar(
            select(PlatformAccount).where(
                PlatformAccount.id == payload.account_id,
                PlatformAccount.platform == row.platform,
            )
        )
        if not account:
            raise AppException(40073, "共享平台账号不存在或与排期平台不匹配")
        values["account_id"] = account.id
    account_id = values.get("account_id", row.account_id)
    account = db.get(PlatformAccount, account_id) if account_id else None
    candidate = PublishSchedule(
        platform=row.platform,
        publish_mode=values.get("publish_mode", row.publish_mode),
        account_id=account_id,
    )
    validate_schedule_account(candidate, account)
    _change_schedule(db, row, observed, values)
    _ensure_schedule_dispatch(db, row)
    record_audit(db, request, user, "UPDATE", "SCHEDULING", "SCHEDULE", row.id)
    db.commit()
    remove_schedule_job(row.id, observed)
    add_schedule_job(row.id, row.scheduled_at, schedule_state(row))
    return success_response(request, _data(db, row), "排期已更新")


@router.delete("/schedules/{schedule_id}")
def delete_schedule(
    schedule_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    row = _schedule_for_change(db, schedule_id, user)
    observed = schedule_state(row)
    if row.status in {
        "RUNNING",
        "PUBLISHING",
        "PUBLISHED",
        "DRAFT_CREATED",
        "PUBLISH_SUBMITTED",
        "MANUAL_PUBLISHED",
    }:
        raise AppException(40903, "已执行任务不能删除", 409)
    # Reserve with the publishing comparison before ORM cascades delete logs.
    _change_schedule(db, row, observed, {"status": "CANCELLED"})
    cancel_dispatch(db, task_type=TASK_TYPE_SCHEDULE, task_id=str(row.id))
    record_audit(db, request, user, "DELETE", "SCHEDULING", "SCHEDULE", row.id)
    db.delete(row)
    db.commit()
    remove_schedule_job(schedule_id)
    return success_response(request, {"id": schedule_id}, "排期已删除")


@router.post("/schedules/{schedule_id}/cancel")
def cancel_schedule(
    schedule_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    row = _schedule_for_change(db, schedule_id, user)
    observed = schedule_state(row)
    if row.status in {
        "RUNNING",
        "PUBLISHING",
        "PUBLISHED",
        "DRAFT_CREATED",
        "PUBLISH_SUBMITTED",
        "MANUAL_PUBLISHED",
    }:
        raise AppException(40903, "已发布任务不能取消", 409)
    _change_schedule(db, row, observed, {"status": "CANCELLED"})
    cancel_dispatch(db, task_type=TASK_TYPE_SCHEDULE, task_id=str(row.id))
    record_audit(db, request, user, "CANCEL", "PUBLISH", "SCHEDULE", row.id)
    db.commit()
    remove_schedule_job(row.id)
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
    cancel_dispatch(db, task_type=TASK_TYPE_SCHEDULE, task_id=str(row.id))
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
    if not row or row.status not in RECOVERABLE_FAILURE_STATUSES:
        raise AppException(40904, "只有失败或需要重新登录处理的任务可以重试", 409)
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
    row = _schedule_for_change(db, schedule_id, user)
    observed = schedule_state(row)
    if row.status != "WAITING_MANUAL_CONFIRM":
        raise AppException(40906, "当前任务不在等待人工确认状态", 409)
    if row.platform == "XIAOHONGSHU" and not payload.published_url:
        raise AppException(40078, "请填写小红书真实发布链接")
    _change_schedule(
        db,
        row,
        observed,
        {
            "status": "MANUAL_PUBLISHED",
            "result_mode": "MANUAL_CONFIRM",
            "actual_publish_at": business_now(),
            "published_url": str(payload.published_url) if payload.published_url else None,
        },
    )
    cancel_dispatch(db, task_type=TASK_TYPE_SCHEDULE, task_id=str(row.id))
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
async def download_publish_package(
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
    images = package.get("images", [])
    if not isinstance(images, list) or len(images) > 30:
        raise AppException(40080, "发布包最多支持 30 张图片")
    stream = io.BytesIO()
    total_bytes = 0
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        text = f"{package.get('title', '')}\n\n{package.get('content', '')}\n\n"
        text += " ".join(package.get("hashtags", []))
        archive.writestr("发布文案.txt", text)
        archive.writestr("发布说明.json", json.dumps(package, ensure_ascii=False, indent=2))
        for index, image_url in enumerate(images, start=1):
            try:
                path = _package_image_path(str(image_url))
                if path:
                    if path.stat().st_size > 12 * 1024 * 1024:
                        raise ValueError("图片超过 12MB")
                    content = path.read_bytes()
                    suffix = image_content_suffix(content)
                else:
                    suffix, content = await _download_generated_image(str(image_url))
                total_bytes += len(content)
                if total_bytes > 60 * 1024 * 1024:
                    raise ValueError("图片总大小超过 60MB")
                archive.writestr(f"images/{index:02d}{suffix}", content)
            except (AppException, ValueError, OSError) as exc:
                raise AppException(
                    50223, f"第 {index} 张图片无法完整打包，请检查图片后重试；未生成缺图发布包", 502
                ) from exc
    stream.seek(0)
    return StreamingResponse(
        stream,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="xiaohongshu-{schedule_id}.zip"'},
    )


def _package_image_path(value: str) -> Path | None:
    return local_media_path(value)
