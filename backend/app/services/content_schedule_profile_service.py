"""LLM content schedule profile (ContentScheduleProfile).

The profile is the semantic input to cross-platform scheduling: the LLM reads
the article plus its platform variants and produces a structured, validated
description of how / when the content should be published. On any failure the
service auto-repairs once (handled by ``_validated_completion``) and then falls
back to deterministic rules, recording ``profile_source`` accordingly.
"""

from __future__ import annotations

import json
import re
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.models.business import ContentArticle, ContentVariant
from app.services.activity_service import CONTENT_TYPE_NAMES, classify_content_type
from app.services.generation_service import _validated_completion, load_llm_runtime

PROFILE_VERSION = "profile-v1"

Urgency = Literal["IMMEDIATE", "TIMELY", "NORMAL", "EVERGREEN"]
ReadingMode = Literal["FRAGMENT", "IMMERSIVE", "REFERENCE"]
CognitiveLoad = Literal["LOW", "MEDIUM", "HIGH"]
CrossPlatformStrategy = Literal["SIMULTANEOUS", "STAGGERED", "WATERFALL"]

_URGENCY_FRESHNESS_CAP = {
    "IMMEDIATE": 24,
    "TIMELY": 72,
    "NORMAL": 24 * 7,
    "EVERGREEN": 24 * 30,
}


class ContentScheduleProfile(BaseModel):
    """Structured scheduling profile produced by the LLM (or the rule fallback)."""

    topic: str = Field(min_length=1, max_length=100)
    content_type: str = Field(min_length=2, max_length=50)
    target_audience: str = Field(min_length=1, max_length=150)
    reading_mode: ReadingMode
    estimated_reading_minutes: float = Field(ge=0.5, le=60)
    urgency: Urgency
    freshness_hours: int = Field(ge=1, le=24 * 30)
    cognitive_load: CognitiveLoad
    platform_priority: list[str] = Field(min_length=1, max_length=7)
    cross_platform_strategy: CrossPlatformStrategy
    minimum_cross_platform_gap_minutes: int = Field(ge=0, le=24 * 60)
    reason_evidence: list[str] = Field(min_length=1, max_length=8)

    @field_validator("content_type")
    @classmethod
    def normalize_type(cls, value: str) -> str:
        upper = value.strip().upper().replace(" ", "_").replace("-", "_")
        if upper in CONTENT_TYPE_NAMES:
            return upper
        for code, name in CONTENT_TYPE_NAMES.items():
            if value.strip() == name:
                return code
        return "UNKNOWN"

    @field_validator("platform_priority")
    @classmethod
    def normalize_platforms(cls, value: list[str]) -> list[str]:
        allowed = {"WEIBO", "XIAOHONGSHU", "WECHAT_OFFICIAL", "TOUTIAO", "X", "BLUESKY", "MASTODON"}
        cleaned = [item.strip().upper() for item in value if item.strip().upper() in allowed]
        if not cleaned:
            raise ValueError("platform_priority 必须包含合法平台标识")
        return list(dict.fromkeys(cleaned))

    @field_validator("freshness_hours")
    @classmethod
    def freshness_matches_urgency(cls, value: int, info) -> int:
        urgency = info.data.get("urgency")
        cap = _URGENCY_FRESHNESS_CAP.get(urgency or "NORMAL", 24 * 7)
        return min(value, cap)


PROFILE_SYSTEM_PROMPT = f"""你是社交媒体内容排期分析师。阅读文章和它的平台版本，输出 JSON 排期画像。
只返回一个 JSON 对象，字段与约束如下：
- topic: 内容主题短语（<=100字）
- content_type: {" / ".join(code for code in CONTENT_TYPE_NAMES if code != "UNKNOWN")} 之一
- target_audience: 目标读者描述
- reading_mode: FRAGMENT（碎片浏览）/ IMMERSIVE（沉浸阅读）/ REFERENCE（工具查阅）
- estimated_reading_minutes: 0.5~60 的数字
- urgency: IMMEDIATE / TIMELY / NORMAL / EVERGREEN
- freshness_hours: 内容保鲜期（小时，1~720，需与 urgency 一致）
- cognitive_load: LOW / MEDIUM / HIGH
- platform_priority: 平台标识数组（WEIBO/XIAOHONGSHU/WECHAT_OFFICIAL/TOUTIAO/X/BLUESKY/MASTODON）
  按建议发布先后排序
- cross_platform_strategy: SIMULTANEOUS（同时）/ STAGGERED（错峰）/ WATERFALL（瀑布式先后）
- minimum_cross_platform_gap_minutes: 跨平台最小间隔分钟（0~1440）
- reason_evidence: 1~8 条给出判断依据的短句数组
不要输出任何额外文字。"""


