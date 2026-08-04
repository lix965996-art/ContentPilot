"""Seed a demo dataset where every schedule carries a real recommendation snapshot.

Existing demo schedules were created without ``recommendation_snapshot_json``, so the
"why this time" chain had to be recomputed after the fact. This script builds a richer
set by driving the actual ``recommend()`` algorithm at a historical point in time, so
each schedule stores the genuine reasons / weights / alternatives it was created with.

Engagement numbers are SIMULATED: the project has no real platform write access. The
simulated rate is derived from the slot's own activity score plus noise, which means
the recommended-vs-custom comparison reflects the model's assumption rather than a
measured platform effect. Everything is written with ``data_source="SIMULATED"`` so the
review page can badge it and keep it out of real-effect conclusions.

Run from project root:
  backend\\.venv\\Scripts\\python.exe scripts\\seed_decision_showcase.py
"""

from __future__ import annotations

import random
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.business import (  # noqa: E402
    ContentArticle,
    ContentVariant,
    EngagementMetric,
    PublishRecommendation,
    PublishSchedule,
)
from app.models.user import User  # noqa: E402
from app.services.activity_service import classify_content_type, content_type_name  # noqa: E402
from app.services.recommendation_service import explain_slot, recommend  # noqa: E402

# Platforms that actually have imported account history, so the "account history"
# weight is non-zero and the decision chain has something to show.
TARGET_PLATFORMS = ("WEIBO", "XIAOHONGSHU", "WECHAT_OFFICIAL")

# Typical engagement rate per platform, used as the midpoint of the simulation.
BASE_RATE = {"WEIBO": 0.022, "XIAOHONGSHU": 0.045, "WECHAT_OFFICIAL": 0.016}
BASE_IMPRESSIONS = {"WEIBO": 5200, "XIAOHONGSHU": 3400, "WECHAT_OFFICIAL": 2600}

# Round hours an operator tends to pick out of habit when ignoring the recommendation.
HABIT_HOURS = (9, 12, 15, 22)

SEED_TAG = "seed-decision-showcase"
RNG = random.Random(20260804)


def pick_variants(db, limit: int) -> list[ContentVariant]:
    """Prefer unused variants from distinct articles so the calendar does not repeat titles."""
    used = {row.variant_id for row in db.scalars(select(PublishSchedule)).all()}
    variants = db.scalars(
        select(ContentVariant)
        .where(ContentVariant.platform.in_(TARGET_PLATFORMS))
        .order_by(ContentVariant.platform, ContentVariant.id)
    ).all()
    free = [item for item in variants if item.id not in used]
    RNG.shuffle(free)

    picked: list[ContentVariant] = []
    seen_articles: set[int] = set()
    for item in free:
        if item.article_id in seen_articles:
            continue
        picked.append(item)
        seen_articles.add(item.article_id)
        if len(picked) >= limit:
            return picked
    # Fill remaining slots only if we still need more than unique articles allow.
    for item in free:
        if len(picked) >= limit:
            break
        if item not in picked:
            picked.append(item)
    return picked


def build_snapshot(rec: dict, recommendation_id: int) -> dict:
    return {
        "recommendationId": recommendation_id,
        "recommendedAt": rec["recommendedAt"].isoformat(),
        "score": rec["score"],
        "confidence": rec["confidence"],
        "algorithmVersion": rec["algorithmVersion"],
        "sampleCount": rec["sampleCount"],
        "accountSampleCount": rec["accountSampleCount"],
        "baselineSampleCount": rec["baselineSampleCount"],
        "weights": rec["weights"],
        "dataSource": rec["dataSource"],
        "reasons": rec["reasons"],
        "alternatives": rec["alternatives"],
        "warnings": rec["warnings"],
        "narrative": None,
        "narrativeProvider": None,
        "contentType": rec["contentType"],
        "contentTypeName": rec["contentTypeName"],
        # Stored so the review page can replay the exact window this score came from.
        "window": rec["window"],
    }


# Assignment cycle applied per platform, so both groups end up with a comparable
# platform mix. Pooling across platforms without stratifying would let the base-rate
# gap (XIAOHONGSHU ~4.5% vs WECHAT_OFFICIAL ~1.6%) dominate the slot effect.
ASSIGNMENT_CYCLE = ("RECOMMENDED", "CUSTOM", "RECOMMENDED", "ALTERNATIVE", "CUSTOM")


def choose_publish_time(rec: dict, day: date, intent: str) -> tuple[datetime, str]:
    """Turn the stratified assignment into a concrete publish time."""
    if intent == "RECOMMENDED":
        return rec["recommendedAt"], "RECOMMENDED"
    if intent == "ALTERNATIVE" and rec["alternatives"]:
        alt = datetime.fromisoformat(rec["alternatives"][0]["recommendedAt"])
        return alt, "ALTERNATIVE"
    options = [hour for hour in HABIT_HOURS if hour != rec["recommendedAt"].hour]
    return datetime.combine(day, time(RNG.choice(options), 0)), "CUSTOM"


