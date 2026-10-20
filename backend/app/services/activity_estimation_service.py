"""Weighted user-activity estimation over semantically similar history.

Every historical record contributes to the 7x24 slot table with a weight built
from four independent factors:

    weight = semantic_similarity * time_decay * data_quality * source_reliability

Time decay is exponential: ``exp(-age_days / decay_days)``, so older evidence
always counts less than fresh evidence. Incomplete rows (missing views /
impressions / interaction columns) get a lower ``data_quality`` factor.

When the account's own similar content is too thin, the slot estimate is
Bayesian-smoothed through a prior chain instead of any hard-coded split between
personal and public data:

    account similar -> account all -> platform similar -> platform all
    -> cross-platform public datasets -> system default

The cross-platform level exists because a brand-new platform often has no data
at all, while public research datasets (currently the YouTube sample) do carry a
usable diurnal shape. Borrowed rows are discounted by
``CROSS_PLATFORM_RELIABILITY`` and reported under their own level name so the UI
never presents them as native platform data.

The shrinkage weight is derived from the effective sample count, so the mix
moves continuously with how much real data exists.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.business import EngagementHistory
from app.services.activity_service import (
    ACCOUNT_SOURCE_TYPES,
    BASELINE_SOURCE_TYPES,
    WEEKDAY_NAMES,
    business_now,
    history_is_simulated,
    load_rows,
    normalize_business_time,
)

ESTIMATOR_VERSION = "activity-semantic-v1"
# Effective sample count at which a slot's own mean fully outweighs its prior.
SHRINKAGE_STRENGTH = 8.0
SYSTEM_DEFAULT_SCORE = 45.0

SOURCE_RELIABILITY = {
    "ACCOUNT_HISTORY": 1.0,
    "PUBLIC_BASELINE": 0.75,
    "RESEARCH_DATASET": 0.7,
    "YOUTUBE_PUBLIC_SAMPLE": 0.55,
}
# Extra discount when a sample is borrowed from a different platform: the
# diurnal shape transfers, the absolute engagement level does not.
CROSS_PLATFORM_RELIABILITY = 0.6


@dataclass(frozen=True)
class WeightedSample:
    row_id: int
    platform: str
    day_of_week: int
    hour_of_day: int
    publish_time: datetime
    semantic_similarity: float
    time_weight: float
    data_quality: float
    source_reliability: float
    views: int
    engagement_rate: float
    favorite_rate: float
    share_rate: float

    @property
    def weight(self) -> float:
        return (
            self.semantic_similarity
            * self.time_weight
            * self.data_quality
            * self.source_reliability
        )


def time_weight(publish_time: datetime, *, now: datetime, decay_days: int | None = None) -> float:
    """Exponential recency decay: exp(-age_days / decay_days)."""
    decay = float(decay_days or settings.activity_decay_days or 90)
    age_days = max(
        0.0,
        (normalize_business_time(now) - normalize_business_time(publish_time)).total_seconds()
        / 86400,
    )
    return math.exp(-age_days / max(1.0, decay))


def data_quality(row: EngagementHistory) -> float:
    """Completeness factor in (0, 1]: rows missing metrics are trusted less."""
    checks = [
        bool(row.views or row.impressions),
        bool(row.likes),
        bool(row.comments or row.shares or row.favorites),
        bool(row.followers),
    ]
    present = sum(1 for item in checks if item)
    # Always keep a floor so a sparse-but-real row still carries some signal.
    return round(0.25 + 0.75 * present / len(checks), 4)


def _rate(numerator: int, denominator: int) -> float:
    base = denominator or 0
    if base <= 0:
        return 0.0
    return round(min(1.0, numerator / base), 6)


def build_samples(
    rows: list[EngagementHistory],
    similarity_by_row: dict[int, float],
    *,
    now: datetime,
    default_similarity: float = 0.35,
    decay_days: int | None = None,
    reliability_factor: float = 1.0,
) -> list[WeightedSample]:
    """Turn history rows into weighted samples, keyed by semantic similarity."""
    samples: list[WeightedSample] = []
    for row in rows:
        if history_is_simulated(row) or normalize_business_time(
            row.publish_time
        ) > normalize_business_time(now):
            continue
        detail = row.metric_detail_json or {}
        basis = str(detail.get("metricBasis") or "")
        if basis in {"UNKNOWN", "NONE"}:
            continue
        similarity = similarity_by_row.get(row.id)
        if similarity is None:
            similarity = default_similarity
        # Cosine can be negative; clamp so a weight never flips sign.
        similarity = max(0.05, min(1.0, float(similarity)))
        reach_value = {
            "IMPRESSIONS": row.impressions,
            "VIEWS": row.views,
            "FOLLOWERS": row.followers,
        }.get(basis)
        if reach_value is None:
            reach_value = detail.get("reach") or row.impressions or row.views or 0
        reach = int(reach_value)
        samples.append(
            WeightedSample(
                row_id=row.id,
                platform=row.platform,
                day_of_week=row.day_of_week,
                hour_of_day=row.hour_of_day,
                publish_time=row.publish_time,
                semantic_similarity=similarity,
                time_weight=time_weight(row.publish_time, now=now, decay_days=decay_days),
                data_quality=data_quality(row),
                source_reliability=SOURCE_RELIABILITY.get(row.source_type, 0.5)
                * reliability_factor,
                views=reach,
                engagement_rate=row.engagement_rate
                or _rate(row.likes + row.comments + row.shares + row.favorites, reach),
                favorite_rate=_rate(row.favorites, reach),
                share_rate=_rate(row.shares, reach),
            )
        )
    return samples


def _slot_table(samples: list[WeightedSample]) -> dict[tuple[int, int], dict]:
    """Weighted aggregates per (weekday, hour) slot."""
    buckets: dict[tuple[int, int], list[WeightedSample]] = defaultdict(list)
    for sample in samples:
        buckets[(sample.day_of_week, sample.hour_of_day)].append(sample)

    table: dict[tuple[int, int], dict] = {}
    for key, bucket in buckets.items():
        total_weight = sum(item.weight for item in bucket)
        if total_weight <= 0:
            continue
        weighted_views = sum(item.views * item.weight for item in bucket) / total_weight
        weighted_engagement = (
            sum(item.engagement_rate * item.weight for item in bucket) / total_weight
        )
        weighted_favorite = sum(item.favorite_rate * item.weight for item in bucket) / total_weight
        weighted_share = sum(item.share_rate * item.weight for item in bucket) / total_weight
        # Effective sample count (Kish): rewards many evenly-weighted samples and
        # penalises a bucket dominated by one heavy record.
        squared = sum(item.weight**2 for item in bucket)
        effective = (total_weight**2 / squared) if squared else 0.0
        mean_engagement = weighted_engagement
        variance = (
            sum(item.weight * (item.engagement_rate - mean_engagement) ** 2 for item in bucket)
            / total_weight
        )
        table[key] = {
            "dayOfWeek": key[0],
            "dayName": WEEKDAY_NAMES[key[0]],
            "hour": key[1],
            "weightedViews": round(weighted_views, 2),
            "weightedEngagementRate": round(weighted_engagement, 6),
            "weightedFavoriteRate": round(weighted_favorite, 6),
            "weightedShareRate": round(weighted_share, 6),
            "effectiveSampleCount": round(effective, 3),
            "variance": round(variance, 8),
            "latestSampleTime": max(item.publish_time for item in bucket).isoformat(),
            "totalWeight": round(total_weight, 4),
            "rawSampleCount": len(bucket),
        }
    return table


def _slot_score(entry: dict) -> float:
    """Map weighted rates onto a 0-100 comparable activity score."""
    engagement = min(1.0, entry["weightedEngagementRate"] * 12)
    favorite = min(1.0, entry["weightedFavoriteRate"] * 25)
    share = min(1.0, entry["weightedShareRate"] * 30)
    reach = min(1.0, math.log10(max(1.0, entry["weightedViews"]) + 1) / 5)
    raw = 0.45 * engagement + 0.2 * favorite + 0.15 * share + 0.2 * reach
    return round(100 * raw, 3)


def _mean_score(table: dict[tuple[int, int], dict]) -> float:
    if not table:
        return SYSTEM_DEFAULT_SCORE
    weights = sum(entry["totalWeight"] for entry in table.values())
    if weights <= 0:
        return SYSTEM_DEFAULT_SCORE
    return round(
        sum(_slot_score(entry) * entry["totalWeight"] for entry in table.values()) / weights, 3
    )


@dataclass(frozen=True)
class PriorLevel:
    name: str
    label: str
    table: dict[tuple[int, int], dict]
    mean: float


def estimate(
    db: Session,
    *,
    platform: str,
    account_id: int | None,
    similarity_by_row: dict[int, float],
    now: datetime | None = None,
    decay_days: int | None = None,
) -> dict:
    """Build the smoothed 7x24 activity estimate for one platform/account.

    ``similarity_by_row`` maps ``engagement_history.id`` to the semantic
    similarity of that record against the content being scheduled. Records not
    present in the map still participate through the prior chain with a low
    default similarity, so the estimate degrades smoothly instead of emptying
    out when retrieval finds few matches.
    """
    now = normalize_business_time(now) if now else business_now()
    similar_ids = set(similarity_by_row)

    account_rows = load_rows(
        db, platform=platform, account_id=account_id, source_types=ACCOUNT_SOURCE_TYPES, end=now
    )
    platform_rows = load_rows(db, platform=platform, end=now)
    baseline_rows = [row for row in platform_rows if row.source_type in BASELINE_SOURCE_TYPES]
    # Public datasets from *other* platforms: the last resort before the flat
    # system default, used mainly while a platform is still in cold start.
    cross_rows = [
        row
        for row in load_rows(db, source_types=BASELINE_SOURCE_TYPES, end=now)
        if row.platform != platform
    ]

    account_similar = [row for row in account_rows if row.id in similar_ids]
    platform_similar = [row for row in platform_rows if row.id in similar_ids]

    def table_for(
        rows: list[EngagementHistory],
        *,
        only_similar: bool,
        reliability_factor: float = 1.0,
    ) -> dict:
        if not rows:
            return {}
        samples = build_samples(
            rows,
            similarity_by_row if only_similar else {},
            now=now,
            decay_days=decay_days,
            reliability_factor=reliability_factor,
        )
        return _slot_table(samples)

    levels: list[PriorLevel] = []
    for name, label, rows, only_similar, reliability in (
        ("ACCOUNT_SIMILAR", "账号内语义相似内容", account_similar, True, 1.0),
        ("ACCOUNT_ALL", "账号全部历史内容", account_rows, False, 1.0),
        ("PLATFORM_SIMILAR", "平台语义相似内容基线", platform_similar, True, 1.0),
        ("PLATFORM_ALL", "平台总体基线", baseline_rows or platform_rows, False, 1.0),
        (
            "CROSS_PLATFORM_PUBLIC",
            "跨平台公开数据集基线（代理）",
            cross_rows,
            False,
            CROSS_PLATFORM_RELIABILITY,
        ),
    ):
        table = table_for(rows, only_similar=only_similar, reliability_factor=reliability)
        if table:
            levels.append(PriorLevel(name, label, table, _mean_score(table)))
    default_label = (
        "人工规则基线（非 Mastodon 历史统计）" if platform == "MASTODON" else "系统默认基线"
    )
    levels.append(PriorLevel("SYSTEM_DEFAULT", default_label, {}, SYSTEM_DEFAULT_SCORE))

    primary = levels[0]
    slots: dict[str, dict] = {}
    covered_slots = 0
    for weekday in range(7):
        for hour in range(24):
            key = (weekday, hour)
            entry = primary.table.get(key)
            observed = _slot_score(entry) if entry else None
            effective = entry["effectiveSampleCount"] if entry else 0.0

            # Walk the prior chain until a level can speak for this slot.
            prior_score = SYSTEM_DEFAULT_SCORE
            prior_level = "SYSTEM_DEFAULT"
            prior_label = default_label
            for level in levels[1:]:
                candidate = level.table.get(key)
                if candidate:
                    prior_score = _slot_score(candidate)
                    prior_level = level.name
                    prior_label = level.label
                    break
                if level.name == "SYSTEM_DEFAULT":
                    prior_score = level.mean
                    prior_level = level.name
                    prior_label = level.label
                    break

            if observed is None:
                score = prior_score
                shrinkage = 0.0
            else:
                covered_slots += 1
                shrinkage = effective / (effective + SHRINKAGE_STRENGTH)
                score = shrinkage * observed + (1 - shrinkage) * prior_score

            slots[f"{weekday}-{hour}"] = {
                "dayOfWeek": weekday,
                "dayName": WEEKDAY_NAMES[weekday],
                "hour": hour,
                "score": round(score, 3),
                "observedScore": round(observed, 3) if observed is not None else None,
                "priorScore": round(prior_score, 3),
                "priorLevel": prior_level,
                "priorLabel": prior_label,
                # 0-1 ratio: how much of the score comes from real observations
                # rather than the smoothing prior.
                "dataConfidence": round(shrinkage, 4),
                "observationWeight": round(shrinkage, 4),
                "effectiveSampleCount": round(effective, 3),
                "variance": entry["variance"] if entry else None,
                "weightedViews": entry["weightedViews"] if entry else None,
                "weightedEngagementRate": entry["weightedEngagementRate"] if entry else None,
                "weightedFavoriteRate": entry["weightedFavoriteRate"] if entry else None,
                "weightedShareRate": entry["weightedShareRate"] if entry else None,
                "latestSampleTime": entry["latestSampleTime"] if entry else None,
                "rawSampleCount": entry["rawSampleCount"] if entry else 0,
            }

    total_effective = round(
        sum(entry["effectiveSampleCount"] for entry in primary.table.values()), 3
    )
    confidence = "HIGH" if total_effective >= 20 else ("MEDIUM" if total_effective >= 6 else "LOW")
    return {
        "estimatorVersion": ESTIMATOR_VERSION,
        "platform": platform,
        "accountId": account_id,
        "decayDays": int(decay_days or settings.activity_decay_days or 90),
        "priorStrength": SHRINKAGE_STRENGTH,
        "primaryLevel": primary.name,
        "primaryLevelLabel": primary.label,
        "priorChain": [
            {
                "level": item.name,
                "label": item.label,
                "slotCount": len(item.table),
                "mean": item.mean,
            }
            for item in levels
        ],
        "levelSampleCounts": {item.name: len(item.table) for item in levels},
        "levelMeans": {item.name: item.mean for item in levels},
        "coveredSlots": covered_slots,
        "similarSampleCount": len(account_similar) or len(platform_similar),
        "accountSampleCount": len(account_rows),
        "platformSampleCount": len(platform_rows),
        "platformEvidenceNote": (
            "尚未导入 Mastodon 账号或实例历史；冷启动仅参考人工规则或已标注的跨平台代理数据。"
            if platform == "MASTODON" and not platform_rows
            else ""
        ),
        "baselineSampleCount": len(baseline_rows),
        "crossPlatformSampleCount": len(cross_rows),
        "effectiveSampleCount": total_effective,
        "confidence": confidence,
        "slots": slots,
    }


def slot_entry(estimate_result: dict, weekday: int, hour: int) -> dict:
    return estimate_result.get("slots", {}).get(f"{weekday}-{hour}") or {}


def slot_score(estimate_result: dict, weekday: int, hour: int) -> float:
    entry = slot_entry(estimate_result, weekday, hour)
    return float(entry["score"]) if entry else SYSTEM_DEFAULT_SCORE


def hourly_curve(estimate_result: dict, weekday: int) -> list[dict]:
    """24-point curve for one weekday, used by the detail drawer chart."""
    return [
        {
            "hour": hour,
            "score": slot_score(estimate_result, weekday, hour),
            "effectiveSampleCount": slot_entry(estimate_result, weekday, hour).get(
                "effectiveSampleCount", 0
            ),
            "dataConfidence": slot_entry(estimate_result, weekday, hour).get("dataConfidence", 0),
        }
        for hour in range(24)
    ]
