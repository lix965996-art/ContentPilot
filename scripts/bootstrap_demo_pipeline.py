"""One-shot bootstrap for demo: migrate, seed, import history, enrich analytics.

Run from project root:
  backend\\.venv\\Scripts\\python.exe scripts\\bootstrap_demo_pipeline.py
"""

from __future__ import annotations

import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND = PROJECT_ROOT / "backend"
CSV_PATH = PROJECT_ROOT / "sample-data" / "history" / "demo-account-history-SIMULATED.csv"
PYTHON = BACKEND / ".venv" / "Scripts" / "python.exe"

sys.path.insert(0, str(BACKEND))

from sqlalchemy import func, select  # noqa: E402

from app.db.seed import seed_database  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.business import (  # noqa: E402
    ContentArticle,
    EngagementHistory,
    EngagementMetric,
    Experiment,
    ExperimentSample,
    PublishRecommendation,
    PublishSchedule,
)
from app.models.user import User  # noqa: E402
from app.services.activity_service import analyze  # noqa: E402
from app.services.history_import_service import commit_import, read_table, suggest_mapping  # noqa: E402
from app.services.recommendation_service import classify_schedule_group, recommend  # noqa: E402


def run_migrations() -> None:
    print("[1/5] Applying Alembic migrations...")
    subprocess.run(
        [str(PYTHON), "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND,
        check=True,
    )


def import_demo_history(db) -> int:
    existing = int(db.scalar(select(func.count()).select_from(EngagementHistory)) or 0)
    if existing > 0:
        print(f"[3/5] History already present ({existing} rows), skip import.")
        return existing
    if not CSV_PATH.exists():
        print(f"[3/5] Demo CSV missing: {CSV_PATH}")
        return 0

    operator = db.scalar(select(User).where(User.username == "operator"))
    raw = CSV_PATH.read_bytes()
    headers, records = read_table(raw, CSV_PATH.name)
    mapping = suggest_mapping(headers)
    batch = commit_import(
        db,
        filename=CSV_PATH.name,
        headers=headers,
        records=records,
        mapping=mapping,
        user_id=operator.id if operator else None,
        default_source_type="ACCOUNT_HISTORY",
        source_note="SIMULATED 演示账号历史（自动生成，非真实平台数据）",
    )
    db.commit()
    print(f"[3/5] Imported {batch.success_count} SIMULATED history rows from {CSV_PATH.name}")
    return batch.success_count


def enrich_schedules_and_metrics(db) -> None:
    """Mark a subset of seed schedules as SUCCESS so analytics/experiments have data."""
    schedules = list(
        db.scalars(select(PublishSchedule).order_by(PublishSchedule.id).limit(8)).all()
    )
    if not schedules:
        return

    changed = 0
    for index, schedule in enumerate(schedules):
        if schedule.status in {"SUCCESS", "MANUAL_PUBLISHED"}:
            continue
        schedule.status = "SUCCESS"
        schedule.actual_publish_at = schedule.scheduled_at
        schedule.time_source = "RECOMMENDED" if index % 2 == 0 else "CUSTOM"
        schedule.recommended_at = schedule.scheduled_at - timedelta(hours=1 if index % 2 else 3)
        changed += 1

    metric_count = int(db.scalar(select(func.count()).select_from(EngagementMetric)) or 0)
    if metric_count == 0:
        for index, schedule in enumerate(schedules):
            impressions = 1200 + index * 180
            total = 90 + index * 11
            db.add(
                EngagementMetric(
                    schedule_id=schedule.id,
                    platform=schedule.platform,
                    metric_date=date.today() - timedelta(days=10 - index),
                    impressions=impressions,
                    likes=int(total * 0.6),
                    comments=int(total * 0.12),
                    collects=int(total * 0.18),
                    shares=total - int(total * 0.6) - int(total * 0.12) - int(total * 0.18),
                    followers=5000,
                    engagement_total=total,
                    engagement_rate=round(total / impressions, 6),
                    group_type="RECOMMENDED_TIME" if index % 2 == 0 else "FIXED_TIME",
                    data_source="SIMULATED",
                )
            )
        print(f"[4/5] Created engagement metrics for {len(schedules)} schedules.")
    elif changed:
        print(f"[4/5] Updated {changed} schedules to SUCCESS for analytics demo.")
    else:
        print("[4/5] Schedules and metrics already prepared.")


def sync_publish_time_experiment(db) -> None:
    experiment = db.scalar(select(Experiment).where(Experiment.type == "PUBLISH_TIME"))
    if not experiment:
        print("[4/5] No PUBLISH_TIME experiment found, skip auto grouping.")
        return

    if experiment.status == "DRAFT":
        experiment.status = "RUNNING"
        experiment.start_date = experiment.start_date or date.today() - timedelta(days=30)

    linked = {sample.schedule_id for sample in experiment.samples if sample.schedule_id}
    created = 0
    schedules = db.scalars(
        select(PublishSchedule).where(PublishSchedule.status.in_(("SUCCESS", "MANUAL_PUBLISHED")))
    ).all()
    for schedule in schedules:
        if schedule.id in linked:
            continue
        metrics = list(
            db.scalars(
                select(EngagementMetric).where(EngagementMetric.schedule_id == schedule.id)
            ).all()
        )
        if not metrics:
            continue
        recommendation = (
            db.get(PublishRecommendation, schedule.recommendation_id)
            if schedule.recommendation_id
            else None
        )
        group_type, reason = classify_schedule_group(schedule, recommendation)
        article = db.get(ContentArticle, schedule.article_id)
        avg_rate = sum(item.engagement_rate for item in metrics) / len(metrics)
        db.add(
            ExperimentSample(
                experiment_id=experiment.id,
                schedule_id=schedule.id,
                group_type=group_type,
                sample_label=f"{article.title if article else '排期任务'} · #{schedule.id}",
                metric_value_json={
                    "engagementRate": round(avg_rate * 100, 3),
                    "dataSource": "SIMULATED",
                    "metricCount": len(metrics),
                },
                assignment_source="AUTO",
                assignment_reason=reason,
            )
        )
        created += 1
    db.commit()
    print(f"[4/5] Auto-grouped {created} schedule samples into experiment #{experiment.id}.")


def run_activity_and_recommendation(db) -> None:
    print("[5/5] Activity analysis summary (window=90D):")
    for platform in ("WEIBO", "XIAOHONGSHU", "WECHAT_OFFICIAL"):
        report = analyze(db, platform=platform, window="90D")
        top = report["topSlots"][0] if report["topSlots"] else None
        slot_text = (
            f"{top['dayName']} {top['time']} score={top['score']}"
            if top
            else "no slots"
        )
        print(
            f"  - {platform}: samples={report['sampleCount']} "
            f"account={report['accountSampleCount']} best={slot_text}"
        )

    article = db.scalar(select(ContentArticle).order_by(ContentArticle.id))
    if not article:
        return
    try:
        rec = recommend(db, "WEIBO", date.today(), window="90D", horizon_days=7)
        row = PublishRecommendation(
            article_id=article.id,
            platform="WEIBO",
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
        )
        db.add(row)
        db.commit()
        print(
            f"  - Sample recommendation for article #{article.id}: "
            f"{rec['recommendedAt']:%Y-%m-%d %H:%M} score={rec['score']}"
        )
    except ValueError as exc:
        print(f"  - Recommendation skipped: {exc}")


def main() -> None:
    if not PYTHON.exists():
        raise SystemExit(f"Backend venv not found: {PYTHON}")

    run_migrations()

    print("[2/5] Seeding roles, demo workspace and baseline rules...")
    with SessionLocal() as db:
        seed_database(db)
        import_demo_history(db)
        enrich_schedules_and_metrics(db)
        sync_publish_time_experiment(db)
        run_activity_and_recommendation(db)
        db.commit()

    print("\n[OK] Demo pipeline ready.")
    print("Next: start backend + frontend, then open:")
    print("  - 发布时间 -> 活跃度分析 / 历史数据导入")
    print("  - 数据 -> 复盘概览")
    print("  - 实验 -> 推荐时间与固定时间对比实验")


if __name__ == "__main__":
    main()
