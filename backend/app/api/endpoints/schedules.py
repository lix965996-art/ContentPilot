import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.exceptions import AppException
from app.core.responses import success_response
from app.db.session import get_db
from app.models.business import ContentArticle, ContentVariant, PublishLog, PublishSchedule
from app.models.user import User
from app.scheduler.runtime import add_schedule_job, remove_schedule_job
from app.schemas.business import ScheduleCreate, ScheduleUpdate
from app.services.audit_service import record_audit
from app.services.publish_service import execute_publish
from app.services.serializers import model_dict

router = APIRouter(tags=["排期与发布"])


def _local_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)


def _data(db: Session, row: PublishSchedule, include_logs: bool = False) -> dict:
    data = model_dict(row, camel=True)
    article = db.get(ContentArticle, row.article_id)
    variant = db.get(ContentVariant, row.variant_id)
    data.update(
        {
            "articleTitle": article.title if article else "",
            "variantTitle": variant.title if variant else "",
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
        filters.append(PublishSchedule.status == status)
    items = db.scalars(
        select(PublishSchedule).where(*filters).order_by(PublishSchedule.scheduled_at)
    ).all()
    return success_response(request, [_data(db, item) for item in items])


@router.post("/schedules")
def create_schedule(
    payload: ScheduleCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    article = db.get(ContentArticle, payload.article_id)
    variant = db.get(ContentVariant, payload.variant_id)
    if not article or not variant or variant.article_id != article.id:
        raise AppException(40031, "文章与平台版本不匹配")
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
    row = PublishSchedule(
        **values,
        status="PENDING",
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
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    row = db.get(PublishSchedule, schedule_id)
    if not row:
        raise AppException(40407, "排期任务不存在", 404)
    if row.status not in {"PENDING", "FAILED", "WAITING_MANUAL_CONFIRM"}:
        raise AppException(40903, "当前状态不允许修改", 409)
    if payload.scheduled_at:
        scheduled_at = _local_naive(payload.scheduled_at)
        if scheduled_at <= datetime.now():
            raise AppException(40032, "排期时间必须晚于当前时间")
        row.scheduled_at = scheduled_at
    if payload.publish_mode:
        row.publish_mode = payload.publish_mode
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
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    row = db.get(PublishSchedule, schedule_id)
    if not row:
        raise AppException(40407, "排期任务不存在", 404)
    if row.status in {"RUNNING", "SUCCESS", "MOCK_SUCCESS"}:
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
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    row = db.get(PublishSchedule, schedule_id)
    if not row:
        raise AppException(40407, "排期任务不存在", 404)
    if row.status in {"SUCCESS", "MOCK_SUCCESS"}:
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
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
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
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    row = db.get(PublishSchedule, schedule_id)
    if not row or row.status != "FAILED":
        raise AppException(40904, "只有失败任务可以重试", 409)
    if row.retry_count >= row.max_retry_count:
        raise AppException(40905, "已达到最大重试次数", 409)
    return await publish_now(schedule_id, request, db, user)


@router.post("/schedules/{schedule_id}/manual-confirm")
async def manual_confirm(
    schedule_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    row = db.get(PublishSchedule, schedule_id)
    if not row or row.status != "WAITING_MANUAL_CONFIRM":
        raise AppException(40906, "当前任务不在等待人工确认状态", 409)
    body = await request.json()
    row.status = "SUCCESS"
    row.actual_publish_at = datetime.now()
    row.published_url = body.get("publishedUrl") or "manual://confirmed"
    db.add(
        PublishLog(
            schedule_id=row.id,
            step="MANUAL_CONFIRM",
            response_summary="运营人员已确认平台发布",
            status="SUCCESS",
        )
    )
    record_audit(db, request, user, "MANUAL_CONFIRM", "PUBLISH", "SCHEDULE", row.id)
    db.commit()
    return success_response(request, _data(db, row, True), "人工发布已确认")
