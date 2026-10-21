import asyncio
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import case, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.credentials import decrypt_json
from app.core.exceptions import AppException
from app.models.business import (
    ContentVariant,
    MediaAsset,
    PlatformAccount,
    PublishLog,
    PublishSchedule,
)
from app.publishers.base import PlatformPublisher, PublishResult
from app.publishers.bluesky import BlueskyPublisher, new_bluesky_record_key
from app.publishers.mastodon import ATTEMPT_FIELD, MastodonPublisher
from app.publishers.official import (
    WechatDraftPublisher,
    WechatPublishPublisher,
    WeiboPublisher,
    XiaohongshuManualPublisher,
)
from app.publishers.toutiao_browser import ToutiaoBrowserPublisher
from app.publishers.wechat_browser import WechatBrowserDraftPublisher
from app.publishers.wechatsync_cli import WechatsyncPublisher
from app.publishers.x_official import XPublisher
from app.publishers.xhs_mcp import XiaohongshuMCPPublisher
from app.services.activity_service import business_now
from app.services.platform_account_service import effective_status
from app.services.platform_content import normalize_image_alt_texts, validate_platform_publish
from app.services.review_fingerprint import require_current_approval
from app.services.thread_publishing import filter_thread_assets, prepare_thread_publish

FINAL_STATUSES: set[str] = {
    "PUBLISHED",
    "DRAFT_CREATED",
    "PUBLISH_SUBMITTED",
    "CANCELLED",
    "MANUAL_PUBLISHED",
    "WAITING_MANUAL_CONFIRM",
    "SUCCESS",  # Legacy records already completed publishing.
    # NOTE: "FAILED" is intentionally excluded — failed schedules are retryable.
}

# Persisted on the schedule so the retry loop can honour PublishResult.retryable
# after the publisher object is gone. Absent means "not automatically retryable".
LAST_FAILURE_RETRYABLE_FIELD = "lastFailureRetryable"
SCHEDULE_REVISION_FIELD = "scheduleRevision"


@dataclass(frozen=True)
class ScheduleState:
    status: str
    retry_count: int
    scheduled_at: datetime
    revision: str | None


@dataclass(frozen=True)
class ScheduleJob:
    state: ScheduleState
    run_at: datetime


def schedule_state(schedule: PublishSchedule) -> ScheduleState:
    return ScheduleState(
        schedule.status,
        schedule.retry_count,
        schedule.scheduled_at,
        (schedule.publish_package_json or {}).get(SCHEDULE_REVISION_FIELD),
    )


def schedule_state_conditions(state: ScheduleState) -> tuple:
    revision = PublishSchedule.publish_package_json[SCHEDULE_REVISION_FIELD].as_string()
    return (
        PublishSchedule.status == state.status,
        PublishSchedule.retry_count == state.retry_count,
        PublishSchedule.scheduled_at == state.scheduled_at,
        revision.is_(None) if state.revision is None else revision == state.revision,
    )


CDP_FALLBACK_WECHAT_CODES = {"48001", "api unauthorized", "43004"}
TEXT_REAL_API_PLATFORMS = frozenset({"WEIBO", "X", "BLUESKY", "MASTODON"})

_wechatsync: WechatsyncPublisher | None = None
_xhs_mcp: XiaohongshuMCPPublisher | None = None


def x_public_publish_enabled(account: PlatformAccount | None) -> bool:
    return bool(
        account
        and account.platform == "X"
        and decrypt_json(account.credentials_encrypted).get("allow_public_publish") is True
    )


def bluesky_public_publish_enabled(account: PlatformAccount | None) -> bool:
    return bool(
        account
        and account.platform == "BLUESKY"
        and decrypt_json(account.credentials_encrypted).get("allow_public_publish") is True
    )


def mastodon_public_publish_enabled(account: PlatformAccount | None) -> bool:
    return bool(
        account
        and account.platform == "MASTODON"
        and decrypt_json(account.credentials_encrypted).get("allow_public_publish") is True
    )


def toutiao_public_publish_enabled(account: PlatformAccount | None) -> bool:
    return bool(
        account
        and account.platform == "TOUTIAO"
        and decrypt_json(account.credentials_encrypted).get("allow_public_publish") is True
    )


