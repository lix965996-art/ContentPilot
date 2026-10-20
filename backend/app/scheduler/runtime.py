import hashlib
import json
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.events import EVENT_JOB_MISSED, JobExecutionEvent
from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from sqlalchemy import select, update

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.business import PublishLog, PublishSchedule
from app.services.publish_service import (
    SCHEDULE_REVISION_FIELD,
    ScheduleJob,
    ScheduleState,
    execute_publish_sync,
    schedule_state,
    schedule_state_conditions,
)

scheduler = BackgroundScheduler(timezone=settings.app_timezone)


def local_now() -> datetime:
    return datetime.now(ZoneInfo(settings.app_timezone)).replace(tzinfo=None)


def _mark_recovery(db, row: PublishSchedule, status: str, message: str) -> bool:
    package = dict(row.publish_package_json or {})
    package[SCHEDULE_REVISION_FIELD] = uuid.uuid4().hex
    changed = db.execute(
        update(PublishSchedule)
        .where(PublishSchedule.id == row.id, *schedule_state_conditions(schedule_state(row)))
        .values(status=status, error_message=message, publish_package_json=package)
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        return False
    db.refresh(row)
    db.add(
        PublishLog(
            schedule_id=row.id,
            step="RECOVERY",
            status=status,
            error_code=status,
            error_message=message,
        )
    )
    return True


def _job_id(schedule_id: int, job: ScheduleJob) -> str:
    state = job.state
    signature = hashlib.sha256(
        json.dumps(
            [
                state.status,
                state.retry_count,
                state.scheduled_at.isoformat(),
                state.revision,
                job.run_at.isoformat(),
            ],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()[:24]
    return f"publish-{schedule_id}-{signature}"


def _local_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(ZoneInfo(settings.app_timezone)).replace(tzinfo=None)


def _handle_missed_job(event: JobExecutionEvent) -> None:
    parts = event.job_id.split("-")
    if len(parts) != 3 or parts[0] != "publish" or not parts[1].isdigit():
        return
    with SessionLocal() as db:
        row = db.get(PublishSchedule, int(parts[1]))
        if (
            row
            and row.status == "PENDING"
            and event.job_id
            == _job_id(
                row.id,
                ScheduleJob(schedule_state(row), _local_naive(event.scheduled_run_time)),
            )
        ):
            _mark_recovery(db, row, "EXPIRED", "错过排期执行时间，未自动补发，请重新排期。")
            db.commit()


scheduler.add_listener(_handle_missed_job, EVENT_JOB_MISSED)


def add_schedule_job(schedule_id: int, run_at: datetime, state: ScheduleState) -> None:
    job = ScheduleJob(state, _local_naive(run_at))
    scheduler.add_job(
        execute_publish_sync,
        DateTrigger(run_date=run_at, timezone=settings.app_timezone),
        args=[schedule_id, job],
        id=_job_id(schedule_id, job),
        replace_existing=True,
        misfire_grace_time=3600,
    )


def remove_schedule_job(schedule_id: int, state: ScheduleState | None = None) -> None:
    for job in scheduler.get_jobs():
        if not job.id.startswith(f"publish-{schedule_id}-"):
            continue
        if state is not None and (
            len(job.args) != 2
            or not isinstance(job.args[1], ScheduleJob)
            or job.args[1].state != state
        ):
            continue
        try:
            scheduler.remove_job(job.id)
        except JobLookupError:
            # Another worker may already have dequeued this one-shot job.
            pass


def start_scheduler() -> None:
    if scheduler.running:
        return
    future: list[tuple[int, datetime, ScheduleState]] = []
    with SessionLocal() as db:
        rows = db.scalars(
            select(PublishSchedule).where(
                PublishSchedule.status.in_(("PENDING", "RUNNING", "PUBLISHING"))
            )
        ).all()
        now = local_now()
        for row in rows:
            if row.status in {"RUNNING", "PUBLISHING"}:
                _mark_recovery(
                    db,
                    row,
                    "INTERRUPTED",
                    "服务停止时任务正在执行，平台结果尚未确认；请先核实平台，再决定是否重新排期。",
                )
            elif row.scheduled_at <= now:
                _mark_recovery(db, row, "EXPIRED", "停机期间错过排期，未自动补发，请重新排期。")
            else:
                future.append((row.id, row.scheduled_at, schedule_state(row)))
        db.commit()
    for schedule_id, run_at, state in future:
        add_schedule_job(schedule_id, run_at, state)
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
