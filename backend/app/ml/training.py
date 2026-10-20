"""Bounded model comparison, purged temporal validation and sealed final holdout."""

from __future__ import annotations

import hashlib
import json
import platform as platform_module
import time
from importlib.metadata import version
from pathlib import Path

import numpy as np

from app.ml import TRAINING_VERSION, native
from app.ml.dataset import SCHEMA_VERSION, TARGET, digest_json, validate_rows
from app.ml.evaluation import (
    improvement_interval,
    metrics,
    split_at,
    statistical_predictions,
    target,
)
from app.ml.features import VERSION, HistoryIndex, fit_schema, timestamp, vector


def _matrix(rows: list[dict], schema: dict, history: HistoryIndex) -> list[list[float]]:
    return [vector(row, schema, history) for row in rows]


def _train_one(
    algorithm: str,
    semantic: bool,
    train: list[dict],
    val: list[dict],
    history: HistoryIndex,
    seed: int,
) -> tuple[object, dict, dict]:
    schema = fit_schema(train, semantic=semantic)
    model = native.fit(
        algorithm,
        _matrix(train, schema, history),
        target(train),
        schema["names"],
        validation=(_matrix(val, schema, history), target(val)),
        seed=seed,
    )
    result = metrics(val, native.predict(model, _matrix(val, schema, history)))
    return model, schema, result


def _cross_validate(rows: list[dict], algorithm: str, semantic: bool, seed: int) -> list[dict]:
    history = HistoryIndex(rows)
    results = []
    for fraction in (0.55, 0.7, 0.85):
        try:
            before, after, boundary = split_at(rows, fraction)
            # Only the next calendar interval is validation; no fold reaches the sealed test.
            limit = (
                timestamp(after[0]["published_at"])
                + (timestamp(rows[-1]["published_at"]) - timestamp(rows[0]["published_at"])) * 0.15
            )
            after = [row for row in after if timestamp(row["published_at"]) <= limit]
            if len(after) < 3:
                continue
            _, _, result = _train_one(algorithm, semantic, before, after, history, seed)
            baselines = statistical_predictions(before, after)
            best = min(metrics(after, p)["maeLog"] for p in baselines.values())
            results.append(
                {**result, **boundary, "baselineMaeLog": best, "improved": result["maeLog"] < best}
            )
        except ValueError:
            continue
    return results


