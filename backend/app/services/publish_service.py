import asyncio
import time
from datetime import datetime, timedelta

from sqlalchemy import case, select
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
from app.publishers.official import (
    WechatDraftPublisher,
    WechatPublishPublisher,
    WeiboPublisher,
    XiaohongshuManualPublisher,
)
from app.publishers.wechatsync_cli import WechatsyncPublisher
from app.publishers.x_official import XPublisher
from app.publishers.xhs_mcp import XiaohongshuMCPPublisher
from app.services.platform_account_service import effective_status
from app.services.platform_content import validate_platform_publish

FINAL_STATUSES: set[str] = {
    "PUBLISHED",
    "DRAFT_CREATED",
    "PUBLISH_SUBMITTED",
    "CANCELLED",
    "FAILED",
}

CDP_FALLBACK_WECHAT_CODES = {"48001", "api unauthorized", "43004"}
TEXT_REAL_API_PLATFORMS = frozenset({"WEIBO", "X"})

_wechatsync: WechatsyncPublisher | None = None
_xhs_mcp: XiaohongshuMCPPublisher | None = None


def x_public_publish_enabled(account: PlatformAccount | None) -> bool:
    return bool(
        account
        and account.platform == "X"
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

    if mode in {"DRAFT_ONLY", "REAL_API"} and platform == "WECHAT_OFFICIAL":
        if mode == "REAL_API":
            return WechatPublishPublisher(db, account)
        return WechatDraftPublisher(db, account)

    if mode == "REAL_API" and platform in TEXT_REAL_API_PLATFORMS:
        return WeiboPublisher(db, account) if platform == "WEIBO" else XPublisher(db, account)

    raise AppException(40071, "当前平台不支持所选发布方式")


def validate_schedule_account(schedule: PublishSchedule, account: PlatformAccount | None) -> None:
    if schedule.platform == "XIAOHONGSHU" and schedule.publish_mode == "MANUAL_CONFIRM":
        return
    if not account:
        raise AppException(40072, "排期任务必须选择平台账号")
    if account.platform != schedule.platform:
        raise AppException(40073, "平台账号与目标平台不匹配")
    if schedule.platform == "X" and not x_public_publish_enabled(account):
        raise AppException(40080, "X 公开发布安全开关未开启，请由管理员确认后启用")

    if schedule.platform == "XIAOHONGSHU":
        if schedule.publish_mode != "MCP_PUBLISH":
            raise AppException(40077, "小红书仅支持本地 MCP 发布或人工确认")
        if not settings.experimental_browser_publishing_enabled:
            raise AppException(40078, "本地 MCP 发布默认关闭，请使用人工交付模式")
        if account.publish_mode != "MCP_PUBLISH":
            raise AppException(40075, "小红书账号未启用本地 MCP 发布")
        if effective_status(account) != "CONNECTED":
            raise AppException(40075, "小红书本地 MCP 尚未登录或连接检测未通过")
        return

    if schedule.publish_mode in {"REAL_API", "DRAFT_ONLY"}:
        allowed_account_modes = (
            {"REAL_API"}
            if schedule.platform in TEXT_REAL_API_PLATFORMS and schedule.publish_mode == "REAL_API"
            else {"SUBMIT_PUBLISH"}
            if schedule.publish_mode == "REAL_API"
            else {"DRAFT_ONLY", "SUBMIT_PUBLISH"}
        )
        if account.publish_mode not in allowed_account_modes:
            raise AppException(40075, "账号配置未启用所选真实发布方式")
        status = effective_status(account)
        x_can_refresh = bool(
            schedule.platform == "X"
            and status == "TOKEN_EXPIRED"
            and account.refresh_token_encrypted
        )
        if status == "TOKEN_EXPIRED" and not x_can_refresh:
            raise AppException(40074, "平台 Token 已过期，请重新授权")
        if status != "CONNECTED" and not x_can_refresh:
            raise AppException(40075, "平台账号未连接或连接无效")
        capabilities = set(account.capabilities_json or [])
        required = (
            "DRAFT_CREATE"
            if schedule.publish_mode == "DRAFT_ONLY"
            else (
                "TEXT_PUBLISH" if schedule.platform in TEXT_REAL_API_PLATFORMS else "SUBMIT_PUBLISH"
            )
        )
        if required not in capabilities and not (
            schedule.platform == "WECHAT_OFFICIAL" and schedule.publish_mode == "DRAFT_ONLY"
        ):
            raise AppException(40076, f"平台账号缺少发布能力：{required}")


async def _publish_wechat_api(
    db: Session,
    schedule: PublishSchedule,
    account: PlatformAccount,
    variant: ContentVariant,
    assets: list[MediaAsset],
) -> PublishResult:
    publisher = WechatDraftPublisher(db, account)
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


async def _publish_xiaohongshu(variant: ContentVariant, assets: list[MediaAsset]) -> PublishResult:
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


async def execute_publish(db: Session, schedule_id: int) -> PublishSchedule:
    schedule = db.scalar(
        select(PublishSchedule).where(PublishSchedule.id == schedule_id).with_for_update()
    )
    if not schedule:
        raise AppException(40407, "排期任务不存在", 404)
    if schedule.status in FINAL_STATUSES:
        return schedule
    if schedule.status in ("PUBLISHING", "RUNNING"):
        raise AppException(40901, "该任务正在执行，请勿重复发布", 409)

    variant = db.get(ContentVariant, schedule.variant_id)
    if not variant:
        raise AppException(40402, "内容版本不存在", 404)
    account = db.get(PlatformAccount, schedule.account_id) if schedule.account_id else None

    validate_schedule_account(schedule, account)

    schedule.status = "PUBLISHING"
    db.commit()
    started = time.perf_counter()
    assets = db.scalars(
        select(MediaAsset)
        .where(MediaAsset.article_id == schedule.article_id, MediaAsset.selected.is_(True))
        .order_by(
            case((MediaAsset.usage_type == "COVER", 0), else_=1),
            MediaAsset.id,
        )
    ).all()
    image_urls = [asset.image_url for asset in assets]

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
            except Exception:
                result = None
            should_use_browser_fallback = settings.wechatsync_cli_enabled and (
                result is None
                or (
                    not result.success
                    and (
                        result.error_code in CDP_FALLBACK_WECHAT_CODES
                        or (
                            result.error_message
                            and any(
                                code in result.error_message.lower()
                                for code in ("48001", "api unauthorized")
                            )
                        )
                    )
                )
            )
            if should_use_browser_fallback:
                result = await _publish_wechat_cli(variant)
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
                    "operation_ip": (schedule.publish_package_json or {}).get("operationIp"),
                    "idempotency_key": schedule.idempotency_key,
                }
            )

        if result:
            _apply_result(schedule, result)
        else:
            schedule.status = "FAILED"
            schedule.error_message = "发布器未返回结果"

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


def _apply_result(schedule: PublishSchedule, result: PublishResult) -> None:
    schedule.status = result.status
    schedule.published_url = result.published_url or None
    schedule.external_id = result.external_id or None
    schedule.result_mode = result.mode or schedule.publish_mode
    schedule.publish_package_json = result.detail.get("publishPackage", {})
    if result.status in ("PUBLISHED", "DRAFT_CREATED", "PUBLISH_SUBMITTED"):
        schedule.actual_publish_at = datetime.now()
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
