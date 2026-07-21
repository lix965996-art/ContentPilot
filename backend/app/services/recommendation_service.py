from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.business import AccountActivityStat, ActivityPrior

DEFAULT_PEAKS = {
    "WEIBO": {8: 78, 12: 82, 18: 88, 20: 96, 21: 91},
    "XIAOHONGSHU": {9: 74, 12: 80, 19: 90, 20: 98, 21: 94, 22: 86},
    "WECHAT_OFFICIAL": {7: 83, 8: 90, 12: 76, 18: 82, 20: 88},
}


def prior_score(db: Session, platform: str, weekday: int, hour: int) -> float:
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


def curve(db: Session, platform: str, target_date: date) -> list[dict]:
    return [
        {
            "hour": hour,
            "time": f"{hour:02d}:00",
            "platformPrior": round(prior_score(db, platform, target_date.weekday(), hour), 1),
            "accountHistory": None,
        }
        for hour in range(24)
    ]


def recommend(db: Session, platform: str, target_date: date) -> dict:
    slots = []
    sample_count = (
        db.scalar(
            select(func.sum(AccountActivityStat.post_count)).where(
                AccountActivityStat.platform == platform
            )
        )
        or 0
    )
    for hour in range(24):
        prior = prior_score(db, platform, target_date.weekday(), hour)
        history = db.scalar(
            select(func.avg(AccountActivityStat.avg_engagement_rate)).where(
                AccountActivityStat.platform == platform,
                AccountActivityStat.day_of_week == target_date.weekday(),
                AccountActivityStat.hour_of_day == hour,
            )
        )
        history_score = min(100, float(history or 0) * 2000)
        content_score = 78 if hour in (8, 12, 18, 19, 20, 21) else 55
        timezone_score = 90 if 7 <= hour <= 22 else 20
        final = (
            0.4 * prior + 0.4 * history_score + 0.1 * content_score + 0.1 * timezone_score
            if sample_count
            else 0.7 * prior + 0.2 * content_score + 0.1 * timezone_score
        )
        for minute in (0, 30):
            slots.append(
                (round(final - (0 if minute == 0 else 1.2), 1), hour, minute, prior, history_score)
            )
    slots.sort(reverse=True)
    best = slots[0]
    recommended_at = datetime.combine(target_date, time(best[1], best[2]))
    if recommended_at <= datetime.now():
        recommended_at += timedelta(days=1)
    confidence = "HIGH" if sample_count >= 30 else "MEDIUM" if sample_count >= 10 else "LOW"
    reasons = [
        {
            "type": "PLATFORM_PRIOR",
            "description": f"{platform} 在 {best[1]:02d}:{best[2]:02d} 的公开活跃规则得分较高",
            "contribution": round(best[3] * (0.4 if sample_count else 0.7), 1),
        }
    ]
    if sample_count:
        reasons.append(
            {
                "type": "ACCOUNT_HISTORY",
                "description": f"已纳入 {sample_count} 条账号历史样本",
                "contribution": round(best[4] * 0.4, 1),
            }
        )
    else:
        reasons.append(
            {
                "type": "COLD_START",
                "description": "暂无账号历史数据，当前主要依据平台先验规则",
                "contribution": 0,
            }
        )
    alternatives = [
        {"recommendedAt": datetime.combine(target_date, time(h, m)).isoformat(), "score": score}
        for score, h, m, _, _ in slots[1:4]
    ]
    return {
        "recommendedAt": recommended_at,
        "score": best[0],
        "confidence": confidence,
        "reasons": reasons,
        "alternatives": alternatives,
        "sampleCount": int(sample_count),
        "algorithmVersion": "weighted-v1",
    }
