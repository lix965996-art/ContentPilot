import asyncio
import time
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.models.business import (
    ContentVariant,
    MediaAsset,
    PlatformAccount,
    PublishLog,
    PublishSchedule,
)
from app.publishers.base import PlatformPublisher, PublishResult
from app.publishers.mock import ManualConfirmPublisher, MockPublisher
from app.publishers.official import (
    WechatDraftPublisher,
    WechatPublishPublisher,
    WeiboPublisher,
    XiaohongshuManualPublisher,
)
from app.services.platform_account_service import effective_status

FINAL_STATUSES = {
    "SUCCESS",
    "MOCK_SUCCESS",
    "MOCK_DRAFT_CREATED",
    "DRAFT_CREATED",
    "PUBLISH_SUBMITTED",
    "MANUAL_PUBLISHED",
    "CANCELLED",
}


def resolve_publisher(
    db: Session, schedule: PublishSchedule, account: PlatformAccount
) -> PlatformPublisher:
    mode = schedule.publish_mode
    if mode == "MOCK":
        if schedule.platform == "WECHAT_OFFICIAL":
            return WechatDraftPublisher(db, account)
        return MockPublisher(schedule.platform)
    if mode == "MANUAL_CONFIRM":
        if schedule.platform == "XIAOHONGSHU":
            return XiaohongshuManualPublisher(account)
        return ManualConfirmPublisher(schedule.platform)
    if mode == "DRAFT_ONLY" and schedule.platform == "WECHAT_OFFICIAL":
        return WechatDraftPublisher(db, account)
    if mode == "REAL_API" and schedule.platform == "WEIBO":
        return WeiboPublisher(db, account)
    if mode == "REAL_API" and schedule.platform == "WECHAT_OFFICIAL":
        return WechatPublishPublisher(db, account)
    raise AppException(40071, "当前平台不支持所选发布方式")


def validate_schedule_account(schedule: PublishSchedule, account: PlatformAccount | None) -> None:
    if not account:
        raise AppException(40072, "排期任务必须选择平台账号")
    if account.platform != schedule.platform:
        raise AppException(40073, "平台账号与目标平台不匹配")
    if account.user_id != schedule.created_by:
        raise AppException(40303, "无权使用该平台账号", 403)
    if schedule.publish_mode in {"REAL_API", "DRAFT_ONLY"}:
        allowed_account_modes = (
            {"REAL_API"}
            if schedule.platform == "WEIBO" and schedule.publish_mode == "REAL_API"
            else {"SUBMIT_PUBLISH"}
            if schedule.publish_mode == "REAL_API"
            else {"DRAFT_ONLY", "SUBMIT_PUBLISH"}
        )
        if account.publish_mode not in allowed_account_modes:
            raise AppException(40075, "账号配置未启用所选真实发布方式")
        status = effective_status(account)
        if status == "TOKEN_EXPIRED":
            raise AppException(40074, "平台 Token 已过期，请重新授权")
        if status != "CONNECTED":
            raise AppException(40075, "平台账号未连接或连接无效")
        capabilities = set(account.capabilities_json or [])
        required = (
            "DRAFT_CREATE"
            if schedule.publish_mode == "DRAFT_ONLY"
            else ("TEXT_PUBLISH" if schedule.platform == "WEIBO" else "SUBMIT_PUBLISH")
        )
        if required not in capabilities:
            raise AppException(40076, f"平台账号缺少发布能力：{required}")
    if schedule.platform == "XIAOHONGSHU" and schedule.publish_mode == "REAL_API":
        raise AppException(40077, "小红书未启用非官方自动发布，仅支持人工确认")


