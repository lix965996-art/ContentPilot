"""Semantic retrieval of similar historical content.

Per platform target:

1. Build a query vector from the platform variant text.
2. Restrict candidates to the same platform / account scope (imported history
   rows) plus previously published system articles.
3. FAISS coarse retrieval → top 20 by cosine similarity.
4. LLM re-ranking on topic / audience / reading scene / freshness.
5. Keep the top 5–10 as the evidence set.

Candidates are never filtered by ``content_type`` alone: the content type is
only one re-ranking signal among several.
"""

from __future__ import annotations

import json

import httpx
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.models.business import ContentArticle, ContentEmbedding, EngagementHistory
from app.services.activity_service import (
    BASELINE_SOURCE_TYPES,
    business_now,
    real_history_conditions,
)
from app.services.content_embedding_service import (
    EMBEDDING_VERSION,
    embed_text,
    ensure_embeddings,
    history_text,
    top_k_similar,
)
from app.services.generation_service import _validated_completion, load_llm_runtime

RETRIEVAL_VERSION = "semantic-retrieval-v1"
COARSE_TOP_K = 20
# Only imported history rows carry engagement metrics, so they get the full
# coarse budget; past system articles are supporting context only.
ARTICLE_TOP_K = 5
FINAL_MIN = 5
FINAL_MAX = 10


class _RerankItem(BaseModel):
    candidate_id: int
    relevance: int = Field(ge=0, le=100)
    reason: str = Field(default="", max_length=200)


class _RerankOutput(BaseModel):
    items: list[_RerankItem] = Field(default_factory=list, max_length=COARSE_TOP_K + ARTICLE_TOP_K)


RERANK_SYSTEM_PROMPT = """你是内容相似度评审员。给定一篇待发布内容和若干历史内容，
从主题、目标受众、阅读场景、时效性四个维度判断历史内容对该次发布时间决策的参考价值。

只返回 JSON：
{"items":[{"candidate_id":整数,"relevance":0到100的整数,"reason":"简短理由"}]}
relevance 越高表示越值得作为发布时间参考。不要输出额外文字。"""


def _scope_embeddings(
    db: Session,
    *,
    platform: str,
    account_id: int | None,
    exclude_article_id: int | None,
) -> tuple[list[ContentEmbedding], list[ContentEmbedding]]:
    """Stored vectors visible to this platform/account scope.

    Returns (history vectors, article vectors). History narrows from account to
    platform and, only if the platform has nothing at all, widens to public
    research datasets imported under another platform - a cold-start proxy that
    callers label as cross-platform. Article vectors are platform-agnostic
    originals with the article being scheduled removed so it cannot match itself.
    """
    history_query = (
        select(ContentEmbedding)
        .join(EngagementHistory, EngagementHistory.id == ContentEmbedding.content_id)
        .where(
            ContentEmbedding.ref_type == "HISTORY",
            ContentEmbedding.embedding_version == EMBEDDING_VERSION,
            ContentEmbedding.platform == platform,
            *real_history_conditions(),
            EngagementHistory.publish_time <= business_now(),
        )
    )
    history = list(db.scalars(history_query.where(ContentEmbedding.account_id == account_id)).all())
    if not history:
        history = list(db.scalars(history_query).all())
    if not history:
        history = list(
            db.scalars(
                select(ContentEmbedding)
                .join(EngagementHistory, EngagementHistory.id == ContentEmbedding.content_id)
                .where(
                    ContentEmbedding.ref_type == "HISTORY",
                    ContentEmbedding.embedding_version == EMBEDDING_VERSION,
                    ContentEmbedding.platform != platform,
                    EngagementHistory.source_type.in_(BASELINE_SOURCE_TYPES),
                    *real_history_conditions(),
                    EngagementHistory.publish_time <= business_now(),
                )
            ).all()
        )
    article_query = select(ContentEmbedding).where(
        ContentEmbedding.ref_type == "ARTICLE",
        ContentEmbedding.embedding_version == EMBEDDING_VERSION,
    )
    if exclude_article_id:
        article_query = article_query.where(ContentEmbedding.content_id != exclude_article_id)
    return history, list(db.scalars(article_query).all())


def _describe(
    row: ContentEmbedding,
    history_by_id: dict[int, EngagementHistory],
    article_by_id: dict[int, ContentArticle],
) -> tuple[str, dict]:
    """Return (text, extra fields) for one retrieval candidate."""
    if row.ref_type == "HISTORY":
        history = history_by_id.get(row.content_id)
        if not history:
            return "", {}
        detail = history.metric_detail_json or {}
        return history_text(history) or f"{history.content_type} 历史记录", {
            "title": str(detail.get("title") or "") or f"{history.content_type} 历史记录",
            "contentType": history.content_type,
            "platform": history.platform,
            "publishTime": history.publish_time.isoformat(),
            "dayOfWeek": history.day_of_week,
            "hourOfDay": history.hour_of_day,
            "views": history.views,
            "engagementRate": history.engagement_rate,
            "engagementScore": history.engagement_score,
            "sourceType": history.source_type,
            "accountId": history.account_id,
        }
    article = article_by_id.get(row.content_id)
    if not article:
        return "", {}
    return f"{article.title} {article.summary or ''}", {
        "title": article.title,
        "contentType": article.topic or "",
        "publishTime": article.created_at.isoformat() if article.created_at else None,
        "dayOfWeek": None,
        "hourOfDay": None,
    }


