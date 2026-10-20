from datetime import date, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_current_user, require_roles
from app.core.exceptions import AppException
from app.core.responses import success_response
from app.db.session import get_db
from app.models.business import (
    AccountActivityStat,
    ActivityPrior,
    ContentArticle,
    ContentVariant,
    EngagementHistory,
    PlatformAccount,
    PublishRecommendation,
    PublishSchedule,
)
from app.models.user import User
from app.schemas.business import RecommendationBatchRequest, RecommendationRequest
from app.services.activity_estimation_service import hourly_curve
from app.services.activity_service import (
    CONTENT_TYPE_NAMES,
    analyze,
    content_type_name,
    normalize_content_type,
)
from app.services.audit_service import record_audit
from app.services.recommendation_analysis import curve
from app.services.recommendation_narrative import classify_with_llm, narrate
from app.services.recommendation_service import recommend, slot_evidence
from app.services.semantic_schedule_pipeline import (
    activity_summary,
    assignment_by_platform,
    run_pipeline,
)
from app.services.serializers import model_dict

router = APIRouter(tags=["发布时间推荐"])


def _recommendation_payload(row: PublishRecommendation) -> dict:
    data = model_dict(row, camel=True)
    data["contentTypeName"] = content_type_name(row.content_type)
    return data


async def _create_publish_recommendation(
    payload: RecommendationRequest,
    request: Request,
    db: Session,
    user: User,
) -> tuple[dict, PublishRecommendation]:
    article = db.get(ContentArticle, payload.article_id)
    if not article:
        raise AppException(40401, "文章不存在", 404)
    variant = db.get(ContentVariant, payload.variant_id) if payload.variant_id else None
    prior_count = db.scalar(select(func.count()).select_from(ActivityPrior)) or 0
    legacy_count = db.scalar(select(func.count()).select_from(AccountActivityStat)) or 0
    history_count = db.scalar(select(func.count()).select_from(EngagementHistory)) or 0
    if not prior_count and not legacy_count and not history_count:
        raise AppException(42221, "暂无可用于推荐的历史数据或人工时段规则", 422)

    account_id = payload.account_id
    if not account_id:
        account = db.scalar(
            select(PlatformAccount).where(PlatformAccount.platform == payload.platform)
        )
        account_id = account.id if account else None

    classification = {"contentType": normalize_content_type(payload.content_type), "provider": ""}
    if not payload.content_type:
        classification = await classify_with_llm(
            db,
            title=(variant.title if variant else article.title),
            content=(variant.content_text if variant else article.source_text),
            hashtags=list(variant.hashtags_json or []) if variant else [],
        )
    content_type = classification["contentType"]

    target_date = payload.target_date or date.today()
    try:
        result = await run_in_threadpool(
            recommend,
            db,
            payload.platform,
            target_date,
            account_id=account_id,
            content_type=content_type,
            horizon_days=payload.horizon_days,
            window=payload.window,
            start_date=payload.window_start_date,
            end_date=payload.window_end_date,
        )
    except ValueError as exc:
        raise AppException(42222, str(exc), 422) from exc

    narrative, provider = (
        await narrate(db, result) if payload.with_narrative else (None, "RULE_BASED")
    )

    row = PublishRecommendation(
        article_id=payload.article_id,
        variant_id=payload.variant_id,
        platform=payload.platform,
        account_id=account_id,
        content_type=content_type,
        target_date=target_date,
        recommended_at=result["recommendedAt"],
        score=result["score"],
        confidence=result["confidence"],
        reason_json=result["reasons"],
        alternative_times_json=result["alternatives"],
        algorithm_version=result["algorithmVersion"],
        sample_count=result["sampleCount"],
        account_sample_count=result["accountSampleCount"],
        baseline_sample_count=result["baselineSampleCount"],
        weights_json=result["weights"],
        data_source_json=result["dataSource"],
        warnings_json=result["warnings"],
        conflicts_json=result["conflicts"],
        narrative=narrative,
        narrative_provider=provider,
        window_json=result["window"],
    )
    db.add(row)
    db.flush()
    record_audit(
        db, request, user, "RECOMMEND", "SCHEDULING", "RECOMMENDATION", row.id, {"score": row.score}
    )

    data = _recommendation_payload(row)
    data.update(
        {
            "curve": curve(
                db,
                payload.platform,
                target_date,
                account_id=account_id,
                window=payload.window,
                start_date=payload.window_start_date,
                end_date=payload.window_end_date,
            ),
            "sampleCount": result["sampleCount"],
            "alternatives": result["alternatives"],
            "reasons": result["reasons"],
            "warnings": result["warnings"],
            "conflicts": result["conflicts"],
            "weights": result["weights"],
            "dataSource": result["dataSource"],
            "dataSufficiency": result["dataSufficiency"],
            "window": result["window"],
            "contentTypeProvider": classification.get("provider") or "MANUAL",
            "topic": classification.get("topic", ""),
            "audience": classification.get("audience", ""),
            "narrative": narrative,
            "narrativeProvider": provider,
        }
    )
    return data, row


