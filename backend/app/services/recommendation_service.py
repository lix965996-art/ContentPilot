"""Data-driven publish-time recommendation.

Scoring is fully statistical: a public activity baseline is corrected by the
account's own imported history, with the history weight growing as more samples
arrive. The LLM is never asked to pick a time; it only labels content and turns
these numbers into prose (see ``recommendation_narrative``).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.business import (
    AccountActivityStat,
    ActivityPrior,
    EngagementHistory,
    PublishRecommendation,
    PublishSchedule,
)
from app.services.activity_service import (
    ACCOUNT_SOURCE_TYPES,
    BASELINE_SOURCE_TYPES,
    DEFAULT_WINDOW,
    SOURCE_TYPE_LABELS,
    WEEKDAY_NAMES,
    content_type_name,
    count_rows,
    load_rows,
    resolve_window,
    slot_statistics,
    window_sufficiency,
)

ALGORITHM_VERSION = "hybrid-v2"
LEGACY_ALGORITHM_VERSION = "weighted-v1"

DEFAULT_PEAKS = {
    "WEIBO": {8: 78, 12: 82, 18: 88, 20: 96, 21: 91},
    "X": {8: 80, 12: 86, 17: 82, 20: 94, 22: 88},
    "XIAOHONGSHU": {9: 74, 12: 80, 19: 90, 20: 98, 21: 94, 22: 86},
    "WECHAT_OFFICIAL": {7: 83, 8: 90, 12: 76, 18: 82, 20: 88},
    "TOUTIAO": {7: 76, 8: 82, 12: 88, 18: 92, 20: 86, 22: 78},
}

SLOT_MINUTES = (0, 30)
# Sample count at which the account history reaches half of its maximum weight.
HISTORY_HALF_LIFE = 20.0
MAX_HISTORY_WEIGHT = 0.60
# Schedules on the same platform closer than this are treated as a hard conflict.
CONFLICT_MINUTES = 30
# Same-account posts closer than this trigger a "posting too densely" warning.
DENSITY_MINUTES = 120
ACTIVE_SCHEDULE_STATUSES = ("PENDING", "RUNNING", "WAITING_MANUAL_CONFIRM")


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
    return float(
        value
        if value is not None
        else DEFAULT_PEAKS.get(platform, {}).get(hour, 42 + (hour % 6) * 3)
    )


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


def recommend(
    db: Session,
    platform: str,
    target_date: date,
    *,
    account_id: int | None = None,
    content_type: str | None = None,
    now: datetime | None = None,
    horizon_days: int = 3,
    window: str = DEFAULT_WINDOW,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    """Score every half-hour slot and return the best time plus two alternatives."""
    now = now or datetime.now()
    window_info = resolve_window(window, start_date, end_date, now=now)
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
        load_rows(
            db,
            platform=platform,
            account_id=account_id,
            content_type=content_type,
            source_types=ACCOUNT_SOURCE_TYPES,
            start=w_start,
            end=w_end,
        )
        if content_type and content_type != "UNKNOWN"
        else []
    )
    if content_type and content_type != "UNKNOWN" and not content_rows:
        content_rows = load_rows(
            db, platform=platform, content_type=content_type, start=w_start, end=w_end
        )

    account_slots, _ = _slot_lookup(account_rows)
    baseline_slots, _ = _slot_lookup(baseline_rows)
    content_slots, _ = _slot_lookup(content_rows)

    account_samples = len(account_rows)
    legacy_samples = 0
    if not account_samples:
        legacy_samples = int(
            db.scalar(
                select(func.sum(AccountActivityStat.post_count)).where(
                    AccountActivityStat.platform == platform
                )
            )
            or 0
        )
    effective_samples = account_samples or legacy_samples
    weights = _weights(effective_samples)

    prior_rule_count = int(
        db.scalar(
            select(func.count())
            .select_from(ActivityPrior)
            .where(ActivityPrior.platform == platform, ActivityPrior.enabled.is_(True))
        )
        or 0
    )

    window_start = _slot_datetime(target_date, 0, 0)
    window_end = window_start + timedelta(days=max(1, horizon_days) + 1)
    existing = _active_schedules(db, platform, window_start - timedelta(days=1), window_end)

    candidates: list[dict] = []
    for offset in range(max(1, horizon_days)):
        day = target_date + timedelta(days=offset)
        weekday = day.weekday()
        account_hours = (
            _hour_scores(account_slots, weekday)
            if account_rows
            else _legacy_history_scores(db, platform, weekday)
        )
        baseline_hours = _hour_scores(baseline_slots, weekday)
        content_hours, content_from_data = _content_scores(content_slots, weekday)
        for hour in range(24):
            prior = prior_score(db, platform, weekday, hour)
            public = baseline_hours.get(hour, {})
            public_score = public.get("score", 0.0)
            public_samples = public.get("sampleCount", 0) + public.get("neighborCount", 0)
            baseline_score = (
                0.5 * prior + 0.5 * public_score if public_samples and public_score else prior
            )
            history = account_hours.get(hour, {"score": 0.0, "sampleCount": 0})
            history_score = history.get("score", 0.0)
            content_score = content_hours[hour]
            timezone_score = _timezone_score(hour)
            base_total = (
                weights["baseline"] * baseline_score
                + weights["history"] * history_score
                + weights["content"] * content_score
                + weights["timezone"] * timezone_score
            )
            for minute in SLOT_MINUTES:
                moment = _slot_datetime(day, hour, minute)
                if moment <= now + timedelta(minutes=30):
                    continue
                # Half-hour slots inherit the hour score with a small decay so
                # that on-the-hour publishing stays the default choice.
                slot_score = base_total if minute == 0 else base_total * 0.985
                conflicts = [
                    {
                        "scheduleId": item.id,
                        "scheduledAt": item.scheduled_at.isoformat(),
                        "minutes": int(abs((item.scheduled_at - moment).total_seconds()) // 60),
                        "sameAccount": bool(account_id and item.account_id == account_id),
                    }
                    for item in existing
                    if abs((item.scheduled_at - moment).total_seconds()) / 60 < DENSITY_MINUTES
                ]
                hard = [item for item in conflicts if item["minutes"] < CONFLICT_MINUTES]
                dense = [
                    item
                    for item in conflicts
                    if item["sameAccount"] and item["minutes"] >= CONFLICT_MINUTES
                ]
                penalty = 40.0 if hard else (8.0 if dense else 0.0)
                candidates.append(
                    {
                        "at": moment,
                        "score": round(max(0.0, slot_score - penalty), 2),
                        "rawScore": round(slot_score, 2),
                        "baselineScore": round(baseline_score, 2),
                        "priorScore": round(prior, 2),
                        "publicScore": round(public_score, 2),
                        "historyScore": round(history_score, 2),
                        "contentScore": round(content_score, 2),
                        "timezoneScore": timezone_score,
                        "slotSamples": history.get("sampleCount", 0),
                        "publicSamples": public_samples,
                        "contentFromData": content_from_data,
                        "conflicts": conflicts,
                        "hardConflict": bool(hard),
                    }
                )

    if not candidates:
        raise ValueError("没有可用于推荐的未来时段")

    candidates.sort(key=lambda item: (item["score"], -item["at"].timestamp()), reverse=True)
    best = candidates[0]

    alternatives: list[dict] = []
    for item in candidates[1:]:
        if item["hardConflict"]:
            continue
        if all(
            abs((item["at"] - chosen).total_seconds()) >= 90 * 60
            for chosen in [best["at"], *[alt["at"] for alt in alternatives]]
        ):
            alternatives.append(item)
        if len(alternatives) == 2:
            break

    total_samples = account_samples + len(baseline_rows)
    confidence = _confidence(effective_samples, best["slotSamples"], total_samples)

    reasons = [
        {
            "type": "PLATFORM_BASELINE",
            "description": (
                f"{platform} 在{WEEKDAY_NAMES[best['at'].weekday()]} "
                f"{best['at']:%H:%M} 的公开活跃基线得分为 {best['baselineScore']}"
                + (
                    f"（其中公开样本 {best['publicSamples']} 条）"
                    if best["publicSamples"]
                    else "（当前来自人工维护的时段规则）"
                )
            ),
            "contribution": round(weights["baseline"] * best["baselineScore"], 2),
        }
    ]
    if effective_samples:
        reasons.append(
            {
                "type": "ACCOUNT_HISTORY",
                "description": (
                    f"账号历史共 {effective_samples} 条样本，该时段命中 {best['slotSamples']} 条，"
                    f"综合互动得分 {best['historyScore']}"
                ),
                "contribution": round(weights["history"] * best["historyScore"], 2),
            }
        )
    else:
        reasons.append(
            {
                "type": "COLD_START",
                "description": (
                    "暂无账号历史数据，当前完全依赖公开基线与时段规则，建议先导入历史数据"
                ),
                "contribution": 0,
            }
        )
    reasons.append(
        {
            "type": "CONTENT_TYPE",
            "description": (
                f"内容类型「{content_type_name(content_type)}」"
                + (
                    "在该时段的历史表现较好"
                    if best["contentFromData"]
                    else "暂无历史样本，按通用时段特征评估"
                )
            ),
            "contribution": round(weights["content"] * best["contentScore"], 2),
        }
    )
    reasons.append(
        {
            "type": "TIMEZONE",
            "description": f"{best['at']:%H:%M} 处于目标读者的活跃作息区间",
            "contribution": round(weights["timezone"] * best["timezoneScore"], 2),
        }
    )

    warnings: list[str] = []
    if not effective_samples:
        warnings.append("账号历史样本为 0，推荐结果仅供冷启动参考，请尽快导入真实历史数据。")
    elif effective_samples < 10:
        warnings.append(
            f"账号历史样本仅 {effective_samples} 条，个人历史权重被压低为 "
            f"{round(weights['history'] * 100)}%，建议继续补充数据。"
        )
    if best["slotSamples"] == 0 and effective_samples:
        warnings.append("推荐时段本身没有直接命中的历史样本，得分由相邻时段与基线推导。")
    window_verdict = window_sufficiency(account_samples, window_info)
    if not window_verdict["sufficient"] and window_info["window"] != "ALL":
        total_account_samples = count_rows(
            db, platform=platform, account_id=account_id, source_types=ACCOUNT_SOURCE_TYPES
        )
        if total_account_samples > account_samples:
            warnings.append(
                f"时间范围「{window_info['label']}」内账号历史样本仅 {account_samples} 条，"
                f"账号在全部时间范围内共有 {total_account_samples} 条历史数据，"
                "可切换为“全部时间”或更大的时间范围获得更稳定的推荐。"
            )
        else:
            warnings.append(
                f"时间范围「{window_info['label']}」内数据不足：{window_verdict['message']}"
            )
    if not baseline_rows and not prior_rule_count:
        warnings.append("尚未导入公开基线数据，也没有人工时段规则，基线部分使用内置经验曲线。")

    conflicts = [
        {
            **item,
            "level": "CONFLICT" if item["minutes"] < CONFLICT_MINUTES else "DENSITY",
            "message": (
                f"该平台已有排期与推荐时间相差 {item['minutes']} 分钟"
                if item["minutes"] < CONFLICT_MINUTES
                else f"同账号 {item['minutes']} 分钟内已有排期，发布可能过密"
            ),
        }
        for item in best["conflicts"]
    ]

    source_counts: dict[str, int] = defaultdict(int)
    for row in [*account_rows, *baseline_rows]:
        source_counts[row.source_type] += 1

    return {
        "recommendedAt": best["at"],
        "score": best["score"],
        "confidence": confidence,
        "reasons": reasons,
        "alternatives": [
            {
                "recommendedAt": item["at"].isoformat(),
                "score": item["score"],
                "confidence": _confidence(effective_samples, item["slotSamples"], total_samples),
                "sampleCount": item["slotSamples"],
                "reason": (
                    f"{WEEKDAY_NAMES[item['at'].weekday()]} {item['at']:%H:%M}"
                    f" 基线 {item['baselineScore']} / 历史 {item['historyScore']}"
                ),
            }
            for item in alternatives
        ],
        "sampleCount": effective_samples,
        "accountSampleCount": account_samples,
        "baselineSampleCount": len(baseline_rows),
        "legacySampleCount": legacy_samples,
        "weights": weights,
        "warnings": warnings,
        "conflicts": conflicts,
        "contentType": content_type or "UNKNOWN",
        "contentTypeName": content_type_name(content_type),
        "dataSource": {
            "baseline": "平台公开活跃基线（人工维护规则 + 已导入公开样本）",
            "accountHistory": (
                f"账号历史导入数据 {account_samples} 条"
                if account_samples
                else (f"历史聚合统计 {legacy_samples} 条" if legacy_samples else "暂无账号历史数据")
            ),
            "priorRuleCount": prior_rule_count,
            "publicSampleCount": len(baseline_rows),
            "accountSampleCount": account_samples,
            "sourceTypes": [
                {
                    "sourceType": key,
                    "label": SOURCE_TYPE_LABELS.get(key, key),
                    "count": value,
                }
                for key, value in sorted(
                    source_counts.items(), key=lambda item: item[1], reverse=True
                )
            ],
        },
        "dataSufficiency": {
            "level": confidence,
            "accountSamples": effective_samples,
            "slotSamples": best["slotSamples"],
            "sufficient": effective_samples >= 30,
            "message": (
                "账号历史样本充足，个人数据主导推荐"
                if effective_samples >= 30
                else "账号历史样本不足，公开基线仍占主要权重"
            ),
        },
        "window": {
            "window": window_info["window"],
            "label": window_info["label"],
            "startDate": window_info["startDate"],
            "endDate": window_info["endDate"],
            "accountSampleCount": account_samples,
            "baselineSampleCount": len(baseline_rows),
            **window_verdict,
        },
        "algorithmVersion": ALGORITHM_VERSION,
    }


def slot_evidence(
    db: Session, platform: str, moment: datetime, *, account_id: int | None = None
) -> dict:
    """Explain how a specific slot scores, used when reviewing an existing schedule."""
    rows = load_rows(
        db, platform=platform, account_id=account_id, source_types=ACCOUNT_SOURCE_TYPES
    )
    slots, global_mean = _slot_lookup(rows)
    slot = slots.get((moment.weekday(), moment.hour), {"sampleCount": 0, "score": 0.0})
    return {
        "platform": platform,
        "at": moment.isoformat(),
        "dayName": WEEKDAY_NAMES[moment.weekday()],
        "hour": moment.hour,
        "prior": round(prior_score(db, platform, moment.weekday(), moment.hour), 1),
        "historyScore": slot.get("score", 0.0),
        "slotSampleCount": slot.get("sampleCount", 0),
        "globalMeanScore": global_mean,
        "totalSampleCount": len(rows),
    }


def engagement_history_count(db: Session, platform: str | None = None) -> int:
    query = select(func.count()).select_from(EngagementHistory)
    if platform:
        query = query.where(EngagementHistory.platform == platform)
    return int(db.scalar(query) or 0)


# Tolerance used to decide whether a manually typed ("CUSTOM") schedule time
# still effectively lands on one of the recommendation's candidate slots. This
# mirrors CONFLICT_MINUTES: within one half-hour slot of a candidate counts as
# "used the recommendation" even if the operator did not click the button.
EXPERIMENT_TIME_TOLERANCE_MINUTES = CONFLICT_MINUTES


def classify_schedule_group(
    schedule: PublishSchedule, recommendation: PublishRecommendation | None
) -> tuple[str, str]:
    """Data-driven default experiment group for a publish-time A/B comparison.

    - RECOMMENDED / ALTERNATIVE time sources always land in the treatment
      group (the operator explicitly used a system-suggested time).
    - A CUSTOM time only counts as the control group when it does not
      coincide (within ``EXPERIMENT_TIME_TOLERANCE_MINUTES``) with any of the
      recommendation's candidate slots; otherwise the operator effectively
      still published at a recommended time and should not dilute the
      control group.
    """
    if schedule.time_source in {"RECOMMENDED", "ALTERNATIVE"}:
        return (
            "TREATMENT",
            f"time_source={schedule.time_source}：采用了系统推荐/备选时间，自动归入推荐时段实验组",
        )

    candidates: list[datetime] = []
    if recommendation is not None:
        if recommendation.recommended_at:
            candidates.append(recommendation.recommended_at)
        for item in recommendation.alternative_times_json or []:
            raw = item.get("recommendedAt") if isinstance(item, dict) else None
            if not raw:
                continue
            try:
                candidates.append(datetime.fromisoformat(str(raw)))
            except ValueError:
                continue

    for candidate in candidates:
        minutes = abs((schedule.scheduled_at - candidate).total_seconds()) / 60
        if minutes < EXPERIMENT_TIME_TOLERANCE_MINUTES:
            return (
                "TREATMENT",
                "time_source=CUSTOM，但发布时间与推荐候选时间相差 "
                f"{round(minutes)} 分钟（容差 {EXPERIMENT_TIME_TOLERANCE_MINUTES} 分钟内），"
                "视为命中推荐时段，自动归入推荐时段实验组",
            )

    return (
        "CONTROL",
        "time_source=CUSTOM，且不在任何推荐候选时间的容差范围内，自动归入非推荐时段对照组",
    )
