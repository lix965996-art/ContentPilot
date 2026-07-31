from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.responses import success_response
from app.db.session import get_db
from app.models.business import (
    ContentArticle,
    GenerationTask,
    PlatformAccount,
    PublishSchedule,
)
from app.models.user import User

router = APIRouter(tags=["运行中心"])


def _generation_run(db: Session, task: GenerationTask) -> dict[str, Any]:
    article = db.get(ContentArticle, task.article_id)
    states = task.platform_status_json or {}
    steps = []
    for platform in task.platforms_json or []:
        state = dict(states.get(platform, {}))
        steps.append(
            {
                "key": platform,
                "name": platform,
                "status": state.get("status", "PENDING"),
                "stage": state.get("stage", "QUEUED"),
                "message": state.get("message", "等待执行"),
                "progress": int(state.get("progress", 0)),
                "durationMs": int(state.get("durationMs", 0)),
                "tokenUsage": int(state.get("tokenUsage", 0)),
                "error": state.get("error"),
                "attempt": int(state.get("attempt", 0)),
            }
        )
    return {
        "id": f"generation:{task.id}",
        "sourceId": task.id,
        "type": "GENERATION",
        "title": article.title if article else f"内容 #{task.article_id}",
        "subtitle": "、".join(task.platforms_json or []),
        "status": task.status,
        "progress": task.progress,
        "provider": task.provider,
        "modelName": task.model_name,
        "tokenUsage": task.token_usage,
        "durationMs": task.duration_ms,
        "errorMessage": task.error_message,
        "createdAt": task.created_at,
        "updatedAt": task.updated_at,
        "steps": steps,
    }


def _publish_run(db: Session, schedule: PublishSchedule) -> dict[str, Any]:
    article = db.get(ContentArticle, schedule.article_id)
    account = db.get(PlatformAccount, schedule.account_id) if schedule.account_id else None
    logs = sorted(schedule.logs, key=lambda item: (item.created_at or datetime.min, item.id))
    steps = [
        {
            "key": str(log.id),
            "name": log.step,
            "status": log.status,
            "message": log.response_summary or log.request_summary or "步骤已执行",
            "progress": 100,
            "durationMs": log.duration_ms,
            "error": log.error_message,
            "createdAt": log.created_at,
        }
        for log in logs
    ]
    if not steps:
        steps.append(
            {
                "key": "queued",
                "name": "等待调度",
                "status": "PENDING",
                "message": "将在计划时间启动发布流程",
                "progress": 0,
                "durationMs": 0,
            }
        )
    terminal = {
        "SUCCESS",
        "MANUAL_PUBLISHED",
        "DRAFT_CREATED",
        "PUBLISH_SUBMITTED",
        "FAILED",
        "CANCELLED",
    }
    progress = (
        100
        if schedule.status in terminal
        else 55
        if schedule.status in {"RUNNING", "PUBLISHING"}
        else 0
    )
    return {
        "id": f"publish:{schedule.id}",
        "sourceId": schedule.id,
        "type": "PUBLISH",
        "title": article.title if article else f"内容 #{schedule.article_id}",
        "subtitle": f"{schedule.platform} · {account.account_name if account else '未绑定账号'}",
        "status": schedule.status,
        "progress": progress,
        "durationMs": sum(log.duration_ms for log in logs),
        "errorMessage": schedule.error_message,
        "createdAt": schedule.created_at,
        "updatedAt": schedule.updated_at,
        "scheduledAt": schedule.scheduled_at,
        "retryCount": schedule.retry_count,
        "maxRetryCount": schedule.max_retry_count,
        "steps": steps,
    }


@router.get("/operation-runs")
def list_operation_runs(
    request: Request,
    run_type: str = Query(default="", pattern="^(|GENERATION|PUBLISH)$"),
    status: str = Query(default="", max_length=40),
    query: str = Query(default="", max_length=100),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    generation_rows: list[GenerationTask] = []
    publish_rows: list[PublishSchedule] = []
    article_ids: set[int] | None = None
    if query:
        article_ids = set(
            db.scalars(
                select(ContentArticle.id).where(ContentArticle.title.ilike(f"%{query.strip()}%"))
            ).all()
        )
        if not article_ids:
            return success_response(
                request,
                {
                    "items": [],
                    "summary": {"total": 0, "running": 0, "failed": 0, "success": 0},
                },
            )
    if run_type != "PUBLISH":
        generation_filters = []
        if status == "ACTIVE":
            generation_filters.append(GenerationTask.status.in_(["PENDING", "RUNNING", "RETRYING"]))
        elif status == "ATTENTION":
            generation_filters.append(GenerationTask.status.in_(["FAILED", "PARTIAL_SUCCESS"]))
        elif status:
            generation_filters.append(GenerationTask.status == status)
        if article_ids is not None:
            generation_filters.append(GenerationTask.article_id.in_(article_ids))
        generation_rows = list(
            db.scalars(
                select(GenerationTask)
                .where(*generation_filters)
                .order_by(GenerationTask.created_at.desc())
                .limit(limit)
            ).all()
        )
    if run_type != "GENERATION":
        publish_filters = []
        if status == "ACTIVE":
            publish_filters.append(PublishSchedule.status.in_(["PENDING", "RUNNING", "PUBLISHING"]))
        elif status == "ATTENTION":
            publish_filters.append(PublishSchedule.status == "FAILED")
        elif status:
            publish_filters.append(PublishSchedule.status == status)
        if article_ids is not None:
            publish_filters.append(PublishSchedule.article_id.in_(article_ids))
        publish_rows = list(
            db.scalars(
                select(PublishSchedule)
                .where(*publish_filters)
                .order_by(PublishSchedule.created_at.desc())
                .limit(limit)
            ).all()
        )
    items = [_generation_run(db, row) for row in generation_rows]
    items.extend(_publish_run(db, row) for row in publish_rows)
    items.sort(key=lambda row: row.get("createdAt") or datetime.min, reverse=True)
    items = items[:limit]
    success_states = {"SUCCESS", "MANUAL_PUBLISHED", "DRAFT_CREATED", "PUBLISH_SUBMITTED"}
    return success_response(
        request,
        {
            "items": items,
            "summary": {
                "total": len(items),
                "running": sum(
                    row["status"] in {"RUNNING", "RETRYING", "PUBLISHING"} for row in items
                ),
                "failed": sum(row["status"] in {"FAILED", "PARTIAL_SUCCESS"} for row in items),
                "success": sum(row["status"] in success_states for row in items),
            },
        },
    )
