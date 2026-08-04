"""Activity analysis over imported historical engagement records.

The analysis never looks at raw view counts alone. Every record is reduced to a
composite score built from like / comment / share / favorite rates plus a
normalised view component, so that a high-reach but low-interaction post does
not outrank a smaller post that actually engaged its audience.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.business import EngagementHistory

WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# Time-window choices shared by activity analysis and publish-time recommendation.
WINDOW_CHOICES = ("30D", "90D", "ALL", "CUSTOM")
WINDOW_LABELS = {
    "30D": "最近30天",
    "90D": "最近90天",
    "ALL": "全部时间",
    "CUSTOM": "自定义时间范围",
}
DEFAULT_WINDOW = "90D"
# Below this many in-window samples, the caller should surface an explicit warning.
MIN_SUFFICIENT_SAMPLES = 10

# Composite interaction weights. Rates dominate; normalised views only act as a
# tie breaker so that reach alone cannot carry a slot.
RATE_WEIGHTS = {"like": 0.30, "comment": 0.30, "share": 0.25, "favorite": 0.15}
RATE_COMPONENT_WEIGHT = 0.85
VIEW_COMPONENT_WEIGHT = 0.15
# Saturation constant for the weighted rate: a 5% weighted interaction rate maps
# to 50 points, which keeps viral outliers from flattening the rest of the curve.
RATE_SATURATION = 0.05
# Bayesian shrinkage strength when a slot only has a handful of samples.
SHRINKAGE_SAMPLES = 3.0

ACCOUNT_SOURCE_TYPES = ("ACCOUNT_HISTORY",)
BASELINE_SOURCE_TYPES = ("PUBLIC_BASELINE", "YOUTUBE_PUBLIC_SAMPLE", "RESEARCH_DATASET")

SOURCE_TYPE_LABELS = {
    "ACCOUNT_HISTORY": "账号历史数据（用户导入）",
    "PUBLIC_BASELINE": "公开数据基线",
    "YOUTUBE_PUBLIC_SAMPLE": "YouTube 公开样本（非国内平台数据）",
    "RESEARCH_DATASET": "公开研究数据集",
}

CONTENT_TYPE_NAMES = {
    "KNOWLEDGE": "知识科普",
    "TUTORIAL": "教程攻略",
    "NEWS": "资讯速递",
    "OPINION": "观点评论",
    "LIFESTYLE": "生活分享",
    "PROMOTION": "活动推广",
    "REVIEW": "测评种草",
    "UNKNOWN": "未分类",
}

_CONTENT_TYPE_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("TUTORIAL", ("教程", "攻略", "步骤", "怎么做", "如何", "手把手", "指南", "清单", "模板")),
    ("KNOWLEDGE", ("原理", "科普", "解析", "为什么", "研究", "知识", "方法论", "概念")),
    ("NEWS", ("发布", "上线", "官宣", "最新", "快讯", "消息", "今日", "刚刚", "通报")),
    ("OPINION", ("观点", "评论", "看法", "思考", "反思", "争议", "我认为", "值得")),
    ("PROMOTION", ("活动", "报名", "优惠", "限时", "抽奖", "福利", "上新", "预约")),
    ("REVIEW", ("测评", "开箱", "体验", "对比", "种草", "实测", "推荐榜")),
    ("LIFESTYLE", ("日常", "生活", "记录", "vlog", "打卡", "随手", "分享一下")),
]


def content_type_name(code: str | None) -> str:
    if not code:
        return CONTENT_TYPE_NAMES["UNKNOWN"]
    return CONTENT_TYPE_NAMES.get(code.upper(), code)


def normalize_content_type(value: str | None) -> str:
    """Map a free-form content type label onto the canonical vocabulary."""
    if not value:
        return "UNKNOWN"
    text = str(value).strip()
    if not text:
        return "UNKNOWN"
    upper = text.upper().replace(" ", "_").replace("-", "_")
    if upper in CONTENT_TYPE_NAMES:
        return upper
    for code, name in CONTENT_TYPE_NAMES.items():
        if text == name:
            return code
    for code, keywords in _CONTENT_TYPE_RULES:
        if any(keyword in text for keyword in keywords):
            return code
    slug = upper.replace("&", "AND")
    slug = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in slug)
    while "__" in slug:
        slug = slug.replace("__", "_")
    slug = slug.strip("_")
    return slug[:50] if slug else "UNKNOWN"


def classify_content_type(*parts: str | None) -> str:
    """Rule-based content classification used whenever the LLM is unavailable."""
    text = " ".join(part for part in parts if part)
    if not text.strip():
        return "UNKNOWN"
    lowered = text.lower()
    scores: dict[str, int] = defaultdict(int)
    for code, keywords in _CONTENT_TYPE_RULES:
        for keyword in keywords:
            if keyword in text or keyword in lowered:
                scores[code] += 1
    if not scores:
        return "KNOWLEDGE" if len(re.findall(r"[\u4e00-\u9fff]", text)) > 120 else "UNKNOWN"
    return max(scores.items(), key=lambda item: item[1])[0]


def resolve_window(
    window: str = DEFAULT_WINDOW,
    start_date: date | None = None,
    end_date: date | None = None,
    *,
    now: datetime | None = None,
) -> dict:
    """Normalise the four supported time-window choices into a concrete range.

    ``start``/``end`` are ``None`` for the unbounded "ALL" window; otherwise they
    are concrete datetimes ready to filter ``EngagementHistory.publish_time``.
    """
    now = now or datetime.now()
    window = (window or DEFAULT_WINDOW).upper()
    if window not in WINDOW_CHOICES:
        raise ValueError("时间范围只能是 30D / 90D / ALL / CUSTOM")
    start: datetime | None
    end: datetime | None
    if window == "ALL":
        start, end = None, None
    elif window == "CUSTOM":
        if not start_date or not end_date:
            raise ValueError("自定义时间范围必须同时提供开始日期和结束日期")
        if end_date < start_date:
            raise ValueError("自定义时间范围的结束日期不能早于开始日期")
        start = datetime.combine(start_date, time.min)
        end = datetime.combine(end_date, time.max)
    else:
        days = 30 if window == "30D" else 90
        end = now
        start = now - timedelta(days=days)
    return {
        "window": window,
        "label": WINDOW_LABELS[window],
        "start": start,
        "end": end,
        "startDate": start.date().isoformat() if start else None,
        "endDate": end.date().isoformat() if end else None,
    }


def window_sufficiency(sample_count: int, window_info: dict) -> dict:
    """Shared "is this enough data" verdict used by both analysis and recommendation."""
    sufficient = sample_count >= MIN_SUFFICIENT_SAMPLES
    label = window_info["label"]
    message = (
        f"{label}内样本 {sample_count} 条，数据充足"
        if sufficient
        else (
            f"{label}内样本仅 {sample_count} 条，可能不足以支撑稳定分析，"
            "建议扩大时间范围或继续导入历史数据"
        )
    )
    return {"sufficient": sufficient, "message": message, "sampleCount": sample_count}


def reach_of(views: int, impressions: int, followers: int) -> tuple[int, str]:
    """Pick the denominator for rate metrics and report which one was used."""
    if impressions > 0:
        return impressions, "IMPRESSIONS"
    if views > 0:
        return views, "VIEWS"
    if followers > 0:
        return followers, "FOLLOWERS"
    return 0, "NONE"


def compute_metrics(
    *,
    views: int,
    impressions: int,
    likes: int,
    comments: int,
    shares: int,
    favorites: int,
    followers: int,
) -> dict:
    """Derive interaction rates and the saturated rate component for one record."""
    reach, basis = reach_of(views, impressions, followers)
    total = likes + comments + shares + favorites
    rates = {
        "like": likes / reach if reach else 0.0,
        "comment": comments / reach if reach else 0.0,
        "share": shares / reach if reach else 0.0,
        "favorite": favorites / reach if reach else 0.0,
    }
    weighted = sum(RATE_WEIGHTS[key] * value for key, value in rates.items())
    rate_component = 100 * (weighted / (weighted + RATE_SATURATION)) if weighted > 0 else 0.0
    return {
        "reach": reach,
        "metricBasis": basis,
        "engagementTotal": total,
        "engagementRate": round(total / reach, 6) if reach else 0.0,
        "likeRate": round(rates["like"], 6),
        "commentRate": round(rates["comment"], 6),
        "shareRate": round(rates["share"], 6),
        "favoriteRate": round(rates["favorite"], 6),
        "rateComponent": round(rate_component, 4),
    }


def _view_reference(rows: list[EngagementHistory]) -> float:
    """Return the 90th percentile of reach, used to normalise the view component."""
    reaches = sorted(
        float(max(row.views, row.impressions))
        for row in rows
        if max(row.views, row.impressions) > 0
    )
    if not reaches:
        return 0.0
    index = min(len(reaches) - 1, int(len(reaches) * 0.9))
    return reaches[index]


def composite_score(row: EngagementHistory, view_reference: float) -> float:
    """Blend the stored rate component with a corpus-normalised view component."""
    rate_component = float(row.engagement_score or 0)
    reach = float(max(row.views, row.impressions))
    if view_reference > 0 and reach > 0:
        views_norm = min(1.0, math.log1p(reach) / math.log1p(view_reference))
    else:
        views_norm = 0.0
    return round(
        RATE_COMPONENT_WEIGHT * rate_component + VIEW_COMPONENT_WEIGHT * views_norm * 100, 3
    )


def history_query(
    *,
    platform: str | None = None,
    account_id: int | None = None,
    content_type: str | None = None,
    source_types: tuple[str, ...] | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> Select:
    query = select(EngagementHistory)
    if platform:
        query = query.where(EngagementHistory.platform == platform)
    if account_id:
        query = query.where(EngagementHistory.account_id == account_id)
    if content_type and content_type != "UNKNOWN":
        query = query.where(EngagementHistory.content_type == content_type)
    if source_types:
        query = query.where(EngagementHistory.source_type.in_(source_types))
    if start:
        query = query.where(EngagementHistory.publish_time >= start)
    if end:
        query = query.where(EngagementHistory.publish_time <= end)
    return query


def load_rows(
    db: Session,
    *,
    platform: str | None = None,
    account_id: int | None = None,
    content_type: str | None = None,
    source_types: tuple[str, ...] | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[EngagementHistory]:
    return list(
        db.scalars(
            history_query(
                platform=platform,
                account_id=account_id,
                content_type=content_type,
                source_types=source_types,
                start=start,
                end=end,
            )
        ).all()
    )


def count_rows(
    db: Session,
    *,
    platform: str | None = None,
    account_id: int | None = None,
    content_type: str | None = None,
    source_types: tuple[str, ...] | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> int:
    query = history_query(
        platform=platform,
        account_id=account_id,
        content_type=content_type,
        source_types=source_types,
        start=start,
        end=end,
    )
    return int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)


def slot_statistics(rows: list[EngagementHistory]) -> dict:
    """Aggregate records into weekday / hour / weekday-hour slot statistics."""
    reference = _view_reference(rows)
    scores = [(row, composite_score(row, reference)) for row in rows]
    global_mean = round(sum(score for _, score in scores) / len(scores), 3) if scores else 0.0

    slots: dict[tuple[int, int], list[float]] = defaultdict(list)
    for row, score in scores:
        slots[(row.day_of_week, row.hour_of_day)].append(score)

    shrunk: dict[tuple[int, int], dict] = {}
    for key, values in slots.items():
        count = len(values)
        raw_mean = sum(values) / count
        adjusted = (count * raw_mean + SHRINKAGE_SAMPLES * global_mean) / (
            count + SHRINKAGE_SAMPLES
        )
        shrunk[key] = {
            "sampleCount": count,
            "rawScore": round(raw_mean, 3),
            "score": round(adjusted, 3),
        }
    return {
        "globalMean": global_mean,
        "viewReference": round(reference, 2),
        "slots": shrunk,
        "scores": scores,
    }


def _bucket_summary(rows: list[tuple[EngagementHistory, float]]) -> dict:
    if not rows:
        return {
            "sampleCount": 0,
            "score": 0.0,
            "engagementRate": 0.0,
            "avgViews": 0,
            "avgLikes": 0,
            "avgComments": 0,
            "avgShares": 0,
            "avgFavorites": 0,
        }
    count = len(rows)
    return {
        "sampleCount": count,
        "score": round(sum(score for _, score in rows) / count, 2),
        "engagementRate": round(
            sum(float(row.engagement_rate) for row, _ in rows) / count * 100, 3
        ),
        "avgViews": round(sum(max(row.views, row.impressions) for row, _ in rows) / count, 1),
        "avgLikes": round(sum(row.likes for row, _ in rows) / count, 1),
        "avgComments": round(sum(row.comments for row, _ in rows) / count, 1),
        "avgShares": round(sum(row.shares for row, _ in rows) / count, 1),
        "avgFavorites": round(sum(row.favorites for row, _ in rows) / count, 1),
    }


_COMPLETENESS_FIELDS = [
    ("views", "浏览量"),
    ("impressions", "曝光量"),
    ("likes", "点赞"),
    ("comments", "评论"),
    ("shares", "转发/分享"),
    ("favorites", "收藏"),
    ("followers", "粉丝数"),
]


def _completeness(rows: list[EngagementHistory]) -> dict:
    total = len(rows)
    fields = []
    for field, label in _COMPLETENESS_FIELDS:
        filled = sum(1 for row in rows if int(getattr(row, field) or 0) > 0)
        fields.append(
            {
                "field": field,
                "label": label,
                "filled": filled,
                "total": total,
                "percent": round(filled / total * 100, 1) if total else 0.0,
            }
        )
    typed = sum(1 for row in rows if row.content_type and row.content_type != "UNKNOWN")
    fields.append(
        {
            "field": "content_type",
            "label": "内容类型",
            "filled": typed,
            "total": total,
            "percent": round(typed / total * 100, 1) if total else 0.0,
        }
    )
    score = round(sum(item["percent"] for item in fields) / len(fields), 1) if total else 0.0
    times = [row.publish_time for row in rows if row.publish_time]
    return {
        "score": score,
        "fields": fields,
        "dateRange": {
            "start": min(times).isoformat() if times else None,
            "end": max(times).isoformat() if times else None,
        },
    }


def analyze(
    db: Session,
    *,
    platform: str | None = None,
    account_id: int | None = None,
    content_type: str | None = None,
    source_scope: str = "ALL",
    window: str = DEFAULT_WINDOW,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    """Full activity report: weekday, hour, weekday×hour and content-type slots."""
    source_types: tuple[str, ...] | None = None
    if source_scope == "ACCOUNT":
        source_types = ACCOUNT_SOURCE_TYPES
    elif source_scope == "BASELINE":
        source_types = BASELINE_SOURCE_TYPES

    window_info = resolve_window(window, start_date, end_date)
    rows = load_rows(
        db,
        platform=platform,
        account_id=account_id,
        content_type=content_type,
        source_types=source_types,
        start=window_info["start"],
        end=window_info["end"],
    )
    stats = slot_statistics(rows)
    scores: list[tuple[EngagementHistory, float]] = stats["scores"]

    weekday_buckets: dict[int, list[tuple[EngagementHistory, float]]] = defaultdict(list)
    hour_buckets: dict[int, list[tuple[EngagementHistory, float]]] = defaultdict(list)
    type_buckets: dict[str, list[tuple[EngagementHistory, float]]] = defaultdict(list)
    for row, score in scores:
        weekday_buckets[row.day_of_week].append((row, score))
        hour_buckets[row.hour_of_day].append((row, score))
        type_buckets[row.content_type or "UNKNOWN"].append((row, score))

    weekday = [
        {"dayOfWeek": day, "name": WEEKDAY_NAMES[day], **_bucket_summary(weekday_buckets[day])}
        for day in range(7)
    ]
    hourly = [
        {"hour": hour, "time": f"{hour:02d}:00", **_bucket_summary(hour_buckets[hour])}
        for hour in range(24)
    ]
    heatmap = [
        {
            "dayOfWeek": day,
            "name": WEEKDAY_NAMES[day],
            "hour": hour,
            "sampleCount": stats["slots"].get((day, hour), {}).get("sampleCount", 0),
            "score": stats["slots"].get((day, hour), {}).get("score", 0.0),
        }
        for day in range(7)
        for hour in range(24)
    ]

    content_types = []
    for code, bucket in type_buckets.items():
        slot_scores: dict[tuple[int, int], list[float]] = defaultdict(list)
        for row, score in bucket:
            slot_scores[(row.day_of_week, row.hour_of_day)].append(score)
        best = sorted(
            (
                {
                    "dayOfWeek": key[0],
                    "dayName": WEEKDAY_NAMES[key[0]],
                    "hour": key[1],
                    "time": f"{key[1]:02d}:00",
                    "sampleCount": len(values),
                    "score": round(sum(values) / len(values), 2),
                }
                for key, values in slot_scores.items()
            ),
            key=lambda item: (item["score"], item["sampleCount"]),
            reverse=True,
        )[:3]
        content_types.append(
            {
                "contentType": code,
                "contentTypeName": content_type_name(code),
                **_bucket_summary(bucket),
                "bestSlots": best,
            }
        )
    content_types.sort(key=lambda item: item["sampleCount"], reverse=True)

    source_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        source_counts[row.source_type] += 1
    sources = [
        {
            "sourceType": key,
            "label": SOURCE_TYPE_LABELS.get(key, key),
            "count": value,
        }
        for key, value in sorted(source_counts.items(), key=lambda item: item[1], reverse=True)
    ]

    account_count = sum(1 for row in rows if row.source_type in ACCOUNT_SOURCE_TYPES)
    baseline_count = len(rows) - account_count
    top_slots = sorted(
        (
            {
                "dayOfWeek": key[0],
                "dayName": WEEKDAY_NAMES[key[0]],
                "hour": key[1],
                "time": f"{key[1]:02d}:00",
                **value,
            }
            for key, value in stats["slots"].items()
        ),
        key=lambda item: (item["score"], item["sampleCount"]),
        reverse=True,
    )[:8]

    return {
        "filters": {
            "platform": platform or "",
            "accountId": account_id,
            "contentType": content_type or "",
            "sourceScope": source_scope,
            "window": window_info["window"],
            "startDate": window_info["startDate"],
            "endDate": window_info["endDate"],
        },
        "windowInfo": {
            "window": window_info["window"],
            "label": window_info["label"],
            "startDate": window_info["startDate"],
            "endDate": window_info["endDate"],
            **window_sufficiency(len(rows), window_info),
        },
        "sampleCount": len(rows),
        "accountSampleCount": account_count,
        "baselineSampleCount": baseline_count,
        "globalMeanScore": stats["globalMean"],
        "weekday": weekday,
        "hourly": hourly,
        "heatmap": heatmap,
        "contentTypes": content_types,
        "topSlots": top_slots,
        "completeness": _completeness(rows),
        "sources": sources,
        "scoreFormula": (
            "综合得分 = 85% × 互动率成分（点赞 30% / 评论 30% / 分享 25% / 收藏 15%，"
            "饱和归一）+ 15% × 标准化浏览量；样本不足的时段按贝叶斯收缩向整体均值回归。"
        ),
        "notice": (
            "分析仅基于已导入的历史数据。公开基线样本（含 YouTube 公开数据集）"
            "只用于冷启动参考，不代表国内平台真实数据。"
        ),
    }


def summarize_import_window(rows: list[EngagementHistory]) -> dict:
    times = [row.publish_time for row in rows if row.publish_time]
    return {
        "start": min(times).isoformat() if times else None,
        "end": max(times).isoformat() if times else None,
        "days": (max(times) - min(times)).days if len(times) > 1 else 0,
    }


def parse_publish_time(value: object) -> datetime:
    """Accept the common spreadsheet date formats used by platform exports."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    text = str(value or "").strip()
    if not text:
        raise ValueError("publish_time 不能为空")
    text = text.replace("/", "-").replace("T", " ").strip()
    if text.endswith("Z"):
        text = text[:-1]
    candidates = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H",
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S.%f",
    )
    for pattern in candidates:
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    raise ValueError(f"无法解析发布时间：{value}")