async def _llm_rerank(
    db: Session,
    profile: dict,
    query_text: str,
    coarse: list[dict],
) -> tuple[dict[int, tuple[int, str]], str]:
    """Return ({candidate_id: (relevance 0-100, reason)}, provider)."""
    runtime = load_llm_runtime(db)
    if not all([runtime.api_key, runtime.base_url, runtime.model_name]):
        return {}, "VECTOR_ONLY"
    payload = [
        {
            "candidate_id": item["candidateId"],
            "text": item["text"][:200],
            "content_type": item.get("contentType") or "",
            "published": item.get("publishTime") or "",
            "vector_similarity": item["vectorSimilarity"],
        }
        for item in coarse
    ]
    prompt = (
        f"待发布内容：{query_text[:600]}\n"
        f"主题：{profile.get('topic')}\n"
        f"目标受众：{profile.get('target_audience')}\n"
        f"阅读场景：{profile.get('reading_mode')}，"
        f"预计阅读 {profile.get('estimated_reading_minutes')} 分钟\n"
        f"时效性：{profile.get('urgency')}，保鲜期 {profile.get('freshness_hours')} 小时\n\n"
        f"候选历史内容：\n{json.dumps(payload, ensure_ascii=False)}"
    )
    try:
        result, _, _, _ = await _validated_completion(
            runtime,
            RERANK_SYSTEM_PROMPT,
            prompt,
            _RerankOutput,
            max_attempts=2,
            temperature=0.1,
        )
        return (
            {item.candidate_id: (item.relevance, item.reason) for item in result.items},
            "LLM_RERANK",
        )
    except (AppException, httpx.HTTPError, ValidationError, ValueError, json.JSONDecodeError):
        return {}, "VECTOR_ONLY"


async def retrieve_similar_history(
    db: Session,
    *,
    platform: str,
    account_id: int | None,
    query_text: str,
    profile: dict,
    exclude_article_id: int | None = None,
) -> dict:
    """Retrieve the similar-history evidence set for one platform target."""
    await ensure_embeddings(db, platform=platform, account_id=account_id)
    history, articles = _scope_embeddings(
        db, platform=platform, account_id=account_id, exclude_article_id=exclude_article_id
    )
    candidates = history + articles
    if not candidates:
        return {
            "retrievalVersion": RETRIEVAL_VERSION,
            "platform": platform,
            "rerankProvider": "NO_HISTORY",
            "queryEmbeddingModel": "",
            "candidateCount": 0,
            "items": [],
        }

    query_vector, model = await embed_text(db, query_text)
    ranked = top_k_similar(query_vector, history, k=COARSE_TOP_K) + top_k_similar(
        query_vector, articles, k=ARTICLE_TOP_K
    )
    ranked.sort(key=lambda item: item[1], reverse=True)
    if not ranked:
        return {
            "retrievalVersion": RETRIEVAL_VERSION,
            "platform": platform,
            "rerankProvider": "NO_VECTOR",
            "queryEmbeddingModel": model,
            "candidateCount": len(candidates),
            "items": [],
        }

    history_ids = [row.content_id for row, _ in ranked if row.ref_type == "HISTORY"]
    article_ids = [row.content_id for row, _ in ranked if row.ref_type == "ARTICLE"]
    history_by_id = {
        row.id: row
        for row in db.scalars(
            select(EngagementHistory).where(EngagementHistory.id.in_(history_ids or [0]))
        ).all()
    }
    article_by_id = {
        row.id: row
        for row in db.scalars(
            select(ContentArticle).where(ContentArticle.id.in_(article_ids or [0]))
        ).all()
    }

    coarse: list[dict] = []
    for index, (row, similarity) in enumerate(ranked):
        text, extra = _describe(row, history_by_id, article_by_id)
        if not text:
            continue
        coarse.append(
            {
                "candidateId": index,
                "refType": row.ref_type,
                "historicalContentId": row.content_id,
                "embeddingModel": row.embedding_model,
                "vectorSimilarity": round(float(similarity), 4),
                "text": text,
                **extra,
            }
        )
    if not coarse:
        return {
            "retrievalVersion": RETRIEVAL_VERSION,
            "platform": platform,
            "rerankProvider": "NO_VECTOR",
            "queryEmbeddingModel": model,
            "candidateCount": len(candidates),
            "items": [],
        }

    llm_scores, provider = await _llm_rerank(db, profile, query_text, coarse)

    items: list[dict] = []
    for entry in coarse:
        relevance, reason = llm_scores.get(entry["candidateId"], (None, ""))
        vector_component = max(0.0, entry["vectorSimilarity"]) * 100
        if relevance is None:
            combined = vector_component
            selection_reason = (
                f"向量相似度 {entry['vectorSimilarity']}，未经 LLM 精排（{provider}）"
            )
        else:
            combined = 0.4 * vector_component + 0.6 * relevance
            selection_reason = reason or f"LLM 判定相关性 {relevance}/100"
        payload = {key: value for key, value in entry.items() if key not in ("candidateId", "text")}
        borrowed = bool(entry.get("platform")) and entry["platform"] != platform
        if borrowed:
            selection_reason = (
                f"{selection_reason}（来自 {entry['platform']} 公开数据集，跨平台代理）"
            )
        items.append(
            {
                **payload,
                "llmRelevance": relevance,
                "combinedScore": round(combined, 3),
                "selectionReason": selection_reason,
                "crossPlatform": borrowed,
                "selected": False,
                "excerpt": entry["text"][:120],
            }
        )

    items.sort(key=lambda item: item["combinedScore"], reverse=True)
    keep = min(FINAL_MAX, max(FINAL_MIN, len(items) // 2 or FINAL_MIN))
    for item in items[:keep]:
        item["selected"] = True

    return {
        "retrievalVersion": RETRIEVAL_VERSION,
        "platform": platform,
        "rerankProvider": provider,
        "queryEmbeddingModel": model,
        "candidateCount": len(candidates),
        "coarseCount": len(coarse),
        "selectedCount": min(keep, len(items)),
        "items": items,
    }