async def execute_publish(db: Session, schedule_id: int) -> PublishSchedule:
    schedule = db.scalar(
        select(PublishSchedule).where(PublishSchedule.id == schedule_id).with_for_update()
    )
    if not schedule:
        raise AppException(40407, "排期任务不存在", 404)
    if schedule.status in FINAL_STATUSES:
        return schedule
    if schedule.status == "RUNNING":
        raise AppException(40901, "该任务正在执行，请勿重复发布", 409)
    variant = db.get(ContentVariant, schedule.variant_id)
    if not variant:
        raise AppException(40402, "内容版本不存在", 404)
    account = db.get(PlatformAccount, schedule.account_id) if schedule.account_id else None
    validate_schedule_account(schedule, account)
    assert account is not None
    publisher = resolve_publisher(db, schedule, account)
    schedule.status = "RUNNING"
    db.commit()
    started = time.perf_counter()
    try:
        assets = db.scalars(
            select(MediaAsset)
            .where(MediaAsset.article_id == schedule.article_id, MediaAsset.selected.is_(True))
            .order_by(MediaAsset.usage_type, MediaAsset.id)
        ).all()
        result = await publisher.publish(
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
                "dry_run": schedule.publish_mode == "MOCK",
            }
        )
        _apply_result(schedule, result)
        db.add(
            PublishLog(
                schedule_id=schedule.id,
                step="PUBLISH",
                request_summary=(
                    f"{schedule.platform} / variant {variant.id} / {schedule.publish_mode}"
                ),
                response_summary=_safe_result_summary(result),
                status=result.status,
                error_code=result.error_code or None,
                error_message=result.error_message[:2000] or None,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        )
    except AppException:
        schedule.status = "FAILED"
        db.commit()
        raise
    except Exception as exc:
        schedule.retry_count += 1
        schedule.status = "FAILED"
        schedule.error_message = str(exc)[:2000]
        db.add(
            PublishLog(
                schedule_id=schedule.id,
                step="PUBLISH",
                status="FAILED",
                error_code="PUBLISH_ERROR",
                error_message=str(exc)[:2000],
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        )
    db.commit()
    db.refresh(schedule)
    return schedule


def _apply_result(schedule: PublishSchedule, result: PublishResult) -> None:
    schedule.status = result.status
    schedule.published_url = result.published_url or None
    schedule.external_id = result.external_id or None
    schedule.result_mode = result.mode
    schedule.publish_package_json = result.detail.get("publishPackage", {})
    schedule.actual_publish_at = (
        datetime.now() if result.status in {"SUCCESS", "MANUAL_PUBLISHED"} else None
    )
    schedule.error_message = result.error_message or None
    if not result.success and result.status == "FAILED":
        schedule.retry_count += 1


def _safe_result_summary(result: PublishResult) -> str:
    label = {
        "MOCK_SUCCESS": "模拟发布完成（SIMULATED）",
        "MOCK_DRAFT_CREATED": "模拟草稿已创建（SIMULATED）",
        "DRAFT_CREATED": "已进入微信公众号草稿箱，尚未公开发布",
        "PUBLISH_SUBMITTED": "已提交微信公众号发布，等待平台处理",
        "WAITING_MANUAL_CONFIRM": "等待运营人员人工发布并确认",
        "SUCCESS": "真实平台发布成功",
    }.get(result.status, result.error_message or result.status)
    return f"{label}; mode={result.mode}; external_id={result.external_id or '-'}"


def execute_publish_sync(schedule_id: int) -> None:
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        try:
            schedule = asyncio.run(execute_publish(db, schedule_id))
        except AppException as exc:
            schedule = db.get(PublishSchedule, schedule_id)
            if schedule:
                schedule.status = "FAILED"
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
        if (
            schedule
            and schedule.status == "FAILED"
            and schedule.retry_count <= schedule.max_retry_count
        ):
            from app.scheduler.runtime import add_schedule_job

            delays = (1, 5, 15)
            delay = delays[min(max(schedule.retry_count - 1, 0), len(delays) - 1)]
            add_schedule_job(schedule.id, datetime.now() + timedelta(minutes=delay))
