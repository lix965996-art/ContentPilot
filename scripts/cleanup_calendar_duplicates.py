"""Remove dense / accidental duplicate schedules so the calendar is readable.

Keeps enough seeded showcase rows for the decision-chain demo. Prefer keeping
schedules that have a recommendation snapshot or engagement metrics.

Run from project root:
  backend\\.venv\\Scripts\\python.exe scripts\\cleanup_calendar_duplicates.py
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.business import (  # noqa: E402
    ContentArticle,
    EngagementMetric,
    ExperimentSample,
    PublishLog,
    PublishRecommendation,
    PublishSchedule,
)

SEED = "seed-decision-showcase"
# Soft cap so one article does not dominate the month grid.
MAX_PER_ARTICLE = 3


def keep_score(schedule: PublishSchedule, has_metric: bool) -> tuple:
    return (
        1 if schedule.recommendation_snapshot_json else 0,
        1 if has_metric else 0,
        1 if schedule.time_source in {"RECOMMENDED", "ALTERNATIVE"} else 0,
        1 if schedule.idempotency_key.startswith(SEED) else 0,
        schedule.scheduled_at.timestamp(),
    )


def delete_schedule(db, schedule: PublishSchedule) -> None:
    for metric in db.scalars(
        select(EngagementMetric).where(EngagementMetric.schedule_id == schedule.id)
    ).all():
        db.delete(metric)
    for log in db.scalars(select(PublishLog).where(PublishLog.schedule_id == schedule.id)).all():
        db.delete(log)
    for sample in db.scalars(
        select(ExperimentSample).where(ExperimentSample.schedule_id == schedule.id)
    ).all():
        db.delete(sample)
    recommendation_id = schedule.recommendation_id
    db.delete(schedule)
    if recommendation_id and schedule.idempotency_key.startswith(SEED):
        # Only delete recommendations created by the showcase seed.
        recommendation = db.get(PublishRecommendation, recommendation_id)
        if recommendation:
            still_used = db.scalar(
                select(PublishSchedule.id).where(
                    PublishSchedule.recommendation_id == recommendation_id
                )
            )
            if still_used is None:
                db.delete(recommendation)


def main() -> None:
    with SessionLocal() as db:
        arts = {
            row.id: row.title for row in db.scalars(select(ContentArticle)).all()
        }
        schedules = list(db.scalars(select(PublishSchedule)).all())
        metric_ids = set(db.scalars(select(EngagementMetric.schedule_id)).all())

        remove: set[int] = set()

        # 1) Same article + platform + calendar day → keep the strongest one.
        by_day: dict[tuple, list[PublishSchedule]] = defaultdict(list)
        for row in schedules:
            key = (row.article_id, row.platform, row.scheduled_at.strftime("%Y-%m-%d"))
            by_day[key].append(row)
        for rows in by_day.values():
            if len(rows) < 2:
                continue
            ranked = sorted(
                rows,
                key=lambda item: keep_score(item, item.id in metric_ids),
                reverse=True,
            )
            for loser in ranked[1:]:
                remove.add(loser.id)

        # 2) Cap remaining schedules per article.
        survivors = [row for row in schedules if row.id not in remove]
        by_article: dict[int, list[PublishSchedule]] = defaultdict(list)
        for row in survivors:
            by_article[row.article_id].append(row)
        for article_id, rows in by_article.items():
            if len(rows) <= MAX_PER_ARTICLE:
                continue
            ranked = sorted(
                rows,
                key=lambda item: keep_score(item, item.id in metric_ids),
                reverse=True,
            )
            keep: list[PublishSchedule] = []
            seen_platforms: set[str] = set()
            # Prefer one schedule per platform first, then fill by score.
            for row in ranked:
                if len(keep) >= MAX_PER_ARTICLE:
                    break
                if row.platform in seen_platforms:
                    continue
                keep.append(row)
                seen_platforms.add(row.platform)
            for row in ranked:
                if len(keep) >= MAX_PER_ARTICLE:
                    break
                if row not in keep:
                    keep.append(row)
            for loser in rows:
                if loser not in keep:
                    remove.add(loser.id)

        if not remove:
            print("没有需要清理的重复排期。")
            return

        print(f"将删除 {len(remove)} 条重复/过密排期，保留示例如下：")
        kept_preview = [row for row in schedules if row.id not in remove]
        from collections import Counter

        print("清理前文章分布：", Counter(arts[s.article_id][:18] for s in schedules).most_common(5))
        print(
            "清理后文章分布：",
            Counter(arts[s.article_id][:18] for s in kept_preview).most_common(8),
        )

        for schedule_id in sorted(remove):
            row = db.get(PublishSchedule, schedule_id)
            if row:
                print(
                    f"  - #{row.id} {row.platform} {row.scheduled_at:%Y-%m-%d %H:%M} "
                    f"{arts.get(row.article_id, '')[:24]}"
                )
                delete_schedule(db, row)

        db.commit()
        left = db.scalars(select(PublishSchedule)).all()
        print(f"\n[OK] 已删除 {len(remove)} 条，当前排期 {len(left)} 条。")


if __name__ == "__main__":
    main()