@router.post("/recommendations/publish-time")
async def publish_time(
    payload: RecommendationRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    data, _ = await _create_publish_recommendation(payload, request, db, user)
    db.commit()
    return success_response(request, data, "推荐时间计算完成")


@router.post("/recommendations/publish-time/batch")
async def publish_time_batch(
    payload: RecommendationBatchRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    article = db.get(ContentArticle, payload.article_id)
    if not article:
        raise AppException(40401, "文章不存在", 404)
    if payload.window == "CUSTOM" and (
        not payload.window_start_date or not payload.window_end_date
    ):
        raise AppException(40001, "自定义时间范围需要填写开始和结束日期")

    items: list[dict] = []
    # Successful targets kept for the semantic optimisation stage.
    resolved: list[dict] = []
    shared_content_type = (
        normalize_content_type(payload.content_type) if payload.content_type else None
    )
    for target in payload.targets:
        variant_id = target.variant_id
        if variant_id:
            variant = db.get(ContentVariant, variant_id)
            if not variant or variant.article_id != payload.article_id:
                items.append(
                    {
                        "platform": target.platform,
                        "success": False,
                        "message": "平台版本与文章不匹配",
                        "code": 40402,
                    }
                )
                continue
            if variant.platform != target.platform:
                items.append(
                    {
                        "platform": target.platform,
                        "success": False,
                        "message": "平台版本与目标平台不匹配",
                        "code": 40033,
                    }
                )
                continue
        else:
            variant = db.scalar(
                select(ContentVariant)
                .where(
                    ContentVariant.article_id == payload.article_id,
                    ContentVariant.platform == target.platform,
                )
                .order_by(ContentVariant.version_no.desc())
            )
            variant_id = variant.id if variant else None
            if not variant_id:
                items.append(
                    {
                        "platform": target.platform,
                        "success": False,
                        "message": "该文章尚未生成此平台版本",
                        "code": 40402,
                    }
                )
                continue

        account = db.scalar(
            select(PlatformAccount).where(
                PlatformAccount.id == target.account_id,
                PlatformAccount.platform == target.platform,
            )
        )
        if not account:
            items.append(
                {
                    "platform": target.platform,
                    "success": False,
                    "message": "平台账号不存在或与平台不匹配",
                    "code": 40073,
                }
            )
            continue

        try:
            single = RecommendationRequest(
                article_id=payload.article_id,
                variant_id=variant_id,
                platform=target.platform,
                account_id=target.account_id,
                content_type=shared_content_type,
                target_date=payload.target_date,
                horizon_days=payload.horizon_days,
                with_narrative=False,
                window=payload.window,
                window_start_date=payload.window_start_date,
                window_end_date=payload.window_end_date,
            )
            data, row = await _create_publish_recommendation(single, request, db, user)
            if not shared_content_type:
                shared_content_type = data.get("contentType")
            item = {"platform": target.platform, "success": True, "data": data}
            items.append(item)
            resolved.append(
                {
                    "platform": target.platform,
                    "account_id": target.account_id,
                    "variant_id": variant_id,
                    "variant": variant,
                    "locked_at": target.locked_at,
                    "row": row,
                    "item": item,
                }
            )
        except AppException as exc:
            items.append(
                {
                    "platform": target.platform,
                    "success": False,
                    "message": exc.message,
                    "code": exc.code,
                }
            )

    plan: dict | None = None
    if payload.optimize and resolved:
        plan = await _apply_semantic_optimization(db, article, resolved)

    db.commit()

    success_items = [item for item in items if item.get("success")]
    time_groups: dict[str, list[str]] = {}
    for item in success_items:
        recommended_at = item["data"]["recommendedAt"]
        time_groups.setdefault(recommended_at, []).append(item["platform"])
    overlap_groups = [platforms for platforms in time_groups.values() if len(platforms) > 1]

    return success_response(
        request,
        {
            "articleId": payload.article_id,
            "contentType": shared_content_type,
            "contentTypeName": content_type_name(shared_content_type or "UNKNOWN"),
            "items": items,
            "successCount": len(success_items),
            "failureCount": len(items) - len(success_items),
            "overlapGroups": overlap_groups,
            "hasOverlap": bool(overlap_groups),
            "plan": plan,
        },
        "跨平台推荐时间计算完成",
    )


async def _apply_semantic_optimization(
    db: Session,
    article: ContentArticle,
    resolved: list[dict],
) -> dict:
    """Run the semantic pipeline and fold its result back into each recommendation.

    The hybrid-v2 result is preserved as ``originalBestTime``; ``recommendedAt``
    is only replaced when CP-SAT produced a feasible assignment for that
    platform. Any other outcome leaves the existing recommendation untouched.
    """
    baseline_results = {item["platform"]: item["item"]["data"] for item in resolved}
    result = await run_pipeline(
        db,
        article=article,
        targets=[
            {
                "platform": item["platform"],
                "account_id": item["account_id"],
                "variant_id": item["variant_id"],
                "locked_at": item["locked_at"],
            }
            for item in resolved
        ],
        baseline_results=baseline_results,
    )

    optimization = result["optimization"]
    assignments = assignment_by_platform(optimization)
    profile = result["profile"]
    review = result["review"]

    for entry in resolved:
        platform = entry["platform"]
        row: PublishRecommendation = entry["row"]
        retrieval = result["retrieval"].get(platform) or {}
        estimate = result["activity"].get(platform)
        assignment = assignments.get(platform)

        similar_items = [item for item in retrieval.get("items", []) if item.get("selected")]
        activity_payload = activity_summary(estimate) if estimate else {}
        if estimate:
            activity_payload["hourlyCurve"] = hourly_curve(
                estimate, (row.recommended_at or datetime.now()).weekday()
            )

        row.profile_json = profile
        row.profile_source = result["profileSource"]
        row.similar_history_json = similar_items
        row.activity_estimate_json = activity_payload
        row.review_json = review or {}

        optimization_payload = {
            "pipelineVersion": result["pipelineVersion"],
            "optimizerVersion": optimization.get("optimizerVersion"),
            "solverStatus": optimization.get("solverStatus"),
            "solveDurationMs": optimization.get("solveDurationMs"),
            "objectiveValue": optimization.get("objectiveValue"),
            "hardConstraints": optimization.get("hardConstraints", []),
            "softObjectiveBreakdown": optimization.get("softObjectiveBreakdown", {}),
            "resolvedAfterReview": optimization.get("resolvedAfterReview", False),
            "candidates": (result.get("candidates") or {}).get(platform, [])[:12],
            **(assignment or {}),
        }
        row.optimization_json = optimization_payload

        if assignment and assignment.get("selectedTime"):
            row.recommended_at = datetime.fromisoformat(assignment["selectedTime"])
            row.algorithm_version = result["pipelineVersion"]
            if estimate:
                row.confidence = estimate["confidence"]

        data = entry["item"]["data"]
        data.update(
            {
                "recommendedAt": row.recommended_at.isoformat(),
                "algorithmVersion": row.algorithm_version,
                "confidence": row.confidence,
                "profile": profile,
                "profileSource": result["profileSource"],
                "similarHistory": similar_items,
                "similarHistoryCount": len(similar_items),
                "retrievalProvider": retrieval.get("rerankProvider"),
                "embeddingModel": retrieval.get("queryEmbeddingModel"),
                "activityEstimate": activity_payload,
                "optimization": optimization_payload,
                "review": review,
                "solverStatus": optimization.get("solverStatus"),
                "stageStatus": result["stageStatus"],
                "originalBestTime": (assignment or {}).get("originalBestTime")
                or baseline_results[platform].get("recommendedAt"),
                "optimizationAdjusted": bool((assignment or {}).get("optimizationAdjusted")),
                "adjustmentReason": (assignment or {}).get("adjustmentReason")
                or "联合求解不可用，保留 hybrid-v2 单平台推荐结果",
                "activityScore": (assignment or {}).get("activityScore"),
                "dataConfidence": (assignment or {}).get("dataConfidence"),
            }
        )

    return {
        "pipelineVersion": result["pipelineVersion"],
        "profile": profile,
        "profileSource": result["profileSource"],
        "solverStatus": optimization.get("solverStatus"),
        "solveDurationMs": optimization.get("solveDurationMs"),
        "objectiveValue": optimization.get("objectiveValue"),
        "hardConstraints": optimization.get("hardConstraints", []),
        "softObjectiveBreakdown": optimization.get("softObjectiveBreakdown", {}),
        "review": review,
        "stageStatus": result["stageStatus"],
        "optimizationApplied": bool(assignments),
    }


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
    return success_response(request, _recommendation_payload(row))


@router.get("/activity/curve")
def activity_curve(
    request: Request,
    platform: str = "WEIBO",
    target_date: date | None = None,
    account_id: int | None = None,
    window: str = "90D",
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    day = target_date or date.today()
    try:
        points = curve(
            db,
            platform,
            day,
            account_id=account_id,
            window=window,
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as exc:
        raise AppException(40022, str(exc)) from exc
    return success_response(
        request,
        {
            "platform": platform,
            "date": day.isoformat(),
            "points": points,
            "source": "人工维护规则、公开基线样本与账号历史数据",
        },
    )


@router.get("/activity/content-types")
def content_types(request: Request, _: User = Depends(get_current_user)) -> dict:
    return success_response(
        request,
        [{"value": key, "label": value} for key, value in CONTENT_TYPE_NAMES.items()],
    )


@router.get("/activity/analysis")
def activity_analysis(
    request: Request,
    platform: str = "",
    account_id: int | None = None,
    content_type: str = "",
    source_scope: str = "ALL",
    window: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    if source_scope not in {"ALL", "ACCOUNT", "BASELINE"}:
        raise AppException(40022, "数据范围只能是 ALL / ACCOUNT / BASELINE")
    effective_window = window or ("ALL" if source_scope == "BASELINE" else "90D")
    try:
        result = analyze(
            db,
            platform=platform or None,
            account_id=account_id,
            content_type=normalize_content_type(content_type) if content_type else None,
            source_scope=source_scope,
            window=effective_window,
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as exc:
        raise AppException(40022, str(exc)) from exc
    return success_response(request, result)


@router.get("/activity/slot-evidence")
def activity_slot_evidence(
    request: Request,
    platform: str,
    at: datetime,
    account_id: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    return success_response(request, slot_evidence(db, platform, at, account_id=account_id))


@router.get("/schedules/{schedule_id}/recommendation-basis")
def schedule_recommendation_basis(
    schedule_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    row = db.get(PublishSchedule, schedule_id)
    if not row:
        raise AppException(40407, "排期任务不存在", 404)
    recommendation = (
        db.get(PublishRecommendation, row.recommendation_id) if row.recommendation_id else None
    )
    return success_response(
        request,
        {
            "scheduleId": row.id,
            "timeSource": row.time_source,
            "scheduledAt": row.scheduled_at.isoformat(),
            "recommendedAt": row.recommended_at.isoformat() if row.recommended_at else None,
            "deviationMinutes": (
                int((row.scheduled_at - row.recommended_at).total_seconds() // 60)
                if row.recommended_at
                else None
            ),
            "contentType": row.content_type,
            "contentTypeName": content_type_name(row.content_type),
            "snapshot": row.recommendation_snapshot_json or {},
            "recommendation": _recommendation_payload(recommendation) if recommendation else None,
            "slotEvidence": slot_evidence(
                db, row.platform, row.scheduled_at, account_id=row.account_id
            ),
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
