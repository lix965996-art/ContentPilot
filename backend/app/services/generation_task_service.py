"""Background execution of persisted generation tasks.

Separated from the HTTP endpoint module so the scheduler can dispatch
generation work without importing the API layer.
"""

import asyncio
import time
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import update

from app.db.session import SessionLocal
from app.models.business import ContentArticle, GenerationTask
from app.services.generation_service import (
    generate_content_brief,
    generate_deep_variant_data,
    generate_variant_data,
    load_llm_runtime,
    save_variant,
)


async def run_generation_task(task_id: str) -> None:
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
            claimed = db.execute(
                update(GenerationTask)
                .where(
                    GenerationTask.id == task_id,
                    GenerationTask.status == "PENDING",
                )
                .values(status="RUNNING")
            )
            db.commit()
            if claimed.rowcount != 1:
                # Another dispatcher already claimed this task, or it was
                # completed/interrupted by recovery.
                return
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

                # Each concurrent task gets its own session to avoid any risk of
                # shared-state issues. In practice runtime is pre-loaded so this
                # session is only a fallback for load_llm_runtime().
                task_db = SessionLocal()
                try:
                    if options.get("generation_mode") == "DEEP" and brief is not None:
                        return await generate_deep_variant_data(
                            task_db,
                            article,
                            platform,
                            options,
                            brief,
                            status_callback=callback,
                            runtime=runtime,
                        )
                    return await generate_variant_data(
                        task_db,
                        article,
                        platform,
                        options,
                        status_callback=callback,
                        runtime=runtime,
                    )
                finally:
                    task_db.close()

            results = await asyncio.gather(
                *(run_one(platform) for platform in task.platforms_json),
                return_exceptions=True,
            )

            successful_result_count = sum(
                not isinstance(result, BaseException) for result in results
            )
            successful_result_index = 0
            variant_ids: list[int] = []
            errors: list[str] = []
            total_tokens = (
                0 if successful_result_count else shared_prompt_tokens + shared_completion_tokens
            )
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
                if successful_result_count:
                    prompt_share, prompt_remainder = divmod(
                        shared_prompt_tokens, successful_result_count
                    )
                    completion_share, completion_remainder = divmod(
                        shared_completion_tokens, successful_result_count
                    )
                    result = replace(
                        result,
                        prompt_tokens=result.prompt_tokens
                        + prompt_share
                        + int(successful_result_index < prompt_remainder),
                        completion_tokens=result.completion_tokens
                        + completion_share
                        + int(successful_result_index < completion_remainder),
                    )
                    successful_result_index += 1
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
                        "candidates": result.candidates,
                        "selectedCandidate": result.selected_candidate,
                    },
                )
                try:
                    variant = save_variant(db, article, platform, result)
                    db.commit()
                    variant_id = variant.id
                except Exception as exc:
                    db.rollback()
                    message = getattr(exc, "message", None) or str(exc) or type(exc).__name__
                    errors.append(f"{platform}: 保存生成结果失败（{message}）")
                    await update_platform(
                        platform,
                        "FAILED",
                        {
                            "progress": 100,
                            "stage": "FAILED",
                            "message": "生成结果保存失败，可单独重试此平台",
                            "error": message,
                        },
                    )
                    continue
                variant_ids.append(variant_id)
                token_usage = result.prompt_tokens + result.completion_tokens
                total_tokens += token_usage
                total_duration = max(total_duration, result.duration_ms)
                await update_platform(
                    platform,
                    "SUCCESS",
                    {
                        "variantId": variant_id,
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
