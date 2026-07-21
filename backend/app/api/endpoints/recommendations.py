from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.exceptions import AppException
from app.core.responses import success_response
from app.db.session import get_db
from app.models.business import (
    AccountActivityStat,
    ActivityPrior,
    ContentArticle,
    PublishRecommendation,
)
from app.models.user import User
from app.schemas.business import RecommendationRequest
from app.services.audit_service import record_audit
from app.services.recommendation_service import curve, recommend
from app.services.serializers import model_dict

router = APIRouter(tags=["发布时间推荐"])


@router.post("/recommendations/publish-time")
def publish_time(
    payload: RecommendationRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    if not db.get(ContentArticle, payload.article_id):
        raise AppException(40401, "文章不存在", 404)
    prior_count = db.scalar(select(func.count()).select_from(ActivityPrior)) or 0
    history_count = db.scalar(select(func.count()).select_from(AccountActivityStat)) or 0
    if not prior_count and not history_count:
        raise AppException(42221, "暂无可用于推荐的真实历史数据或人工时段规则", 422)
    result = recommend(
        db, payload.platform, payload.target_date or (date.today() + timedelta(days=1))
    )
    row = PublishRecommendation(
        article_id=payload.article_id,
        variant_id=payload.variant_id,
        platform=payload.platform,
        recommended_at=result["recommendedAt"],
        score=result["score"],
        confidence=result["confidence"],
        reason_json=result["reasons"],
        alternative_times_json=result["alternatives"],
        algorithm_version=result["algorithmVersion"],
    )
    db.add(row)
    db.flush()
    record_audit(
        db, request, user, "RECOMMEND", "SCHEDULING", "RECOMMENDATION", row.id, {"score": row.score}
    )
    db.commit()
    db.refresh(row)
    data = model_dict(row, camel=True)
    data["curve"] = curve(db, payload.platform, payload.target_date or date.today())
    data["sampleCount"] = result["sampleCount"]
    return success_response(request, data, "推荐时间计算完成")


@router.get("/recommendations/{recommendation_id}")
def get_recommendation(
    recommendation_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    row = db.get(PublishRecommendation, recommendation_id)
    if not row:
        raise AppException(40405, "推荐记录不存在", 404)
    return success_response(request, model_dict(row, camel=True))


@router.get("/activity/curve")
def activity_curve(
    request: Request,
    platform: str = "WEIBO",
    target_date: date | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    return success_response(
        request,
        {
            "platform": platform,
            "date": (target_date or date.today()).isoformat(),
            "points": curve(db, platform, target_date or date.today()),
            "source": "人工维护规则与账号历史数据",
        },
    )


@router.get("/activity/platform-priors")
def priors(
    request: Request,
    platform: str = "",
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    query = select(ActivityPrior).order_by(
        ActivityPrior.platform, ActivityPrior.day_of_week, ActivityPrior.hour_of_day
    )
    if platform:
        query = query.where(ActivityPrior.platform == platform)
    return success_response(
        request, [model_dict(row, camel=True) for row in db.scalars(query).all()]
    )


@router.put("/activity/platform-priors/{prior_id}")
async def update_prior(
    prior_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> dict:
    row = db.get(ActivityPrior, prior_id)
    if not row:
        raise AppException(40406, "活跃规则不存在", 404)
    body = await request.json()
    score = float(body.get("baseScore", row.base_score))
    if not 0 <= score <= 100:
        raise AppException(40021, "活跃度得分必须在 0—100")
    row.base_score = score
    row.enabled = bool(body.get("enabled", row.enabled))
    record_audit(db, request, user, "UPDATE", "SETTINGS", "ACTIVITY_PRIOR", row.id)
    db.commit()
    return success_response(request, model_dict(row, camel=True), "活跃规则已更新")
