from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.business import PublishSchedule
from app.services.publish_service import execute_publish_sync

scheduler = BackgroundScheduler(timezone=settings.app_timezone)


def add_schedule_job(schedule_id: int, run_at: datetime) -> None:
    scheduler.add_job(
        execute_publish_sync,
        DateTrigger(run_date=run_at),
        args=[schedule_id],
        id=f"publish-{schedule_id}",
        replace_existing=True,
        misfire_grace_time=3600,
    )


def remove_schedule_job(schedule_id: int) -> None:
    job = scheduler.get_job(f"publish-{schedule_id}")
    if job:
        scheduler.remove_job(job.id)


def start_scheduler() -> None:
    if not scheduler.running:
        scheduler.start()
    with SessionLocal() as db:
        rows = db.scalars(
            select(PublishSchedule).where(
                PublishSchedule.status == "PENDING", PublishSchedule.scheduled_at > datetime.now()
            )
        ).all()
        for row in rows:
            add_schedule_job(row.id, row.scheduled_at)


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
