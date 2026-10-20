import uuid
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.exceptions import AppException
from app.core.responses import success_response
from app.db.session import get_db
from app.models.business import ContentArticle, ContentVariant, GenerationTask
from app.models.user import User
from app.prompts.profiles import PROMPT_VERSION
from app.schemas.business import (
    DeepCandidateSelectRequest,
    DeepRegenerateRequest,
    GenerateRequest,
    KeywordRequest,
    Platform,
)
from app.services.activity_service import business_now
from app.services.audit_service import record_audit
from app.services.generation_service import (
    GenerationResult,
    extract_keywords_with_llm,
    load_llm_runtime,
    review_variant_quality,
    save_variant,
)
from app.services.generation_task_service import (
    run_generation_task as _run_generation_task,
)
from app.services.review_fingerprint import (
    commit_content_change,
    content_fingerprint,
    variant_fingerprint,
)
from app.services.serializers import model_dict
from app.services.task_dispatch_service import (
    TASK_TYPE_GENERATION,
    upsert_dispatch,
)

router = APIRouter(tags=["AI 内容生成"])


def _initial_platform_status(platforms: list[Platform]) -> dict[str, dict[str, Any]]:
    return {
        platform: {
            "status": "PENDING",
            "progress": 0,
            "stage": "QUEUED",
            "message": "已进入队列，等待开始处理",
            "attempt": 0,
            "variantId": None,
            "error": None,
            "durationMs": 0,
            "tokenUsage": 0,
            "updatedAt": datetime.now(UTC).isoformat(),
        }
        for platform in platforms
    }


def _create_task(db: Session, payload: GenerateRequest) -> GenerationTask:
    runtime = load_llm_runtime(db)
    task = GenerationTask(
        id=str(uuid.uuid4()),
        article_id=payload.article_id,
        status="PENDING",
        progress=0,
        platforms_json=payload.platforms,
        result_variant_ids_json=[],
        model_name=runtime.model_name,
        provider=runtime.provider,
        prompt_version=PROMPT_VERSION,
        token_usage=0,
        duration_ms=0,
        platform_status_json=_initial_platform_status(payload.platforms),
        options_json=payload.model_dump(mode="json"),
    )
    db.add(task)
    db.flush()
    return task


def _enqueue_generation_dispatch(db: Session, task: GenerationTask) -> None:
    """Write the dispatch intent in the same transaction as the task row."""
    upsert_dispatch(
        db,
        task_type=TASK_TYPE_GENERATION,
        task_id=task.id,
        revision=task.id,
        run_at=business_now(),
    )


def _task_data(db: Session, task: GenerationTask) -> dict[str, Any]:
    data = model_dict(task, camel=True)
    if task.result_variant_ids_json:
        variants = (
            db.query(ContentVariant)
            .filter(ContentVariant.id.in_(task.result_variant_ids_json))
            .all()
        )
        order = {variant_id: index for index, variant_id in enumerate(task.result_variant_ids_json)}
        article = db.get(ContentArticle, task.article_id)
        source_text = article.source_text if article else ""
        payloads = []
        for item in sorted(variants, key=lambda item: order[item.id]):
            variant_data = model_dict(item, camel=True)
            variant_data["contentFingerprint"] = content_fingerprint(
                platform=item.platform,
                title=item.title,
                content=item.content_text,
                hashtags=item.hashtags_json,
                source_text=source_text,
            )
            payloads.append(variant_data)
        data["variants"] = payloads
    else:
        data["variants"] = []
    return data


