import asyncio
import time
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.models.business import ContentVariant, PublishLog, PublishSchedule
from app.publishers.mock import ManualConfirmPublisher, MockPublisher

FINAL_STATUSES = {"SUCCESS", "MOCK_SUCCESS", "CANCELLED"}


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
    schedule.status = "RUNNING"
    db.commit()
    started = time.perf_counter()
    publisher = ManualConfirmPublisher() if schedule.publish_mode == "MANUAL" else MockPublisher()
    try:
        result = await publisher.publish(
            {
                "schedule_id": schedule.id,
                "platform": schedule.platform,
                "title": variant.title,
                "content": variant.content_text,
                "idempotency_key": schedule.idempotency_key,
            }
        )
        schedule.status = result.status
        schedule.published_url = result.url
        schedule.actual_publish_at = datetime.now() if result.success else None
        schedule.error_message = None
        db.add(
            PublishLog(
                schedule_id=schedule.id,
                step="PUBLISH",
                request_summary=f"{schedule.platform} / variant {variant.id}",
                response_summary=result.message,
                status=result.status,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        )
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


def execute_publish_sync(schedule_id: int) -> None:
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        schedule = asyncio.run(execute_publish(db, schedule_id))
        if schedule.status == "FAILED" and schedule.retry_count <= schedule.max_retry_count:
            from app.scheduler.runtime import add_schedule_job

            delays = (1, 5, 15)
            delay = delays[min(schedule.retry_count - 1, len(delays) - 1)]
            add_schedule_job(schedule.id, datetime.now() + timedelta(minutes=delay))