def _estimate_reading_minutes(text: str) -> float:
    chars = len(re.findall(r"[\u4e00-\u9fff]", text)) + len(re.findall(r"[A-Za-z]+", text))
    return round(max(0.5, min(60.0, chars / 400)), 1)


def rule_based_profile(
    article: ContentArticle,
    variants: list[ContentVariant],
    target_platforms: list[str],
) -> ContentScheduleProfile:
    """Deterministic fallback used when the LLM is unavailable or keeps failing."""
    content_type = classify_content_type(article.title, article.source_text)
    urgency: Urgency = "TIMELY" if content_type == "NEWS" else "NORMAL"
    long_form = [item for item in variants if item.platform in ("WECHAT_OFFICIAL", "TOUTIAO")]
    reading_minutes = _estimate_reading_minutes(
        long_form[0].content_text if long_form else article.source_text
    )
    return ContentScheduleProfile(
        topic=(article.topic or article.title)[:100],
        content_type=content_type,
        target_audience=(article.target_audience or "关注该主题的普通读者")[:150],
        reading_mode="IMMERSIVE" if reading_minutes >= 5 else "FRAGMENT",
        estimated_reading_minutes=reading_minutes,
        urgency=urgency,
        freshness_hours=_URGENCY_FRESHNESS_CAP[urgency],
        cognitive_load=(
            "HIGH" if reading_minutes >= 8 else ("MEDIUM" if reading_minutes >= 3 else "LOW")
        ),
        platform_priority=target_platforms or ["WEIBO"],
        cross_platform_strategy="STAGGERED",
        minimum_cross_platform_gap_minutes=30,
        reason_evidence=[
            f"规则判定内容类型为 {CONTENT_TYPE_NAMES.get(content_type, content_type)}",
            f"按正文长度估算阅读时长约 {reading_minutes} 分钟",
            "LLM 不可用，画像由本地规则生成（FALLBACK）",
        ],
    )


def _profile_user_prompt(
    article: ContentArticle,
    variants: list[ContentVariant],
    target_platforms: list[str],
) -> str:
    variant_briefs = [
        {
            "platform": item.platform,
            "title": item.title,
            "wordCount": item.word_count,
            "excerpt": (item.content_text or "")[:300],
        }
        for item in variants
    ]
    return (
        f"目标平台：{'、'.join(target_platforms)}\n"
        f"文章标题：{article.title}\n"
        f"文章主题：{article.topic or '未标注'}\n"
        f"目标读者（作者标注）：{article.target_audience or '未标注'}\n"
        f"原文（截断）：\n{article.source_text[:1500]}\n\n"
        f"平台版本概览：\n{json.dumps(variant_briefs, ensure_ascii=False)}"
    )


async def build_profile(
    db: Session,
    article: ContentArticle,
    variants: list[ContentVariant],
    target_platforms: list[str],
) -> tuple[ContentScheduleProfile, str]:
    """Return (profile, source). source is "LLM" or "FALLBACK"."""
    runtime = load_llm_runtime(db)
    if all([runtime.api_key, runtime.base_url, runtime.model_name]):
        try:
            # max_attempts=2 → one automatic repair round before falling back.
            result, _, _, _ = await _validated_completion(
                runtime,
                PROFILE_SYSTEM_PROMPT,
                _profile_user_prompt(article, variants, target_platforms),
                ContentScheduleProfile,
                max_attempts=2,
                temperature=0.2,
            )
            return result, "LLM"
        except (AppException, httpx.HTTPError, ValidationError, ValueError, json.JSONDecodeError):
            pass
    return rule_based_profile(article, variants, target_platforms), "FALLBACK"
