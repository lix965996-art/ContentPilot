import asyncio
import html
import json
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppException
from app.models.business import ContentArticle, ContentVariant
from app.prompts.profiles import (
    CONTENT_BRIEF_PROMPT,
    DEEP_REVIEW_PROMPT,
    KEYWORD_PROMPT,
    PLATFORM_PROFILES,
    PROMPT_VERSION,
    QUALITY_REVIEW_PROMPT,
    SYSTEM_PROMPT,
    build_deep_draft_prompt,
    build_generation_prompt,
)
from app.schemas.generation import (
    DEEP_DRAFT_MODELS,
    DEEP_FINAL_MODELS,
    OUTPUT_MODELS,
    ContentBriefOutput,
    KeywordExtractionOutput,
    QualityReviewOutput,
)
from app.services.platform_content import (
    build_weibo_status,
    build_x_post,
    normalize_topics,
    x_weighted_length,
)
from app.services.setting_service import setting_value
from app.services.wechat_formatting import format_wechat_html

PLATFORM_NAMES = {
    "WEIBO": "微博",
    "X": "X",
    "XIAOHONGSHU": "小红书",
    "WECHAT_OFFICIAL": "微信公众号",
}
MAX_STRUCTURED_ATTEMPTS = 3
StatusCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


@dataclass(frozen=True)
class LlmRuntime:
    provider: str
    api_key: str
    base_url: str
    model_name: str


@dataclass(frozen=True)
class GenerationResult:
    data: dict[str, Any]
    model_name: str
    provider: str
    duration_ms: int
    prompt_tokens: int
    completion_tokens: int
    attempts: int
    strategy: dict[str, Any] | None = None
    review_detail: dict[str, Any] | None = None
    candidate_titles: list[str] | None = None
    candidates: list[dict[str, Any]] | None = None
    selected_candidate: int | None = None


def load_llm_runtime(db: Session) -> LlmRuntime:
    return LlmRuntime(
        provider=setting_value(db, "llm.provider", settings.llm_provider),
        api_key=setting_value(db, "llm.api_key", settings.llm_api_key),
        base_url=setting_value(db, "llm.base_url", settings.llm_base_url),
        model_name=setting_value(db, "llm.model", settings.llm_model),
    )


def extract_keywords(text: str) -> list[dict[str, str]]:
    """Deterministic keyword fallback used only when the configured LLM is unavailable."""
    mapping = {
        "人工智能": "artificial intelligence",
        "校园": "campus",
        "内容": "content creation",
        "社交媒体": "social media",
        "数据": "data analytics",
        "旅行": "travel",
        "学习": "study",
        "科技": "technology",
        "文化": "culture",
        "城市": "city life",
    }
    found = [key for key in mapping if key in text]
    if not found:
        stopwords = {"我们", "这个", "一种", "可以", "以及", "通过", "进行", "文章"}
        found = [
            word for word in re.findall(r"[\u4e00-\u9fff]{2,6}", text) if word not in stopwords
        ][:4]
    found = list(dict.fromkeys(found or ["内容创作"]))[:6]
    return [
        {"zh": word, "en": mapping.get(word, "creative editorial"), "reason": "与文章主题直接相关"}
        for word in found
    ]


def _source_points(article: ContentArticle) -> list[str]:
    source = re.sub(r"\s+", " ", article.source_text).strip()
    points = [item.strip("。！？； ") for item in re.split(r"[。！？；]", source) if item.strip()]
    return points[:8] or [source[:160]]


