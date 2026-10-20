"""Persistent dispatch intents shared by schedule and generation tasks."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.business import GenerationTask, PublishSchedule, TaskDispatch
from app.services.activity_service import business_now

TASK_TYPE_SCHEDULE = "PUBLISH_SCHEDULE"
TASK_TYPE_GENERATION = "GENERATION"
SCHEDULE_REVISION_FIELD = "scheduleRevision"

ACTIVE_DISPATCH_STATUSES = ("PENDING", "CLAIMED")


def upsert_dispatch(
    db: Session,
    *,
    task_type: str,
    task_id: str,
    revision: str,
    run_at: datetime,
    status: str = "PENDING",
) -> TaskDispatch:
    row = db.scalar(
        select(TaskDispatch).where(
            TaskDispatch.task_type == task_type,
            TaskDispatch.task_id == task_id,
        )
    )
    if row is None:
        row = TaskDispatch(
            task_type=task_type,
            task_id=task_id,
            revision=revision,
            run_at=run_at,
            status=status,
        )
        db.add(row)
    else:
        row.revision = revision
        row.run_at = run_at
        row.status = status
        row.attempts = 0
        row.last_error = None
        row.completed_at = None
    db.flush()
    return row


def cancel_dispatch(db: Session, *, task_type: str, task_id: str) -> None:
    row = db.scalar(
        select(TaskDispatch).where(
            TaskDispatch.task_type == task_type,
            TaskDispatch.task_id == task_id,
        )
    )
    if row is not None and row.status in ACTIVE_DISPATCH_STATUSES:
        row.status = "CANCELLED"
        row.completed_at = business_now()
        db.flush()


def ensure_dispatch_intents(db: Session) -> int:
    """Backfill intents and re-arm tasks whose dispatch never took effect."""
    schedule_rows = {
        row.task_id: row
        for row in db.scalars(
            select(TaskDispatch).where(TaskDispatch.task_type == TASK_TYPE_SCHEDULE)
        ).all()
    }
    pending_schedules = db.scalars(
        select(PublishSchedule).where(PublishSchedule.status == "PENDING")
    ).all()
    created = 0
    for schedule in pending_schedules:
        row = schedule_rows.get(str(schedule.id))
        if row is not None and row.status in ACTIVE_DISPATCH_STATUSES:
            continue
        upsert_dispatch(
            db,
            task_type=TASK_TYPE_SCHEDULE,
            task_id=str(schedule.id),
            revision=str((schedule.publish_package_json or {}).get(SCHEDULE_REVISION_FIELD) or ""),
            run_at=schedule.scheduled_at,
        )
        created += 1

    generation_rows = {
        row.task_id: row
        for row in db.scalars(
            select(TaskDispatch).where(TaskDispatch.task_type == TASK_TYPE_GENERATION)
        ).all()
    }
    pending_tasks = db.scalars(
        select(GenerationTask).where(GenerationTask.status == "PENDING")
    ).all()
    for task in pending_tasks:
        row = generation_rows.get(task.id)
        if row is not None and row.status in ACTIVE_DISPATCH_STATUSES:
            continue
        upsert_dispatch(
            db,
            task_type=TASK_TYPE_GENERATION,
            task_id=task.id,
            revision=task.id,
            run_at=business_now(),
        )
        created += 1
    return created
