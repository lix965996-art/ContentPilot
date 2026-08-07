"""Orchestration for the semantic cross-platform scheduling pipeline.

Stages (each degrades independently, never raising to the endpoint):

    1. LLM content schedule profile          content_schedule_profile_service
    2. Semantic similar-history retrieval    semantic_history_retrieval_service
    3. Weighted user-activity estimation     activity_estimation_service
    4. Candidate slot generation + CP-SAT    schedule_optimization_service
    5. LLM plan review (at most one re-solve) schedule_plan_review_service

The existing hybrid-v2 per-platform recommendation is computed by the endpoint
before this pipeline runs: it supplies ``original_best_time`` for every platform
and stays the fallback result whenever OR-Tools is unavailable or infeasible.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.business import ContentArticle, ContentVariant, PublishSchedule
from app.services import (
    activity_estimation_service,
    content_embedding_service,
    content_schedule_profile_service,
    schedule_optimization_service,
    schedule_plan_review_service,
    semantic_history_retrieval_service,
)
from app.services.activity_service import content_type_name

PIPELINE_VERSION = "semantic-cpsat-v1"
ACTIVE_SCHEDULE_STATUSES = ("PENDING", "RUNNING", "AWAITING_CONFIRM")


def _active_schedules(
    db: Session, now: datetime
) -> list[schedule_optimization_service.ExistingSchedule]:
    rows = db.scalars(
        select(PublishSchedule).where(
            PublishSchedule.status.in_(ACTIVE_SCHEDULE_STATUSES),
            PublishSchedule.scheduled_at >= now,
        )
    ).all()
    return [
        schedule_optimization_service.ExistingSchedule(
            platform=row.platform,
            account_id=row.account_id,
            scheduled_at=row.scheduled_at,
        )
        for row in rows
    ]


def _similarity_by_history_row(retrieval: dict) -> dict[int, float]:
    """Map ``engagement_history.id`` → weight, from selected candidates only.

    Vector similarity and LLM relevance are blended so the activity estimate
    reflects both the coarse retrieval and the semantic re-rank.
    """
    mapping: dict[int, float] = {}
    for item in retrieval.get("items", []):
        if not item.get("selected") or item.get("refType") != "HISTORY":
            continue
        relevance = float(item.get("llmRelevance") or 0) / 100
        vector = max(0.0, float(item.get("vectorSimilarity") or 0))
        mapping[int(item["historicalContentId"])] = max(0.05, 0.5 * vector + 0.5 * relevance)
    return mapping


def _semantic_slot_scores(estimate: dict, has_similar: bool) -> dict[tuple[int, int], float]:
    """Slot score attributable specifically to semantically similar history."""
    scores: dict[tuple[int, int], float] = {}
    for entry in estimate.get("slots", {}).values():
        key = (entry["dayOfWeek"], entry["hour"])
        observed = entry.get("observedScore")
        if has_similar and observed is not None:
            scores[key] = float(observed)
        else:
            # No direct similar-content evidence for this slot: keep a damped
            # signal so S2 never dominates on borrowed prior data.
            scores[key] = float(entry["score"]) * 0.6
    return scores


_CONFIDENCE_SCORE = {"HIGH": 90.0, "MEDIUM": 60.0, "LOW": 30.0}


def _baseline_time(baseline: dict) -> datetime | None:
    value = baseline.get("recommendedAt")
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


async def run_pipeline(
    db: Session,
    *,
    article: ContentArticle,
    targets: list[dict],
    baseline_results: dict[str, dict],
    horizon_days: int = 7,
) -> dict:
    """Execute the full pipeline.

    ``targets`` items: ``{platform, account_id, variant_id, locked_at}``.
    ``baseline_results`` maps platform → the hybrid-v2 recommendation payload,
    whose ``recommendedAt`` becomes the optimiser's ``original_best_time``.

    Returns ``{pipelineVersion, profile, profileSource, retrieval, activity,
    candidates, optimization, review, stageStatus}``. ``optimization["assignments"]``
    is empty whenever the solver could not produce a plan, which is the caller's
    signal to keep the hybrid-v2 result untouched.
    """
    now = datetime.now()
    stage_status: dict[str, str] = {}
    platforms = [item["platform"] for item in targets]

    # H6: a target without a platform content version can never be scheduled.
    schedulable: list[dict] = []
    variants: list[ContentVariant] = []
    for item in targets:
        variant = db.get(ContentVariant, item["variant_id"]) if item.get("variant_id") else None
        if variant is None:
            continue
        schedulable.append({**item, "variant": variant})
        variants.append(variant)

    # ---- Stage 1: LLM content schedule profile ------------------------------
    profile, profile_source = await content_schedule_profile_service.build_profile(
        db, article, variants, platforms
    )
    profile_dict = profile.model_dump()
    profile_dict["contentTypeName"] = content_type_name(profile.content_type)
    stage_status["profile"] = profile_source

    retrieval_by_platform: dict[str, dict] = {}
    activity_by_platform: dict[str, dict] = {}
    candidates_by_platform: dict[str, list[schedule_optimization_service.Candidate]] = {}
    solver_targets: list[schedule_optimization_service.PlatformTarget] = []

    existing = _active_schedules(db, now)
    context = schedule_optimization_service.default_context(
        now=now,
        freshness_hours=profile.freshness_hours,
        urgency=profile.urgency,
        cross_platform_strategy=profile.cross_platform_strategy,
        minimum_gap_minutes=profile.minimum_cross_platform_gap_minutes,
        platform_priority=profile.platform_priority,
        horizon_days=horizon_days,
    )

    for item in schedulable:
        platform = item["platform"]
        variant = item["variant"]

        # ---- Stage 2: semantic similar-history retrieval --------------------
        query_text = content_embedding_service.article_text(article, variant)
        try:
            retrieval = await semantic_history_retrieval_service.retrieve_similar_history(
                db,
                platform=platform,
                account_id=item.get("account_id"),
                query_text=query_text,
                profile=profile_dict,
                exclude_article_id=article.id,
            )
            retrieval["retrievalMode"] = retrieval.get("rerankProvider", "VECTOR_ONLY")
        except Exception:  # noqa: BLE001 - retrieval must never break scheduling
            retrieval = {
                "items": [],
                "rerankProvider": "UNAVAILABLE",
                "retrievalMode": "UNAVAILABLE",
                "candidateCount": 0,
                "queryEmbeddingModel": "",
            }
        retrieval_by_platform[platform] = retrieval

        # ---- Stage 3: weighted activity estimation --------------------------
        similarity = _similarity_by_history_row(retrieval)
        estimate = activity_estimation_service.estimate(
            db,
            platform=platform,
            account_id=item.get("account_id"),
            similarity_by_row=similarity,
            now=now,
        )
        activity_by_platform[platform] = estimate
        semantic_scores = _semantic_slot_scores(estimate, bool(similarity))

        target = schedule_optimization_service.PlatformTarget(
            platform=platform,
            account_id=item.get("account_id"),
            variant_id=variant.id,
            original_best_time=_baseline_time(baseline_results.get(platform) or {}),
            locked_time=item.get("locked_at"),
            priority_rank=(
                profile.platform_priority.index(platform)
                if platform in profile.platform_priority
                else len(profile.platform_priority)
            ),
            data_confidence=_CONFIDENCE_SCORE.get(estimate["confidence"], 30.0),
        )
        solver_targets.append(target)

        # ---- Stage 4a: candidate slot generation ----------------------------
        candidates_by_platform[platform] = schedule_optimization_service.build_candidates(
            target,
            context,
            activity_slot_score=lambda weekday, hour, _e=estimate: (
                activity_estimation_service.slot_score(_e, weekday, hour)
            ),
            semantic_slot_score=lambda weekday, hour, _s=semantic_scores: _s.get(
                (weekday, hour), 0.0
            ),
            reading_mode=profile.reading_mode,
            cognitive_load=profile.cognitive_load,
            existing=existing,
        )

    stage_status["retrieval"] = (
        "OK" if any(item.get("items") for item in retrieval_by_platform.values()) else "NO_HISTORY"
    )
    stage_status["activity"] = "OK" if activity_by_platform else "SKIPPED"

    if not solver_targets:
        stage_status["optimization"] = "NO_TARGET"
        return {
            "pipelineVersion": PIPELINE_VERSION,
            "profile": profile_dict,
            "profileSource": profile_source,
            "retrieval": retrieval_by_platform,
            "activity": activity_by_platform,
            "candidates": {},
            "optimization": {
                "solverStatus": "NO_TARGET",
                "assignments": [],
                "solveDurationMs": 0,
                "hardConstraints": [],
                "softObjectiveBreakdown": {},
                "message": "没有可排期的平台目标（缺少平台内容版本）",
            },
            "review": None,
            "stageStatus": stage_status,
        }

    # ---- Stage 4b: CP-SAT joint solve --------------------------------------
    optimization = schedule_optimization_service.optimize(
        solver_targets, candidates_by_platform, context
    )
    stage_status["optimization"] = optimization["solverStatus"]

    # ---- Stage 5: LLM plan review (at most one re-solve) -------------------
    review: dict | None = None
    if optimization.get("assignments"):
        plan_facts = schedule_plan_review_service.build_plan_facts(
            profile=profile_dict,
            platform_contents=[
                {
                    "platform": variant.platform,
                    "title": variant.title,
                    "wordCount": variant.word_count,
                    "reviewStatus": variant.review_status,
                }
                for variant in variants
            ],
            activity_summaries=[
                {
                    "platform": platform,
                    "confidence": estimate["confidence"],
                    "primaryLevel": estimate["primaryLevel"],
                    "effectiveSampleCount": estimate["effectiveSampleCount"],
                    "similarSampleCount": estimate["similarSampleCount"],
                }
                for platform, estimate in activity_by_platform.items()
            ],
            optimization=optimization,
        )
        review = await schedule_plan_review_service.review_plan(db, plan_facts)

        if review.get("verdict") == "REQUEST_RESOLVE":
            resolve = review.get("resolve_request") or {}
            order = resolve.get("platform_order") or []
            if order:
                context.platform_priority = order
            resolved = schedule_optimization_service.optimize(
                solver_targets,
                candidates_by_platform,
                context,
                extra_min_gap_minutes=resolve.get("minimum_cross_platform_gap_minutes"),
            )
            applied = bool(resolved.get("assignments"))
            if applied:
                optimization = resolved
                optimization["resolvedAfterReview"] = True
                stage_status["optimization"] = resolved["solverStatus"]
            review["resolveApplied"] = applied
            review["resolveRounds"] = schedule_plan_review_service.MAX_RESOLVE_ROUNDS

    stage_status["review"] = (review or {}).get("provider", "SKIPPED")

    return {
        "pipelineVersion": PIPELINE_VERSION,
        "profile": profile_dict,
        "profileSource": profile_source,
        "retrieval": retrieval_by_platform,
        "activity": activity_by_platform,
        "candidates": {
            platform: [candidate.as_dict() for candidate in items]
            for platform, items in candidates_by_platform.items()
        },
        "optimization": optimization,
        "review": review,
        "stageStatus": stage_status,
    }


def assignment_by_platform(optimization: dict) -> dict[str, dict]:
    """Only platforms the solver actually placed a time on."""
    return {
        item["platform"]: item
        for item in optimization.get("assignments", [])
        if item.get("selectedTime")
    }


def activity_summary(estimate: dict) -> dict:
    """Compact, JSON-safe activity payload for storage and API responses."""
    return {
        "estimatorVersion": estimate.get("estimatorVersion"),
        "confidence": estimate.get("confidence"),
        "primaryLevel": estimate.get("primaryLevel"),
        "primaryLevelLabel": estimate.get("primaryLevelLabel"),
        "priorChain": estimate.get("priorChain"),
        "levelSampleCounts": estimate.get("levelSampleCounts"),
        "levelMeans": estimate.get("levelMeans"),
        "decayDays": estimate.get("decayDays"),
        "priorStrength": estimate.get("priorStrength"),
        "coveredSlots": estimate.get("coveredSlots"),
        "similarSampleCount": estimate.get("similarSampleCount"),
        "accountSampleCount": estimate.get("accountSampleCount"),
        "platformSampleCount": estimate.get("platformSampleCount"),
        "baselineSampleCount": estimate.get("baselineSampleCount"),
        "crossPlatformSampleCount": estimate.get("crossPlatformSampleCount"),
        "effectiveSampleCount": estimate.get("effectiveSampleCount"),
    }
