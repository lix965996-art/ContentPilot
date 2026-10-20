"""Pure scoring, activity-curve and slot-explanation helpers.

Kept separate from recommendation assembly so the HTTP layer can request a
curve or explain one slot without loading the full ranking pipeline.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.business import AccountActivityStat, ActivityPrior, PublishSchedule
from app.services.activity_prior_service import default_prior_score
from app.services.activity_service import (
    ACCOUNT_SOURCE_TYPES,
    BASELINE_SOURCE_TYPES,
    DEFAULT_WINDOW,
    SOURCE_TYPE_LABELS,
    WEEKDAY_NAMES,
    content_type_name,
    load_rows,
    resolve_window,
    slot_statistics,
)
from app.services.recommendation_constants import (
    ACTIVE_SCHEDULE_STATUSES,
    ALGORITHM_VERSION,
    HISTORY_HALF_LIFE,
    MAX_HISTORY_WEIGHT,
)


def prior_score(db: Session, platform: str, weekday: int, hour: int) -> float:
    """Manually maintained platform activity rule, falling back to the built-in curve."""
    value = db.scalar(
        select(ActivityPrior.base_score).where(
            ActivityPrior.platform == platform,
            ActivityPrior.day_of_week == weekday,
            ActivityPrior.hour_of_day == hour,
            ActivityPrior.enabled.is_(True),
        )
    )
    return float(value if value is not None else default_prior_score(platform, weekday, hour))


def _slot_lookup(rows: list) -> tuple[dict[tuple[int, int], dict], float]:
    stats = slot_statistics(rows)
    return stats["slots"], stats["globalMean"]


def _hour_scores(slots: dict[tuple[int, int], dict], weekday: int) -> dict[int, dict]:
    """Blend the exact weekday slot with the same hour on other weekdays."""
    same_day = {hour: slots.get((weekday, hour)) for hour in range(24)}
    all_days: dict[int, list[dict]] = defaultdict(list)
    for (day, hour), value in slots.items():
        if day != weekday:
            all_days[hour].append(value)
    result: dict[int, dict] = {}
    for hour in range(24):
        exact = same_day.get(hour)
        others = all_days.get(hour, [])
        other_count = sum(item["sampleCount"] for item in others)
        other_score = (
            sum(item["score"] * item["sampleCount"] for item in others) / other_count
            if other_count
            else 0.0
        )
        if exact and exact["sampleCount"]:
            weight = min(1.0, exact["sampleCount"] / 5)
            score = weight * exact["score"] + (1 - weight) * (other_score or exact["score"])
            result[hour] = {
                "score": round(score, 3),
                "sampleCount": exact["sampleCount"],
                "neighborCount": other_count,
            }
        elif other_count:
            result[hour] = {
                "score": round(other_score * 0.85, 3),
                "sampleCount": 0,
                "neighborCount": other_count,
            }
        else:
            result[hour] = {"score": 0.0, "sampleCount": 0, "neighborCount": 0}
    return result


def _legacy_history_scores(db: Session, platform: str, weekday: int) -> dict[int, dict]:
    """Fallback to the pre-existing aggregate table when no records were imported."""
    rows = db.execute(
        select(
            AccountActivityStat.hour_of_day,
            func.avg(AccountActivityStat.avg_engagement_rate),
            func.sum(AccountActivityStat.post_count),
        )
        .where(
            AccountActivityStat.platform == platform,
            AccountActivityStat.day_of_week == weekday,
        )
        .group_by(AccountActivityStat.hour_of_day)
    ).all()
    result = {hour: {"score": 0.0, "sampleCount": 0, "neighborCount": 0} for hour in range(24)}
    for hour, rate, count in rows:
        result[int(hour)] = {
            "score": round(min(100.0, float(rate or 0) * 2000), 3),
            "sampleCount": int(count or 0),
            "neighborCount": 0,
        }
    return result


def _content_scores(
    content_slots: dict[tuple[int, int], dict], weekday: int
) -> tuple[dict[int, float], bool]:
    hours = _hour_scores(content_slots, weekday)
    has_data = any(item["sampleCount"] or item["neighborCount"] for item in hours.values())
    if has_data:
        return {hour: value["score"] for hour, value in hours.items()}, True
    return (
        {hour: (78.0 if hour in (8, 12, 18, 19, 20, 21) else 55.0) for hour in range(24)},
        False,
    )


def _timezone_score(hour: int) -> float:
    if 7 <= hour <= 22:
        return 90.0
    if hour in (6, 23):
        return 55.0
    return 20.0


def _weights(account_samples: int) -> dict[str, float]:
    history = MAX_HISTORY_WEIGHT * account_samples / (account_samples + HISTORY_HALF_LIFE)
    remaining = 1 - history
    return {
        "history": round(history, 4),
        "baseline": round(remaining * 0.62, 4),
        "content": round(remaining * 0.20, 4),
        "timezone": round(remaining * 0.18, 4),
    }


def _active_schedules(db: Session, platform: str, start: datetime, end: datetime) -> list:
    return list(
        db.scalars(
            select(PublishSchedule).where(
                PublishSchedule.platform == platform,
                PublishSchedule.status.in_(ACTIVE_SCHEDULE_STATUSES),
                PublishSchedule.scheduled_at >= start,
                PublishSchedule.scheduled_at <= end,
            )
        ).all()
    )


def curve(
    db: Session,
    platform: str,
    target_date: date,
    *,
    account_id: int | None = None,
    window: str = DEFAULT_WINDOW,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict]:
    """24-hour curve combining the platform prior with the account's own history."""
    weekday = target_date.weekday()
    window_info = resolve_window(window, start_date, end_date)
    w_start, w_end = window_info["start"], window_info["end"]
    account_rows = load_rows(
        db,
        platform=platform,
        account_id=account_id,
        source_types=ACCOUNT_SOURCE_TYPES,
        start=w_start,
        end=w_end,
    )
    baseline_rows = load_rows(
        db, platform=platform, source_types=BASELINE_SOURCE_TYPES, start=w_start, end=w_end
    )
    account_slots, _ = _slot_lookup(account_rows)
    baseline_slots, _ = _slot_lookup(baseline_rows)
    account_hours = _hour_scores(account_slots, weekday) if account_rows else {}
    baseline_hours = _hour_scores(baseline_slots, weekday) if baseline_rows else {}
    if not account_rows:
        legacy = _legacy_history_scores(db, platform, weekday)
        account_hours = {hour: value for hour, value in legacy.items() if value["sampleCount"]}
    points = []
    for hour in range(24):
        account = account_hours.get(hour)
        baseline = baseline_hours.get(hour)
        points.append(
            {
                "hour": hour,
                "time": f"{hour:02d}:00",
                "platformPrior": round(prior_score(db, platform, weekday, hour), 1),
                "accountHistory": round(account["score"], 1)
                if account and (account["sampleCount"] or account.get("neighborCount"))
                else None,
                "publicBaseline": round(baseline["score"], 1)
                if baseline and (baseline["sampleCount"] or baseline.get("neighborCount"))
                else None,
                "sampleCount": (account or {}).get("sampleCount", 0),
            }
        )
    return points