def _get_wechatsync() -> WechatsyncPublisher:
    global _wechatsync
    if _wechatsync is None:
        _wechatsync = WechatsyncPublisher()
    return _wechatsync


def _get_xhs_mcp() -> XiaohongshuMCPPublisher:
    global _xhs_mcp
    if _xhs_mcp is None:
        _xhs_mcp = XiaohongshuMCPPublisher()
    return _xhs_mcp


def resolve_publisher(
    db: Session, schedule: PublishSchedule, account: PlatformAccount
) -> PlatformPublisher:
    mode = schedule.publish_mode
    platform = schedule.platform

    if platform == "XIAOHONGSHU":
        if mode == "MANUAL_CONFIRM":
            return XiaohongshuManualPublisher(account)
        if mode != "MCP_PUBLISH":
            raise AppException(40077, "小红书仅支持本地 MCP 发布或人工确认")
        if not settings.experimental_browser_publishing_enabled:
            raise AppException(40078, "本地 MCP 发布默认关闭，请使用人工交付模式")
        return _get_xhs_mcp()  # type: ignore[return-value]

    if platform == "TOUTIAO":
        if mode not in {"BROWSER_PUBLISH", "BROWSER_DRAFT"}:
            raise AppException(40081, "今日头条仅支持本机浏览器发布或保存草稿")
        if not settings.toutiao_browser_publishing_enabled:
            raise AppException(40082, "今日头条本机浏览器发布功能已关闭")
        return ToutiaoBrowserPublisher(account.id, mode=mode)

    if platform == "WECHAT_OFFICIAL" and mode == "BROWSER_DRAFT":
        if not settings.wechat_browser_publishing_enabled:
            raise AppException(40084, "微信公众号本机扫码草稿功能已关闭")
        return WechatBrowserDraftPublisher(account.id)

    if mode in {"DRAFT_ONLY", "REAL_API"} and platform == "WECHAT_OFFICIAL":
        if mode == "REAL_API":
            return WechatPublishPublisher(db, account)
        return WechatDraftPublisher(db, account)

    if mode == "REAL_API" and platform in TEXT_REAL_API_PLATFORMS:
        if platform == "BLUESKY":
            return BlueskyPublisher(db, account)
        if platform == "MASTODON":
            return MastodonPublisher(db, account)
        return WeiboPublisher(db, account) if platform == "WEIBO" else XPublisher(db, account)

    raise AppException(40071, "当前平台不支持所选发布方式")


def _validate_public_publish_switches(schedule: PublishSchedule, account: PlatformAccount) -> None:
    if schedule.platform == "X" and not x_public_publish_enabled(account):
        raise AppException(40080, "X 公开发布安全开关未开启，请由管理员确认后启用")
    if schedule.platform == "BLUESKY" and not bluesky_public_publish_enabled(account):
        raise AppException(40085, "Bluesky 真实发布开关未开启，请在账号设置中启用")
    if schedule.platform == "MASTODON" and not mastodon_public_publish_enabled(account):
        raise AppException(40086, "Mastodon 真实发布开关未开启，请在账号设置中启用")


def _validate_toutiao_publish(schedule: PublishSchedule, account: PlatformAccount) -> None:
    if schedule.publish_mode not in {"BROWSER_PUBLISH", "BROWSER_DRAFT"}:
        raise AppException(40081, "今日头条仅支持本机浏览器发布或保存草稿")
    if not settings.toutiao_browser_publishing_enabled:
        raise AppException(40082, "今日头条本机浏览器发布功能已关闭")
    if account.publish_mode != "BROWSER_PUBLISH":
        raise AppException(40075, "今日头条账号未启用本机浏览器发布")
    if effective_status(account) != "CONNECTED":
        raise AppException(40075, "今日头条账号尚未扫码登录或登录已失效")
    if schedule.publish_mode == "BROWSER_PUBLISH" and not toutiao_public_publish_enabled(account):
        raise AppException(40083, "今日头条真实发布开关未开启，请由管理员确认后启用")