def _baseline_variant(
    article: ContentArticle, platform: str, options: dict[str, Any]
) -> dict[str, Any]:
    points = _source_points(article)
    length = options.get("length", "MEDIUM")
    point_count = {"SHORT": 2, "MEDIUM": 4, "LONG": 7}.get(length, 4)
    selected = points[:point_count]
    keywords = [item["zh"] for item in extract_keywords(article.title + article.source_text)]
    emoji = " ✨" if options.get("include_emoji", True) else ""
    audience = options.get("target_audience") or article.target_audience or "读者"
    style = options.get("style", "专业自然")
    include_tags = options.get("include_hashtags", True)

    if platform == "WEIBO":
        content = f"{selected[0]}。" + "；".join(selected[1:])
        content = f"面向{audience}，{content}{emoji}"
        return {
            "title": article.title[:60],
            "content": content[:2000],
            "hashtags": [f"#{item}#" for item in keywords[:3]] if include_tags else [],
            "warnings": [f"Prompt 回归基线：本地规则按“{style}”风格生成"],
        }
    if platform == "X":
        title = article.title[:35]
        content = "；".join(selected)[:80] or title
        tags = [f"#{item}" for item in keywords[:2]] if include_tags else []
        while x_weighted_length(build_x_post(title, content, tags)) > 280 and len(content) > 1:
            content = content[:-1]
        return {
            "title": title,
            "content": content,
            "hashtags": tags,
            "warnings": [f"Prompt 回归基线：本地规则按“{style}”风格生成"],
        }
    if platform == "XIAOHONGSHU":
        sections = "\n\n".join(f"{index + 1}. {point}" for index, point in enumerate(selected))
        return {
            "title": article.title[:20],
            "content": f"给{audience}的重点整理{emoji}\n\n{sections}\n\n以上内容均来自原文。",
            "hashtags": [f"#{item}" for item in keywords[:6]] if include_tags else [],
            "cover_text": article.title[:20],
            "warnings": [f"Prompt 回归基线：本地规则按“{style}”风格生成"],
        }
    section_numbers = ("一", "二", "三", "四", "五", "六")
    sections = "\n\n".join(
        f"{section_numbers[index]}、{point[:22]}\n\n{point}。"
        for index, point in enumerate(selected)
    )
    wechat_content = (
        f"{article.title}\n\n面向{audience}的内容整理。\n\n"
        f"{sections}\n\n结语\n\n以上内容基于原文整理。"
    )
    return {
        "title": article.title[:64],
        "summary": (article.summary or selected[0])[:120],
        "content": wechat_content,
        "author": "",
        "hashtags": [f"#{item}" for item in keywords[:5]] if include_tags else [],
        "cover_prompt": f"{article.topic or article.title}，简洁编辑配图",
        "warnings": [f"Prompt 回归基线：本地规则按“{style}”风格生成"],
    }


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.S)
        if not match:
            raise ValueError("模型响应中没有 JSON 对象") from None
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("模型响应必须是 JSON 对象")
    return payload


def validate_platform_output(platform: str, raw_text: str) -> dict[str, Any]:
    model = OUTPUT_MODELS[platform]
    validated = model.model_validate(_parse_json_object(raw_text))
    return validated.model_dump()


async def _chat_completion(
    runtime: LlmRuntime,
    system_prompt: str,
    messages: list[dict[str, str]],
) -> tuple[str, int, int]:
    request_payload: dict[str, Any] = {
        "model": runtime.model_name,
        "temperature": 0.5,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system_prompt}, *messages],
    }
    if runtime.provider.lower() == "siliconflow":
        request_payload["enable_thinking"] = False
    async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
        response = await client.post(
            f"{runtime.base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {runtime.api_key}"},
            json=request_payload,
        )
        response.raise_for_status()
        payload = response.json()
        usage = payload.get("usage", {})
        prompt_tok = int(usage.get("prompt_tokens", 0))
        completion_tok = int(usage.get("completion_tokens", 0))
        # Some providers omit completion_tokens but return total_tokens.
        # Derive the completion count from the difference so that downstream
        # cost estimates (prompt * input_price + completion * output_price)
        # are not inflated by double-counting prompt tokens.
        if not completion_tok:
            total_tok = int(usage.get("total_tokens", 0))
            completion_tok = max(0, total_tok - prompt_tok)
        return (
            payload["choices"][0]["message"]["content"],
            prompt_tok,
            completion_tok,
        )


