import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.paths import RUN_DIR, UPLOADS_DIR, ensure_directory
from app.db.session import SessionLocal
from app.models.business import GenerationTask
from app.scheduler.dispatch import start_dispatcher, stop_dispatcher
from app.scheduler.lease import SchedulerLease
from app.scheduler.runtime import start_scheduler, stop_scheduler
from app.services.task_dispatch_service import ensure_dispatch_intents

logger = logging.getLogger(__name__)


def _reconcile_stale_tasks() -> None:
    """Terminate interrupted generation runs and backfill dispatch intents.

    PENDING generation tasks are not failed here: they are still dispatchable and
    the persistent dispatcher will pick them up. RUNNING tasks belonged to the
    previous process and are conservatively moved to FAILED with their platform
    substates synchronised.
    """
    with SessionLocal() as db:
        stale = (
            db.execute(select(GenerationTask).where(GenerationTask.status == "RUNNING"))
            .scalars()
            .all()
        )
        for task in stale:
            task.status = "FAILED"
            task.progress = 100
            task.error_message = "服务重启，生成任务中断"
            states = dict(task.platform_status_json or {})
            for platform, state in list(states.items()):
                if not isinstance(state, dict):
                    continue
                if state.get("status") in {"PENDING", "RUNNING", "RETRYING"}:
                    updated = dict(state)
                    updated.update(
                        status="FAILED",
                        progress=100,
                        message="服务重启，生成任务中断",
                        error="服务重启",
                    )
                    states[platform] = updated
            task.platform_status_json = states
        created = ensure_dispatch_intents(db)
        db.commit()
        if stale or created:
            logger.warning(
                "Reconciled %d interrupted generation tasks; created %d dispatch intents",
                len(stale),
                created,
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_directory(RUN_DIR)
    lease = SchedulerLease(RUN_DIR / "scheduler.lock")
    active = lease.acquire()
    app.state.scheduler_role = "active" if active else "standby"
    if active:
        _reconcile_stale_tasks()
        start_scheduler()
        start_dispatcher()
    else:
        logger.warning(
            "Another ContentPilot instance holds the scheduler lease; "
            "starting in API-only standby mode (no recovery or dispatch)."
        )
    try:
        yield
    finally:
        if active:
            stop_dispatcher()
            stop_scheduler()
            lease.release()


app = FastAPI(
    title=settings.app_name,
    description="ContentPilot 多平台内容运营 API：内容、生成、媒体、排期、发布、分析与实验",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    request.state.trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex
    response = await call_next(request)
    response.headers["X-Trace-Id"] = request.state.trace_id
    return response


register_exception_handlers(app)
app.include_router(api_router, prefix=settings.api_prefix)
app.mount("/uploads", StaticFiles(directory=ensure_directory(UPLOADS_DIR)), name="uploads")
