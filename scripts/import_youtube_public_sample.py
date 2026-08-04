"""Downloaded YouTubeDurationData → engagement_history via history_import_service.

Imports the original CSV files from:
  sample-data/history/YouTubeDurationData/
without modifying them. Creates a historical backtest experiment from real rows.

Run:
  backend\\.venv\\Scripts\\python.exe scripts\\import_youtube_public_sample.py
"""

from __future__ import annotations

import csv
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND = PROJECT_ROOT / "backend"
REPO_DIR = PROJECT_ROOT / "sample-data" / "history" / "YouTubeDurationData"
PYTHON = BACKEND / ".venv" / "Scripts" / "python.exe"

sys.path.insert(0, str(BACKEND))

from sqlalchemy import func, select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.business import EngagementHistory, Experiment, ExperimentSample  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.activity_service import analyze, slot_statistics  # noqa: E402
from app.services.history_import_service import commit_import, read_table  # noqa: E402

SOURCE_FILES = (
    {
        "filename": "RandomVideo_dataTable.csv",
        "note": (
            "sTechLab/YouTubeDurationData Random Videos (ICWSM 2016); "
            "1,125 random YouTube videos with aggregate statistics"
        ),
    },
    {
        "filename": "IndividualLogs_dataTable.csv",
        "note": (
            "sTechLab/YouTubeDurationData Individual Logs (ICWSM 2016); "
            "1,814 participant viewing sessions"
        ),
    },
)

YOUTUBE_MAPPING = {
    "account_id": "video_id",
    "content_type": "category_term",
    "publish_time": "publishedAt",
    "views": "viewCount",
    "likes": "likeCount",
    "comments": "numParent",
    "shares": "numShare",
    "followers": "numSubscriber",
    "favorites": "favoriteCount",
}

EXPERIMENT_NAME = "公开样本发布时间历史回测实验"


def count_csv_rows(path: Path) -> int:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def import_file(db, path: Path, source_note: str, operator_id: int | None) -> dict:
    raw = path.read_bytes()
    headers, records = read_table(raw, path.name)
    batch = commit_import(
        db,
        filename=path.name,
        headers=headers,
        records=records,
        mapping=YOUTUBE_MAPPING,
        user_id=operator_id,
        default_platform="YOUTUBE",
        default_source_type="YOUTUBE_PUBLIC_SAMPLE",
        source_note=source_note[:255],
    )
    db.commit()
    return {
        "filename": path.name,
        "originalRows": len(records),
        "successCount": batch.success_count,
        "duplicateCount": batch.duplicate_count,
        "errorCount": batch.error_count,
        "batchId": batch.id,
    }


