"""Persistent dispatch scanner for schedules and generation tasks.

The API writes a ``task_dispatch`` row in the same transaction as the business
task. This scanner is the safety net for the gap between that commit and the
in-process scheduler/background task accepting the work. It is deliberately
idempotent: schedule jobs use deterministic IDs with ``replace_existing`` and
generation runs claim the task with a status CAS.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.business import GenerationTask, PublishSchedule, TaskDispatch
from app.scheduler import runtime
from app.services.activity_service import business_now
from app.services.publish_service import LAST_FAILURE_RETRYABLE_FIELD, schedule_state
from app.services.task_dispatch_service import (
    TASK_TYPE_GENERATION,
    TASK_TYPE_SCHEDULE,
)

logger = logging.getLogger(__name__)

_generation_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="generation-dispatch")


def _complete(db: Session, row: TaskDispatch, status: str = "DONE") -> None:
    row.status = status
    row.completed_at = business_now()
    db.commit()


def _fail_attempt(db: Session, row: TaskDispatch, error: str) -> bool:
    row.attempts += 1
    row.last_error = error[:2000]
    terminal = row.attempts >= settings.dispatch_max_attempts
    if terminal:
        row.status = "FAILED"
        row.completed_at = business_now()
        logger.error(
            "Task dispatch %s/%s failed after %d attempts: %s",
            row.task_type,
            row.task_id,
            row.attempts,
            error,
        )
    db.commit()
    return terminal


def _dispatch_schedule(db: Session, row: TaskDispatch, now: datetime) -> None:
    try:
        schedule = db.get(PublishSchedule, int(row.task_id))
    except ValueError:
        _complete(db, row, "CANCELLED")
        return
    if schedule is None:
        _complete(db, row, "CANCELLED")
        return
    state = schedule_state(schedule)
    if schedule.status == "PENDING":
        if schedule.scheduled_at <= now:
            runtime._mark_recovery(
                db,
                schedule,
                "EXPIRED",
                "派发扫描发现排期已过期，未自动补发，请重新排期。",
            )
            _complete(db, row)
            return
        try:
            runtime.add_schedule_job(schedule.id, schedule.scheduled_at, state)
        except Exception as exc:  # pragma: no cover - scheduler integration guard
            if _fail_attempt(db, row, f"添加排期作业失败：{exc}"):
                runtime._mark_recovery(
                    db,
                    schedule,
                    "FAILED",
                    f"排期派发失败：{exc}；请重新排期",
                )
                _complete(db, row, "FAILED")
            return
        _complete(db, row)
        return
    if (
        schedule.status == "FAILED"
        and (schedule.publish_package_json or {}).get(LAST_FAILURE_RETRYABLE_FIELD) is True
    ):
        try:
            runtime.add_schedule_job(schedule.id, row.run_at, state)
        except Exception as exc:  # pragma: no cover - scheduler integration guard
            if _fail_attempt(db, row, f"添加重试作业失败：{exc}"):
                runtime._mark_recovery(
                    db,
                    schedule,
                    "FAILED",
                    f"排期重试派发失败：{exc}；请重新排期",
                )
                _complete(db, row, "FAILED")
            return
        _complete(db, row)
        return
    # Cancelled/published/manual states no longer need a dispatch.
    _complete(db, row)


def _run_generation_in_thread(task_id: str) -> None:
    from app.services.generation_task_service import run_generation_task

    asyncio.run(run_generation_task(task_id))


def _dispatch_generation(db: Session, row: TaskDispatch) -> None:
    task = db.get(GenerationTask, row.task_id)
    if task is None or task.status != "PENDING":
        _complete(db, row)
        return
    try:
        _generation_executor.submit(_run_generation_in_thread, task.id)
    except Exception as exc:  # pragma: no cover - executor guard
        if _fail_attempt(db, row, f"提交生成任务失败：{exc}"):
            task = db.get(GenerationTask, row.task_id)
            if task is not None and task.status == "PENDING":
                task.status = "FAILED"
                task.progress = 100
                task.error_message = f"生成任务派发失败：{exc}；请重新生成"
                states = dict(task.platform_status_json or {})
                for platform, state in list(states.items()):
                    if isinstance(state, dict) and state.get("status") in {
                        "PENDING",
                        "RUNNING",
                        "RETRYING",
                    }:
                        updated = dict(state)
                        updated.update(
                            status="FAILED",
                            progress=100,
                            message="生成任务派发失败",
                            error=str(exc),
                        )
                        states[platform] = updated
                task.platform_status_json = states
                db.commit()
            _complete(db, row, "FAILED")
        return
    _complete(db, row)


def dispatch_pending() -> None:
    """Scan and dispatch pending intents. Safe to run repeatedly."""
    now = business_now()
    with SessionLocal() as db:
        rows = db.scalars(
            select(TaskDispatch)
            .where(TaskDispatch.status == "PENDING")
            .order_by(TaskDispatch.run_at, TaskDispatch.id)
            .limit(200)
        ).all()
        for row in rows:
            try:
                if row.task_type == TASK_TYPE_SCHEDULE:
                    _dispatch_schedule(db, row, now)
                elif row.task_type == TASK_TYPE_GENERATION:
                    _dispatch_generation(db, row)
                else:
                    _complete(db, row, "CANCELLED")
            except Exception as exc:  # pragma: no cover - defensive per-row isolation
                db.rollback()
                row = db.get(TaskDispatch, row.id)
                if row is not None:
                    _fail_attempt(db, row, f"派发异常：{exc}")


def start_dispatcher() -> None:
    if runtime.scheduler.get_job("dispatch-pending") is None:
        dispatch_pending()
        runtime.scheduler.add_job(
            dispatch_pending,
            "interval",
            seconds=max(5, settings.dispatch_poll_seconds),
            id="dispatch-pending",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )


def stop_dispatcher() -> None:
    if runtime.scheduler.get_job("dispatch-pending") is not None:
        try:
            runtime.scheduler.remove_job("dispatch-pending")
        except Exception:
            pass
