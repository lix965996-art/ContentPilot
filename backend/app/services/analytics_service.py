from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.business import EngagementMetric


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
