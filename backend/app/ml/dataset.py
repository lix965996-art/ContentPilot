"""Fixed-window datasets. No credential access, synthetic mixing or legacy-time invention."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.models.business import EngagementHistory
from app.models.learning import EngagementObservation, PublishedContentSnapshot

SCHEMA_VERSION = "engagement-24h-v1"
TARGET = "log1p(likes+replies+reposts)@24h"


def iso_utc(value: datetime) -> str:
    return value.replace(tzinfo=UTC).isoformat()


def digest_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def eligible_row(
    obs: EngagementObservation,
    snapshot: PublishedContentSnapshot | None,
    tolerance_seconds: int = 900,
) -> tuple[dict | None, str]:
    if obs.status != "SUCCEEDED":
        return None, "COLLECTION_FAILED"
    if obs.source_type != "ACCOUNT_API":
        return None, "SOURCE_NOT_VERIFIED"
    if snapshot is None:
        return None, "NO_PUBLICATION_SNAPSHOT"
    if (
        obs.platform != snapshot.platform
        or obs.account_ref != snapshot.account_ref
        or obs.external_id != snapshot.external_id
    ):
        return None, "IDENTITY_MISMATCH"
    if obs.published_at is None or obs.age_seconds is None:
        return None, "UNKNOWN_PUBLICATION_TIME"
    actual_age = (obs.observed_at - obs.published_at).total_seconds()
    if not 86400 <= actual_age <= 86400 + tolerance_seconds or obs.age_seconds != int(actual_age):
        return None, "OUTSIDE_24H_WINDOW"
    if obs.window_seconds not in (0, 86400):
        return None, "DIFFERENT_TARGET_WINDOW"
    counts = (obs.likes, obs.replies, obs.reposts)
    if any(type(value) is not int or value < 0 for value in counts):
        return None, "MISSING_COUNTS"
    if snapshot.feature_available_at > obs.published_at:
        return None, "FEATURE_NOT_AVAILABLE_AT_PUBLICATION"
    features = snapshot.content_json
    if not isinstance(features.get("text"), str) or not features["text"].strip():
        return None, "MISSING_TEXT"
    post_key = digest_json([obs.platform, obs.account_ref, obs.external_id])
    return {
        "post_id": post_key,
        "platform": obs.platform,
        "account": obs.account_ref,
        "group": features.get("articleGroup") or snapshot.content_hash,
        "content_hash": snapshot.content_hash,
        "published_at": iso_utc(obs.published_at),
        "observed_at": iso_utc(obs.observed_at),
        "decision_at": iso_utc(min(snapshot.feature_available_at, obs.published_at)),
        "age_seconds": obs.age_seconds,
        "likes": obs.likes,
        "replies": obs.replies,
        "reposts": obs.reposts,
        "interactions": sum(int(value) for value in counts if value is not None),
        "text": features["text"],
        "title": features.get("title", ""),
        "hashtags": features.get("hashtags", []),
        "image_count": features.get("imageCount", 0),
        "language": features.get("language", "unknown"),
        "source": obs.source_type,
    }, "ACCEPTED"


def audit_dataset(
    db: Session, *, platform: str | None = None, tolerance_seconds: int = 900
) -> tuple[list[dict], dict]:
    tables = inspect(db.get_bind()).get_table_names()
    legacy = (
        [
            dict(platform=p, source=s, rows=n)
            for p, s, n in db.execute(
                select(
                    EngagementHistory.platform, EngagementHistory.source_type, func.count()
                ).group_by(EngagementHistory.platform, EngagementHistory.source_type)
            )
        ]
        if "engagement_history" in tables
        else []
    )
    reasons: Counter = Counter()
    accepted: dict[str, dict] = {}
    if "engagement_observation" in tables:
        query = (
            select(EngagementObservation, PublishedContentSnapshot)
            .outerjoin(
                PublishedContentSnapshot,
                PublishedContentSnapshot.schedule_id == EngagementObservation.schedule_id,
            )
            .order_by(EngagementObservation.observed_at, EngagementObservation.id)
        )
        if platform:
            query = query.where(EngagementObservation.platform == platform)
        for obs, snapshot in db.execute(query):
            item, reason = eligible_row(obs, snapshot, tolerance_seconds)
            if item is not None and item["post_id"] in accepted:
                reason = "DUPLICATE_POST"
            elif item is not None:
                accepted[item["post_id"]] = item
            reasons[reason] += 1
    rows = sorted(accepted.values(), key=lambda row: (row["published_at"], row["post_id"]))
    report = {
        "schemaVersion": SCHEMA_VERSION,
        "target": TARGET,
        "toleranceSeconds": tolerance_seconds,
        "platform": platform,
        "accepted": len(rows),
        "reasons": dict(reasons),
        "legacyHistory": legacy,
        "legacyWindowPolicy": "UNKNOWN_WINDOW_NOT_TRAINABLE",
        "accounts": len({r["account"] for r in rows}),
        "firstPublishedAt": rows[0]["published_at"] if rows else None,
        "lastPublishedAt": rows[-1]["published_at"] if rows else None,
        "status": "READY_FOR_EXPERIMENT" if len(rows) >= 20 else "NEEDS_MATURE_OBSERVATIONS",
    }
    return rows, report


def export_dataset(db: Session, directory: Path, *, platform: str | None = None) -> dict:
    rows, report = audit_dataset(db, platform=platform)
    if not rows:
        return {**report, "exported": False}
    dataset_id = digest_json(rows)[:24]
    target = directory / dataset_id
    if not target.exists():
        target.mkdir(parents=True, exist_ok=False)
        data = "".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in rows)
        (target / "data.jsonl").write_bytes(data.encode("utf-8"))
        manifest = {
            **report,
            "datasetId": dataset_id,
            "sha256": hashlib.sha256(data.encode()).hexdigest(),
        }
        (target / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    data_hash = hashlib.sha256((target / "data.jsonl").read_bytes()).hexdigest()
    if manifest["sha256"] != data_hash:
        raise ValueError("冻结数据集已被修改，拒绝复用")
    return {**manifest, "directory": str(target), "exported": True}


def load_dataset(directory: Path) -> tuple[list[dict], dict]:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    data = (directory / "data.jsonl").read_bytes()
    allowed_versions = {SCHEMA_VERSION, "public-youtube-watch-v1"}
    if manifest.get("schemaVersion") not in allowed_versions or hashlib.sha256(
        data
    ).hexdigest() != manifest.get("sha256"):
        raise ValueError("数据集版本或哈希校验失败")
    rows = [json.loads(line) for line in data.decode("utf-8").splitlines() if line]
    sources = (
        {"YOUTUBE_PUBLIC_RESEARCH"}
        if manifest.get("profile") == "YOUTUBE_RANDOM_WATCH_FRACTION"
        else {"ACCOUNT_API"}
    )
    if any(row.get("source") not in sources for row in rows):
        raise ValueError("仅接受有发布快照与成熟观测的真实 API 数据集")
    validate_rows(rows, research=sources == {"YOUTUBE_PUBLIC_RESEARCH"})
    return rows, manifest


def validate_rows(rows: list[dict], *, research: bool = False) -> None:
    from app.ml.features import timestamp

    for row in rows:
        published = timestamp(row["published_at"])
        if timestamp(row["decision_at"]) > published:
            raise ValueError("特征时间晚于发布时间")
        if research:
            if (
                row.get("platform") != "YOUTUBE"
                or row.get("retrospective") is not True
                or row.get("observed_at") is not None
                or not 0 <= row["label"] <= 1
            ):
                raise ValueError("公开研究数据目标定义不一致")
            continue
        observed = timestamp(row["observed_at"])
        age = (observed - published).total_seconds()
        counts = [row.get(key) for key in ("likes", "replies", "reposts")]
        if (
            row.get("platform") not in {"BLUESKY", "MASTODON"}
            or not 86400 <= age <= 87300
            or abs(age - row.get("age_seconds", -1)) >= 1
            or any(type(value) is not int or value < 0 for value in counts)
            or row.get("interactions") != sum(value for value in counts if isinstance(value, int))
            or row.get("retrospective")
        ):
            raise ValueError("真实平台数据必须满足相同的24小时目标与完整计数")