def simulated_metric(
    db, schedule: PublishSchedule, content_type: str, adopted: bool
) -> EngagementMetric:
    """Derive a plausible engagement rate from the slot's own activity score.

    The mapping is intentionally noisy so the resulting comparison is not a
    perfectly straight line, but it is still a simulation, not a measurement.
    """
    evidence = explain_slot(
        db,
        platform=schedule.platform,
        moment=schedule.scheduled_at,
        content_type=content_type,
        account_id=schedule.account_id,
    )
    best = evidence["bestHourScore"] or 1.0
    quality = 0.70 + 0.6 * min(1.0, evidence["score"] / best)
    rate = BASE_RATE[schedule.platform] * quality * RNG.uniform(0.88, 1.12)
    impressions = int(BASE_IMPRESSIONS[schedule.platform] * RNG.uniform(0.6, 1.5))
    total = max(1, round(impressions * rate))

    likes = round(total * RNG.uniform(0.55, 0.68))
    comments = round(total * RNG.uniform(0.08, 0.14))
    collects = round(total * RNG.uniform(0.12, 0.20))
    shares = max(0, total - likes - comments - collects)

    return EngagementMetric(
        schedule_id=schedule.id,
        platform=schedule.platform,
        metric_date=schedule.scheduled_at.date() + timedelta(days=1),
        impressions=impressions,
        likes=likes,
        comments=comments,
        collects=collects,
        shares=shares,
        followers=RNG.randint(3200, 9800),
        engagement_total=total,
        engagement_rate=round(total / impressions, 6),
        group_type="RECOMMENDED_TIME" if adopted else "FIXED_TIME",
        data_source="SIMULATED",
    )


def reset(db) -> int:
    """Remove everything a previous run of this script created."""
    schedules = [
        row
        for row in db.scalars(select(PublishSchedule)).all()
        if row.idempotency_key.startswith(SEED_TAG)
    ]
    for schedule in schedules:
        for metric in db.scalars(
            select(EngagementMetric).where(EngagementMetric.schedule_id == schedule.id)
        ).all():
            db.delete(metric)
        recommendation_id = schedule.recommendation_id
        db.delete(schedule)
        if recommendation_id:
            recommendation = db.get(PublishRecommendation, recommendation_id)
            if recommendation:
                db.delete(recommendation)
    db.commit()
    return len(schedules)


def main(count: int = 30) -> None:
    with SessionLocal() as db:
        operator = db.scalar(select(User).where(User.username == "operator"))
        if not operator:
            raise SystemExit("operator 用户不存在，请先运行 seed_database")

        removed = reset(db)
        if removed:
            print(f"清理上一批种子数据：{removed} 条排期")

        variants = pick_variants(db, count)
        if not variants:
            print("没有可用的未排期版本，跳过。")
            return

        today = date.today()
        created = 0
        skipped = 0
        cycle_position: dict[str, int] = {}

        for index, variant in enumerate(variants):
            # Spread the schedules across the last ~50 days, newest first.
            day = today - timedelta(days=2 + index * 48 // max(1, len(variants)))
            article = db.get(ContentArticle, variant.article_id)
            content_type = classify_content_type(variant.title, variant.content_text)
            planning_moment = datetime.combine(day, time.min) - timedelta(hours=6)

            try:
                rec = recommend(
                    db,
                    variant.platform,
                    day,
                    content_type=content_type,
                    now=planning_moment,
                    horizon_days=1,
                    window="90D",
                )
            except ValueError as exc:
                print(f"  跳过 variant#{variant.id}（{variant.platform} {day}）：{exc}")
                skipped += 1
                continue

            recommendation = PublishRecommendation(
                article_id=variant.article_id,
                variant_id=variant.id,
                platform=variant.platform,
                recommended_at=rec["recommendedAt"],
                score=rec["score"],
                confidence=rec["confidence"],
                reason_json=rec["reasons"],
                alternative_times_json=rec["alternatives"],
                algorithm_version=rec["algorithmVersion"],
                sample_count=rec["sampleCount"],
                account_sample_count=rec["accountSampleCount"],
                baseline_sample_count=rec["baselineSampleCount"],
                weights_json=rec["weights"],
                data_source_json=rec["dataSource"],
                warnings_json=rec["warnings"],
                conflicts_json=rec["conflicts"],
                window_json=rec["window"],
                content_type=rec["contentType"],
            )
            db.add(recommendation)
            db.flush()

            position = cycle_position.get(variant.platform, 0)
            cycle_position[variant.platform] = position + 1
            intent = ASSIGNMENT_CYCLE[position % len(ASSIGNMENT_CYCLE)]
            published_at, time_source = choose_publish_time(rec, day, intent)
            schedule = PublishSchedule(
                article_id=variant.article_id,
                variant_id=variant.id,
                platform=variant.platform,
                scheduled_at=published_at,
                publish_mode="MANUAL_CONFIRM",
                status="SUCCESS",
                actual_publish_at=published_at + timedelta(minutes=RNG.randint(0, 4)),
                idempotency_key=f"{SEED_TAG}-{variant.id}-{int(published_at.timestamp())}",
                created_by=operator.id,
                recommendation_id=recommendation.id,
                recommended_at=rec["recommendedAt"],
                time_source=time_source,
                content_type=rec["contentType"],
                recommendation_snapshot_json=build_snapshot(rec, recommendation.id),
                publish_package_json={"seededBy": SEED_TAG, "simulated": True},
            )
            db.add(schedule)
            db.flush()

            db.add(
                simulated_metric(
                    db, schedule, rec["contentType"], time_source != "CUSTOM"
                )
            )
            created += 1
            print(
                f"  #{schedule.id} {variant.platform} {published_at:%Y-%m-%d %H:%M} "
                f"{time_source:<11} score={rec['score']:<6} "
                f"{content_type_name(rec['contentType'])} · "
                f"{(article.title if article else '')[:24]}"
            )

        db.commit()
        print(f"\n[OK] 新增 {created} 条带真实推荐快照的排期（跳过 {skipped} 条）。")
        print("互动数据标记为 SIMULATED，复盘页需开启「包含演示数据」才会纳入对比。")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 30)
