"""Temporal/purged holdouts and predictive metrics, never counterfactual policy lift."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import timedelta

import numpy as np
import pandas as pd

from app.ml.features import timestamp


def target(rows: list[dict]) -> np.ndarray:
    return np.asarray(
        [math.log1p(row.get("label", row["interactions"])) for row in rows], dtype=float
    )


def split_at(rows: list[dict], fraction: float) -> tuple[list[dict], list[dict], dict]:
    ordered = sorted(rows, key=lambda row: (row["published_at"], row["post_id"]))
    if len(ordered) < 10:
        raise ValueError("至少需要10条成熟观测才能执行时间切分")
    boundary = ordered[max(1, min(len(ordered) - 1, int(len(ordered) * fraction)))]["published_at"]
    later = [row for row in ordered if timestamp(row["published_at"]) >= timestamp(boundary)]
    label_cutoff = min(timestamp(row["decision_at"]) for row in later)
    groups = {row["group"] for row in later}
    hashes = {row["content_hash"] for row in later}
    prior = [row for row in ordered if timestamp(row["published_at"]) < timestamp(boundary)]
    earlier = [
        row
        for row in prior
        if (row.get("retrospective") is True or timestamp(row["observed_at"]) <= label_cutoff)
        and row["group"] not in groups
        and row["content_hash"] not in hashes
    ]
    if len(earlier) < 5 or len(later) < 3:
        raise ValueError("时间/标签成熟性/内容组隔离后样本不足")
    return (
        earlier,
        later,
        {
            "cutoff": boundary,
            "labelAvailableThrough": label_cutoff.isoformat(),
            "purged": len(prior) - len(earlier),
        },
    )


def rank_correlation(actual: np.ndarray, prediction: np.ndarray) -> float | None:
    if len(actual) < 3 or np.ptp(actual) == 0 or np.ptp(prediction) == 0:
        return None
    ranks_a = pd.Series(actual).rank().to_numpy()
    ranks_b = pd.Series(prediction).rank().to_numpy()
    result = float(np.corrcoef(ranks_a, ranks_b)[0, 1])
    return result if math.isfinite(result) else None


def metrics(rows: list[dict], predictions: np.ndarray) -> dict:
    actual = target(rows)
    if len(predictions) != len(rows) or not np.isfinite(predictions).all():
        raise ValueError("预测长度或数值无效")
    by_account: dict[str, list[int]] = defaultdict(list)
    for i, row in enumerate(rows):
        if row.get("account_known", True):
            by_account[row["account"]].append(i)
    within = [rank_correlation(actual[index], predictions[index]) for index in by_account.values()]
    valid = [value for value in within if value is not None]
    return {
        "count": len(rows),
        "maeLog": float(np.abs(actual - predictions).mean()),
        "maeOriginal": float(
            np.abs(np.expm1(actual) - np.expm1(np.clip(predictions, 0, 30))).mean()
        ),
        "spearman": rank_correlation(actual, predictions),
        "withinAccountSpearman": float(np.mean(valid)) if valid else None,
        "rankableAccounts": len(valid),
    }


def statistical_predictions(train: list[dict], rows: list[dict]) -> dict[str, np.ndarray]:
    y = target(train)
    mean = float(y.mean())
    account: dict[str, list[float]] = defaultdict(list)
    slots: dict[tuple[int, int], list[float]] = defaultdict(list)
    for row, value in zip(train, y, strict=True):
        account[row["account"]].append(float(value))
        when = timestamp(row["published_at"])
        slots[(when.weekday(), when.hour)].append(float(value))

    def smooth(values: list[float], prior: float, strength: int = 5) -> float:
        return (sum(values) + strength * prior) / (len(values) + strength)

    accounts, times, hierarchy = [], [], []
    for row in rows:
        when = timestamp(row["published_at"])
        a = smooth(account.get(row["account"], []), mean)
        values = slots.get((when.weekday(), when.hour), [])
        accounts.append(a)
        times.append(smooth(values, mean))
        hierarchy.append(smooth(values, a))
    return {
        "global_mean": np.full(len(rows), mean),
        "account_smoothed": np.array(accounts),
        "slot_smoothed": np.array(times),
        "hierarchical_counts": np.array(hierarchy),
    }


def improvement_interval(
    rows: list[dict], baseline: np.ndarray, model: np.ndarray, *, seed: int = 20261020
) -> dict:
    actual = target(rows)
    difference = np.abs(actual - baseline) - np.abs(actual - model)
    blocks: dict[str, list[float]] = defaultdict(list)
    for row, value in zip(rows, difference, strict=True):
        day = timestamp(row["published_at"]).date()
        monday = day - timedelta(days=day.weekday())
        blocks[f"{row['account']}:{monday.isoformat()}"].append(float(value))
    groups = list(blocks.values())
    interval = None
    if len(groups) >= 8:
        rng = np.random.default_rng(seed)
        bootstrap = [
            float(
                np.mean(
                    [
                        v
                        for index in rng.integers(0, len(groups), len(groups))
                        for v in groups[index]
                    ]
                )
            )
            for _ in range(500)
        ]
        low, high = np.percentile(bootstrap, [2.5, 97.5])
        interval = [float(low), float(high)]
    baseline_mae = float(np.abs(actual - baseline).mean())
    return {
        "maeDifference": float(difference.mean()),
        "difference95CI": interval,
        "relativeImprovement": float(difference.mean() / baseline_mae) if baseline_mae else 0,
        "resampling": "ACCOUNT_WEEK_BLOCK",
        "blocks": len(groups),
    }
