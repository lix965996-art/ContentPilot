"""Semantic vectors for historical content, stored in MySQL and indexed with FAISS.

MySQL (``content_embedding``) is the source of truth; the FAISS index is built
in-process from those rows and cached per (platform, account, version) scope.

Embeddings come from the configured OpenAI-compatible ``/embeddings`` endpoint
when available. Without an embedding model the service falls back to a
deterministic hashed character-n-gram vector, so semantic retrieval still works
offline (marked ``embedding_model = "hashing-ngram-v1"``).
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass

import httpx
import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppException
from app.models.business import ContentArticle, ContentEmbedding, ContentVariant, EngagementHistory
from app.services.activity_service import BASELINE_SOURCE_TYPES, content_type_name
from app.services.generation_service import load_llm_runtime
from app.services.llm_usage_service import begin_usage, finish_usage
from app.services.setting_service import setting_value

EMBEDDING_VERSION = "v1"
FALLBACK_MODEL = "hashing-ngram-v1"

try:  # pragma: no cover - import guard only
    import faiss

    FAISS_AVAILABLE = True
except ImportError:  # pragma: no cover
    faiss = None  # type: ignore[assignment]
    FAISS_AVAILABLE = False


@dataclass(frozen=True)
class EmbeddingRuntime:
    model: str
    base_url: str
    api_key: str

    @property
    def usable(self) -> bool:
        return bool(self.model and self.base_url and self.api_key)


def load_embedding_runtime(db: Session) -> EmbeddingRuntime:
    llm = load_llm_runtime(db)
    return EmbeddingRuntime(
        model=setting_value(db, "llm.embedding_model", settings.embedding_model),
        base_url=llm.base_url,
        api_key=llm.api_key,
    )


def _tokens(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text or "").strip().lower()
    if not cleaned:
        return []
    han = re.findall(r"[\u4e00-\u9fff]", cleaned)
    bigrams = ["".join(pair) for pair in zip(han, han[1:], strict=False)]
    words = re.findall(r"[a-z0-9]{2,}", cleaned)
    return han + bigrams + words


def hashed_vector(text: str, dimensions: int | None = None) -> list[float]:
    """Deterministic hashed n-gram vector, L2-normalised.

    This is not a trained model: it is a bag-of-character-ngram projection that
    keeps lexically/semantically overlapping Chinese texts close together, which
    is enough for the offline demo path.
    """
    size = dimensions or settings.embedding_fallback_dimensions
    vector = [0.0] * size
    counts = Counter(_tokens(text))
    if not counts:
        return vector
    for token, count in counts.items():
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "big") % size
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign * (1.0 + math.log(count))
    norm = math.sqrt(sum(value * value for value in vector))
    if norm:
        vector = [value / norm for value in vector]
    return vector


async def embed_text(db: Session, text: str) -> tuple[list[float], str]:
    """Return (vector, model_name). Falls back to hashed vectors on any failure."""
    runtime = load_embedding_runtime(db)
    if runtime.usable:
        ticket = None
        try:
            ticket = begin_usage(
                load_llm_runtime(db), "EMBEDDING", model=runtime.model, token_priced=False
            )
            async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
                response = await client.post(
                    f"{runtime.base_url.rstrip('/')}/embeddings",
                    headers={"Authorization": f"Bearer {runtime.api_key}"},
                    json={"model": runtime.model, "input": text[:4000]},
                )
                payload = response.json()
                usage = payload.get("usage") or {}
                tokens = usage.get("prompt_tokens", usage.get("total_tokens"))
                finish_usage(
                    ticket,
                    prompt_tokens=int(tokens) if tokens is not None else None,
                    completion_tokens=0 if tokens is not None else None,
                    status="SUCCEEDED" if response.is_success else "FAILED",
                    error_code=None if response.is_success else f"HTTP_{response.status_code}",
                )
                response.raise_for_status()
                vector = payload["data"][0]["embedding"]
                if isinstance(vector, list) and vector:
                    return [float(value) for value in vector], runtime.model
        except AppException as exc:
            if exc.code not in {40961, 40962, 40963}:
                raise
            # Optional embeddings degrade to the explicitly labelled local
            # vector without sending an unpriced/budget-blocked external call.
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            finish_usage(ticket, status="FAILED", error_code=type(exc).__name__)
    return hashed_vector(text), FALLBACK_MODEL


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def history_text(row: EngagementHistory) -> str:
    """Best available text for an imported history row.

    Imports are metric-centric, so the semantic signal is whatever descriptive
    columns survived the mapping (kept in ``metric_detail_json``) plus the
    content type in both its code and human-readable form.

    ``account_ref`` is deliberately excluded. Retrieval is already scoped by
    platform and account, and public datasets put an opaque id there (a YouTube
    video id, for instance) which would otherwise dominate the hashed vector.
    """
    detail = row.metric_detail_json or {}
    content_type = (row.content_type or "").replace("_", " ").strip()
    label = content_type_name(row.content_type) if row.content_type else ""
    parts = [
        str(detail.get("title") or ""),
        str(detail.get("summary") or ""),
        str(detail.get("tags") or ""),
        str(detail.get("topic") or ""),
        content_type,
        label if label != row.content_type else "",
    ]
    return " ".join(part for part in parts if part).strip()


def article_text(article: ContentArticle, variant: ContentVariant | None = None) -> str:
    if variant:
        return f"{variant.title}\n{variant.content_text[:2000]}"
    return f"{article.title}\n{(article.summary or article.source_text)[:2000]}"


async def ensure_embedding(
    db: Session,
    *,
    ref_type: str,
    content_id: int,
    text: str,
    platform: str | None = None,
    account_id: int | None = None,
) -> ContentEmbedding | None:
    """Create or refresh the stored vector for one content item."""
    if not text.strip():
        return None
    digest = _text_hash(text)
    existing = db.scalar(
        select(ContentEmbedding).where(
            ContentEmbedding.ref_type == ref_type,
            ContentEmbedding.content_id == content_id,
            ContentEmbedding.embedding_version == EMBEDDING_VERSION,
        )
    )
    if existing and existing.text_hash == digest and existing.vector_json:
        return existing
    vector, model = await embed_text(db, text)
    if existing:
        existing.vector_json = vector
        existing.embedding_model = model
        existing.text_hash = digest
        existing.platform = platform
        existing.account_id = account_id
        db.flush()
        return existing
    row = ContentEmbedding(
        ref_type=ref_type,
        content_id=content_id,
        platform=platform,
        account_id=account_id,
        embedding_model=model,
        embedding_version=EMBEDDING_VERSION,
        vector_json=vector,
        text_hash=digest,
    )
    db.add(row)
    db.flush()
    return row


async def backfill_history_embeddings(
    db: Session,
    *,
    platform: str,
    account_id: int | None = None,
    limit: int = 200,
) -> int:
    """Embed history rows for one platform/account scope that have no vector yet."""
    query = select(EngagementHistory).where(EngagementHistory.platform == platform)
    if account_id:
        query = query.where(EngagementHistory.account_id == account_id)
    rows = list(
        db.scalars(query.order_by(EngagementHistory.publish_time.desc()).limit(limit)).all()
    )
    existing_ids = set(
        db.scalars(
            select(ContentEmbedding.content_id).where(
                ContentEmbedding.ref_type == "HISTORY",
                ContentEmbedding.embedding_version == EMBEDDING_VERSION,
                ContentEmbedding.content_id.in_([row.id for row in rows] or [0]),
            )
        ).all()
    )
    created = 0
    for row in rows:
        if row.id in existing_ids:
            continue
        text = history_text(row)
        if not text:
            continue
        await ensure_embedding(
            db,
            ref_type="HISTORY",
            content_id=row.id,
            text=text,
            platform=row.platform,
            account_id=row.account_id,
        )
        created += 1
    return created


async def backfill_baseline_embeddings(
    db: Session,
    *,
    exclude_platform: str,
    limit: int = 200,
) -> int:
    """Embed public-dataset rows imported under a different platform.

    Only used for cold start: a platform with no history of its own borrows the
    diurnal shape of public research data until it has been used for real.
    """
    rows = list(
        db.scalars(
            select(EngagementHistory)
            .where(
                EngagementHistory.platform != exclude_platform,
                EngagementHistory.source_type.in_(BASELINE_SOURCE_TYPES),
            )
            .order_by(EngagementHistory.publish_time.desc())
            .limit(limit)
        ).all()
    )
    if not rows:
        return 0
    existing_ids = set(
        db.scalars(
            select(ContentEmbedding.content_id).where(
                ContentEmbedding.ref_type == "HISTORY",
                ContentEmbedding.embedding_version == EMBEDDING_VERSION,
                ContentEmbedding.content_id.in_([row.id for row in rows]),
            )
        ).all()
    )
    created = 0
    for row in rows:
        if row.id in existing_ids:
            continue
        text = history_text(row)
        if not text:
            continue
        await ensure_embedding(
            db,
            ref_type="HISTORY",
            content_id=row.id,
            text=text,
            platform=row.platform,
            account_id=row.account_id,
        )
        created += 1
    return created


async def backfill_article_embeddings(db: Session, *, limit: int = 200) -> int:
    """Embed system articles so past originals also become retrievable history."""
    articles = list(
        db.scalars(select(ContentArticle).order_by(ContentArticle.id.desc()).limit(limit)).all()
    )
    if not articles:
        return 0
    existing_ids = set(
        db.scalars(
            select(ContentEmbedding.content_id).where(
                ContentEmbedding.ref_type == "ARTICLE",
                ContentEmbedding.embedding_version == EMBEDDING_VERSION,
                ContentEmbedding.content_id.in_([item.id for item in articles]),
            )
        ).all()
    )
    created = 0
    for article in articles:
        if article.id in existing_ids:
            continue
        await ensure_embedding(
            db,
            ref_type="ARTICLE",
            content_id=article.id,
            text=article_text(article),
        )
        created += 1
    return created


async def ensure_embeddings(
    db: Session,
    *,
    platform: str,
    account_id: int | None = None,
) -> dict[str, int]:
    """Make sure the retrieval corpus for one platform scope has vectors."""
    history = await backfill_history_embeddings(db, platform=platform, account_id=account_id)
    cross = 0
    platform_rows = db.scalar(
        select(func.count())
        .select_from(EngagementHistory)
        .where(EngagementHistory.platform == platform)
    )
    if not platform_rows:
        cross = await backfill_baseline_embeddings(db, exclude_platform=platform)
    articles = await backfill_article_embeddings(db)
    return {"history": history, "crossPlatform": cross, "articles": articles}


def top_k_similar(
    query_vector: list[float],
    candidates: list[ContentEmbedding],
    *,
    k: int,
) -> list[tuple[ContentEmbedding, float]]:
    """FAISS coarse retrieval over stored vectors, returning (row, cosine)."""
    usable = [
        row for row in candidates if row.vector_json and len(row.vector_json) == len(query_vector)
    ]
    if not usable or not query_vector:
        return []
    matrix = np.array([list(row.vector_json) for row in usable], dtype="float32")
    matrix_norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    matrix_norms[matrix_norms == 0] = 1.0
    matrix = matrix / matrix_norms
    query = np.array([query_vector], dtype="float32")
    query = query / (float(np.linalg.norm(query)) or 1.0)
    limit = min(k, len(usable))
    if FAISS_AVAILABLE:
        assert faiss is not None
        index = faiss.IndexFlatIP(matrix.shape[1])
        index.add(matrix)
        scores, positions = index.search(query, limit)
        return [
            (usable[int(pos)], float(score))
            for pos, score in zip(positions[0], scores[0], strict=False)
            if int(pos) >= 0
        ]
    scores = (matrix @ query[0]).tolist()
    ranked = sorted(zip(usable, scores, strict=False), key=lambda item: item[1], reverse=True)
    return [(row, float(score)) for row, score in ranked[:limit]]
