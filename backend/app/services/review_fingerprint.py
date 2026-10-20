"""Stable fingerprints binding a review to the content it actually reviewed."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.core.exceptions import AppException
from app.models.business import ContentVariant
from app.services.activity_service import business_now


def normalize_review_text(value: str | None) -> str:
    """Normalize line endings/trailing spaces while preserving real edits."""
    text = (value or "").replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


def normalize_review_tags(values: Iterable[object] | None) -> list[str]:
    tags: list[str] = []
    for value in values or []:
        tag = "".join(str(value or "").strip().lstrip("#").split())
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def content_fingerprint(
    *,
    platform: str,
    title: str,
    content: str,
    hashtags: Iterable[object] | None,
    source_text: str | None,
) -> str:
    payload = {
        "platform": platform,
        "title": normalize_review_text(title),
        "content": normalize_review_text(content),
        "hashtags": normalize_review_tags(hashtags),
        "source": normalize_review_text(source_text),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def variant_fingerprint(variant: ContentVariant) -> str:
    return content_fingerprint(
        platform=variant.platform,
        title=variant.title,
        content=variant.content_text,
        hashtags=variant.hashtags_json,
        source_text=variant.article.source_text,
    )


def invalidate_review(variant: ContentVariant, reason: str) -> None:
    variant.review_status = "PENDING"
    variant.quality_score = 0.0
    variant.review_detail_json = {
        "stale": True,
        "staleAt": business_now().isoformat(timespec="seconds"),
        "staleReason": reason,
    }
    variant.review_fingerprint = None


def commit_content_change(db: Session, *, code: int = 40908) -> None:
    """The mapper revision also guards changes after the fingerprint check."""
    try:
        db.commit()
    except StaleDataError as exc:
        db.rollback()
        raise AppException(code, "内容或审核已被修改，请刷新后重试", 409) from exc


def require_current_approval(variant: ContentVariant, *, db: Session | None = None) -> None:
    if variant.article is None:
        raise AppException(40401, "原文不存在，请重新创建内容后发布", 404)
    if db is not None:
        db.refresh(variant.article)
    if variant.review_status != "APPROVED" or variant.review_fingerprint != variant_fingerprint(
        variant
    ):
        raise AppException(40909, "内容尚未审核通过或审核已失效，请重新审核后发布", 409)
