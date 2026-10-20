"""Time-held-out evaluation of publish-slot strategies on a public YouTube sample.

Split videos by ``publishedAt``: earlier videos build the slot statistics, and
later videos are evaluated once. All strategies rank the same 7x24 slots and
are scored on the same held-out videos, using the same target and constraints.

This is an offline, observational experiment. It cannot establish a causal
effect of publishing time: video topic, channel size and audience are not
controlled. Results are reported as correlation/lift with bootstrap intervals.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.services.activity_prior_service import default_prior_score  # noqa: E402
from app.services.recommendation_analysis import _timezone_score, _weights  # noqa: E402

DEFAULT_CSV = (
    PROJECT_ROOT / "examples/history/YouTubeDurationData/IndividualLogs_dataTable.csv"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "var/reports/experiments/r01_youtube_heldout.json"
ALGORITHM_VERSION = "hybrid-v2"
TARGET_COLUMN = "engagement"
SLOT_COUNT = 7 * 24
SELECTED_SLOTS = 7
MIN_TRAIN_SAMPLES = 5
FORBIDDEN_HOURS = {1, 2, 3, 4, 5}


@dataclass(frozen=True)
class Split:
    train: pd.DataFrame
    test: pd.DataFrame
    cutoff: pd.Timestamp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--train-fraction", type=float, default=0.7)
    parser.add_argument("--seed", type=int, default=20261020)
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument(
        "--timezone",
        default="UTC",
        help="Timezone used to derive weekday/hour from publishedAt (default UTC).",
    )
    return parser.parse_args()


def load_videos(csv_path: Path, timezone: str) -> pd.DataFrame:
    frame = pd.read_csv(
        csv_path,
        usecols=["video_id", "publishedAt", TARGET_COLUMN],
    )
    frame = frame.dropna(subset=["video_id", "publishedAt", TARGET_COLUMN])
    frame = frame.drop_duplicates(subset=["video_id"], keep="first").copy()
    published = pd.to_datetime(frame["publishedAt"], utc=True, errors="coerce")
    frame = frame.loc[published.notna()].copy()
    published = published.loc[published.notna()]
    local = published.dt.tz_convert(ZoneInfo(timezone))
    frame["published_utc"] = published
    frame["weekday"] = local.dt.weekday
    frame["hour"] = local.dt.hour
    frame["target"] = frame[TARGET_COLUMN].astype(float)
    return frame.sort_values("published_utc").reset_index(drop=True)


def split_by_time(frame: pd.DataFrame, train_fraction: float) -> Split:
    cutoff_index = max(1, min(len(frame) - 1, int(math.floor(len(frame) * train_fraction))))
    train = frame.iloc[:cutoff_index].copy()
    test = frame.iloc[cutoff_index:].copy()
    cutoff = frame.iloc[cutoff_index]["published_utc"]
    return Split(train=train, test=test, cutoff=cutoff)


def slot_statistics(train: pd.DataFrame) -> tuple[pd.Series, pd.Series, float]:
    grouped = train.groupby(["weekday", "hour"])["target"]
    sums = grouped.sum()
    counts = grouped.size()
    global_mean = float(train["target"].mean())
    # Empirical-Bayes smoothing toward the training global mean.
    smoothed = (sums + MIN_TRAIN_SAMPLES * global_mean) / (counts + MIN_TRAIN_SAMPLES)
    return smoothed, counts, global_mean


def all_slots() -> pd.MultiIndex:
    return pd.MultiIndex.from_product([range(7), range(24)], names=["weekday", "hour"])


def minmax(series: pd.Series) -> pd.Series:
    low, high = float(series.min()), float(series.max())
    if high - low < 1e-12:
        return pd.Series(50.0, index=series.index)
    return (series - low) / (high - low) * 100.0


def strategy_scores(train: pd.DataFrame, strategy: str) -> pd.Series:
    slots = all_slots()
    stats, counts, global_mean = slot_statistics(train)
    stats = stats.reindex(slots).fillna(global_mean)
    counts = counts.reindex(slots).fillna(0)
    prior = pd.Series(
        [default_prior_score("YOUTUBE", weekday, hour) for weekday, hour in slots],
        index=slots,
    )
    if strategy == "fixed_time":
        return pd.Series(
            [100.0 if hour == 20 else 0.0 for _, hour in slots], index=slots, dtype=float
        )
    if strategy == "platform_prior":
        return prior.astype(float)
    history = minmax(stats)
    baseline = minmax(prior)
    content = minmax(prior)
    timezone = pd.Series([_timezone_score(hour) for _, hour in slots], index=slots)
    weights = _weights(len(train))
    hybrid = (
        weights["history"] * history
        + weights["baseline"] * baseline
        + weights["content"] * content
        + weights["timezone"] * timezone
    )
    if strategy == "hybrid_v2":
        return hybrid.astype(float)
    if strategy == "full_pipeline":
        # Same hybrid score plus the product's operational constraints: sparse
        # slots fall back to the platform prior, and forbidden hours are out.
        full = hybrid.copy()
        sparse = counts < MIN_TRAIN_SAMPLES
        full.loc[sparse] = 0.6 * prior.loc[sparse] + 0.4 * full.loc[sparse]
        forbidden = pd.Series([hour in FORBIDDEN_HOURS for _, hour in slots], index=slots)
        full.loc[forbidden] = -1.0
        return full.astype(float)
    raise ValueError(f"unknown strategy: {strategy}")


def selected_slots(scores: pd.Series, strategy: str) -> list[tuple[int, int]]:
    if strategy == "fixed_time":
        return [(weekday, 20) for weekday in range(7)]
    return list(scores.sort_values(ascending=False).head(SELECTED_SLOTS).index)


def score_test(scores: pd.Series, test: pd.DataFrame) -> pd.Series:
    keys = pd.MultiIndex.from_frame(test[["weekday", "hour"]])
    return pd.Series(scores.reindex(keys).to_numpy(), index=test.index, dtype=float)


def bootstrap_lift(
    selected: np.ndarray, overall: np.ndarray, rng: np.random.Generator, rounds: int
) -> tuple[float, float, float]:
    if len(selected) == 0:
        return 0.0, 0.0, 0.0
    observed = float(selected.mean() - overall.mean())
    draws = np.empty(rounds)
    for index in range(rounds):
        selected_sample = rng.choice(selected, size=len(selected), replace=True)
        overall_sample = rng.choice(overall, size=len(overall), replace=True)
        draws[index] = selected_sample.mean() - overall_sample.mean()
    low, high = np.percentile(draws, [2.5, 97.5])
    return observed, float(low), float(high)


def evaluate(
    frame: pd.DataFrame,
    split: Split,
    strategy: str,
    *,
    seed: int,
    bootstrap_rounds: int,
) -> dict:
    scores = strategy_scores(split.train, strategy)
    chosen = selected_slots(scores, strategy)
    chosen_set = set(chosen)
    test = split.test.copy()
    test["score"] = score_test(scores, test).to_numpy()
    selected_mask = [
        (int(weekday), int(hour)) in chosen_set
        for weekday, hour in zip(test["weekday"], test["hour"], strict=True)
    ]
    selected_targets = test.loc[selected_mask, "target"].to_numpy()
    overall_targets = test["target"].to_numpy()
    rng = np.random.default_rng(seed)
    lift, low, high = bootstrap_lift(selected_targets, overall_targets, rng, bootstrap_rounds)

    slot_means = test.groupby(["weekday", "hour"])["target"].mean()
    slot_counts = test.groupby(["weekday", "hour"])["target"].size()
    eligible = slot_counts[slot_counts >= 3].index
    actual = scores.reindex(eligible)
    observed = slot_means.reindex(eligible)
    spearman = (
        float(actual.rank().corr(observed.rank())) if len(eligible) >= 3 else None
    )

    quartile = pd.qcut(test["score"], 4, labels=False, duplicates="drop")
    top_quartile = test.loc[quartile == quartile.max(), "target"].mean() if len(test) else None
    bottom_quartile = test.loc[quartile == 0, "target"].mean() if len(test) else None

    return {
        "strategy": strategy,
        "selectedSlots": [f"{weekday}-{hour:02d}" for weekday, hour in chosen],
        "selectedCount": int(len(selected_targets)),
        "coverage": round(float(len(selected_targets) / max(1, len(test))), 4),
        "meanTargetSelected": round(float(selected_targets.mean()), 6)
        if len(selected_targets)
        else None,
        "meanTargetAll": round(float(overall_targets.mean()), 6),
        "liftSelectedVsAll": round(lift, 6),
        "liftCi95": [round(low, 6), round(high, 6)],
        "spearmanActualSlot": round(spearman, 4) if spearman is not None else None,
        "topQuartileMean": round(float(top_quartile), 6) if top_quartile is not None else None,
        "bottomQuartileMean": round(float(bottom_quartile), 6)
        if bottom_quartile is not None
        else None,
    }


def oracle(frame: pd.DataFrame, split: Split) -> dict:
    test = split.test
    means = test.groupby(["weekday", "hour"])["target"].mean()
    counts = test.groupby(["weekday", "hour"]).size()
    eligible = means[counts >= 3].sort_values(ascending=False).head(SELECTED_SLOTS)
    chosen = set(eligible.index)
    mask = [(int(weekday), int(hour)) in chosen for weekday, hour in zip(test["weekday"], test["hour"], strict=True)]
    values = test.loc[mask, "target"]
    return {
        "strategy": "oracle_top7_test_slots",
        "note": "In-sample upper bound computed from the test period; not deployable.",
        "selectedSlots": [f"{weekday}-{hour:02d}" for weekday, hour in eligible.index],
        "selectedCount": int(len(values)),
        "meanTargetSelected": round(float(values.mean()), 6) if len(values) else None,
        "meanTargetAll": round(float(test["target"].mean()), 6),
    }


def main() -> None:
    args = parse_args()
    frame = load_videos(args.csv, args.timezone)
    split = split_by_time(frame, args.train_fraction)
    strategies = ["fixed_time", "platform_prior", "hybrid_v2", "full_pipeline"]
    results = [
        evaluate(
            frame,
            split,
            strategy,
            seed=args.seed + index,
            bootstrap_rounds=args.bootstrap,
        )
        for index, strategy in enumerate(strategies)
    ]
    payload = {
        "experiment": "R-01 time-held-out publish-slot evaluation",
        "source": str(args.csv),
        "sourceRows": int(len(frame)),
        "sourceVideos": int(frame["video_id"].nunique()),
        "target": TARGET_COLUMN,
        "targetDescription": "Per-video engagement score from the public sample (0-1).",
        "timezone": args.timezone,
        "split": {
            "method": "chronological by publishedAt",
            "trainFraction": args.train_fraction,
            "cutoff": split.cutoff.isoformat(),
            "trainVideos": int(len(split.train)),
            "testVideos": int(len(split.test)),
            "trainStart": split.train["published_utc"].min().isoformat(),
            "trainEnd": split.train["published_utc"].max().isoformat(),
            "testStart": split.test["published_utc"].min().isoformat(),
            "testEnd": split.test["published_utc"].max().isoformat(),
        },
        "algorithmVersion": ALGORITHM_VERSION,
        "seed": args.seed,
        "bootstrapRounds": args.bootstrap,
        "constraints": {
            "selectedSlotsPerStrategy": SELECTED_SLOTS,
            "minTrainSamplesForFullPipeline": MIN_TRAIN_SAMPLES,
            "forbiddenHoursFullPipeline": sorted(FORBIDDEN_HOURS),
            "sameTestVideosForAllStrategies": True,
        },
        "results": results,
        "oracle": oracle(frame, split),
        "limitations": [
            "Observational offline data; no randomized assignment, so lift is not causal.",
            "Video topic, channel size and audience composition are uncontrolled.",
            "publishedAt timezone is not recorded by the source; UTC is primary and local-time sensitivity must be checked separately.",
            "The sample is a public YouTube subset, not the operator's own account.",
        ],
        "testVideoIds": split.test["video_id"].tolist(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# R-01 YouTube 时间留出评估",
        "",
        f"- 数据源：`{args.csv}`（{len(frame)} 个去重视频）",
        f"- 目标：`{TARGET_COLUMN}`；时区：{args.timezone}",
        f"- 切分：按 `publishedAt` 时间排序，前 {args.train_fraction:.0%} 训练，未来 {1 - args.train_fraction:.0%} 留出",
        f"- 切分边界：{split.cutoff.isoformat()}；训练 {len(split.train)} / 留出 {len(split.test)}",
        f"- 算法版本：{ALGORITHM_VERSION}；随机种子：{args.seed}；Bootstrap：{args.bootstrap} 次",
        "",
        "| 策略 | 留出样本覆盖 | 命中时段均值 | 全部留出均值 | 提升 | 95% CI | Spearman |",
        "| --- | ---: | ---: | ---: | ---: | --- | ---: |",
    ]
    for item in results:
        lines.append(
            "| {strategy} | {coverage:.1%} | {meanTargetSelected:.4f} | {meanTargetAll:.4f} | "
            "{liftSelectedVsAll:+.4f} | [{low:+.4f}, {high:+.4f}] | {spearman} |".format(
                strategy=item["strategy"],
                coverage=item["coverage"],
                meanTargetSelected=item["meanTargetSelected"] or 0.0,
                meanTargetAll=item["meanTargetAll"],
                liftSelectedVsAll=item["liftSelectedVsAll"],
                low=item["liftCi95"][0],
                high=item["liftCi95"][1],
                spearman=item["spearmanActualSlot"],
            )
        )
    lines.extend(
        [
            "",
            f"Oracle（留出期内样本内上界，不可部署）：{payload['oracle']['meanTargetSelected']}",
            "",
            "## 解释边界",
            "",
            "该实验是离线观察性回测，只能说明时段得分与未来样本互动指标的相关/提升，"
            "不能证明真实发布时间的因果提升。样本来源、样本量、时区假设与不确定性见 JSON。",
        ]
    )
    markdown = args.output.with_suffix(".md")
    markdown.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "markdown": str(markdown)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