async def _validated_completion(
    runtime: LlmRuntime,
    system_prompt: str,
    user_prompt: str,
    output_model: type[BaseModel],
    *,
    status_callback: StatusCallback | None = None,
    max_attempts: int = MAX_STRUCTURED_ATTEMPTS,
) -> tuple[BaseModel, int, int, int]:
    messages = [{"role": "user", "content": user_prompt}]
    prompt_tokens = 0
    completion_tokens = 0
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        current_status = "RETRYING" if attempt > 1 else "RUNNING"
        if status_callback:
            await status_callback(
                current_status,
                {
                    "progress": 80 if attempt > 1 else 35,
                    "stage": "REQUESTING_MODEL",
                    "message": (
                        f"第 {attempt} 次请求模型修正输出"
                        if attempt > 1
                        else "已发送请求，等待模型生成内容"
                    ),
                    "attempt": attempt,
                    "maxAttempts": max_attempts,
                    "error": str(last_error) if last_error else None,
                },
            )
        try:
            raw, used_prompt, used_completion = await _chat_completion(
                runtime, system_prompt, messages
            )
            prompt_tokens += used_prompt
            completion_tokens += used_completion
            if status_callback:
                await status_callback(
                    current_status,
                    {
                        "progress": 85 if attempt > 1 else 75,
                        "stage": "VALIDATING_OUTPUT",
                        "message": "模型已返回，正在校验结构与平台格式",
                        "attempt": attempt,
                        "maxAttempts": max_attempts,
                        "error": None,
                    },
                )
            parsed = _parse_json_object(raw)
            return output_model.model_validate(parsed), prompt_tokens, completion_tokens, attempt
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            messages.extend(
                [
                    {"role": "assistant", "content": raw if "raw" in locals() else ""},
                    {
                        "role": "user",
                        "content": (
                            "上次输出未通过结构校验。请根据以下错误修正，并只返回完整 JSON：\n"
                            f"{exc}"
                        ),
                    },
                ]
            )
        except (httpx.HTTPError, KeyError, TypeError) as exc:
            last_error = exc
            if attempt < max_attempts:
                if status_callback:
                    await status_callback(
                        "RETRYING",
                        {
                            "progress": 78,
                            "stage": "WAITING_TO_RETRY",
                            "message": "模型请求异常，准备自动重试",
                            "attempt": attempt + 1,
                            "maxAttempts": max_attempts,
                            "error": str(exc),
                        },
                    )
                await asyncio.sleep(0)
                continue
    raise AppException(50201, f"结构化输出连续 {max_attempts} 次校验失败：{last_error}", 502)


def compact_weibo_image_payload(data: dict[str, Any], limit: int = 140) -> dict[str, Any]:
    """Return a deterministic, publishable fallback for Weibo's image endpoint."""
    fitted = sanitize_generation_payload(data)
    title = str(fitted.get("title") or "").strip()[:32]
    content = str(fitted.get("content") or "").strip()
    hashtags = normalize_topics(fitted.get("hashtags"), limit=2)

    def status(body: str, topics: list[str] | None = None) -> str:
        return build_weibo_status(title, body, hashtags if topics is None else topics)

    while hashtags and len(status(content)) > limit:
        hashtags.pop()

    if len(status(content)) > limit:
        low, high = 1, len(content)
        best = ""
        while low <= high:
            middle = (low + high) // 2
            candidate = content[:middle].rstrip("，、；：,. ")
            if middle < len(content):
                candidate = f"{candidate}…"
            if len(status(candidate)) <= limit:
                best = candidate
                low = middle + 1
            else:
                high = middle - 1
        content = best or content[:1]

    fitted["title"] = title
    fitted["content"] = content
    fitted["hashtags"] = hashtags
    warnings = [str(item) for item in fitted.get("warnings") or []]
    notice = "已自动压缩为适合微博图文接口的 140 字版本"
    fitted["warnings"] = list(dict.fromkeys([*warnings, notice]))
    return fitted