def _validate_xhs_publish(schedule: PublishSchedule, account: PlatformAccount) -> None:
    if schedule.publish_mode != "MCP_PUBLISH":
        raise AppException(40077, "小红书仅支持本地 MCP 发布或人工确认")
    if not settings.experimental_browser_publishing_enabled:
        raise AppException(40078, "本地 MCP 发布默认关闭，请使用人工交付模式")
    if account.publish_mode != "MCP_PUBLISH":
        raise AppException(40075, "小红书账号未启用本地 MCP 发布")
    if effective_status(account) != "CONNECTED":
        raise AppException(40075, "小红书本地 MCP 尚未登录或连接检测未通过")


def _validate_wechat_browser_publish(schedule: PublishSchedule, account: PlatformAccount) -> None:
    if not settings.wechat_browser_publishing_enabled:
        raise AppException(40084, "微信公众号本机扫码草稿功能已关闭")
    if account.publish_mode != "BROWSER_DRAFT" or account.auth_type != "QR_LOGIN":
        raise AppException(40075, "微信公众号账号未启用本机扫码草稿模式")
    if effective_status(account) != "CONNECTED":
        raise AppException(40075, "微信公众号后台尚未扫码登录或登录已失效")


def _validate_real_api_publish(schedule: PublishSchedule, account: PlatformAccount) -> None:
    if schedule.platform in TEXT_REAL_API_PLATFORMS and schedule.publish_mode == "REAL_API":
        allowed_account_modes = {"REAL_API"}
    elif schedule.publish_mode == "REAL_API":
        allowed_account_modes = {"SUBMIT_PUBLISH"}
    else:
        allowed_account_modes = {"DRAFT_ONLY", "SUBMIT_PUBLISH"}
    if account.publish_mode not in allowed_account_modes:
        raise AppException(40075, "账号配置未启用所选真实发布方式")
    status = effective_status(account)
    can_refresh = bool(
        schedule.platform in {"X", "BLUESKY"}
        and status == "TOKEN_EXPIRED"
        and account.refresh_token_encrypted
    )
    if status == "TOKEN_EXPIRED" and not can_refresh:
        raise AppException(40074, "平台 Token 已过期，请重新授权")
    if status != "CONNECTED" and not can_refresh:
        raise AppException(40075, "平台账号未连接或连接无效")
    capabilities = set(account.capabilities_json or [])
    if schedule.publish_mode == "DRAFT_ONLY":
        required = "DRAFT_CREATE"
    elif schedule.platform in TEXT_REAL_API_PLATFORMS:
        required = "TEXT_PUBLISH"
    else:
        required = "SUBMIT_PUBLISH"
    if required not in capabilities and not (
        schedule.platform == "WECHAT_OFFICIAL" and schedule.publish_mode == "DRAFT_ONLY"
    ):
        raise AppException(40076, f"平台账号缺少发布能力：{required}")


def validate_schedule_account(schedule: PublishSchedule, account: PlatformAccount | None) -> None:
    if schedule.platform == "XIAOHONGSHU" and schedule.publish_mode == "MANUAL_CONFIRM":
        return
    if not account:
        raise AppException(40072, "排期任务必须选择平台账号")
    if account.platform != schedule.platform:
        raise AppException(40073, "平台账号与目标平台不匹配")
    _validate_public_publish_switches(schedule, account)
    if schedule.platform == "TOUTIAO":
        _validate_toutiao_publish(schedule, account)
        return
    if schedule.platform == "XIAOHONGSHU":
        _validate_xhs_publish(schedule, account)
        return
    if schedule.platform == "WECHAT_OFFICIAL" and schedule.publish_mode == "BROWSER_DRAFT":
        _validate_wechat_browser_publish(schedule, account)
        return
    if schedule.publish_mode in {"REAL_API", "DRAFT_ONLY"}:
        _validate_real_api_publish(schedule, account)


async def _publish_wechat_api(
    db: Session,
    schedule: PublishSchedule,
    account: PlatformAccount,
    variant: ContentVariant,
    assets: list[MediaAsset],
) -> PublishResult:
    publisher = (
        WechatPublishPublisher(db, account)
        if schedule.publish_mode == "REAL_API"
        else WechatDraftPublisher(db, account)
    )
    return await publisher.publish(
        {
            "schedule_id": schedule.id,
            "platform": schedule.platform,
            "title": variant.title,
            "content": variant.content_text,
            "content_html": variant.content_html,
            "summary": variant.content_text[:120],
            "hashtags": variant.hashtags_json or [],
            "images": [asset.image_url for asset in assets],
            "idempotency_key": schedule.idempotency_key,
        }
    )


