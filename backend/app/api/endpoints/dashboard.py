from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.config import settings
from app.core.responses import success_response
from app.db.session import get_db
from app.models.business import ContentArticle, ContentVariant, EngagementMetric, PublishSchedule
from app.models.user import User
from app.schemas.user import UserData

router = APIRouter(tags=["工作台"])


@router.get("/dashboard/summary", summary="阶段 1 工作台概览")
def dashboard_summary(
    request: Request,
    user: User = Depends(get_current_user),
) -> dict:
    role_codes = [role.code for role in user.roles]
    role_capabilities = {
        "ADMIN": ["用户与权限管理", "系统配置", "查看全局统计"],
        "OPERATOR": ["内容运营", "内容审核", "排期与发布", "数据复盘与实验"],
        "VIEWER": ["查看内容", "查看排期与报告"],
    }
    capabilities = sorted({item for code in role_codes for item in role_capabilities.get(code, [])})
    return success_response(
        request,
        {
            "phase": 9,
            "phaseName": "完整系统",
            "user": UserData.model_validate(user).model_dump(mode="json"),
            "capabilities": capabilities,
            "serviceStatus": {
                "api": "healthy",
                "database": "connected",
                "auth": "enabled",
                "demoMode": settings.app_demo_mode,
            },
            "availableModules": [
                "内容管理",
                "平台内容适配",
                "素材管理",
                "发布时间推荐",
                "排期日历",
                "发布中心",
                "数据复盘",
                "实验管理",
            ],
            "upcomingModules": [],
        },
    )


@router.get("/admin/users", summary="管理员查看用户列表")
def list_users(
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("ADMIN")),
) -> dict:
    users = db.scalars(select(User).order_by(User.id)).all()
    return success_response(
        request,
        [UserData.model_validate(user).model_dump(mode="json") for user in users],
    )


@router.get("/admin/overview", summary="管理员基础统计")
def admin_overview(
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("ADMIN")),
) -> dict:
    user_count = db.scalar(select(func.count()).select_from(User)) or 0
    active_count = (
        db.scalar(select(func.count()).select_from(User).where(User.status == "ACTIVE")) or 0
    )
    return success_response(
        request,
        {"userCount": user_count, "activeUserCount": active_count},
    )


@router.get("/dashboard/business", summary="完整业务工作台")
def business_dashboard(
    request: Request, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> dict:
    article_count = db.scalar(select(func.count()).select_from(ContentArticle)) or 0
    pending_review = (
        db.scalar(
            select(func.count())
            .select_from(ContentVariant)
            .where(ContentVariant.review_status == "PENDING")
        )
        or 0
    )
    pending_schedule = (
        db.scalar(
            select(func.count())
            .select_from(PublishSchedule)
            .where(PublishSchedule.status == "PENDING")
        )
        or 0
    )
    failed = (
        db.scalar(
            select(func.count())
            .select_from(PublishSchedule)
            .where(PublishSchedule.status == "FAILED")
        )
        or 0
    )
    today_items = db.scalars(
        select(PublishSchedule)
        .where(func.date(PublishSchedule.scheduled_at) == func.current_date())
        .order_by(PublishSchedule.scheduled_at)
        .limit(8)
    ).all()
    metrics = db.scalars(select(EngagementMetric).order_by(EngagementMetric.metric_date)).all()
    simulated_count = sum(1 for metric in metrics if metric.data_source == "SIMULATED")
    trend_map = {}
    for metric in metrics:
        key = metric.metric_date.isoformat()
        item = trend_map.setdefault(key, {"date": key, "engagement": 0, "impressions": 0})
        item["engagement"] += metric.engagement_total
        item["impressions"] += metric.impressions
    groups = {}
    for metric in metrics:
        item = groups.setdefault(
            metric.group_type, {"engagement": 0, "impressions": 0, "samples": 0}
        )
        item["engagement"] += metric.engagement_total
        item["impressions"] += metric.impressions
        item["samples"] += 1
    comparison = [
        {
            "name": key,
            "rate": round(value["engagement"] / value["impressions"] * 100, 2)
            if value["impressions"]
            else 0,
            "samples": value["samples"],
        }
        for key, value in groups.items()
    ]
    return success_response(
        request,
        {
            "stats": {
                "articles": article_count,
                "pendingReview": pending_review,
                "pendingSchedule": pending_schedule,
                "failed": failed,
            },
            "todaySchedules": [
                {
                    "id": row.id,
                    "platform": row.platform,
                    "scheduledAt": row.scheduled_at.isoformat(),
                    "status": row.status,
                }
                for row in today_items
            ],
            "trend": list(trend_map.values())[-14:],
            "timeComparison": comparison,
            "dataNotice": (
                f"当前有 {simulated_count} 条演示指标，统计时请注意数据来源。"
                if simulated_count
                else "当前仅统计实际录入或导入的数据。"
            ),
            "hasSimulatedData": bool(simulated_count),
        },
    )
