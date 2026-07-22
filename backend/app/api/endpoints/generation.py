import asyncio
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.exceptions import AppException
from app.core.responses import success_response
from app.db.session import SessionLocal, get_db
from app.models.business import ContentArticle, ContentVariant, GenerationTask
from app.models.user import User
from app.prompts.profiles import PROMPT_VERSION
from app.schemas.business import GenerateRequest, KeywordRequest, Platform
from app.services.audit_service import record_audit
from app.services.generation_service import (
    extract_keywords_with_llm,
    generate_content_brief,
    generate_deep_variant_data,
    generate_variant_data,
    load_llm_runtime,
    review_variant_quality,
    save_variant,
)
from app.services.serializers import model_dict

router = APIRouter(tags=["AI 内容生成"])


def _initial_platform_status(platforms: list[str]) -> dict[str, dict[str, Any]]:
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
    db.commit()
    return task


async def _run_generation_task(task_id: str) -> None:
    started = time.perf_counter()
    lock = asyncio.Lock()

    async def update_platform(platform: str, status: str, detail: dict[str, Any]) -> None:
        async with lock:
            with SessionLocal() as state_db:
                task = state_db.get(GenerationTask, task_id)
                if not task:
                    return
                states = dict(task.platform_status_json or {})
                state = dict(states.get(platform, {}))
                previous_progress = int(state.get("progress", 0))
                state.update(detail)
                state["status"] = status
                fallback_progress = {
                    "PENDING": 0,
                    "RUNNING": 35,
                    "RETRYING": 65,
                    "SUCCESS": 100,
                    "FAILED": 100,
                }[status]
                state["progress"] = max(
                    previous_progress, int(detail.get("progress", fallback_progress))
                )
                state["updatedAt"] = datetime.now(UTC).isoformat()
                states[platform] = state
                task.platform_status_json = states
                task.progress = int(
                    sum(int(item.get("progress", 0)) for item in states.values())
                    / max(1, len(states))
                )
                task.status = "RUNNING"
                state_db.commit()

    try:
        with SessionLocal() as db:
            task = db.get(GenerationTask, task_id)
            if not task:
                return
            article = db.get(ContentArticle, task.article_id)
            if not article:
                task.status = "FAILED"
                task.error_message = "文章不存在"
                db.commit()
                return
            runtime = load_llm_runtime(db)
            options = dict(task.options_json or {})
            task.status = "RUNNING"
            db.commit()

            brief: dict[str, Any] | None = None
            shared_prompt_tokens = 0
            shared_completion_tokens = 0
            if options.get("generation_mode") == "DEEP":
                for platform in task.platforms_json:
                    await update_platform(
                        platform,
                        "RUNNING",
                        {
                            "progress": 8,
                            "stage": "ANALYZING_SOURCE",
                            "message": "正在提取原文核心论点、事实边界和信息缺口",
                        },
                    )
                (
                    brief,
                    shared_prompt_tokens,
                    shared_completion_tokens,
                ) = await generate_content_brief(runtime, article, options)
                for platform in task.platforms_json:
                    await update_platform(
                        platform,
                        "RUNNING",
                        {
                            "progress": 18,
                            "stage": "SOURCE_ANALYZED",
                            "message": "原文事实简报已完成，准备制定平台策略",
                            "brief": brief,
                        },
                    )

            async def run_one(platform: str):
                async def callback(status: str, detail: dict[str, Any]) -> None:
                    await update_platform(platform, status, detail)

                if options.get("generation_mode") == "DEEP" and brief is not None:
                    return await generate_deep_variant_data(
                        db,
                        article,
                        platform,
                        options,
                        brief,
                        status_callback=callback,
                        runtime=runtime,
                    )
                return await generate_variant_data(
                    db, article, platform, options, status_callback=callback, runtime=runtime
                )

            results = await asyncio.gather(
                *(run_one(platform) for platform in task.platforms_json),
                return_exceptions=True,
            )

            variant_ids: list[int] = []
            errors: list[str] = []
            total_tokens = shared_prompt_tokens + shared_completion_tokens
            total_duration = 0
            for platform, result in zip(task.platforms_json, results, strict=True):
                if isinstance(result, BaseException):
                    message = (
                        getattr(result, "message", None) or str(result) or type(result).__name__
                    )
                    errors.append(f"{platform}: {message}")
                    await update_platform(
                        platform,
                        "FAILED",
                        {
                            "progress": 100,
                            "stage": "FAILED",
                            "message": "生成失败，可单独重试此平台",
                            "error": message,
                        },
                    )
                    continue
                await update_platform(
                    platform,
                    "RUNNING",
                    {
                        "progress": 90,
                        "stage": "SAVING_RESULT",
                        "message": "模型输出已通过校验，正在保存版本",
                        "strategy": result.strategy,
                        "review": result.review_detail,
                        "candidateTitles": result.candidate_titles,
                        "selectedCandidate": result.selected_candidate,
                    },
                )
                variant = save_variant(db, article, platform, result)
                db.commit()
                db.refresh(variant)
                variant_ids.append(variant.id)
                token_usage = result.prompt_tokens + result.completion_tokens
                total_tokens += token_usage
                total_duration = max(total_duration, result.duration_ms)
                await update_platform(
                    platform,
                    "SUCCESS",
                    {
                        "variantId": variant.id,
                        "progress": 100,
                        "stage": "COMPLETED",
                        "message": "平台版本已生成",
                        "attempt": result.attempts,
                        "error": None,
                        "durationMs": result.duration_ms,
                        "tokenUsage": token_usage,
                    },
                )

            task = db.get(GenerationTask, task_id)
            if not task:
                return
            task.result_variant_ids_json = variant_ids
            task.progress = 100
            task.token_usage = total_tokens
            task.duration_ms = max(total_duration, int((time.perf_counter() - started) * 1000))
            task.error_message = "；".join(errors) or None
            if variant_ids and errors:
                task.status = "PARTIAL_SUCCESS"
            elif variant_ids:
                task.status = "SUCCESS"
            else:
                task.status = "FAILED"
            if variant_ids:
                article.status = "GENERATED"
            db.commit()
    except Exception as exc:
        with SessionLocal() as db:
            task = db.get(GenerationTask, task_id)
            if task:
                task.status = "FAILED"
                task.progress = 100
                task.duration_ms = int((time.perf_counter() - started) * 1000)
                task.error_message = str(exc) or type(exc).__name__
                db.commit()