async def _publish_wechat_cli(variant: ContentVariant) -> PublishResult:
    pub = _get_wechatsync()
    logged, info = await pub.check_login()
    if not logged:
        return PublishResult(
            False,
            "WECHAT_OFFICIAL",
            "WECHATSYNC_CLI",
            "LOGIN_REQUIRED",
            error_code="LOGIN_REQUIRED",
            error_message=f"wechatsync 未登录微信: {info}",
            suggested_action="安装 Wechatsync Chrome 扩展并登录 mp.weixin.qq.com 后重试。",
        )
    return await pub.publish(
        title=variant.title,
        content_md=variant.content_text,
        author="",
        summary=variant.content_text[:120] if variant.content_text else "",
    )


async def _publish_xiaohongshu(
    variant: ContentVariant, assets: Sequence[MediaAsset]
) -> PublishResult:
    pub = _get_xhs_mcp()
    logged, info = await pub.check_login()
    if not logged:
        return PublishResult(
            False,
            "XIAOHONGSHU",
            "MCP_PUBLISH",
            "LOGIN_REQUIRED",
            error_code="LOGIN_REQUIRED",
            error_message=f"xiaohongshu-mcp 未登录: {info}",
            suggested_action="启动 xiaohongshu-mcp 并完成扫码登录。",
        )
    images = [a.image_url for a in assets if a.usage_type in ("COVER", "BODY")]
    return await pub.publish(
        title=variant.title,
        content=variant.content_text,
        images=images,
        tags=variant.hashtags_json or [],
        visibility="only_self",
    )


def _validate_content_approval(
    db: Session, schedule: PublishSchedule, variant: ContentVariant
) -> None:
    # Working drafts are not public posts. Public API routes, including
    # Bluesky and Mastodon, always retain the current-approval check.
    if schedule.platform in {"WECHAT_OFFICIAL", "TOUTIAO"} and schedule.publish_mode in {
        "BROWSER_DRAFT",
        "DRAFT_ONLY",
    }:
        return
    require_current_approval(variant, db=db)


def _frozen_social_images(
    db: Session, schedule: PublishSchedule, assets: Sequence[MediaAsset]
) -> tuple[list[str], list[str]]:
    """Bind descriptions and image order before uploads, including safe retries."""
    package = dict(schedule.publish_package_json or {})
    snapshot = package.get("imageDescriptions")
    if snapshot is None:
        snapshot = [{"url": item.image_url, "alt": item.alt_text or ""} for item in assets]
    if not isinstance(snapshot, list) or any(
        not isinstance(item, dict) or not isinstance(item.get("url"), str) for item in snapshot
    ):
        raise AppException(40079, "已保存的发布配图信息无效，请重新排期")
    image_urls = [item["url"] for item in snapshot]
    try:
        alt_texts = normalize_image_alt_texts([item.get("alt") for item in snapshot], len(snapshot))
    except ValueError as exc:
        raise AppException(40079, str(exc)) from exc
    if "imageDescriptions" not in package:
        package["imageDescriptions"] = [
            {"url": url, "alt": alt} for url, alt in zip(image_urls, alt_texts, strict=True)
        ]
        schedule.publish_package_json = package
        db.commit()
    return image_urls, alt_texts


def _images_for_publish(
    db: Session, schedule: PublishSchedule, assets: Sequence[MediaAsset]
) -> tuple[list[str], list[str] | None]:
    if schedule.platform not in {"BLUESKY", "MASTODON"} or schedule.publish_mode != "REAL_API":
        return [asset.image_url for asset in assets], None
    try:
        return _frozen_social_images(db, schedule, assets)
    except AppException as exc:
        _record_precheck_failure(db, schedule, exc)
        raise


