"""Measured analytics with explicit source scope and denominator provenance."""

from collections import defaultdict
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.business import EngagementMetric, PublishSchedule

DataScope = Literal["REAL", "SIMULATED", "ALL"]
KNOWN_BASES = ("IMPRESSIONS", "FOLLOWERS")
COUNTERS = (
    "impressions",
    "likes",
    "comments",
    "collects",
    "shares",
    "followers",
    "engagementTotal",
)


def metric_scope(data_scope: DataScope = "REAL") -> tuple:
    simulated = func.upper(EngagementMetric.data_source) == "SIMULATED"
    return () if data_scope == "ALL" else (simulated if data_scope == "SIMULATED" else ~simulated,)


def metric_denominator(row: EngagementMetric) -> int:
    return {"IMPRESSIONS": row.impressions, "FOLLOWERS": row.followers}.get(
        row.metric_basis, 0
    ) or 0


def metric_values(row: EngagementMetric) -> dict:
    denominator = metric_denominator(row)
    return {
        **{
            key: getattr(row, "engagement_total" if key == "engagementTotal" else key)
            for key in COUNTERS
        },
        "metricBasis": row.metric_basis or "UNKNOWN",
        "rateAvailable": denominator > 0,
        "engagementRate": round(row.engagement_total / denominator * 100, 2)
        if denominator
        else None,
        "rateDenominator": denominator,
    }


def aggregate_metrics(metrics: list[EngagementMetric], *, by_source: bool = True) -> dict:
    totals: dict[str, Any] = {
        key: sum(
            getattr(row, "engagement_total" if key == "engagementTotal" else key) for row in metrics
        )
        for key in COUNTERS
    }
    buckets: dict[str, list[EngagementMetric]] = defaultdict(list)
    for row in metrics:
        basis = row.metric_basis if row.metric_basis in KNOWN_BASES else "UNKNOWN"
        buckets[basis].append(row)
    by_basis: list[dict[str, Any]] = []
    for basis, rows in sorted(buckets.items()):
        valid = [row for row in rows if metric_denominator(row) > 0]
        denominator = sum(metric_denominator(row) for row in valid)
        engagement = sum(row.engagement_total for row in valid)
        by_basis.append(
            {
                "metricBasis": basis,
                "sampleCount": len(rows),
                "validRateCount": len(valid),
                "excludedRateCount": len(rows) - len(valid),
                "rateDenominator": denominator,
                "engagementTotal": sum(row.engagement_total for row in rows),
                "ratedEngagementTotal": engagement,
                "rateAvailable": bool(denominator),
                "engagementRate": round(engagement / denominator * 100, 2) if denominator else None,
            }
        )
    source_groups: dict[str, list[EngagementMetric]] = defaultdict(list)
    for row in metrics:
        source_groups["SIMULATED" if row.data_source.upper() == "SIMULATED" else "REAL"].append(row)
    basis = next(iter(buckets)) if len(buckets) == 1 else "MIXED" if buckets else "UNKNOWN"
    excluded = sum(item["excludedRateCount"] for item in by_basis)
    available = basis in KNOWN_BASES and excluded == 0 and len(source_groups) == 1
    totals.update(
        {
            "sampleCount": len(metrics),
            "simulatedCount": len(source_groups.get("SIMULATED", [])),
            "metricBasis": basis,
            "rateAvailable": available,
            "unknownBasisCount": len(buckets.get("UNKNOWN", [])),
            "excludedRateCount": excluded,
            "mixedDataSources": len(source_groups) > 1,
            "byBasis": by_basis,
            "rateDenominator": by_basis[0]["rateDenominator"] if available else None,
            "engagementRate": by_basis[0]["engagementRate"] if available else None,
        }
    )
    if by_source:
        totals["bySource"] = [
            {"dataScope": scope, **aggregate_metrics(rows, by_source=False)}
            for scope, rows in sorted(source_groups.items())
        ]
    return totals


