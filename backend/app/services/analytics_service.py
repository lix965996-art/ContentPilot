from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.business import EngagementMetric, PublishSchedule


def metric_values(row: EngagementMetric) -> dict:
    return {
        "impressions": row.impressions,
        "likes": row.likes,
        "comments": row.comments,
        "collects": row.collects,
        "shares": row.shares,
        "engagementTotal": row.engagement_total,
        "engagementRate": row.engagement_rate,
    }


def summarize(db: Session) -> dict:
    rows = db.scalars(select(EngagementMetric)).all()
    total = {
        key: 0
        for key in ("impressions", "likes", "comments", "collects", "shares", "engagementTotal")
    }
    for row in rows:
        total["impressions"] += row.impressions
        total["likes"] += row.likes
        total["comments"] += row.comments
        total["collects"] += row.collects
        total["shares"] += row.shares
        total["engagementTotal"] += row.engagement_total
    total["engagementRate"] = (
        round(total["engagementTotal"] / total["impressions"] * 100, 2)
        if total["impressions"]
        else 0
    )
    total["sampleCount"] = len(rows)
    total["simulatedCount"] = sum(row.data_source == "SIMULATED" for row in rows)
    return total


def grouped(db: Session, field: str) -> list[dict]:
    rows = db.scalars(select(EngagementMetric)).all()
    groups = defaultdict(list)
    for row in rows:
        groups[getattr(row, field)].append(row)
    result = []
    for key, items in groups.items():
        impressions = sum(x.impressions for x in items)
        engagement = sum(x.engagement_total for x in items)
        result.append(
            {
                "name": key,
                "sampleCount": len(items),
                "impressions": impressions,
                "engagementTotal": engagement,
                "engagementRate": round(engagement / impressions * 100, 2) if impressions else 0,
                "likes": sum(x.likes for x in items),
                "comments": sum(x.comments for x in items),
                "collects": sum(x.collects for x in items),
                "shares": sum(x.shares for x in items),
            }
        )
    return sorted(result, key=lambda x: x["engagementRate"], reverse=True)


def _metric_payload(metric: EngagementMetric, schedule_id: int, platform: str) -> dict:
    return {
        "scheduleId": schedule_id,
        "platform": platform,
        "metricDate": metric.metric_date.isoformat(),
        "impressions": metric.impressions,
        "likes": metric.likes,
        "comments": metric.comments,
        "collects": metric.collects,
        "shares": metric.shares,
        "followers": metric.followers,
        "engagementTotal": metric.engagement_total,
        "engagementRate": round(metric.engagement_rate * 100, 2),
        "dataSource": metric.data_source,
    }


def _aggregate_totals(metrics: list[EngagementMetric]) -> dict:
    totals = {
        "impressions": sum(item.impressions for item in metrics),
        "likes": sum(item.likes for item in metrics),
        "comments": sum(item.comments for item in metrics),
        "collects": sum(item.collects for item in metrics),
        "shares": sum(item.shares for item in metrics),
        "engagementTotal": sum(item.engagement_total for item in metrics),
    }
    totals["engagementRate"] = (
        round(totals["engagementTotal"] / totals["impressions"] * 100, 2)
        if totals["impressions"]
        else 0
    )
    return totals


def latest_platform_metrics(
    db: Session, article_id: int
) -> dict[str, tuple[PublishSchedule, EngagementMetric]]:
    schedules = db.scalars(
        select(PublishSchedule).where(PublishSchedule.article_id == article_id)
    ).all()
    if not schedules:
        return {}
    schedule_map = {item.id: item for item in schedules}
    metrics = db.scalars(
        select(EngagementMetric)
        .where(EngagementMetric.schedule_id.in_(schedule_map.keys()))
        .order_by(EngagementMetric.schedule_id, EngagementMetric.metric_date.desc())
    ).all()
    by_platform: dict[str, tuple[PublishSchedule, EngagementMetric]] = {}
    for metric in metrics:
        schedule = schedule_map.get(metric.schedule_id)
        if not schedule or schedule.platform in by_platform:
            continue
        by_platform[schedule.platform] = (schedule, metric)
    return by_platform


def article_engagement(db: Session, article_id: int) -> dict:
    by_platform = latest_platform_metrics(db, article_id)
    if not by_platform:
        return {
            "articleId": article_id,
            "hasData": False,
            "platforms": [],
            "totals": None,
            "dataSources": [],
            "simulated": False,
        }
    platforms = [
        _metric_payload(metric, schedule.id, schedule.platform)
        for schedule, metric in by_platform.values()
    ]
    data_sources = sorted({metric.data_source for _, metric in by_platform.values()})
    return {
        "articleId": article_id,
        "hasData": True,
        "platforms": platforms,
        "totals": _aggregate_totals([metric for _, metric in by_platform.values()]),
        "dataSources": data_sources,
        "simulated": any(source == "SIMULATED" for source in data_sources),
    }


def articles_engagement_batch(db: Session, article_ids: list[int]) -> dict[int, dict]:
    if not article_ids:
        return {}
    schedules = db.scalars(
        select(PublishSchedule).where(PublishSchedule.article_id.in_(article_ids))
    ).all()
    schedules_by_article: dict[int, list[PublishSchedule]] = defaultdict(list)
    schedule_map: dict[int, PublishSchedule] = {}
    for schedule in schedules:
        schedules_by_article[schedule.article_id].append(schedule)
        schedule_map[schedule.id] = schedule
    if not schedule_map:
        return {}
    metrics = db.scalars(
        select(EngagementMetric)
        .where(EngagementMetric.schedule_id.in_(schedule_map.keys()))
        .order_by(EngagementMetric.schedule_id, EngagementMetric.metric_date.desc())
    ).all()
    latest_by_schedule: dict[int, EngagementMetric] = {}
    for metric in metrics:
        if metric.schedule_id not in latest_by_schedule:
            latest_by_schedule[metric.schedule_id] = metric
    result: dict[int, dict] = {}
    for article_id in article_ids:
        article_schedules = schedules_by_article.get(article_id, [])
        by_platform: dict[str, EngagementMetric] = {}
        for schedule in article_schedules:
            metric = latest_by_schedule.get(schedule.id)
            if metric and schedule.platform not in by_platform:
                by_platform[schedule.platform] = metric
        if not by_platform:
            continue
        data_sources = sorted({metric.data_source for metric in by_platform.values()})
        result[article_id] = {
            "articleId": article_id,
            "hasData": True,
            "totals": _aggregate_totals(list(by_platform.values())),
            "dataSources": data_sources,
            "simulated": any(source == "SIMULATED" for source in data_sources),
        }
    return result
