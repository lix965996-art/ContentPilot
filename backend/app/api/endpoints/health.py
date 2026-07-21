from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.responses import success_response
from app.db.session import get_db

router = APIRouter(tags=["系统"])


@router.get("/health", summary="服务健康检查")
def health(request: Request, db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return success_response(
        request,
        {
            "status": "healthy",
            "app": settings.app_name,
            "environment": settings.app_env,
            "database": "connected",
        },
    )