async def _ensure_weibo_image_safe(
    runtime: LlmRuntime,
    article: ContentArticle,
    data: dict[str, Any],
    *,
    status_callback: StatusCallback | None = None,
) -> tuple[dict[str, Any], int, int, int]:
    """Ask the LLM to shorten an over-limit Weibo result, then fall back locally."""
    current = sanitize_generation_payload(data)
    if (
        len(
            build_weibo_status(
                current.get("title", ""), current.get("content", ""), current.get("hashtags")
            )
        )
        <= 140
    ):
        return current, 0, 0, 0

    prompt_tokens = 0
    completion_tokens = 0
    attempts = 0
    for correction in range(1, 3):
        attempts += 1
        if status_callback:
            await status_callback(
                "RETRYING",
                {
                    "progress": 88,
                    "stage": "FITTING_PLATFORM_LIMIT",
                    "message": f"微博图文超出接口限制，正在自动压缩（第 {correction} 次）",
                    "attempt": correction,
                    "maxAttempts": 2,
                },
            )
        compression_prompt = (
            "请把下面的微博稿压缩为可直接带图发布的版本。"
            "title、content 和 hashtags 按微博显示形式合并后必须不超过 140 个字符；"
            "保留原文中最重要的事实，不新增数据，不输出 Markdown，只返回完整 JSON。\n"
            f"原文标题：{article.title}\n原文正文：{article.source_text}\n"
            f"待压缩稿：{json.dumps(current, ensure_ascii=False)}"
        )
        try:
            corrected, used_prompt, used_completion, _ = await _validated_completion(
                runtime,
                SYSTEM_PROMPT,
                compression_prompt,
                OUTPUT_MODELS["WEIBO"],
                max_attempts=1,
            )
            prompt_tokens += used_prompt
            completion_tokens += used_completion
            candidate = sanitize_generation_payload(corrected.model_dump())
            if (
                len(
                    build_weibo_status(
                        candidate.get("title", ""),
                        candidate.get("content", ""),
                        candidate.get("hashtags"),
                    )
                )
                <= 140
            ):
                warnings = [str(item) for item in candidate.get("warnings") or []]
                candidate["warnings"] = list(
                    dict.fromkeys([*warnings, "已由 AI 自动压缩为可带图发布版本"])
                )
                return candidate, prompt_tokens, completion_tokens, attempts
            current = candidate
        except AppException:
            continue
    return (
        compact_weibo_image_payload(current),
        prompt_tokens,
        completion_tokens,
        attempts,
    )


async def generate_variant_data(
    db: Session,
    article: ContentArticle,
    platform: str,
    options: dict[str, Any],
    *,
    status_callback: StatusCallback | None = None,
    runtime: LlmRuntime | None = None,
) -> GenerationResult:
    started = time.perf_counter()
    runtime = runtime or load_llm_runtime(db)
    if status_callback:
        await status_callback(
            "RUNNING",
            {
                "progress": 10,
                "stage": "PREPARING_PROMPT",
                "message": "正在整理原文、风格、长度和平台参数",
                "attempt": 1,
            },
        )
    if not runtime.api_key or not runtime.base_url or not runtime.model_name:
        raise AppException(
            50301,
            "尚未配置真实大模型，请由管理员在系统设置中填写接口地址、API Key 和模型名称",
            503,
        )
    prompt = build_generation_prompt(article, platform, options)
    if status_callback:
        await status_callback(
            "RUNNING",
            {
                "progress": 25,
                "stage": "PROMPT_READY",
                "message": "平台提示词已准备完成",
                "attempt": 1,
            },
        )
    validated, prompt_tokens, completion_tokens, attempts = await _validated_completion(
        runtime,
        SYSTEM_PROMPT,
        prompt,
        OUTPUT_MODELS[platform],
        status_callback=status_callback,
    )
    data = validated.model_dump()
    if platform == "WEIBO":
        data, fit_prompt, fit_completion, fit_attempts = await _ensure_weibo_image_safe(
            runtime,
            article,
            data,
            status_callback=status_callback,
        )
        prompt_tokens += fit_prompt
        completion_tokens += fit_completion
        attempts += fit_attempts
    return GenerationResult(
        data,
        runtime.model_name,
        runtime.provider,
        int((time.perf_counter() - started) * 1000),
        prompt_tokens,
        completion_tokens,
        attempts,
    )


