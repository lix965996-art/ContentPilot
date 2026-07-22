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
    KEYWORD_PROMPT,
    PLATFORM_PROFILES,
    PROMPT_VERSION,
    QUALITY_REVIEW_PROMPT,
    SYSTEM_PROMPT,
    build_generation_prompt,
)
from app.schemas.generation import (
    OUTPUT_MODELS,
    KeywordExtractionOutput,
    QualityReviewOutput,
)
from app.services.setting_service import setting_value

PLATFORM_NAMES = {"WEIBO": "微博", "XIAOHONGSHU": "小红书", "WECHAT_OFFICIAL": "微信公众号"}
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
    if platform == "XIAOHONGSHU":
        sections = "\n\n".join(f"{index + 1}. {point}" for index, point in enumerate(selected))
        return {
            "title": article.title[:30],
            "content": f"给{audience}的重点整理{emoji}\n\n{sections}\n\n以上内容均来自原文。",
            "hashtags": [f"#{item}" for item in keywords[:6]] if include_tags else [],
            "cover_text": article.title[:20],
            "warnings": [f"Prompt 回归基线：本地规则按“{style}”风格生成"],
        }
    sections = "\n\n".join(f"## {point[:22]}\n\n{point}。" for point in selected)
    wechat_content = (
        f"# {article.title}\n\n> 面向{audience}的内容整理。\n\n"
        f"{sections}\n\n## 结语\n\n以上内容基于原文整理。"
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
        return (
            payload["choices"][0]["message"]["content"],
            int(usage.get("prompt_tokens", 0)),
            int(usage.get("completion_tokens", 0) or usage.get("total_tokens", 0)),
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
        if attempt > 1 and status_callback:
            await status_callback(
                "RETRYING",
                {"attempt": attempt, "maxAttempts": max_attempts, "error": str(last_error)},
            )
        try:
            raw, used_prompt, used_completion = await _chat_completion(
                runtime, system_prompt, messages
            )
            prompt_tokens += used_prompt
            completion_tokens += used_completion
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
                await asyncio.sleep(0)
                continue
    raise AppException(50201, f"结构化输出连续 {max_attempts} 次校验失败：{last_error}", 502)


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
        await status_callback("RUNNING", {"attempt": 1})
    if not runtime.api_key or not runtime.base_url or not runtime.model_name:
        raise AppException(
            50301,
            "尚未配置真实大模型，请由管理员在系统设置中填写接口地址、API Key 和模型名称",
            503,
        )
    prompt = build_generation_prompt(article, platform, options)
    validated, prompt_tokens, completion_tokens, attempts = await _validated_completion(
        runtime,
        SYSTEM_PROMPT,
        prompt,
        OUTPUT_MODELS[platform],
        status_callback=status_callback,
    )
    return GenerationResult(
        validated.model_dump(),
        runtime.model_name,
        runtime.provider,
        int((time.perf_counter() - started) * 1000),
        prompt_tokens,
        completion_tokens,
        attempts,
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
        bullet = re.match(r"^[-*]\s+(.+)$", line)
        if heading:
            if list_open:
                blocks.append("</ul>")
                list_open = False
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{_inline_markdown(heading.group(2))}</h{level}>")
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
    if platform == "WECHAT_OFFICIAL" and "## " not in content:
        format_score -= 25
        issues.append("公众号正文缺少二级标题")
    if platform == "XIAOHONGSHU" and len(data.get("title", "")) > 30:
        format_score -= 30
        issues.append("小红书标题过长")
    if platform == "WEIBO" and len(content) > 2000:
        format_score -= 30
        issues.append("微博正文过长")
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
    data = result.data
    content = data["content"]
    input_price = float(setting_value(db, "llm.input_price_per_million", "0") or 0)
    output_price = float(setting_value(db, "llm.output_price_per_million", "0") or 0)
    estimated_cost = (
        result.prompt_tokens * input_price + result.completion_tokens * output_price
    ) / 1_000_000
    review = rule_quality_review(article, platform, data)
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
        content_html=markdown_to_safe_html(content),
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
