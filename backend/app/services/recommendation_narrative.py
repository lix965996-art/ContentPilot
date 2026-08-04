"""Turn recommendation statistics into prose, and label content with the LLM.

The model is intentionally kept out of the decision loop: it receives numbers
that were already computed and may only describe them. If it is not configured,
or it answers with anything unexpected, a deterministic template is used.
"""

from __future__ import annotations

import json
import logging

import httpx
from sqlalchemy.orm import Session

from app.services import generation_service
from app.services.activity_service import (
    CONTENT_TYPE_NAMES,
    classify_content_type,
    content_type_name,
    normalize_content_type,
)
from app.services.generation_service import load_llm_runtime

logger = logging.getLogger(__name__)

CLASSIFY_SYSTEM_PROMPT = (
    "你是中文社交媒体内容分析助手。只做分类，不做任何时间建议。\n"
    "根据标题与正文判断内容类型、主题和目标受众。\n"
    f"content_type 只能取以下之一：{'、'.join(CONTENT_TYPE_NAMES)}。\n"
    '返回 JSON：{"content_type": "...", "topic": "...", "audience": "..."}'
)

NARRATIVE_SYSTEM_PROMPT = (
    "你是中文数据分析助理。下面给出的统计结果由系统计算完成，你不得修改任何数字，"
    "也不得自行推荐其他时间。请用 2～3 句中文说明为什么推荐这个时段、"
    "数据依据是什么、以及样本不足时需要注意什么。\n"
    '返回 JSON：{"narrative": "..."}'
)


def rule_based_narrative(stats: dict) -> str:
    moment = stats["recommendedAt"]
    text = moment.strftime("%m月%d日 %H:%M") if hasattr(moment, "strftime") else str(moment)
    weights = stats.get("weights", {})
    parts = [
        f"建议在 {text} 发布，综合得分 {stats.get('score')}，置信度 {stats.get('confidence')}。",
        (
            f"该结论由公开基线（权重 {round(weights.get('baseline', 0) * 100)}%）、"
            f"账号历史（权重 {round(weights.get('history', 0) * 100)}%，"
            f"共 {stats.get('sampleCount', 0)} 条样本）、"
            f"内容类型「{stats.get('contentTypeName', '未分类')}」与作息时段共同计算得出。"
        ),
    ]
    if stats.get("warnings"):
        parts.append("注意：" + stats["warnings"][0])
    return "".join(parts)


async def classify_with_llm(
    db: Session, *, title: str, content: str, hashtags: list[str] | None = None
) -> dict:
    """Return content type / topic / audience, falling back to keyword rules."""
    fallback = {
        "contentType": classify_content_type(title, content, " ".join(hashtags or [])),
        "topic": "",
        "audience": "",
        "provider": "RULE_BASED",
    }
    runtime = load_llm_runtime(db)
    if not all([runtime.api_key, runtime.base_url, runtime.model_name]):
        return fallback
    prompt = (
        f"标题：{title}\n"
        f"话题标签：{' '.join(hashtags or []) or '无'}\n"
        f"正文（截断）：{content[:1200]}"
    )
    try:
        raw, _, _ = await generation_service._chat_completion(
            runtime, CLASSIFY_SYSTEM_PROMPT, [{"role": "user", "content": prompt}], temperature=0.1
        )
        payload = json.loads(raw)
    except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError, ValueError) as exc:
        logger.warning("内容类型识别失败，回退规则分类：%s", exc)
        return fallback
    content_type = normalize_content_type(payload.get("content_type"))
    if content_type == "UNKNOWN":
        content_type = fallback["contentType"]
    return {
        "contentType": content_type,
        "topic": str(payload.get("topic") or "")[:120],
        "audience": str(payload.get("audience") or "")[:120],
        "provider": "LLM",
    }


async def narrate(db: Session, stats: dict) -> tuple[str, str]:
    """Return (narrative, provider). Never raises; falls back to the template."""
    fallback = rule_based_narrative(stats)
    runtime = load_llm_runtime(db)
    if not all([runtime.api_key, runtime.base_url, runtime.model_name]):
        return fallback, "RULE_BASED"
    moment = stats["recommendedAt"]
    facts = {
        "recommended_at": moment.isoformat() if hasattr(moment, "isoformat") else str(moment),
        "score": stats.get("score"),
        "confidence": stats.get("confidence"),
        "weights": stats.get("weights"),
        "account_sample_count": stats.get("sampleCount"),
        "baseline_sample_count": stats.get("baselineSampleCount"),
        "content_type": content_type_name(stats.get("contentType")),
        "reasons": [item["description"] for item in stats.get("reasons", [])],
        "warnings": stats.get("warnings", []),
        "alternatives": [item["recommendedAt"] for item in stats.get("alternatives", [])],
    }
    try:
        raw, _, _ = await generation_service._chat_completion(
            runtime,
            NARRATIVE_SYSTEM_PROMPT,
            [{"role": "user", "content": json.dumps(facts, ensure_ascii=False)}],
            temperature=0.2,
        )
        payload = json.loads(raw)
        narrative = str(payload.get("narrative") or "").strip()
    except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError, ValueError) as exc:
        logger.warning("推荐理由改写失败，使用规则文案：%s", exc)
        return fallback, "RULE_BASED"
    if not narrative:
        return fallback, "RULE_BASED"
    return narrative[:800], "LLM"