def slot_quartiles(rows: list[EngagementHistory]) -> tuple[float, float]:
    stats = slot_statistics(rows)
    scores = sorted(item["score"] for item in stats["slots"].values() if item["sampleCount"] > 0)
    if len(scores) < 4:
        return scores[-1], scores[0]
    q1 = scores[len(scores) // 4]
    q3 = scores[(len(scores) * 3) // 4]
    return q3, q1


def create_backtest_experiment(db, operator_id: int | None) -> dict:
    rows = list(
        db.scalars(
            select(EngagementHistory).where(
                EngagementHistory.platform == "YOUTUBE",
                EngagementHistory.source_type == "YOUTUBE_PUBLIC_SAMPLE",
            )
        ).all()
    )
    if not rows:
        return {"created": 0, "message": "no youtube public rows"}

    high_threshold, low_threshold = slot_quartiles(rows)
    stats = slot_statistics(rows)
    slot_scores = stats["slots"]

    existing = db.scalar(select(Experiment).where(Experiment.name == EXPERIMENT_NAME))
    if existing:
        db.query(ExperimentSample).filter(ExperimentSample.experiment_id == existing.id).delete()
        experiment = existing
        experiment.status = "FINISHED"
        experiment.hypothesis = (
            "在 YouTube 公开样本中，发布于历史高活跃时段（热力图上四分位）的视频，"
            "其互动率高于发布于低活跃时段（下四分位）的视频。"
        )
        experiment.control_description = f"发布时段得分 ≤ {low_threshold:.2f}（历史下四分位时段）"
        experiment.treatment_description = f"发布时段得分 ≥ {high_threshold:.2f}（历史上四分位时段）"
        experiment.conclusion = None
        experiment.result_json = {}
    else:
        experiment = Experiment(
            name=EXPERIMENT_NAME,
            type="PUBLISH_TIME",
            hypothesis=(
                "在 YouTube 公开样本中，发布于历史高活跃时段（热力图上四分位）的视频，"
                "其互动率高于发布于低活跃时段（下四分位）的视频。"
            ),
            status="FINISHED",
            control_description=f"发布时段得分 ≤ {low_threshold:.2f}（历史下四分位时段）",
            treatment_description=f"发布时段得分 ≥ {high_threshold:.2f}（历史上四分位时段）",
            metrics_json={"engagementRate": "互动率(%)", "engagementScore": "综合互动得分"},
            created_by=operator_id or 1,
            start_date=min(row.publish_time.date() for row in rows),
            end_date=max(row.publish_time.date() for row in rows),
        )
        db.add(experiment)
        db.flush()

    treatment_rates: list[float] = []
    control_rates: list[float] = []
    created = 0

    for row in rows:
        slot = slot_scores.get((row.day_of_week, row.hour_of_day), {"score": 0.0})
        score = float(slot.get("score", 0.0))
        if score >= high_threshold:
            group = "TREATMENT"
            treatment_rates.append(float(row.engagement_rate))
        elif score <= low_threshold:
            group = "CONTROL"
            control_rates.append(float(row.engagement_rate))
        else:
            continue

        db.add(
            ExperimentSample(
                experiment_id=experiment.id,
                schedule_id=None,
                group_type=group,
                sample_label=f"YouTube {row.account_ref} · {row.publish_time:%Y-%m-%d %H:%M}",
                metric_value_json={
                    "engagementRate": round(float(row.engagement_rate) * 100, 4),
                    "engagementScore": round(float(row.engagement_score), 3),
                    "views": row.views,
                    "likes": row.likes,
                    "comments": row.comments,
                    "shares": row.shares,
                    "slotScore": round(score, 3),
                    "dataSource": "YOUTUBE_PUBLIC_SAMPLE",
                    "videoId": row.account_ref,
                    "category": row.content_type,
                },
                assignment_source="AUTO",
                assignment_reason=(
                    f"历史回测：发布于{row.day_of_week}日{row.hour_of_day}时，"
                    f"该时段历史得分 {score:.2f}，"
                    f"{'≥' if group == 'TREATMENT' else '≤'}阈值 "
                    f"{high_threshold if group == 'TREATMENT' else low_threshold:.2f}"
                ),
            )
        )
        created += 1

    treat_avg = sum(treatment_rates) / len(treatment_rates) if treatment_rates else 0.0
    ctrl_avg = sum(control_rates) / len(control_rates) if control_rates else 0.0
    experiment.result_json = {
        "TREATMENT": {
            "engagementRate": round(treat_avg * 100, 4),
            "sampleCount": len(treatment_rates),
        },
        "CONTROL": {
            "engagementRate": round(ctrl_avg * 100, 4),
            "sampleCount": len(control_rates),
        },
        "highSlotThreshold": round(high_threshold, 3),
        "lowSlotThreshold": round(low_threshold, 3),
        "dataSource": "YOUTUBE_PUBLIC_SAMPLE",
        "platform": "YOUTUBE",
        "method": "historical_backtest_by_slot_quartile",
    }
    diff = (treat_avg - ctrl_avg) * 100
    experiment.conclusion = (
        f"基于 {len(rows)} 条 YouTube 公开样本的历史回测："
        f"高活跃时段组 {len(treatment_rates)} 条，平均互动率 {treat_avg * 100:.3f}%；"
        f"低活跃时段组 {len(control_rates)} 条，平均互动率 {ctrl_avg * 100:.3f}%；"
        f"差值 {diff:+.3f} 个百分点。"
        "数据来源于 sTechLab/YouTubeDurationData（ICWSM 2016），非国内平台数据。"
    )
    experiment.status = "FINISHED"
    db.commit()

    return {
        "experimentId": experiment.id,
        "samplesCreated": created,
        "treatmentCount": len(treatment_rates),
        "controlCount": len(control_rates),
        "treatmentAvgEngagementRate": round(treat_avg * 100, 4),
        "controlAvgEngagementRate": round(ctrl_avg * 100, 4),
        "differencePctPoints": round(diff, 4),
        "highThreshold": round(high_threshold, 3),
        "lowThreshold": round(low_threshold, 3),
    }


def main() -> None:
    if not REPO_DIR.exists():
        raise SystemExit(f"Repository not found: {REPO_DIR}. Run git clone first.")

    report: dict = {"sourceRepo": "https://github.com/sTechLab/YouTubeDurationData", "files": []}

    with SessionLocal() as db:
        operator = db.scalar(select(User).where(User.username == "operator"))

        for item in SOURCE_FILES:
            path = REPO_DIR / item["filename"]
            if not path.exists():
                raise SystemExit(f"Missing file: {path}")
            original_rows = count_csv_rows(path)
            result = import_file(db, path, item["note"], operator.id if operator else None)
            result["originalRowsVerified"] = original_rows
            report["files"].append(result)

        youtube_rows = list(
            db.scalars(
                select(EngagementHistory).where(
                    EngagementHistory.source_type == "YOUTUBE_PUBLIC_SAMPLE"
                )
            ).all()
        )
        times = [row.publish_time for row in youtube_rows if row.publish_time]
        report["database"] = {
            "youtubePublicSampleCount": len(youtube_rows),
            "earliestPublishTime": min(times).isoformat() if times else None,
            "latestPublishTime": max(times).isoformat() if times else None,
            "simulatedAccountHistoryCount": int(
                db.scalar(
                    select(func.count())
                    .select_from(EngagementHistory)
                    .where(EngagementHistory.source_type == "ACCOUNT_HISTORY")
                )
                or 0
            ),
        }

        analysis = analyze(db, platform="YOUTUBE", source_scope="BASELINE", window="ALL")
        report["activityAnalysis"] = {
            "sampleCount": analysis["sampleCount"],
            "topSlot": analysis["topSlots"][0] if analysis["topSlots"] else None,
            "window": analysis["windowInfo"],
        }

        report["backtest"] = create_backtest_experiment(db, operator.id if operator else None)

    print("=== YouTube Public Sample Import Report ===")
    for key, value in report.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
