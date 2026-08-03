import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.db.session import SessionLocal
from app.models.business import GenerationTask
from app.scheduler.runtime import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)


def _reconcile_stale_tasks() -> None:
    """Mark generation tasks stuck in RUNNING as FAILED after a server restart."""
    with SessionLocal() as db:
        stale = (
            db.execute(
                select(GenerationTask).where(GenerationTask.status == "RUNNING")
            )
            .scalars()
            .all()
        )
        for task in stale:
            task.status = "FAILED"
            task.error_message = "服务重启，生成任务中断"
        if stale:
            db.commit()
            logger.warning("Reconciled %d stale RUNNING generation tasks → FAILED", len(stale))


@asynccontextmanager
async def lifespan(_: FastAPI):
    _reconcile_stale_tasks()
    start_scheduler()
    yield
    stop_scheduler()


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
uploads_dir = Path(__file__).resolve().parents[2] / "uploads"
uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")
