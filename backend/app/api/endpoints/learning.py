"""Read-only feedback operations and validated local model management."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.exceptions import AppException
from app.core.responses import success_response
from app.db.session import get_db
from app.ml import registry
from app.ml.dataset import audit_dataset, iso_utc
from app.models.business import PublishSchedule
from app.models.learning import EngagementObservation, MetricCollectionTask
from app.models.user import User
from app.services.audit_service import record_audit
from app.services.engagement_collection_service import PLATFORMS, request_collection

router = APIRouter(prefix="/learning", tags=["互动学习"])


class CollectionRequest(BaseModel):
    request_key: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")


class ActivationRequest(BaseModel):
    platform: Literal["BLUESKY", "MASTODON"]
    model_id: str | None = Field(default=None, max_length=80)


@router.get("/status")
def status(
    request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    # The application shares aggregate analytics; manual collection remains owner-only.
    _, readiness = audit_dataset(db)
    schedules = db.scalars(
        select(PublishSchedule)
        .where(
            PublishSchedule.platform.in_(PLATFORMS),
            PublishSchedule.status == "PUBLISHED",
            PublishSchedule.created_by == user.id,
        )
        .order_by(PublishSchedule.id.desc())
        .limit(30)
    ).all()
    ids = [row.id for row in schedules]
    observations = (
        db.scalars(
            select(EngagementObservation)
            .where(EngagementObservation.schedule_id.in_(ids))
            .order_by(EngagementObservation.observed_at.desc())
            .limit(200)
        ).all()
        if ids
        else []
    )
    tasks = (
        db.scalars(
            select(MetricCollectionTask)
            .where(MetricCollectionTask.schedule_id.in_(ids))
            .order_by(MetricCollectionTask.due_at.desc())
            .limit(200)
        ).all()
        if ids
        else []
    )
    latest = {}
    for item in observations:
        latest.setdefault(item.schedule_id, item)
    items = []
    for row in schedules:
        obs = latest.get(row.id)
        items.append(
            {
                "scheduleId": row.id,
                "platform": row.platform,
                "url": row.published_url,
                "observedAt": iso_utc(obs.observed_at) if obs else None,
                "ageSeconds": obs.age_seconds if obs else None,
                "status": obs.status if obs else "NOT_COLLECTED",
                "errorCode": obs.error_code if obs else None,
                "likes": obs.likes if obs else None,
                "replies": obs.replies if obs else None,
                "reposts": obs.reposts if obs else None,
                "tasks": [
                    {
                        "id": task.id,
                        "status": task.status,
                        "dueAt": iso_utc(task.due_at),
                        "windowSeconds": task.window_seconds,
                        "errorCode": task.last_error,
                    }
                    for task in tasks
                    if task.schedule_id == row.id
                ],
            }
        )
    return success_response(
        request,
        {
            "readiness": readiness,
            "items": items,
            "activeModels": {p: registry.active_id(db, p) for p in sorted(PLATFORMS)},
            "models": registry.list_models(),
            "exposureAvailable": False,
        },
    )


@router.post("/collect/{schedule_id}")
def collect(
    schedule_id: int,
    payload: CollectionRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    schedule = db.get(PublishSchedule, schedule_id)
    if schedule is None:
        raise AppException(40407, "排期不存在", 404)
    if schedule.created_by != user.id:
        raise AppException(40303, "只能采集自己创建的发布任务", 403)
    task = request_collection(db, schedule, request_key=payload.request_key)
    db.commit()
    return success_response(request, {"taskId": task.id, "status": task.status})


@router.post("/models/activate")
def activate(
    payload: ActivationRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> dict:
    try:
        registry.set_active(db, payload.platform, payload.model_id)
    except (OSError, ValueError, KeyError, TypeError):
        raise AppException(40091, "模型不存在、损坏或未达到该平台的启用门槛") from None
    record_audit(
        db,
        request,
        user,
        action="ML_MODEL_ACTIVATE",
        module="LEARNING",
        target_type="MODEL",
        target_id=payload.model_id,
        detail={"platform": payload.platform, "modelId": payload.model_id},
    )
    db.commit()
    return success_response(request, {"platform": payload.platform, "modelId": payload.model_id})
