"""Author-shared YouTube research sample, explicitly distinct from 24-hour social counts."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import httpx
import pandas as pd

from app.ml.dataset import digest_json
from app.ml.features import timestamp

YOUTUBE_SHA256 = "cb797be395cafc7248067b55085d487528b5b5a70a7319d6ddce28a1c5857c16"
YOUTUBE_URL = (
    "https://raw.githubusercontent.com/sTechLab/YouTubeDurationData/"
    "26fb382979617d823960d980642f3044094c9ec7/RandomVideo_dataTable.csv"
)


def obtain_youtube(directory: Path, *, proxy: str | None = None) -> Path:
    """Download one pinned CSV; never execute repository code or redistribute raw data."""
    destination = directory / "RandomVideo_dataTable.csv"
    if not destination.exists():
        with httpx.Client(
            timeout=60, proxy=proxy, trust_env=False, follow_redirects=False
        ) as client:
            response = client.get(YOUTUBE_URL)
            response.raise_for_status()
        data = response.content
        if len(data) > 2_000_000 or hashlib.sha256(data).hexdigest() != YOUTUBE_SHA256:
            raise ValueError("公开数据下载完整性校验失败")
        directory.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    if hashlib.sha256(destination.read_bytes()).hexdigest() != YOUTUBE_SHA256:
        raise ValueError("公开数据缓存与固定版本不一致")
    return destination


def prepare_youtube(source: Path, directory: Path) -> dict:
    """Random Videos only: individual-session engagement has a different definition."""
    frame = pd.read_csv(
        source,
        usecols=lambda column: column
        in {"video_id", "duration", "publishedAt", "category_term", "engagement"},
    )
    duplicates = int(frame.video_id.duplicated().sum())
    frame = frame.drop_duplicates("video_id", keep="first")
    rows = []
    rejected = 0
    for item in frame.to_dict("records"):
        try:
            label, duration = float(item["engagement"]), float(item["duration"])
            published = timestamp(str(item["publishedAt"])).isoformat()
            if not (
                math.isfinite(label)
                and 0 <= label <= 1
                and math.isfinite(duration)
                and duration > 0
            ):
                raise ValueError("Invalid public value")
        except (ValueError, TypeError):
            rejected += 1
            continue
        identity = digest_json(["YOUTUBE_RANDOM_VIDEO", str(item["video_id"])])
        category = str(item["category_term"]) if pd.notna(item["category_term"]) else "unknown"
        rows.append(
            {
                "post_id": identity,
                "platform": "YOUTUBE",
                "account": "UNKNOWN_CHANNEL",
                "account_known": False,
                "group": identity,
                "content_hash": identity,
                "published_at": published,
                "decision_at": published,
                "observed_at": None,
                "retrospective": True,
                "label": label,
                "interactions": None,
                "text": category,
                "title": "",
                "textSource": "CATEGORY_ONLY",
                "hashtags": [],
                "image_count": 0,
                "language": "unknown",
                "category": category,
                "duration": duration,
                "source": "YOUTUBE_PUBLIC_RESEARCH",
            }
        )
    rows.sort(key=lambda row: (row["published_at"], row["post_id"]))
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    dataset_id = "youtube-random-v1-" + source_hash[:16]
    target = directory / dataset_id
    source_info = {
        "url": "https://github.com/sTechLab/YouTubeDurationData",
        "file": source.name,
        "rawSha256": source_hash,
        "citation": (
            "Park, Naaman & Berger (2016), A Data-driven Study of View Duration "
            "on YouTube, ICWSM 2016"
        ),
        "permissionNote": (
            "Authors share research data and request citation; no SPDX license declared"
        ),
        "targetDefinition": (
            "Random Videos: aggregate average view duration divided by video duration"
        ),
        "limitations": [
            "Observation time unknown",
            "Lifetime measurements; not 24h labels",
            "No channel IDs or original post text",
            "Historical sample selection bias",
            "Publication-time split is retrospective; not a historical deployment simulation",
        ],
        "excludedInputs": [
            "viewCount",
            "likeCount",
            "numShare",
            "numSubscriber",
            "numParent",
            "watchTime",
            "averageViewDuration",
            "elapsed_time",
            "comment sentiment",
            "user_id",
            "user_gender",
            "user_zip",
        ],
    }
    data = "".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in rows)
    manifest = {
        "schemaVersion": "public-youtube-watch-v1",
        "datasetId": dataset_id,
        "profile": "YOUTUBE_RANDOM_WATCH_FRACTION",
        "platform": "YOUTUBE",
        "target": "log1p(view_duration_fraction)",
        "targetUnit": "VIEW_DURATION_FRACTION",
        "accepted": len(rows),
        "duplicatesExcluded": duplicates,
        "invalidExcluded": rejected,
        "sha256": hashlib.sha256(data.encode()).hexdigest(),
        "sourceInfo": source_info,
    }
    if not target.exists():
        target.mkdir(parents=True, exist_ok=False)
        (target / "data.jsonl").write_bytes(data.encode("utf-8"))
        (target / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if hashlib.sha256((target / "data.jsonl").read_bytes()).hexdigest() != manifest["sha256"]:
        raise ValueError("公开冻结数据被修改，拒绝覆盖")
    return {**manifest, "directory": str(target)}
