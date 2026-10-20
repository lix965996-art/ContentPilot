"""Local native-model registry, integrity checks and platform-scoped activation."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.paths import VAR_DIR
from app.ml import TRAINING_VERSION
from app.ml.dataset import SCHEMA_VERSION, TARGET
from app.ml.features import BASE_NAMES, VERSION
from app.models.business import SystemSetting

MODEL_ROOT = VAR_DIR / "models"
PLATFORMS = {"BLUESKY", "MASTODON"}
CHECKS = {
    "validationImprovement",
    "realData",
    "prospectiveTargetEvidence",
    "sampleSupport",
    "rollingConsistency",
    "independentTestImprovement",
    "intervalSupportsImprovement",
}


def read_model(model_id: str, root: Path | None = None) -> tuple[Path, dict, dict, dict]:
    root = (root or MODEL_ROOT).resolve()
    if not re.fullmatch(r"[a-z]+-[a-f0-9]{16}", model_id):
        raise ValueError("模型标识无效")
    directory = (root / model_id).resolve()
    if not directory.is_relative_to(root):
        raise ValueError("模型路径无效")
    manifest_path = (directory / "manifest.json").resolve()
    if not manifest_path.is_relative_to(directory) or manifest_path.stat().st_size > 2_000_000:
        raise ValueError("模型清单路径或大小无效")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), dict):
        raise ValueError("模型清单格式无效")
    if (
        manifest.get("modelId") != model_id
        or manifest.get("featureVersion") != VERSION
        or manifest.get("trainingVersion") != TRAINING_VERSION
    ):
        raise ValueError("模型版本不匹配")
    expected = {"catboost": "model.cbm", "lightgbm": "model.txt"}.get(
        str(manifest.get("algorithm") or "")
    )
    if expected is None or manifest.get("modelFile") != expected:
        raise ValueError("只支持已知的原生模型格式")
    for name in (expected, "features.json", "evaluation.json"):
        path = (directory / name).resolve()
        if not path.is_relative_to(directory) or path.stat().st_size > 50_000_000:
            raise ValueError("模型文件越界或过大")
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest.get("files", {}).get(name):
            raise ValueError("模型文件完整性校验失败")
    schema = json.loads((directory / "features.json").read_text(encoding="utf-8"))
    report = json.loads((directory / "evaluation.json").read_text(encoding="utf-8"))
    if not isinstance(schema, dict) or not isinstance(report, dict):
        raise ValueError("模型特征或评估格式无效")
    vocabulary, idf = schema.get("vocabulary"), schema.get("idf")
    if (
        schema.get("version") != VERSION
        or not isinstance(vocabulary, list)
        or not isinstance(idf, list)
        or len(vocabulary) != len(idf)
        or len(vocabulary) > 128
        or any(not isinstance(term, str) for term in vocabulary)
        or not all(isinstance(value, int | float) and math.isfinite(value) for value in idf)
        or schema.get("names") != BASE_NAMES + [f"text_{i}" for i in range(len(vocabulary))]
    ):
        raise ValueError("模型特征配置无效")
    test, improvement = report.get("test"), report.get("improvement")
    if (
        not isinstance(test, dict)
        or not isinstance(improvement, dict)
        or not all(
            isinstance(value, int | float) and math.isfinite(value)
            for value in (
                test.get("count"),
                test.get("maeLog"),
                test.get("maeOriginal"),
                improvement.get("relativeImprovement"),
            )
        )
    ):
        raise ValueError("模型评估指标无效")
    return directory, manifest, schema, report


def activation_reason(manifest: dict, report: dict, platform: str) -> str | None:
    if platform not in PLATFORMS or manifest.get("platform") != platform:
        return "PLATFORM_MISMATCH"
    if manifest.get("researchOnly") or manifest.get("testOnly"):
        return "RESEARCH_OR_TEST_ONLY"
    if manifest.get("schemaVersion") != SCHEMA_VERSION or manifest.get("target") != TARGET:
        return "TARGET_MISMATCH"
    if manifest.get("windowSeconds") != 86400 or manifest.get("timezone") != "UTC":
        return "WINDOW_MISMATCH"
    if manifest.get("eligibility") != "VALIDATED" or not all(
        report.get("checks", {}).get(check) is True for check in CHECKS
    ):
        return "VALIDATION_GATE_FAILED"
    if not manifest.get("sources") or set(manifest["sources"]) - {"ACCOUNT_API"}:
        return "UNVERIFIED_SOURCE"
    calibration = manifest.get("scoreCalibration", {})
    low, high = calibration.get("low"), calibration.get("high")
    if not all(isinstance(x, float | int) and math.isfinite(x) for x in (low, high)):
        return "CALIBRATION_INVALID"
    if high <= low or not manifest.get("trainedThrough"):
        return "CALIBRATION_INVALID"
    return None


def active_id(db: Session, platform: str) -> str | None:
    row = db.scalar(
        select(SystemSetting).where(SystemSetting.setting_key == f"ml.active.{platform}")
    )
    return row.setting_value if row and row.setting_value else None


def set_active(db: Session, platform: str, model_id: str | None) -> None:
    if platform not in PLATFORMS:
        raise ValueError("不支持的平台")
    if model_id:
        _, manifest, _, report = read_model(model_id)
        reason = activation_reason(manifest, report, platform)
        if reason:
            raise ValueError(f"模型不满足启用条件：{reason}")
    key = f"ml.active.{platform}"
    row = db.scalar(select(SystemSetting).where(SystemSetting.setting_key == key))
    if row is None:
        row = SystemSetting(setting_key=key, is_secret=False)
        db.add(row)
    row.setting_value = model_id or ""


def list_models(root: Path | None = None) -> list[dict]:
    directory = root or MODEL_ROOT
    if not directory.is_dir():
        return []
    items = []
    for child in sorted(directory.iterdir())[:100]:
        if not child.is_dir():
            continue
        try:
            _, manifest, _, report = read_model(child.name, directory)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        items.append(
            {
                "modelId": child.name,
                "platform": manifest["platform"],
                "algorithm": manifest["algorithm"],
                "target": manifest["target"],
                "eligibility": manifest["eligibility"],
                "researchOnly": bool(manifest.get("researchOnly")),
                "activationBlocked": activation_reason(manifest, report, manifest["platform"]),
                "test": report.get("test"),
                "improvement": report.get("improvement"),
                "checks": report.get("checks"),
                "timeValidity": report.get("timeValidity"),
                "trainRows": report.get("trainRows"),
                "validationRows": report.get("validationRows"),
                "testRows": report.get("testRows"),
                "sourceInfo": manifest.get("sourceInfo"),
            }
        )
    return items