async def generate_content_brief(
    runtime: LlmRuntime,
    article: ContentArticle,
    options: dict[str, Any],
) -> tuple[dict[str, Any], int, int]:
    prompt = (
        f"创作目标：{options.get('creative_goal', '知识分享')}\n"
        f"额外创作要求：{options.get('creative_requirements') or '未提供'}\n"
        f"目标受众：{options.get('target_audience') or article.target_audience or '普通中文读者'}\n"
        f"原文标题：{article.title}\n原文摘要：{article.summary or '未提供'}\n"
        f"原文正文：\n{article.source_text}"
    )
    brief_schema = json.dumps(ContentBriefOutput.model_json_schema(), ensure_ascii=False)
    result, prompt_tokens, completion_tokens, _ = await _validated_completion(
        runtime,
        CONTENT_BRIEF_PROMPT,
        f"{prompt}\n输出结构：{brief_schema}",
        ContentBriefOutput,
    )
    return result.model_dump(), prompt_tokens, completion_tokens


async def generate_deep_variant_data(
    db: Session,
    article: ContentArticle,
    platform: str,
    options: dict[str, Any],
    brief: dict[str, Any],
    *,
    status_callback: StatusCallback | None = None,
    runtime: LlmRuntime | None = None,
) -> GenerationResult:
    started = time.perf_counter()
    runtime = runtime or load_llm_runtime(db)
    if not all([runtime.api_key, runtime.base_url, runtime.model_name]):
        raise AppException(50301, "尚未配置真实大模型，请先在系统设置中完成配置", 503)

    async def mapped_callback(status: str, detail: dict[str, Any]) -> None:
        if not status_callback:
            return
        stage = detail.get("stage")
        mapped = dict(detail)
        if stage == "REQUESTING_MODEL":
            mapped.update(
                progress=35,
                stage="GENERATING_CANDIDATES",
                message="正在按策略生成两个不同角度的候选稿",
            )
        elif stage == "VALIDATING_OUTPUT":
            mapped.update(
                progress=55,
                stage="VALIDATING_CANDIDATES",
                message="候选稿已返回，正在校验结构和平台格式",
            )
        await status_callback(status, mapped)

    if status_callback:
        await status_callback(
            "RUNNING",
            {
                "progress": 20,
                "stage": "PLANNING_STRATEGY",
                "message": "原文分析完成，正在制定平台创作策略",
                "brief": brief,
            },
        )
    draft_schema = json.dumps(DEEP_DRAFT_MODELS[platform].model_json_schema(), ensure_ascii=False)
    draft, p1, c1, attempts1 = await _validated_completion(
        runtime,
        SYSTEM_PROMPT,
        (
            f"{build_deep_draft_prompt(article, platform, options, brief)}\n"
            f"完整输出结构：{draft_schema}"
        ),
        DEEP_DRAFT_MODELS[platform],
        status_callback=mapped_callback,
    )
    draft_data = draft.model_dump()
    draft_data["candidates"] = [
        sanitize_generation_payload(candidate) for candidate in draft_data["candidates"]
    ]
    if status_callback:
        await status_callback(
            "RUNNING",
            {
                "progress": 65,
                "stage": "REVIEWING_AND_REFINING",
                "message": "两个候选稿已生成，AI 主编正在对照事实逐项评审并修订",
                "strategy": draft_data["strategy"],
                "candidateTitles": [item["title"] for item in draft_data["candidates"]],
                "candidates": draft_data["candidates"],
            },
        )

    final_schema = json.dumps(DEEP_FINAL_MODELS[platform].model_json_schema(), ensure_ascii=False)
    review_prompt = (
        f"目标平台：{PLATFORM_NAMES[platform]}\n"
        f"用户参数：{json.dumps(options, ensure_ascii=False)}\n"
        f"原文创作简报：{json.dumps(brief, ensure_ascii=False)}\n"
        f"创作策略与候选稿：{json.dumps(draft_data, ensure_ascii=False)}"
        f"\n完整输出结构：{final_schema}"
    )

    async def review_callback(status: str, detail: dict[str, Any]) -> None:
        if not status_callback:
            return
        mapped = dict(detail)
        if detail.get("stage") == "REQUESTING_MODEL":
            mapped.update(
                progress=72,
                stage="REVIEWING_AND_REFINING",
                message="AI 主编正在评分、选择并修订候选稿",
            )
        elif detail.get("stage") == "VALIDATING_OUTPUT":
            mapped.update(
                progress=88,
                stage="VALIDATING_FINAL",
                message="最终稿已返回，正在做最后的结构与字段校验",
            )
        await status_callback(status, mapped)

    final, p2, c2, attempts2 = await _validated_completion(
        runtime,
        DEEP_REVIEW_PROMPT,
        review_prompt,
        DEEP_FINAL_MODELS[platform],
        status_callback=review_callback,
    )
    final_data = final.model_dump()
    final_data["final"] = sanitize_generation_payload(final_data["final"])
    if platform == "WEIBO":
        fitted, fit_prompt, fit_completion, fit_attempts = await _ensure_weibo_image_safe(
            runtime,
            article,
            final_data["final"],
            status_callback=status_callback,
        )
        final_data["final"] = fitted
        p2 += fit_prompt
        c2 += fit_completion
        attempts2 += fit_attempts
    review = {key: value for key, value in final_data.items() if key != "final"}
    return GenerationResult(
        data=final_data["final"],
        model_name=runtime.model_name,
        provider=runtime.provider,
        duration_ms=int((time.perf_counter() - started) * 1000),
        prompt_tokens=p1 + p2,
        completion_tokens=c1 + c2,
        attempts=attempts1 + attempts2,
        strategy=draft_data["strategy"],
        review_detail=review,
        candidate_titles=[item["title"] for item in draft_data["candidates"]],
        candidates=draft_data["candidates"],
        selected_candidate=review["selected_candidate"],
    )