@router.post("/generation/content")
async def generate(
    payload: GenerateRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    article = db.get(ContentArticle, payload.article_id)
    if not article:
        raise AppException(40401, "文章不存在", 404)
    if not payload.target_audience:
        payload.target_audience = article.target_audience
    task = _create_task(db, payload)
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
    data = model_dict(task, camel=True)
    if task.result_variant_ids_json:
        variants = (
            db.query(ContentVariant)
            .filter(ContentVariant.id.in_(task.result_variant_ids_json))
            .all()
        )
        order = {variant_id: index for index, variant_id in enumerate(task.result_variant_ids_json)}
        data["variants"] = [
            model_dict(item, camel=True) for item in sorted(variants, key=lambda x: order[x.id])
        ]
    else:
        data["variants"] = []
    return success_response(request, data)


@router.post("/generation/tasks/{task_id}/platforms/{platform}/retry")
async def retry_task_platform(
    task_id: str,
    platform: Platform,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
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
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    old = db.get(ContentVariant, variant_id)
    if not old:
        raise AppException(40402, "内容版本不存在", 404)
    article = db.get(ContentArticle, old.article_id)
    payload = GenerateRequest(
        article_id=old.article_id,
        platforms=[old.platform],
        style=article.tone or "专业自然",
        target_audience=article.target_audience,
    )
    task = _create_task(db, payload)
    background_tasks.add_task(_run_generation_task, task.id)
    return success_response(
        request, {"taskId": task.id, "status": task.status}, "重新生成任务已创建"
    )


@router.post("/generation/keywords")
async def keywords(
    payload: KeywordRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
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
    _: User = Depends(get_current_user),
) -> dict:
    variant = db.get(ContentVariant, payload.article_id)
    if not variant:
        raise AppException(40402, "内容版本不存在", 404)
    result, provider = await review_variant_quality(db, variant.article, variant)
    dimension_keys = (
        "factual_consistency",
        "information_completeness",
        "platform_fit",
        "readability",
        "format_compliance",
    )
    score = round(sum(float(result[key]) for key in dimension_keys) / len(dimension_keys), 1)
    variant.quality_score = score
    variant.review_detail_json = result
    db.commit()
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
            "needHumanReview": bool(result["issues"] or score < 85),
            "provider": provider,
            "ruleReview": result.get("ruleReview", {}),
            "semanticReview": result.get("semanticReview"),
        },
    )