async def execute_publish(
    db: Session, schedule_id: int, *, expected_state: ScheduleState | None = None
) -> PublishSchedule:
    schedule = db.scalar(
        select(PublishSchedule)
        .where(PublishSchedule.id == schedule_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not schedule:
        raise AppException(40407, "排期任务不存在", 404)
    observed_state = schedule_state(schedule)
    if expected_state is not None and observed_state != expected_state:
        raise AppException(40901, "定时任务对应的排期已变更，已跳过旧作业", 409)
    if schedule.status in FINAL_STATUSES:
        return schedule
    if schedule.status in ("PUBLISHING", "RUNNING"):
        raise AppException(40901, "该任务正在执行，请勿重复发布", 409)
    if schedule.status in {"EXPIRED", "INTERRUPTED"}:
        raise AppException(40903, "任务已错过或中断，请先确认平台结果并重新排期", 409)

    # FOR UPDATE row locks are unavailable on SQLite. Claim the exact
    # observed attempt atomically as well, so two workers cannot both publish.
    # retry_count guards against FAILED -> PUBLISHING -> FAILED returning to
    # the same status while another worker is still holding an older snapshot.
    publish_context = dict(schedule.publish_package_json or {})
    publish_context[LAST_FAILURE_RETRYABLE_FIELD] = False
    if schedule.platform == "BLUESKY":
        if not publish_context.get("blueskyRkey"):
            publish_context["blueskyRkey"] = new_bluesky_record_key(schedule.idempotency_key)
    claim = db.execute(
        update(PublishSchedule)
        .where(
            PublishSchedule.id == schedule.id,
            *schedule_state_conditions(observed_state),
        )
        .values(status="PUBLISHING", publish_package_json=publish_context)
        .execution_options(synchronize_session=False)
    )
    if claim.rowcount != 1:
        db.rollback()
        db.refresh(schedule)
        if expected_state is not None:
            raise AppException(40901, "定时任务对应的排期已变更，已跳过旧作业", 409)
        if schedule.status in FINAL_STATUSES:
            return schedule
        if schedule.status in {"EXPIRED", "INTERRUPTED"}:
            raise AppException(40903, "任务已错过或中断，请先确认平台结果并重新排期", 409)
        raise AppException(40901, "该任务已被其他执行器处理，请刷新后核对结果", 409)
    db.commit()
    db.refresh(schedule)
    # Preconditions may record a failure, so they must also run only after the
    # worker owns the claim rather than overwrite a different worker's state.
    variant = db.get(ContentVariant, schedule.variant_id, populate_existing=True)
    if not variant:
        exc = AppException(40402, "内容版本不存在", 404)
        _record_precheck_failure(db, schedule, exc)
        raise exc
    account = (
        db.get(PlatformAccount, schedule.account_id, populate_existing=True)
        if schedule.account_id
        else None
    )
    try:
        _validate_content_approval(db, schedule, variant)
        validate_schedule_account(schedule, account)
        thread_context, thread_reply = prepare_thread_publish(db, schedule)
    except AppException as exc:
        _record_precheck_failure(db, schedule, exc)
        raise

    started = time.perf_counter()
    assets = db.scalars(
        select(MediaAsset)
        .where(MediaAsset.article_id == schedule.article_id, MediaAsset.selected.is_(True))
        .order_by(
            case((MediaAsset.usage_type == "COVER", 0), else_=1),
            MediaAsset.id,
        )
    ).all()
    assets = filter_thread_assets(thread_context, assets)
    image_urls, image_alt_texts = _images_for_publish(db, schedule, assets)

    from app.services.engagement_collection_service import (
        capture_publication,
        content_features,
        freeze_attempt_features,
    )

    sent_features = freeze_attempt_features(
        db, schedule, content_features(variant, len(image_urls), schedule, account)
    )

    result: PublishResult | None = None
    log_step = "PUBLISH"

    try:
        validation_errors = validate_platform_publish(
            platform=schedule.platform,
            title=variant.title,
            content=variant.content_text,
            hashtags=variant.hashtags_json or [],
            images=image_urls,
        )
        if validation_errors:
            raise AppException(40079, "；".join(validation_errors))
        if schedule.platform == "XIAOHONGSHU":
            if schedule.publish_mode == "MANUAL_CONFIRM":
                publisher = XiaohongshuManualPublisher(account)
                result = await publisher.publish(
                    {
                        "schedule_id": schedule.id,
                        "platform": schedule.platform,
                        "title": variant.title,
                        "content": variant.content_text,
                        "hashtags": variant.hashtags_json or [],
                        "images": image_urls,
                        "idempotency_key": schedule.idempotency_key,
                    }
                )
                log_step = "PREPARE_XHS_MANUAL_PACKAGE"
            else:
                if not settings.experimental_browser_publishing_enabled:
                    raise AppException(40078, "本地 MCP 发布默认关闭，请使用人工交付模式")
                result = await _publish_xiaohongshu(variant, assets)
                log_step = "PUBLISH_XHS_MCP"
        elif schedule.platform == "WECHAT_OFFICIAL" and schedule.publish_mode in (
            "DRAFT_ONLY",
            "REAL_API",
        ):
            try:
                result = await _publish_wechat_api(db, schedule, account, variant, assets)  # type: ignore[arg-type]
            except Exception as exc:
                result = PublishResult(
                    False,
                    schedule.platform,
                    schedule.publish_mode,
                    "FAILED",
                    error_code="WECHAT_API_ERROR",
                    error_message=(str(exc) or type(exc).__name__)[:1000],
                    suggested_action="检查公众号 API 配置，或改用本机草稿模式。",
                )
            wechat_attempt = (schedule.publish_package_json or {}).get("wechatPublish") or {}
            should_use_browser_fallback = (
                settings.wechatsync_cli_enabled
                and result is not None
                and not result.success
                and not wechat_attempt.get("draftId")
                and wechat_attempt.get("stage") in {None, "DRAFT_REJECTED"}
                and result.error_code in CDP_FALLBACK_WECHAT_CODES
            )
            if should_use_browser_fallback:
                result = await _publish_wechat_cli(variant)
                if result is not None and not result.success:
                    # CLI sync has no stable draft ID or idempotency key. A
                    # timeout can happen after the extension created a draft.
                    result.retryable = False
                    result.suggested_action = (
                        "请先核对公众号后台草稿箱，确认没有生成草稿后再手动处理；不会自动重试。"
                    )
                log_step = "PUBLISH_WECHAT_CLI"
        else:
            assert account is not None
            publisher = resolve_publisher(db, schedule, account)
            result = await publisher.publish(
                {
                    "schedule_id": schedule.id,
                    "platform": schedule.platform,
                    "title": variant.title,
                    "content": variant.content_text,
                    "content_html": variant.content_html,
                    "summary": variant.content_text[:120],
                    "hashtags": variant.hashtags_json or [],
                    "images": image_urls,
                    "image_alt_texts": image_alt_texts,
                    "thread_reply": thread_reply,
                    "operation_ip": (schedule.publish_package_json or {}).get("operationIp"),
                    "idempotency_key": schedule.idempotency_key,
                    "record_key": (schedule.publish_package_json or {}).get("blueskyRkey"),
                }
            )

        if result:
            _apply_result(schedule, result)
            capture_publication(db, schedule, sent_features)
        else:
            _clear_retryable_failure(schedule)
            schedule.status = "FAILED"
            schedule.error_message = "发布器未返回结果"
            schedule.retry_count += 1

        db.add(
            PublishLog(
                schedule_id=schedule.id,
                step=log_step,
                request_summary=(
                    f"{schedule.platform} / variant {variant.id} / {schedule.publish_mode}"
                ),
                response_summary=_safe_result_summary(result) if result else "无结果",
                status=result.status if result else "FAILED",
                error_code=result.error_code or None if result else None,
                error_message=(result.error_message or "")[:2000] if result else None,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        )
    except AppException as exc:
        _record_precheck_failure(db, schedule, exc)
        raise
    except Exception as exc:
        _clear_retryable_failure(schedule)
        schedule.retry_count += 1
        schedule.status = "FAILED"
        schedule.error_message = str(exc)[:2000]
        db.add(
            PublishLog(
                schedule_id=schedule.id,
                step=log_step,
                status="FAILED",
                error_code="PUBLISH_ERROR",
                error_message=str(exc)[:2000],
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        )

    db.commit()
    db.refresh(schedule)
    return schedule


def _clear_retryable_failure(schedule: PublishSchedule) -> None:
    package = dict(schedule.publish_package_json or {})
    package[LAST_FAILURE_RETRYABLE_FIELD] = False
    schedule.publish_package_json = package


def _record_precheck_failure(db: Session, schedule: PublishSchedule, exc: AppException) -> None:
    _clear_retryable_failure(schedule)
    schedule.status = "FAILED"
    schedule.retry_count += 1
    schedule.error_message = exc.message
    db.add(
        PublishLog(
            schedule_id=schedule.id,
            step="PRECHECK",
            status="FAILED",
            error_code=str(exc.code),
            error_message=exc.message,
        )
    )
    db.commit()


def _apply_result(schedule: PublishSchedule, result: PublishResult) -> None:
    schedule.status = result.status
    schedule.published_url = result.published_url or None
    schedule.external_id = result.external_id or None
    schedule.result_mode = result.mode or schedule.publish_mode
    existing_package = dict(schedule.publish_package_json or {})
    publish_package = dict(existing_package)
    publish_package.update((result.detail or {}).get("publishPackage", {}))
    if schedule.platform == "BLUESKY":
        record_key = existing_package.get("blueskyRkey")
        if record_key:
            publish_package["blueskyRkey"] = record_key
    if schedule.platform == "MASTODON":
        attempt = existing_package.get(ATTEMPT_FIELD)
        if attempt:
            publish_package[ATTEMPT_FIELD] = attempt
    if result.success:
        publish_package.pop(LAST_FAILURE_RETRYABLE_FIELD, None)
    else:
        publish_package[LAST_FAILURE_RETRYABLE_FIELD] = bool(result.retryable)
    schedule.publish_package_json = publish_package
    if result.status in ("PUBLISHED", "DRAFT_CREATED", "PUBLISH_SUBMITTED"):
        schedule.actual_publish_at = business_now()
        if result.status == "PUBLISHED" and schedule.platform in {"BLUESKY", "MASTODON"}:
            from app.publishers.metrics import parse_utc
            from app.services.engagement_collection_service import utc_to_business

            platform_time = parse_utc((result.detail or {}).get("publishedAtUTC"))
            if platform_time:
                schedule.actual_publish_at = utc_to_business(platform_time)
    elif not result.success:
        schedule.retry_count += 1
    schedule.error_message = result.error_message or None


def _safe_result_summary(result: PublishResult | None) -> str:
    if result is None:
        return "无结果"
    labels: dict[str, str] = {
        "PUBLISHED": "已公开发布",
        "DRAFT_CREATED": "已保存到草稿箱",
        "PUBLISH_SUBMITTED": "已提交发布",
        "LOGIN_REQUIRED": "需要登录",
        "NEED_USER_ACTION": "需要人工处理",
        "FAILED": result.error_message or "发布失败",
    }
    label = labels.get(result.status, result.error_message or result.status)
    return f"{label}; mode={result.mode}; external_id={result.external_id or '-'}"


def _should_retry(schedule: PublishSchedule | None) -> bool:
    """Only publishers that explicitly marked the failure retryable are retried.

    X/Weibo/WeChat/Toutiao have no publisher-side idempotency key, so retrying
    an uncertain failure can create a duplicate public post.
    """
    if schedule is None or schedule.status != "FAILED":
        return False
    package = schedule.publish_package_json or {}
    return bool(package.get(LAST_FAILURE_RETRYABLE_FIELD)) and (
        schedule.retry_count <= schedule.max_retry_count
    )


def execute_publish_sync(schedule_id: int, expected_job: ScheduleJob | None = None) -> None:
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        if expected_job is not None and business_now() < expected_job.run_at:
            return
        try:
            schedule = asyncio.run(
                execute_publish(
                    db,
                    schedule_id,
                    expected_state=expected_job.state if expected_job else None,
                )
            )
        except AppException:
            # Preconditions need operator action; repeated timers cannot repair
            # an expired login, disabled mode, invalid content, or stale state.
            return
        if _should_retry(schedule):
            from app.scheduler.runtime import add_schedule_job
            from app.services.task_dispatch_service import TASK_TYPE_SCHEDULE, upsert_dispatch

            delays = (1, 5, 15)
            delay = delays[min(max(schedule.retry_count - 1, 0), len(delays) - 1)]
            retry_at = business_now() + timedelta(minutes=delay)
            state = schedule_state(schedule)
            upsert_dispatch(
                db,
                task_type=TASK_TYPE_SCHEDULE,
                task_id=str(schedule.id),
                revision=str(state.revision or ""),
                run_at=retry_at,
            )
            db.commit()
            add_schedule_job(schedule.id, retry_at, state)