def _confidence(account_samples: int, slot_samples: int, total_samples: int) -> str:
    if account_samples >= 30 and slot_samples >= 3:
        return "HIGH"
    if account_samples >= 10 or total_samples >= 40:
        return "MEDIUM"
    return "LOW"


def _slot_datetime(target_date: date, hour: int, minute: int) -> datetime:
    return datetime.combine(target_date, time(hour, minute))


def explain_slot(
    db: Session,
    *,
    platform: str,
    moment: datetime,
    content_type: str | None = None,
    account_id: int | None = None,
    window: str = DEFAULT_WINDOW,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    """Recompute the four scoring components for one concrete slot.

    ``recommend`` only explains the slot it picked. This reconstructs the same
    breakdown for an arbitrary moment so that a past schedule can show why its
    time scored the way it did, even when no recommendation snapshot was saved.

    Pass ``start_date``/``end_date`` to replay the exact window a stored
    recommendation used; a relative window resolved against *now* would score the
    same slot differently and contradict the saved snapshot.
    """
    weekday = moment.weekday()
    hour = moment.hour
    if start_date and end_date:
        window_info = resolve_window("CUSTOM", start_date, end_date)
    else:
        window_info = resolve_window(window, None, None)
    w_start, w_end = window_info["start"], window_info["end"]

    account_rows = load_rows(
        db,
        platform=platform,
        account_id=account_id,
        source_types=ACCOUNT_SOURCE_TYPES,
        start=w_start,
        end=w_end,
    )
    baseline_rows = load_rows(
        db, platform=platform, source_types=BASELINE_SOURCE_TYPES, start=w_start, end=w_end
    )
    content_rows = (
        load_rows(db, platform=platform, content_type=content_type, start=w_start, end=w_end)
        if content_type and content_type != "UNKNOWN"
        else []
    )

    account_slots, _ = _slot_lookup(account_rows)
    baseline_slots, _ = _slot_lookup(baseline_rows)
    content_slots, _ = _slot_lookup(content_rows)

    account_samples = len(account_rows)
    if not account_samples:
        account_samples = int(
            db.scalar(
                select(func.sum(AccountActivityStat.post_count)).where(
                    AccountActivityStat.platform == platform
                )
            )
            or 0
        )
    weights = _weights(account_samples)

    account_hours = (
        _hour_scores(account_slots, weekday)
        if account_rows
        else _legacy_history_scores(db, platform, weekday)
    )
    baseline_hours = _hour_scores(baseline_slots, weekday)
    content_hours, content_from_data = _content_scores(content_slots, weekday)

    def slot_total(target_hour: int) -> dict:
        prior = prior_score(db, platform, weekday, target_hour)
        public = baseline_hours.get(target_hour, {})
        public_score = public.get("score", 0.0)
        public_samples = public.get("sampleCount", 0) + public.get("neighborCount", 0)
        baseline_score = (
            0.5 * prior + 0.5 * public_score if public_samples and public_score else prior
        )
        history = account_hours.get(target_hour, {"score": 0.0, "sampleCount": 0})
        history_score = history.get("score", 0.0)
        content_score = content_hours[target_hour]
        timezone_score = _timezone_score(target_hour)
        return {
            "baselineScore": round(baseline_score, 2),
            "priorScore": round(prior, 2),
            "publicScore": round(public_score, 2),
            "publicSamples": public_samples,
            "historyScore": round(history_score, 2),
            "slotSamples": history.get("sampleCount", 0),
            "contentScore": round(content_score, 2),
            "timezoneScore": timezone_score,
            "score": round(
                weights["baseline"] * baseline_score
                + weights["history"] * history_score
                + weights["content"] * content_score
                + weights["timezone"] * timezone_score,
                2,
            ),
        }

    chosen = slot_total(hour)
    hourly = [{"hour": item, **slot_total(item)} for item in range(24)]
    best_hour = max(hourly, key=lambda item: item["score"])

    components = [
        {
            "type": "PLATFORM_BASELINE",
            "label": "公开活跃基线",
            "weight": weights["baseline"],
            "rawScore": chosen["baselineScore"],
            "contribution": round(weights["baseline"] * chosen["baselineScore"], 2),
            "description": (
                f"{WEEKDAY_NAMES[weekday]} {hour:02d}:00 的公开活跃基线得分 "
                f"{chosen['baselineScore']}"
                + (
                    f"，来自 {chosen['publicSamples']} 条公开样本"
                    if chosen["publicSamples"]
                    else "，当前来自人工维护的时段规则"
                )
            ),
        },
        {
            "type": "ACCOUNT_HISTORY",
            "label": "账号历史活跃度",
            "weight": weights["history"],
            "rawScore": chosen["historyScore"],
            "contribution": round(weights["history"] * chosen["historyScore"], 2),
            "description": (
                f"账号历史共 {account_samples} 条样本，该时段命中 {chosen['slotSamples']} 条，"
                f"互动综合得分 {chosen['historyScore']}"
                if account_samples
                else "暂无账号历史样本，该项不参与打分"
            ),
        },
        {
            "type": "CONTENT_TYPE",
            "label": "内容类型适配",
            "weight": weights["content"],
            "rawScore": chosen["contentScore"],
            "contribution": round(weights["content"] * chosen["contentScore"], 2),
            "description": (
                f"内容类型「{content_type_name(content_type)}」"
                + (
                    f"在该时段的历史得分 {chosen['contentScore']}"
                    if content_from_data
                    else "暂无该类型历史样本，按通用时段特征评估"
                )
            ),
        },
        {
            "type": "TIMEZONE",
            "label": "读者作息",
            "weight": weights["timezone"],
            "rawScore": chosen["timezoneScore"],
            "contribution": round(weights["timezone"] * chosen["timezoneScore"], 2),
            "description": (
                f"{hour:02d}:00 处于读者活跃作息区间"
                if chosen["timezoneScore"] >= 90
                else f"{hour:02d}:00 处于读者低活跃时段"
            ),
        },
    ]

    return {
        "algorithmVersion": ALGORITHM_VERSION,
        "weekday": weekday,
        "weekdayName": WEEKDAY_NAMES[weekday],
        "hour": hour,
        "score": chosen["score"],
        "confidence": _confidence(
            account_samples, chosen["slotSamples"], account_samples + len(baseline_rows)
        ),
        "weights": weights,
        "components": components,
        "hourly": [{"hour": item["hour"], "score": item["score"]} for item in hourly],
        "bestHour": best_hour["hour"],
        "bestHourScore": best_hour["score"],
        "accountSampleCount": account_samples,
        "baselineSampleCount": len(baseline_rows),
        "contentSampleCount": len(content_rows),
        "window": {"window": window_info["window"], "label": window_info["label"]},
        "sourceTypes": [
            {"sourceType": key, "label": SOURCE_TYPE_LABELS.get(key, key), "count": value}
            for key, value in sorted(_source_breakdown(account_rows + baseline_rows).items())
        ],
    }


def _source_breakdown(rows: list) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row.source_type] += 1
    return dict(counts)