def count_emoji(text: str) -> int:
    emoji_pattern = re.compile(
        "["
        "\U0001f1e6-\U0001f1ff"
        "\U0001f300-\U0001f5ff"
        "\U0001f600-\U0001f64f"
        "\U0001f680-\U0001f6ff"
        "\U0001f700-\U0001f77f"
        "\U0001f780-\U0001f7ff"
        "\U0001f800-\U0001f8ff"
        "\U0001f900-\U0001f9ff"
        "\U0001fa00-\U0001faff"
        "\u2600-\u26ff\u2700-\u27bf"
        "](?:\ufe0f|\U0001f3fb-\U0001f3ff)?(?:\u200d[\U0001f300-\U0001faff](?:\ufe0f)?)?"
    )
    return len(emoji_pattern.findall(text))


def normalize_visible_markdown(text: str) -> str:
    """Remove all visible Markdown markers and forbid hash characters."""
    cleaned = text.replace("#", "")
    cleaned = re.sub(r"(?m)^[ \t]+", "", cleaned)
    cleaned = re.sub(r"\*\*([^*\n]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"(?m)^\s*\*\s+", "• ", cleaned)
    cleaned = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", cleaned)
    return cleaned


def sanitize_generation_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Sanitize every model field shown to users while preserving hashtags."""
    sanitized = dict(data)
    for key in ("title", "content", "summary", "cover_text", "cover_prompt", "author"):
        value = sanitized.get(key)
        if isinstance(value, str):
            sanitized[key] = normalize_visible_markdown(value)
    return sanitized


def _inline_markdown(value: str) -> str:
    escaped = html.escape(value, quote=True)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    return escaped


def markdown_to_safe_html(markdown: str) -> str:
    """Render the supported Markdown subset after escaping all raw HTML."""
    blocks: list[str] = []
    list_open = False
    for raw_line in markdown.replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            if list_open:
                blocks.append("</ul>")
                list_open = False
            continue
        heading = re.match(r"^(#{1,3})\s+(.+)$", line)
        plain_heading = re.match(r"^(?:[一二三四五六七八九十]+、|\d+[、.])\s*(.+)$", line)
        bullet = re.match(r"^[-*]\s+(.+)$", line)
        if heading:
            if list_open:
                blocks.append("</ul>")
                list_open = False
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{_inline_markdown(heading.group(2))}</h{level}>")
        elif plain_heading:
            if list_open:
                blocks.append("</ul>")
                list_open = False
            blocks.append(f"<h3>{_inline_markdown(line)}</h3>")
        elif bullet:
            if not list_open:
                blocks.append("<ul>")
                list_open = True
            blocks.append(f"<li>{_inline_markdown(bullet.group(1))}</li>")
        elif line.startswith("> "):
            if list_open:
                blocks.append("</ul>")
                list_open = False
            blocks.append(f"<blockquote>{_inline_markdown(line[2:])}</blockquote>")
        else:
            if list_open:
                blocks.append("</ul>")
                list_open = False
            blocks.append(f"<p>{_inline_markdown(line)}</p>")
    if list_open:
        blocks.append("</ul>")
    return "\n".join(blocks)


def rule_quality_review(
    article: ContentArticle, platform: str, data: dict[str, Any]
) -> dict[str, Any]:
    content = data.get("content", "")
    source_terms = set(re.findall(r"[\u4e00-\u9fff]{2,6}", article.source_text))
    content_terms = set(re.findall(r"[\u4e00-\u9fff]{2,6}", content))
    overlap = len(source_terms & content_terms) / max(1, min(len(source_terms), 30))
    completeness = min(100.0, 55 + overlap * 45)
    factual = min(100.0, 70 + overlap * 30)
    profile = PLATFORM_PROFILES[platform]
    issues: list[str] = []
    format_score = 100.0
    if platform == "WECHAT_OFFICIAL" and not re.search(
        r"(?m)^(?:[一二三四五六七八九十]+、|\d+[、.])", content
    ):
        format_score -= 25
        issues.append("公众号正文缺少清晰的小标题")
    if platform == "XIAOHONGSHU" and len(data.get("title", "")) > 20:
        format_score -= 30
        issues.append("小红书标题过长")
    if platform == "XIAOHONGSHU" and len(content) > 1000:
        format_score -= 30
        issues.append("小红书正文超过 1000 个字符")
    if platform == "WEIBO" and len(content) > 2000:
        format_score -= 30
        issues.append("微博正文过长")
    if platform == "X":
        weighted_length = x_weighted_length(
            build_x_post(data.get("title", ""), content, data.get("hashtags", []))
        )
        if weighted_length > 280:
            format_score -= 40
            issues.append(f"X 帖子超过 280 个加权字符（当前 {weighted_length}）")
    readability = max(
        55.0, 100 - max(0, len(max(content.split("\n"), key=len, default="")) - 120) / 3
    )
    platform_fit = min(100.0, 75 + (10 if data.get("hashtags") else 0))
    return {
        "factual_consistency": round(factual, 1),
        "information_completeness": round(completeness, 1),
        "platform_fit": round(platform_fit, 1),
        "readability": round(readability, 1),
        "format_compliance": round(max(0, format_score), 1),
        "issues": issues,
        "suggestions": [f"发布前按{profile.name}规范完成最终事实核验"],
    }


async def review_variant_quality(
    db: Session, article: ContentArticle, variant: ContentVariant
) -> tuple[dict[str, Any], str]:
    rule_result = rule_quality_review(
        article,
        variant.platform,
        {
            "title": variant.title,
            "content": variant.content_text,
            "hashtags": variant.hashtags_json,
        },
    )
    runtime = load_llm_runtime(db)
    if not all([runtime.api_key, runtime.base_url, runtime.model_name]):
        return {**rule_result, "ruleReview": rule_result}, "RULE_FALLBACK"
    prompt = (
        f"平台：{PLATFORM_NAMES[variant.platform]}\n原文：\n{article.source_text}\n\n"
        f"改写标题：{variant.title}\n改写正文：\n{variant.content_text}\n\n"
        f"规则校验结果：{json.dumps(rule_result, ensure_ascii=False)}"
    )
    try:
        semantic, _, _, _ = await _validated_completion(
            runtime, QUALITY_REVIEW_PROMPT, prompt, QualityReviewOutput
        )
        semantic_data = semantic.model_dump()
        combined = {
            key: round(rule_result[key] * 0.4 + semantic_data[key] * 0.6, 1)
            for key in (
                "factual_consistency",
                "information_completeness",
                "platform_fit",
                "readability",
                "format_compliance",
            )
        }
        combined["issues"] = list(dict.fromkeys(rule_result["issues"] + semantic_data["issues"]))
        combined["suggestions"] = list(
            dict.fromkeys(rule_result["suggestions"] + semantic_data["suggestions"])
        )
        combined["ruleReview"] = rule_result
        combined["semanticReview"] = semantic_data
        return combined, runtime.provider
    except (AppException, httpx.HTTPError, ValidationError, ValueError):
        return {**rule_result, "ruleReview": rule_result}, "RULE_FALLBACK"


async def extract_keywords_with_llm(db: Session, text: str) -> tuple[list[dict[str, str]], str]:
    runtime = load_llm_runtime(db)
    if not all([runtime.api_key, runtime.base_url, runtime.model_name]):
        return extract_keywords(text), "RULE_FALLBACK"
    try:
        result, _, _, _ = await _validated_completion(
            runtime, KEYWORD_PROMPT, f"文章内容：\n{text}", KeywordExtractionOutput
        )
        return [item.model_dump() for item in result.keywords], runtime.provider
    except (AppException, httpx.HTTPError, ValidationError, ValueError):
        return extract_keywords(text), "RULE_FALLBACK"


def save_variant(
    db: Session,
    article: ContentArticle,
    platform: str,
    result: GenerationResult,
) -> ContentVariant:
    version = (
        db.scalar(
            select(func.max(ContentVariant.version_no)).where(
                ContentVariant.article_id == article.id, ContentVariant.platform == platform
            )
        )
        or 0
    ) + 1
    data = sanitize_generation_payload(result.data)
    if platform == "WEIBO":
        data = compact_weibo_image_payload(data)
    content = data["content"]
    data["title"] = normalize_visible_markdown(data.get("title") or article.title)
    data["hashtags"] = normalize_topics(
        data.get("hashtags", []),
        limit={"WEIBO": 5, "X": 4, "XIAOHONGSHU": 10, "WECHAT_OFFICIAL": 8}.get(platform, 10),
    )
    if platform == "WECHAT_OFFICIAL":
        content_html, format_profile = format_wechat_html(content)
    else:
        content_html, format_profile = markdown_to_safe_html(content), {}
    input_price = float(setting_value(db, "llm.input_price_per_million", "0") or 0)
    output_price = float(setting_value(db, "llm.output_price_per_million", "0") or 0)
    estimated_cost = (
        result.prompt_tokens * input_price + result.completion_tokens * output_price
    ) / 1_000_000
    rule_review = rule_quality_review(article, platform, data)
    if result.review_detail:
        semantic_review = result.review_detail
        scored_keys = (
            "factual_consistency",
            "information_completeness",
            "platform_fit",
            "readability",
            "format_compliance",
        )
        review = {
            key: round(rule_review[key] * 0.35 + float(semantic_review[key]) * 0.65, 1)
            for key in scored_keys
        }
        review.update(
            issues=list(dict.fromkeys(rule_review["issues"] + semantic_review.get("issues", []))),
            suggestions=semantic_review.get("improvements", []),
            ruleReview=rule_review,
            deepReview=semantic_review,
            strategy=result.strategy,
        )
    else:
        review = rule_review
    quality_score = (
        sum(
            review[key]
            for key in (
                "factual_consistency",
                "information_completeness",
                "platform_fit",
                "readability",
                "format_compliance",
            )
        )
        / 5
    )
    variant = ContentVariant(
        article_id=article.id,
        platform=platform,
        version_no=version,
        title=data.get("title") or article.title,
        content_text=content,
        content_html=content_html,
        format_profile_json=format_profile,
        hashtags_json=data.get("hashtags", []),
        emoji_count=count_emoji(content + data.get("title", "")),
        word_count=len(content),
        model_name=result.model_name,
        prompt_version=PROMPT_VERSION,
        generation_duration_ms=result.duration_ms,
        token_usage=result.prompt_tokens + result.completion_tokens,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        estimated_cost=round(estimated_cost, 8),
        quality_score=round(quality_score, 1),
        review_detail_json=review,
        original_generated_text=content,
    )
    db.add(variant)
    db.flush()
    return variant


def edit_ratio(original: str | None, current: str) -> float:
    if not original:
        return 0.0
    return round((1 - SequenceMatcher(None, original, current).ratio()) * 100, 2)