@router.post("/generation/content")
async def generate(
    payload: GenerateRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    article = db.get(ContentArticle, payload.article_id)
    if not article:
        raise AppException(40401, "文章不存在", 404)
    if not payload.target_audience:
        payload.target_audience = article.target_audience
    task = _create_task(db, payload)
    _enqueue_generation_dispatch(db, task)
    record_audit(
        db,
        request,
        user,
        "GENERATE",
        "AI",
        "ARTICLE",
        article.id,
        {"platforms": payload.platforms, "taskId": task.id, "options": task.options_json},
    )
    db.commit()
    background_tasks.add_task(_run_generation_task, task.id)
    return success_response(request, {"taskId": task.id, "status": task.status}, "生成任务已创建")


@router.get("/generation/tasks/{task_id}")
def task_status(
    task_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    task = db.get(GenerationTask, task_id)
    if not task:
        raise AppException(40403, "生成任务不存在", 404)
    return success_response(request, _task_data(db, task))


@router.get("/generation/articles/{article_id}/latest-deep-task")
def latest_deep_task(
    article_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    tasks = db.scalars(
        select(GenerationTask)
        .where(GenerationTask.article_id == article_id)
        .order_by(GenerationTask.created_at.desc())
        .limit(30)
    ).all()
    task = next(
        (item for item in tasks if (item.options_json or {}).get("generation_mode") == "DEEP"),
        None,
    )
    return success_response(request, _task_data(db, task) if task else None)


@router.post("/generation/tasks/{task_id}/platforms/{platform}/select-candidate")
def select_deep_candidate(
    task_id: str,
    platform: Platform,
    payload: DeepCandidateSelectRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    task = db.get(GenerationTask, task_id)
    if not task:
        raise AppException(40403, "生成任务不存在", 404)
    if (task.options_json or {}).get("generation_mode") != "DEEP":
        raise AppException(40032, "该任务不是深度创作任务")
    state = dict((task.platform_status_json or {}).get(platform, {}))
    candidates = state.get("candidates") or []
    if len(candidates) != 2:
        raise AppException(40931, "候选稿尚未生成完成", 409)
    article = db.get(ContentArticle, task.article_id)
    if not article:
        raise AppException(40401, "文章不存在", 404)

    candidate = dict(candidates[payload.candidate_index])
    result = GenerationResult(
        data=candidate,
        model_name=task.model_name,
        provider=task.provider,
        duration_ms=0,
        prompt_tokens=0,
        completion_tokens=0,
        attempts=0,
        strategy=state.get("strategy"),
    )
    variant = save_variant(db, article, platform, result)
    review_detail = dict(variant.review_detail_json or {})
    review_detail.update(
        {
            "strategy": state.get("strategy"),
            "humanSelection": {
                "candidateIndex": payload.candidate_index,
                "sourceTaskId": task.id,
            },
        }
    )
    variant.review_detail_json = review_detail
    db.flush()

    states = dict(task.platform_status_json or {})
    state.update(
        {
            "userSelectedCandidate": payload.candidate_index,
            "userSelectedVariantId": variant.id,
            "message": f"已采用候选稿 {payload.candidate_index + 1}，并保存为新版本",
            "updatedAt": datetime.now(UTC).isoformat(),
        }
    )
    states[platform] = state
    task.platform_status_json = states
    result_ids = list(task.result_variant_ids_json or [])
    result_ids.append(variant.id)
    task.result_variant_ids_json = result_ids
    record_audit(
        db,
        request,
        user,
        "SELECT_DEEP_CANDIDATE",
        "AI",
        "GENERATION_TASK",
        task.id,
        {
            "platform": platform,
            "candidateIndex": payload.candidate_index,
            "variantId": variant.id,
        },
    )
    db.commit()
    db.refresh(variant)
    db.refresh(task)
    variant_data = model_dict(variant, camel=True)
    variant_data["contentFingerprint"] = variant_fingerprint(variant)
    return success_response(
        request,
        {"variant": variant_data, "task": _task_data(db, task)},
        "候选稿已保存为新版本",
    )


@router.post("/generation/tasks/{task_id}/platforms/{platform}/regenerate")
async def regenerate_deep_platform(
    task_id: str,
    platform: Platform,
    payload: DeepRegenerateRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    previous = db.get(GenerationTask, task_id)
    if not previous:
        raise AppException(40403, "生成任务不存在", 404)
    if (previous.options_json or {}).get("generation_mode") != "DEEP":
        raise AppException(40032, "该任务不是深度创作任务")
    if platform not in previous.platforms_json:
        raise AppException(40031, "该平台不属于原生成任务")
    options = dict(previous.options_json or {})
    existing_requirements = str(options.get("creative_requirements") or "").strip()
    combined_requirements = "\n".join(
        item for item in (existing_requirements, f"本轮修改意见：{payload.feedback}") if item
    )[-1000:]
    options.update(
        {
            "article_id": previous.article_id,
            "platforms": [platform],
            "creative_requirements": combined_requirements,
        }
    )
    task = _create_task(db, GenerateRequest.model_validate(options))
    _enqueue_generation_dispatch(db, task)
    record_audit(
        db,
        request,
        user,
        "REGENERATE_DEEP_PLATFORM",
        "AI",
        "GENERATION_TASK",
        task.id,
        {"sourceTaskId": task_id, "platform": platform, "feedback": payload.feedback},
    )
    db.commit()
    background_tasks.add_task(_run_generation_task, task.id)
    return success_response(
        request,
        {"taskId": task.id, "status": task.status},
        "已按修改意见创建新的深度创作任务",
    )


@router.post("/generation/tasks/{task_id}/platforms/{platform}/retry")
async def retry_task_platform(
    task_id: str,
    platform: Platform,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    previous = db.get(GenerationTask, task_id)
    if not previous:
        raise AppException(40403, "生成任务不存在", 404)
    if platform not in previous.platforms_json:
        raise AppException(40031, "该平台不属于原生成任务")
    options = dict(previous.options_json or {})
    options.update({"article_id": previous.article_id, "platforms": [platform]})
    payload = GenerateRequest.model_validate(options)
    task = _create_task(db, payload)
    _enqueue_generation_dispatch(db, task)
    record_audit(
        db,
        request,
        user,
        "RETRY_PLATFORM",
        "AI",
        "GENERATION_TASK",
        task.id,
        {"sourceTaskId": task_id, "platform": platform},
    )
    db.commit()
    background_tasks.add_task(_run_generation_task, task.id)
    return success_response(
        request, {"taskId": task.id, "status": task.status}, "平台重试任务已创建"
    )


@router.post("/generation/content/{variant_id}/regenerate")
async def regenerate(
    variant_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    old = db.get(ContentVariant, variant_id)
    if not old:
        raise AppException(40402, "内容版本不存在", 404)
    article = db.get(ContentArticle, old.article_id)
    if not article:
        raise AppException(40401, "内容文章不存在", 404)
    payload = GenerateRequest(
        article_id=old.article_id,
        platforms=[cast(Platform, old.platform)],
        style=article.tone or "专业自然",
        target_audience=article.target_audience,
    )
    task = _create_task(db, payload)
    _enqueue_generation_dispatch(db, task)
    db.commit()
    background_tasks.add_task(_run_generation_task, task.id)
    return success_response(
        request, {"taskId": task.id, "status": task.status}, "重新生成任务已创建"
    )


@router.post("/generation/keywords")
async def keywords(
    payload: KeywordRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("OPERATOR")),
) -> dict:
    article = db.get(ContentArticle, payload.article_id)
    if not article:
        raise AppException(40401, "文章不存在", 404)
    items, provider = await extract_keywords_with_llm(
        db, article.title + "\n" + article.source_text
    )
    return success_response(request, {"keywords": items, "provider": provider})


@router.post("/generation/review")
async def review(
    payload: KeywordRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("OPERATOR")),
) -> dict:
    variant = db.get(ContentVariant, payload.article_id)
    if not variant:
        raise AppException(40402, "内容版本不存在", 404)
    fingerprint_before = content_fingerprint(
        platform=variant.platform,
        title=variant.title,
        content=variant.content_text,
        hashtags=variant.hashtags_json,
        source_text=variant.article.source_text,
    )
    revision_before = variant.content_revision
    result, provider = await review_variant_quality(db, variant.article, variant)
    # Lock only after the slow model call, in the same article -> variant order
    # as source edits. Locking reads also see committed changes on MySQL.
    db.scalar(
        select(ContentArticle)
        .where(ContentArticle.id == variant.article_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    variant = db.scalar(
        select(ContentVariant)
        .where(ContentVariant.id == variant.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if variant is None:
        raise AppException(40907, "评审期间内容版本已删除，请刷新后重试", 409)
    fingerprint_after = content_fingerprint(
        platform=variant.platform,
        title=variant.title,
        content=variant.content_text,
        hashtags=variant.hashtags_json,
        source_text=variant.article.source_text,
    )
    if fingerprint_after != fingerprint_before or variant.content_revision != revision_before:
        raise AppException(
            40907,
            "评审期间内容已被修改，评审结果已过期，请重新评审",
            409,
        )
    dimension_keys = (
        "factual_consistency",
        "information_completeness",
        "platform_fit",
        "readability",
        "format_compliance",
    )
    score = round(sum(float(result[key]) for key in dimension_keys) / len(dimension_keys), 1)
    need_human_review = bool(
        result.get("needHumanReview")
        or provider == "RULE_FALLBACK"
        or result["issues"]
        or score < 85
    )
    result = {**result, "provider": provider, "needHumanReview": need_human_review}
    variant.quality_score = score
    variant.review_detail_json = result
    variant.review_fingerprint = fingerprint_after
    commit_content_change(db, code=40907)
    return success_response(
        request,
        {
            "overallScore": score,
            "factualConsistency": result["factual_consistency"],
            "informationCompleteness": result["information_completeness"],
            "platformFit": result["platform_fit"],
            "readability": result["readability"],
            "formatCompliance": result["format_compliance"],
            "issues": result["issues"],
            "suggestions": result["suggestions"],
            "needHumanReview": need_human_review,
            "provider": provider,
            "reviewSource": result.get("reviewSource", provider),
            "factCheckStatus": result.get("factCheckStatus"),
            "factCheckIssues": result.get("factCheckIssues", []),
            "ruleReview": result.get("ruleReview", {}),
            "semanticReview": result.get("semanticReview"),
        },
    )