def train_experiment(
    rows: list[dict],
    dataset_manifest: dict,
    directory: Path,
    *,
    seed: int = 20261020,
    test_only: bool = False,
) -> dict:
    started = time.perf_counter()
    rows = sorted(rows, key=lambda row: (row["published_at"], row["post_id"]))
    public_research = dataset_manifest.get("profile") == "YOUTUBE_RANDOM_WATCH_FRACTION"
    if not 20 <= len(rows) <= 30000:
        raise ValueError("训练需要20～30000条成熟观测；大数据请明确采样与评估设计")
    platforms = {row["platform"] for row in rows}
    allowed_platforms = {"YOUTUBE"} if public_research else {"BLUESKY", "MASTODON"}
    if len(platforms) != 1 or not platforms.issubset(allowed_platforms):
        raise ValueError("每次训练仅接受一个目标平台")
    if len({row["post_id"] for row in rows}) != len(rows):
        raise ValueError("训练数据包含重复帖子")
    expected_source = "YOUTUBE_PUBLIC_RESEARCH" if public_research else "ACCOUNT_API"
    if not test_only and any(row.get("source") != expected_source for row in rows):
        raise ValueError("合成数据只能用于隔离的管道自检")
    if not test_only:
        validate_rows(rows, research=public_research)
    model_id = (
        f"{next(iter(platforms)).lower()}-"
        f"{digest_json([dataset_manifest, seed, VERSION, TRAINING_VERSION])[:16]}"
    )
    destination = directory / model_id
    if destination.exists():
        raise ValueError("该数据/配置模型已存在；禁止覆盖已冻结的实验")
    development, test, test_boundary = split_at(rows, 0.8)
    train, val, validation_boundary = split_at(development, 0.75)
    history = HistoryIndex(rows)
    comparison = {}
    trained = {}
    candidates = [
        (algorithm, semantic)
        for algorithm in ("catboost", "lightgbm")
        for semantic in (False, True)
    ]
    for algorithm, semantic in candidates:
        key = f"{algorithm}-{'text' if semantic else 'structure'}"
        model, schema, result = _train_one(algorithm, semantic, train, val, history, seed)
        folds = _cross_validate(development, algorithm, semantic, seed)
        comparison[key] = {"validation": result, "rollingValidation": folds}
        trained[key] = (model, schema)
    chosen = min(comparison, key=lambda key: comparison[key]["validation"]["maeLog"])
    algorithm, mode = chosen.split("-", 1)
    selected_model = trained[chosen][0]
    selected_iterations = (
        int(selected_model.tree_count_)
        if algorithm == "catboost"
        else int(selected_model.current_iteration())
    )
    final_schema = fit_schema(development, semantic=mode == "text")
    final_model = native.fit(
        algorithm,
        _matrix(development, final_schema, history),
        target(development),
        final_schema["names"],
        iterations=selected_iterations,
        seed=seed,
    )
    test_prediction = native.predict(final_model, _matrix(test, final_schema, history))
    validation_baselines = statistical_predictions(train, val)
    best_baseline = min(
        validation_baselines, key=lambda key: metrics(val, validation_baselines[key])["maeLog"]
    )
    baselines = statistical_predictions(development, test)
    interval = improvement_interval(test, baselines[best_baseline], test_prediction, seed=seed)
    span = (timestamp(rows[-1]["published_at"]) - timestamp(rows[0]["published_at"])).days
    folds = comparison[chosen]["rollingValidation"]
    checks = {
        "realData": not test_only,
        "prospectiveTargetEvidence": not public_research,
        "sampleSupport": len(rows) >= 300 and len(val) >= 50 and len(test) >= 50 and span >= 56,
        "rollingConsistency": len(folds) >= 3 and sum(f["improved"] for f in folds) >= 2,
        "validationImprovement": comparison[chosen]["validation"]["maeLog"]
        < metrics(val, validation_baselines[best_baseline])["maeLog"],
        "independentTestImprovement": interval["relativeImprovement"] >= 0.05,
        "intervalSupportsImprovement": bool(
            interval["difference95CI"] and interval["difference95CI"][0] > 0
        ),
    }
    active_accounts = sorted(
        {row["account"] for row in development if row.get("account_known", True)}
    )
    cold = [
        i
        for i, row in enumerate(test)
        if row.get("account_known", True) and row["account"] not in active_accounts
    ]
    warm = [
        i
        for i, row in enumerate(test)
        if row.get("account_known", True) and row["account"] in active_accounts
    ]
    unknown = [i for i, row in enumerate(test) if not row.get("account_known", True)]
    report = {
        "version": "temporal-evaluation-v1",
        "selected": chosen,
        "selectionPolicy": "VALIDATION_ONLY",
        "selectedIterations": selected_iterations,
        "comparison": comparison,
        "validationBaselines": {k: metrics(val, p) for k, p in validation_baselines.items()},
        "testBaselines": {key: metrics(test, value) for key, value in baselines.items()},
        "test": metrics(test, test_prediction),
        "baselineChosenOnValidation": best_baseline,
        "coldAccountTest": metrics([test[i] for i in cold], test_prediction[cold])
        if cold
        else None,
        "knownAccountTest": metrics([test[i] for i in warm], test_prediction[warm])
        if warm
        else None,
        "unknownAccountTest": metrics([test[i] for i in unknown], test_prediction[unknown])
        if unknown
        else None,
        "improvement": interval,
        "checks": checks,
        "testBoundary": test_boundary,
        "validationBoundary": validation_boundary,
        "trainRows": len(train),
        "validationRows": len(val),
        "testRows": len(test),
        "historyPolicy": "NO_ACCOUNT_HISTORY" if public_research else "ASOF_OBSERVED_LABELS_ONLY",
        "timeValidity": "RETROSPECTIVE_PUBLICATION_SPLIT_LABEL_TIME_UNKNOWN"
        if public_research
        else "PURGED_BY_LABEL_AVAILABILITY",
        "researchOnly": public_research,
        "policyCausalEvidence": False,
        "hybridV2Comparison": "RATE_BASED_TARGET_NOT_COMPARABLE_TO_RAW_COUNTS",
        "seed": seed,
        "durationSeconds": round(time.perf_counter() - started, 3),
        "hardware": {
            "system": platform_module.system(),
            "processor": platform_module.machine(),
            "threads": 2,
        },
    }
    destination.mkdir(parents=True, exist_ok=False)
    model_file = "model.cbm" if algorithm == "catboost" else "model.txt"
    native.save(final_model, destination / model_file)
    feature_text = json.dumps(final_schema, ensure_ascii=False, sort_keys=True, allow_nan=False)
    (destination / "features.json").write_text(feature_text, encoding="utf-8")
    (destination / "evaluation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    low, high = np.percentile(target(development), [5, 95])
    manifest = {
        "modelId": model_id,
        "trainingVersion": TRAINING_VERSION,
        "schemaVersion": dataset_manifest.get("schemaVersion", SCHEMA_VERSION),
        "featureVersion": VERSION,
        "algorithm": algorithm,
        "platform": next(iter(platforms)),
        "target": dataset_manifest.get("target", TARGET),
        "windowSeconds": None if public_research else 86400,
        "timezone": "UTC",
        "modelFile": model_file,
        "eligibility": "VALIDATED" if all(checks.values()) else "EXPERIMENT_ONLY",
        "testOnly": test_only,
        "sources": sorted({row.get("source", "UNKNOWN") for row in rows}),
        "dataHash": dataset_manifest.get("sha256") or digest_json(rows),
        "trainedThrough": None
        if public_research
        else max(row["observed_at"] for row in development),
        "researchOnly": public_research,
        "sourceInfo": dataset_manifest.get("sourceInfo"),
        "trainingAccounts": active_accounts,
        "scoreCalibration": {"low": float(low), "high": float(max(high, low + 1))},
        "dependencies": {name: version(name) for name in ("catboost", "lightgbm", "numpy")},
        "files": {
            name: hashlib.sha256((destination / name).read_bytes()).hexdigest()
            for name in (model_file, "features.json", "evaluation.json")
        },
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"manifest": manifest, "evaluation": report, "directory": str(destination)}
