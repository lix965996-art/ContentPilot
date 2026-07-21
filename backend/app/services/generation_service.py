import json
import re
import time
from difflib import SequenceMatcher

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppException
from app.models.business import ContentArticle, ContentVariant
from app.prompts.templates import PLATFORM_RULES, SYSTEM_PROMPT, SYSTEM_PROMPT_VERSION
from app.services.setting_service import setting_value

PLATFORM_NAMES = {"WEIBO": "微博", "XIAOHONGSHU": "小红书", "WECHAT_OFFICIAL": "微信公众号"}


def extract_keywords(text: str) -> list[dict[str, str]]:
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
        found = [
            word
            for word in re.findall(r"[\u4e00-\u9fff]{2,6}", text)
            if word not in {"我们", "这个", "一种", "可以"}
        ][:4]
    found = (found or ["内容创作"])[0:6]
    return [
        {"zh": word, "en": mapping.get(word, "creative editorial"), "reason": "与文章主题直接相关"}
        for word in found
    ]


def _mock_variant(article: ContentArticle, platform: str, options: dict) -> dict:
    source = re.sub(r"\s+", " ", article.source_text).strip()
    key_points = [item.strip("。！？ ") for item in re.split(r"[。！？]", source) if item.strip()][
        :4
    ]
    key_points = key_points or [source[:120]]
    keywords = [item["zh"] for item in extract_keywords(article.title + source)]
    if platform == "WEIBO":
        content = f"{article.title}：{key_points[0]}。" + "；".join(key_points[1:3])
        content = content[:155]
        hashtags = [f"#{x}#" for x in keywords[:3]] if options.get("include_hashtags", True) else []
        if options.get("include_emoji", True):
            content += " ✨"
        title = article.title[:30]
    elif platform == "XIAOHONGSHU":
        sections = [f"{i + 1}. {point}" for i, point in enumerate(key_points)]
        content = (
            f"想快速了解「{article.title}」？这篇帮你抓住重点。\n\n"
            + "\n\n".join(sections)
            + "\n\n保存下来，按自己的节奏慢慢实践。"
        )
        hashtags = [f"#{x}" for x in keywords[:6]] if options.get("include_hashtags", True) else []
        title = f"{article.title[:14]}｜重点整理"
    else:
        sections = "\n\n".join(f"## {point[:18]}\n\n{point}。" for point in key_points)
        content = (
            f"# {article.title}\n\n> {article.summary or key_points[0]}\n\n{sections}"
            "\n\n## 写在最后\n\n以上内容基于原文整理，建议结合实际场景使用。"
        )
        hashtags = []
        title = article.title
    return {
        "title": title,
        "content": content,
        "hashtags": hashtags,
        "warnings": ["MOCK：当前结果由本地规则模型生成，可配置 OpenAI 兼容模型获得更自然结果"],
    }


def _parse_json(text: str) -> dict:
    cleaned = text.strip().removeprefix("```json").removesuffix("```").strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        match = re.search(r"\{.*\}", cleaned, re.S)
        if not match:
            raise AppException(50201, "大模型返回内容不是有效 JSON") from exc
        data = json.loads(match.group(0))
    if not isinstance(data, dict) or not data.get("content"):
        raise AppException(50201, "大模型返回缺少 content 字段")
    return data


async def generate_variant_data(
    db: Session, article: ContentArticle, platform: str, options: dict
) -> tuple[dict, str, int, int, int]:
    started = time.perf_counter()
    provider = setting_value(db, "llm.provider", settings.llm_provider)
    api_key = setting_value(db, "llm.api_key", settings.llm_api_key)
    base_url = setting_value(db, "llm.base_url", settings.llm_base_url)
    model_name = setting_value(db, "llm.model", settings.llm_model)
    if provider.lower() == "mock" and settings.app_demo_mode:
        data = _mock_variant(article, platform, options)
        elapsed = int((time.perf_counter() - started) * 1000) + 180
        prompt_tokens = max(50, len(article.source_text) // 2)
        completion_tokens = max(30, len(data["content"]) // 2)
        return data, "contentpilot-local", elapsed, prompt_tokens, completion_tokens
    if provider.lower() == "mock" or not api_key or not base_url or not model_name:
        raise AppException(
            50301,
            "尚未配置真实大模型，请由管理员在系统设置中填写接口地址、API Key 和模型名称",
            503,
        )
    prompt = (
        f"{PLATFORM_RULES[platform]}\n标题：{article.title}\n正文：{article.source_text}\n"
        "只输出 JSON，字段为 title、content、hashtags、warnings。"
    )
    try:
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            response = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model_name,
                    "temperature": 0.6,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            response.raise_for_status()
            payload = response.json()
            data = _parse_json(payload["choices"][0]["message"]["content"])
            usage = payload.get("usage", {})
            prompt_tokens = int(usage.get("prompt_tokens", 0))
            completion_tokens = int(usage.get("completion_tokens", 0))
            if not prompt_tokens and not completion_tokens:
                completion_tokens = int(usage.get("total_tokens", 0))
            return (
                data,
                model_name or "openai-compatible",
                int((time.perf_counter() - started) * 1000),
                prompt_tokens,
                completion_tokens,
            )
    except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError) as exc:
        if settings.app_demo_mode:
            data = _mock_variant(article, platform, options)
            data["warnings"].append("真实模型调用失败，演示模式已启用本地规则生成")
            return (
                data,
                "contentpilot-local-fallback",
                int((time.perf_counter() - started) * 1000),
                0,
                0,
            )
        raise AppException(50202, f"大模型调用失败：{type(exc).__name__}", 502) from exc


def save_variant(
    db: Session,
    article: ContentArticle,
    platform: str,
    data: dict,
    model: str,
    duration: int,
    prompt_tokens: int,
    completion_tokens: int,
) -> ContentVariant:
    version = (
        db.scalar(
            select(func.max(ContentVariant.version_no)).where(
                ContentVariant.article_id == article.id, ContentVariant.platform == platform
            )
        )
        or 0
    ) + 1
    content = data["content"]
    input_price = float(setting_value(db, "llm.input_price_per_million", "0") or 0)
    output_price = float(setting_value(db, "llm.output_price_per_million", "0") or 0)
    estimated_cost = (prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000
    variant = ContentVariant(
        article_id=article.id,
        platform=platform,
        version_no=version,
        title=data.get("title") or article.title,
        content_text=content,
        content_html=None,
        hashtags_json=data.get("hashtags", []),
        emoji_count=len(re.findall(r"[^\w\s，。！？、；：‘’“”（）《》\u4e00-\u9fff]", content)),
        word_count=len(content),
        model_name=model,
        prompt_version=SYSTEM_PROMPT_VERSION,
        generation_duration_ms=duration,
        token_usage=prompt_tokens + completion_tokens,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        estimated_cost=round(estimated_cost, 8),
        quality_score=round(min(98, 72 + len(content) / max(1, len(article.source_text)) * 20), 1),
        original_generated_text=content,
    )
    db.add(variant)
    db.flush()
    return variant


def edit_ratio(original: str | None, current: str) -> float:
    if not original:
        return 0.0
    return round((1 - SequenceMatcher(None, original, current).ratio()) * 100, 2)