def summarize(db: Session, *, data_scope: DataScope = "REAL") -> dict:
    rows = list(db.scalars(select(EngagementMetric).where(*metric_scope(data_scope))).all())
    excluded = (
        int(
            db.scalar(
                select(func.count()).select_from(EngagementMetric).where(*metric_scope("SIMULATED"))
            )
            or 0
        )
        if data_scope == "REAL"
        else 0
    )
    return {**aggregate_metrics(rows), "dataScope": data_scope, "excludedSimulatedCount": excluded}


def grouped(db: Session, field: str, *, data_scope: DataScope = "REAL") -> list[dict]:
    rows = db.scalars(select(EngagementMetric).where(*metric_scope(data_scope))).all()
    groups = defaultdict(list)
    for row in rows:
        groups[getattr(row, field)].append(row)
    result = [
        {"name": key, **aggregate_metrics(items), "dataScope": data_scope}
        for key, items in groups.items()
    ]
    return sorted(
        result, key=lambda item: (item["rateAvailable"], item["engagementRate"] or 0), reverse=True
    )


def _metric_payload(metric: EngagementMetric, schedule_id: int, platform: str) -> dict:
    return {
        "scheduleId": schedule_id,
        "platform": platform,
        "metricDate": metric.metric_date.isoformat(),
        **metric_values(metric),
        "dataSource": metric.data_source,
    }


def latest_platform_metrics(
    db: Session, article_id: int, *, data_scope: DataScope = "REAL"
) -> dict[str, tuple[PublishSchedule, EngagementMetric]]:
    schedules = db.scalars(
        select(PublishSchedule).where(PublishSchedule.article_id == article_id)
    ).all()
    schedule_map = {item.id: item for item in schedules}
    if not schedule_map:
        return {}
    metrics = db.scalars(
        select(EngagementMetric)
        .where(EngagementMetric.schedule_id.in_(schedule_map), *metric_scope(data_scope))
        .order_by(EngagementMetric.metric_date.desc(), EngagementMetric.id.desc())
    ).all()
    by_platform = {}
    for metric in metrics:
        schedule = schedule_map[metric.schedule_id]
        by_platform.setdefault(schedule.platform, (schedule, metric))
    return by_platform


def article_engagement(db: Session, article_id: int, *, data_scope: DataScope = "REAL") -> dict:
    by_platform = latest_platform_metrics(db, article_id, data_scope=data_scope)
    metrics = [metric for _, metric in by_platform.values()]
    return {
        "articleId": article_id,
        "hasData": bool(metrics),
        "dataScope": data_scope,
        "platforms": [
            _metric_payload(metric, schedule.id, schedule.platform)
            for schedule, metric in by_platform.values()
        ],
        "totals": aggregate_metrics(metrics) if metrics else None,
        "dataSources": sorted({metric.data_source for metric in metrics}),
        "simulated": any(metric.data_source == "SIMULATED" for metric in metrics),
    }


def articles_engagement_batch(
    db: Session, article_ids: list[int], *, data_scope: DataScope = "REAL"
) -> dict[int, dict]:
    if not article_ids:
        return {}
    schedules = db.scalars(
        select(PublishSchedule).where(PublishSchedule.article_id.in_(article_ids))
    ).all()
    schedule_map = {item.id: item for item in schedules}
    if not schedule_map:
        return {}
    metrics = db.scalars(
        select(EngagementMetric)
        .where(EngagementMetric.schedule_id.in_(schedule_map), *metric_scope(data_scope))
        .order_by(EngagementMetric.metric_date.desc(), EngagementMetric.id.desc())
    ).all()
    by_article = defaultdict(dict)
    for metric in metrics:
        schedule = schedule_map[metric.schedule_id]
        by_article[schedule.article_id].setdefault(schedule.platform, metric)
    return {
        article_id: {
            "articleId": article_id,
            "hasData": True,
            "dataScope": data_scope,
            "totals": aggregate_metrics(list(platforms.values())),
            "dataSources": sorted({metric.data_source for metric in platforms.values()}),
            "simulated": any(metric.data_source == "SIMULATED" for metric in platforms.values()),
        }
        for article_id, platforms in by_article.items()
    }
