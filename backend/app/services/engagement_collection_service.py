"""Durable read-only measurements. All internal timestamps in this module are UTC."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.credentials import decrypt_json
from app.core.exceptions import AppException
from app.models.business import ContentVariant, PlatformAccount, PublishSchedule, TaskDispatch
from app.models.learning import (
    EngagementObservation,
    MetricCollectionTask,
    PublishedContentSnapshot,
)
from app.publishers.bluesky import BlueskyPublisher
from app.publishers.mastodon import MastodonPublisher
from app.publishers.metrics import MetricReadResult, utc_now
from app.services.task_dispatch_service import upsert_dispatch

TASK_TYPE_METRIC = "METRIC_COLLECTION"
PLATFORMS = {"BLUESKY", "MASTODON"}
WINDOWS = (3600, 86400, 259200)
MAX_ATTEMPTS = 6


def business_to_utc(value: datetime) -> datetime:
    aware = value if value.tzinfo else value.replace(tzinfo=ZoneInfo(settings.app_timezone))
    return aware.astimezone(UTC).replace(tzinfo=None)


def utc_to_business(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=UTC).astimezone(ZoneInfo(settings.app_timezone)).replace(tzinfo=None)
    )


def account_reference(schedule: PublishSchedule, account: PlatformAccount | None = None) -> str:
    config = decrypt_json(account.credentials_encrypted) if account else {}
    origin = str(config.get("instance_url") or "").rstrip("/")
    identity = (
        config.get("bluesky_did")
        if schedule.platform == "BLUESKY"
        else f"{origin}:{config.get('mastodon_account_id')}"
    )
    return hashlib.sha256(
        f"{schedule.platform}:{identity or schedule.account_id}".encode()
    ).hexdigest()


def content_features(
    variant: ContentVariant,
    image_count: int,
    schedule: PublishSchedule,
    account: PlatformAccount | None,
) -> dict:
    return {
        "title": variant.title,
        "text": variant.content_text,
        "hashtags": list(variant.hashtags_json or []),
        "imageCount": image_count,
        "reviewFingerprint": variant.review_fingerprint,
        "featureAvailableAt": utc_now().isoformat(),
        "accountRef": account_reference(schedule, account),
        "articleGroup": str(variant.article_id),
        "language": "zh"
        if any("\u4e00" <= c <= "\u9fff" for c in variant.content_text)
        else "other",
    }


def freeze_attempt_features(db: Session, schedule: PublishSchedule, features: dict) -> dict:
    """Persist before any platform write, so receipt recovery keeps pre-publication evidence."""
    if schedule.platform not in PLATFORMS:
        return features
    context = dict(schedule.publish_package_json or {})
    versions = dict(context.get("learningFeatureVersions") or {})
    encoded = json.dumps(
        {key: features[key] for key in ("title", "text", "hashtags", "imageCount", "accountRef")},
        sort_keys=True,
        ensure_ascii=False,
    ).encode()
    key = hashlib.sha256(encoded).hexdigest()
    existing = versions.get(key)
    if isinstance(existing, dict) and existing.get("featureAvailableAt"):
        return existing
    versions[key] = features
    context["learningFeatureVersions"] = dict(list(versions.items())[-8:])
    schedule.publish_package_json = context
    db.commit()
    return features


def _arm(db: Session, task: MetricCollectionTask) -> None:
    upsert_dispatch(
        db,
        task_type=TASK_TYPE_METRIC,
        task_id=task.id,
        revision=task.id,
        run_at=utc_to_business(task.due_at),
    )


def request_collection(
    db: Session,
    schedule: PublishSchedule,
    *,
    window: int = 0,
    request_key: str | None = None,
) -> MetricCollectionTask:
    if (
        schedule.platform not in PLATFORMS
        or schedule.status != "PUBLISHED"
        or not schedule.external_id
    ):
        raise AppException(40090, "只有已确认发布的 Bluesky/Mastodon 帖子可以采集")
    if window not in (0, *WINDOWS):
        raise AppException(40090, "不支持的采集窗口")
    key = "scheduled" if window else (request_key or str(uuid.uuid4()))
    prior = db.scalar(
        select(MetricCollectionTask).where(
            MetricCollectionTask.schedule_id == schedule.id,
            MetricCollectionTask.window_seconds == window,
            MetricCollectionTask.request_key == key,
        )
    )
    if prior:
        return prior
    if not window:
        inflight = db.scalar(
            select(MetricCollectionTask).where(
                MetricCollectionTask.schedule_id == schedule.id,
                MetricCollectionTask.window_seconds == 0,
                MetricCollectionTask.status.in_(("PENDING", "RUNNING")),
            )
        )
        if inflight:
            return inflight
    published = business_to_utc(schedule.actual_publish_at or schedule.scheduled_at)
    task = MetricCollectionTask(
        id=str(uuid.uuid4()),
        schedule_id=schedule.id,
        window_seconds=window,
        request_key=key,
        due_at=published + timedelta(seconds=window) if window else utc_now(),
        status="PENDING",
        attempts=0,
    )
    db.add(task)
    db.flush()
    _arm(db, task)
    return task


def capture_publication(db: Session, schedule: PublishSchedule, features: dict) -> None:
    """Called in the publication-result transaction; never backfill old drafts as evidence."""
    if schedule.platform not in PLATFORMS or schedule.status != "PUBLISHED":
        return
    if db.get(PublishedContentSnapshot, schedule.id) is None:
        encoded = json.dumps(
            {k: features[k] for k in ("title", "text", "hashtags", "imageCount")},
            ensure_ascii=False,
            sort_keys=True,
        ).encode()
        db.add(
            PublishedContentSnapshot(
                schedule_id=schedule.id,
                platform=schedule.platform,
                account_ref=features["accountRef"],
                external_id=schedule.external_id or "",
                content_hash=hashlib.sha256(encoded).hexdigest(),
                content_json=features,
                feature_available_at=datetime.fromisoformat(features["featureAvailableAt"]),
                published_at=business_to_utc(schedule.actual_publish_at or schedule.scheduled_at),
            )
        )
    for window in WINDOWS:
        request_collection(db, schedule, window=window)


def recover_collection_tasks(db: Session) -> int:
    """A crashed worker is reclaimable after its bounded lease, including outbox handoff."""
    now = utc_now()
    rows = db.execute(
        select(MetricCollectionTask, TaskDispatch)
        .outerjoin(
            TaskDispatch,
            (TaskDispatch.task_type == TASK_TYPE_METRIC)
            & (TaskDispatch.task_id == MetricCollectionTask.id),
        )
        .where(
            or_(
                (MetricCollectionTask.status == "RUNNING")
                & or_(
                    MetricCollectionTask.claim_expires_at <= now,
                    MetricCollectionTask.claim_expires_at.is_(None),
                ),
                (MetricCollectionTask.status == "PENDING")
                & or_(
                    TaskDispatch.id.is_(None),
                    TaskDispatch.status.not_in(("PENDING", "CLAIMED")),
                    (TaskDispatch.status == "CLAIMED")
                    & or_(
                        MetricCollectionTask.claim_expires_at <= now,
                        MetricCollectionTask.claim_expires_at.is_(None),
                    ),
                ),
            )
        )
        .order_by(MetricCollectionTask.due_at, MetricCollectionTask.id)
        .limit(500)
    ).all()
    recovered = 0
    for task, intent in rows:
        if task.status == "RUNNING":
            task.status = "FAILED" if task.attempts >= MAX_ATTEMPTS else "PENDING"
            task.last_error = "WORKER_INTERRUPTED"
            task.claim_expires_at = None
        if task.status == "FAILED":
            task.completed_at = now
            _finish_intent(db, task)
        if task.status == "PENDING" and (intent is None or intent.status != "PENDING"):
            task.claim_expires_at = None
            _arm(db, task)
            recovered += 1
    db.flush()
    return recovered


async def _read(db: Session, schedule: PublishSchedule) -> MetricReadResult:
    account = db.get(PlatformAccount, schedule.account_id) if schedule.account_id else None
    if account is None or account.platform != schedule.platform or account.status != "CONNECTED":
        return MetricReadResult("FAILED", error_code="ACCOUNT_NOT_CONNECTED")
    snapshot = db.get(PublishedContentSnapshot, schedule.id)
    if snapshot and snapshot.account_ref != account_reference(schedule, account):
        return MetricReadResult("FAILED", error_code="ACCOUNT_IDENTITY_CHANGED")
    if schedule.platform == "MASTODON":
        config = decrypt_json(account.credentials_encrypted)
        if (
            urlsplit(schedule.published_url or "").netloc
            != urlsplit(str(config.get("instance_url") or "")).netloc
        ):
            return MetricReadResult("FAILED", error_code="ACCOUNT_IDENTITY_CHANGED")
    if schedule.platform == "BLUESKY":
        return await BlueskyPublisher(db, account).read_metrics(schedule.external_id or "")
    if schedule.platform == "MASTODON":
        return await MastodonPublisher(db, account).read_metrics(schedule.external_id or "")
    return MetricReadResult("FAILED", error_code="PLATFORM_UNSUPPORTED")


def _finish_intent(db: Session, task: MetricCollectionTask) -> None:
    if task.status == "PENDING":
        _arm(db, task)
        return
    intent = db.scalar(
        select(TaskDispatch).where(
            TaskDispatch.task_type == TASK_TYPE_METRIC,
            TaskDispatch.task_id == task.id,
        )
    )
    if intent:
        intent.status = "DONE" if task.status == "SUCCEEDED" else "FAILED"
        intent.last_error = task.last_error
        intent.completed_at = utc_to_business(utc_now())


async def collect_task(db: Session, task_id: str) -> MetricCollectionTask | None:
    now = utc_now()
    claim = db.execute(
        update(MetricCollectionTask)
        .where(
            MetricCollectionTask.id == task_id,
            MetricCollectionTask.status == "PENDING",
            MetricCollectionTask.due_at <= now,
        )
        .values(
            status="RUNNING",
            attempts=MetricCollectionTask.attempts + 1,
            claim_expires_at=now + timedelta(minutes=5),
        )
        .execution_options(synchronize_session=False)
    )
    db.commit()
    task = db.get(MetricCollectionTask, task_id, populate_existing=True)
    if claim.rowcount != 1 or task is None:
        return task
    schedule = db.get(PublishSchedule, task.schedule_id)
    if schedule is None:
        return None
    try:
        result = await _read(db, schedule)
    except Exception:  # malformed third-party transport must not strand a durable claim
        result = MetricReadResult("FAILED", error_code="COLLECTION_FAILED", retryable=True)
    observed = utc_now()
    age = int((observed - result.published_at).total_seconds()) if result.published_at else None
    db.add(
        EngagementObservation(
            id=str(uuid.uuid4()),
            task_id=task.id,
            attempt=task.attempts,
            schedule_id=schedule.id,
            platform=schedule.platform,
            account_ref=account_reference(
                schedule,
                db.get(PlatformAccount, schedule.account_id) if schedule.account_id else None,
            ),
            external_id=schedule.external_id or "",
            observed_at=observed,
            published_at=result.published_at,
            age_seconds=age,
            window_seconds=task.window_seconds,
            status=result.status,
            likes=result.counts.get("likes"),
            replies=result.counts.get("replies"),
            reposts=result.counts.get("reposts"),
            quotes=result.counts.get("quotes"),
            http_status=result.http_status,
            error_code=result.error_code or None,
            source_type="ACCOUNT_API",
            adapter_version="counts-v1",
        )
    )
    task.last_error = result.error_code or None
    task.claim_expires_at = None
    if result.status == "SUCCEEDED":
        task.status = "SUCCEEDED"
        task.completed_at = observed
    elif result.retryable and task.attempts < MAX_ATTEMPTS:
        task.status = "PENDING"
        task.due_at = observed + timedelta(
            seconds=max(result.retry_after, min(3600, 30 * 2**task.attempts))
        )
    else:
        task.status = "FAILED"
        task.completed_at = observed
    _finish_intent(db, task)
    db.commit()
    return task
