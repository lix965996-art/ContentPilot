"""Publish-effect feedback: fold measured results back into the evidence base.

The recommender scores time slots from ``engagement_history``. Everything the
system publishes itself only ever landed in ``engagement_metric``, which is
keyed by schedule and reporting date, so the loop
"recommend -> publish -> measure -> recommend better" never closed.

This service bridges the two. Once a schedule has actually been published and
carries at least one measurement, it is projected into a single history row:

* the row is keyed by schedule, so re-syncing a newer measurement snapshot
  updates that row instead of appending a duplicate;
* the variant's real title / summary / hashtags travel with it, which is what
  gives semantic retrieval genuine text to match against - imported CSV history
  usually has none;
* it is recorded as ``ACCOUNT_HISTORY`` from ``PUBLISH_FEEDBACK``, so it carries
  full source reliability while still being distinguishable from file imports.

Rows with no measurable reach are skipped rather than written as zeros, because
a zero-engagement row would drag the slot estimate down without evidence.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.business import (
    ContentArticle,
    ContentVariant,
    EngagementHistory,
    EngagementMetric,
    PlatformAccount,
    PublishSchedule,
)
from app.services.activity_service import (
    classify_content_type,
    compute_metrics,
    normalize_business_time,
    normalize_content_type,
)

FEEDBACK_SOURCE_NOTE = "系统内发布效果回流（PUBLISH_FEEDBACK）"
# Only states where the content is actually live can produce audience metrics.
PUBLISHED_STATUSES: set[str] = {"PUBLISHED", "PUBLISH_SUBMITTED", "MANUAL_PUBLISHED"}


def feedback_row_hash(schedule_id: int) -> str:
    """Stable key so one schedule always maps to exactly one history row."""
    return hashlib.sha256(f"publish-feedback:{schedule_id}".encode()).hexdigest()


def _latest_metric(db: Session, schedule_id: int) -> EngagementMetric | None:
    return db.scalar(
        select(EngagementMetric)
        .where(
            EngagementMetric.schedule_id == schedule_id,
            EngagementMetric.data_source.in_(("REAL", "MANUAL", "IMPORTED")),
            EngagementMetric.metric_basis.in_(("IMPRESSIONS", "FOLLOWERS")),
            or_(
                and_(
                    EngagementMetric.metric_basis == "IMPRESSIONS", EngagementMetric.impressions > 0
                ),
                and_(EngagementMetric.metric_basis == "FOLLOWERS", EngagementMetric.followers > 0),
            ),
        )
        .order_by(EngagementMetric.metric_date.desc(), EngagementMetric.id.desc())
        .limit(1)
    )


def _content_type(article: ContentArticle | None, variant: ContentVariant | None) -> str:
    if article and article.topic:
        resolved = normalize_content_type(article.topic)
        if resolved != "UNKNOWN":
            return resolved
    return classify_content_type(
        variant.title if variant else None,
        article.title if article else None,
        article.summary if article else None,
    )


def sync_schedule_feedback(db: Session, schedule_id: int) -> EngagementHistory | None:
    """Project one published schedule's latest measurement into history.

    Returns the created or updated row, or ``None`` when the schedule is not
    published yet, has no measurement, or the measurement has no reach.
    """
    schedule = db.get(PublishSchedule, schedule_id)
    if not schedule or schedule.status not in PUBLISHED_STATUSES:
        return None
    published_at = schedule.actual_publish_at or schedule.scheduled_at
    if not published_at:
        return None
    published_at = normalize_business_time(published_at)
    metric = _latest_metric(db, schedule_id)
    if not metric:
        return None

    computed = compute_metrics(
        views=0,
        impressions=metric.impressions,
        likes=metric.likes,
        comments=metric.comments,
        shares=metric.shares,
        favorites=metric.collects,
        followers=metric.followers,
        metric_basis=metric.metric_basis,
    )
    if computed["reach"] <= 0:
        return None

    variant = db.get(ContentVariant, schedule.variant_id) if schedule.variant_id else None
    article = db.get(ContentArticle, schedule.article_id) if schedule.article_id else None
    account = db.get(PlatformAccount, schedule.account_id) if schedule.account_id else None

    digest = feedback_row_hash(schedule_id)
    row = db.scalar(select(EngagementHistory).where(EngagementHistory.row_hash == digest))
    if row is None:
        row = EngagementHistory(row_hash=digest)
        db.add(row)

    row.platform = schedule.platform
    row.account_id = schedule.account_id
    row.account_ref = (account.account_name if account else schedule.platform)[:120]
    row.content_type = _content_type(article, variant)
    row.publish_time = published_at
    row.day_of_week = published_at.weekday()
    row.hour_of_day = published_at.hour
    row.views = 0
    row.impressions = metric.impressions
    row.likes = metric.likes
    row.comments = metric.comments
    row.shares = metric.shares
    row.favorites = metric.collects
    row.followers = metric.followers
    row.engagement_total = computed["engagementTotal"]
    row.engagement_rate = computed["engagementRate"]
    row.engagement_score = computed["rateComponent"]
    row.metric_detail_json = {
        "likeRate": computed["likeRate"],
        "commentRate": computed["commentRate"],
        "shareRate": computed["shareRate"],
        "favoriteRate": computed["favoriteRate"],
        "metricBasis": computed["metricBasis"],
        "reach": computed["reach"],
        # Real text from the published variant is the point of the feedback
        # loop: it is the only history text semantic retrieval can fully trust.
        "title": (variant.title if variant else (article.title if article else ""))[:500],
        "summary": ((article.summary if article else "") or "")[:500],
        "tags": " ".join(variant.hashtags_json or [])[:500] if variant else "",
        "scheduleId": schedule.id,
        "metricDate": metric.metric_date.isoformat(),
        "dataSource": metric.data_source,
        "syncedAt": datetime.now().isoformat(timespec="seconds"),
    }
    row.source_type = "ACCOUNT_HISTORY"
    row.source_note = FEEDBACK_SOURCE_NOTE
    db.flush()
    return row


def sync_published_feedback(db: Session, *, limit: int = 500) -> dict:
    """Fold every measurable published schedule back into history."""
    schedules = list(
        db.scalars(
            select(PublishSchedule.id)
            .where(PublishSchedule.status.in_(PUBLISHED_STATUSES))
            .order_by(PublishSchedule.id.desc())
            .limit(limit)
        ).all()
    )
    synced = 0
    for schedule_id in schedules:
        if sync_schedule_feedback(db, schedule_id) is not None:
            synced += 1
    return {"consideredSchedules": len(schedules), "syncedRows": synced}
