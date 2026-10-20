import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from app.ml import native, public_data, registry
from app.ml.dataset import SCHEMA_VERSION, TARGET, load_dataset, validate_rows
from app.ml.evaluation import (
    improvement_interval,
    metrics,
    split_at,
    statistical_predictions,
    target,
)
from app.ml.features import HistoryIndex, fit_schema, timestamp, vector
from app.ml.public_data import prepare_youtube
from app.ml.training import train_experiment


def examples(count=80):
    start = datetime(2025, 1, 1, tzinfo=UTC)
    rows = []
    for i in range(count):
        when = start + timedelta(days=i * 2, hours=i % 24)
        rows.append(
            {
                "post_id": str(i),
                "platform": "BLUESKY",
                "account": f"account-{i % 2}",
                "group": str(i),
                "content_hash": str(i),
                "published_at": when.isoformat(),
                "decision_at": (when - timedelta(minutes=1)).isoformat(),
                "observed_at": (when + timedelta(days=1)).isoformat(),
                "age_seconds": 86400,
                "interactions": i % 17,
                "likes": i % 17,
                "replies": 0,
                "reposts": 0,
                "text": "校园内容 content test" + "学习" * (i % 10),
                "title": "title",
                "hashtags": [],
                "image_count": i % 3,
                "language": "zh",
                "source": "SYNTHETIC",
            }
        )
    return rows


def test_asof_history_does_not_change_when_future_labels_are_appended():
    rows = examples()
    row = rows[20]
    schema = fit_schema(rows[:15], semantic=True)
    before = vector(row, schema, HistoryIndex(rows[:20]))
    after = vector(row, schema, HistoryIndex(rows))
    assert before == after
    polluted = copy.deepcopy(rows)
    polluted[19]["interactions"] = 99999
    polluted[19]["observed_at"] = rows[21]["published_at"]
    expected = vector(row, schema, HistoryIndex([r for r in polluted if r["post_id"] != "19"]))
    assert vector(row, schema, HistoryIndex(polluted)) == expected
    assert "futureonly" not in schema["vocabulary"]
    unseen = {**row, "text": "futureonly"}
    assert np.isfinite(vector(unseen, schema, HistoryIndex(rows))).all()
    with pytest.raises(ValueError, match="偏移"):
        timestamp("2025-01-01T00:00:00")


def test_dataset_schema_rejects_future_features_missing_counts_and_window_laundering():
    rows = examples(20)
    validate_rows(rows)
    for change in (
        {"likes": None},
        {"age_seconds": 12},
        {"retrospective": True},
        {"decision_at": rows[1]["observed_at"]},
        {"interactions": 9999},
    ):
        mutated = [{**rows[0], **change}]
        with pytest.raises(ValueError):
            validate_rows(mutated)


def test_pinned_public_csv_download_and_cache_integrity(monkeypatch, tmp_path):
    import httpx

    content = b"video_id,duration\na,100\n"
    monkeypatch.setattr(public_data, "YOUTUBE_SHA256", hashlib.sha256(content).hexdigest())
    original = httpx.Client
    calls = []

    def handle(request):
        calls.append(request)
        assert request.method == "GET" and str(request.url) == public_data.YOUTUBE_URL
        return httpx.Response(200, content=content)

    monkeypatch.setattr(
        public_data.httpx,
        "Client",
        lambda **kwargs: original(transport=httpx.MockTransport(handle)),
    )
    path = public_data.obtain_youtube(tmp_path)
    assert public_data.obtain_youtube(tmp_path) == path and len(calls) == 1
    path.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="固定版本"):
        public_data.obtain_youtube(tmp_path)


def test_temporal_split_purges_immature_labels_and_content_groups():
    rows = examples()
    rows[55]["observed_at"] = rows[-1]["observed_at"]
    rows[10]["group"] = rows[70]["group"]
    rows[11]["content_hash"] = rows[71]["content_hash"]
    before, after, boundary = split_at(rows, 0.7)
    assert "55" not in {r["post_id"] for r in before}
    assert not ({r["group"] for r in before} & {r["group"] for r in after})
    assert not ({r["content_hash"] for r in before} & {r["content_hash"] for r in after})
    assert all(timestamp(r["observed_at"]) <= timestamp(boundary["cutoff"]) for r in before)
    with pytest.raises(ValueError):
        split_at(rows[:5], 0.5)


def test_predictive_metrics_and_block_interval_never_claim_policy_lift():
    rows = examples()
    predictions = target(rows)
    result = metrics(rows, predictions)
    assert result["maeOriginal"] < 1e-10
    assert result["spearman"] == pytest.approx(1)
    assert metrics(rows, np.zeros(len(rows)))["spearman"] is None
    interval = improvement_interval(rows, predictions + 0.2, predictions)
    assert interval["difference95CI"][0] > 0 and interval["resampling"] == "ACCOUNT_WEEK_BLOCK"
    assert set(statistical_predictions(rows[:50], rows[50:])) == {
        "global_mean",
        "account_smoothed",
        "slot_smoothed",
        "hierarchical_counts",
    }


@pytest.fixture(scope="module")
def experiment(tmp_path_factory):
    pytest.importorskip("catboost")
    pytest.importorskip("lightgbm")
    directory = tmp_path_factory.mktemp("learning-models")
    result = train_experiment(
        examples(), {"schemaVersion": SCHEMA_VERSION}, directory, test_only=True
    )
    return directory, result


def test_real_native_training_registry_integrity_and_test_model_activation_blocked(experiment):
    root, result = experiment
    manifest = result["manifest"]
    assert manifest["testOnly"] is True and manifest["eligibility"] == "EXPERIMENT_ONLY"
    directory, loaded, schema, report = registry.read_model(manifest["modelId"], root)
    assert report["selectionPolicy"] == "VALIDATION_ONLY"
    assert report["policyCausalEvidence"] is False
    assert len(report["comparison"]) == 4
    assert registry.activation_reason(loaded, report, "BLUESKY") == "RESEARCH_OR_TEST_ONLY"
    model = native.load(loaded["algorithm"], directory / loaded["modelFile"])
    values = vector(examples()[0], schema, HistoryIndex([]))
    assert native.predict(model, [values]).shape == (1,)
    assert len(native.contributions(model, loaded["algorithm"], values)) == len(values)
    assert registry.list_models(root)[0]["testRows"] > 0
    with pytest.raises(ValueError, match="已存在"):
        train_experiment(examples(), {"schemaVersion": SCHEMA_VERSION}, root, test_only=True)


@pytest.mark.parametrize("algorithm", ["catboost", "lightgbm"])
def test_both_native_formats_load_predict_and_explain(tmp_path, algorithm):
    pytest.importorskip(algorithm)
    x = [[float(i), float(i % 5)] for i in range(30)]
    model = native.fit(algorithm, x, np.arange(30, dtype=float), ["length", "hour"], iterations=8)
    path = tmp_path / ("model.cbm" if algorithm == "catboost" else "model.txt")
    native.save(model, path)
    loaded = native.load(algorithm, path)
    assert np.allclose(native.predict(model, x), native.predict(loaded, x))
    assert len(native.contributions(loaded, algorithm, x[0])) == 2


def test_registry_rejects_path_escape_and_corruption(experiment):
    root, result = experiment
    with pytest.raises(ValueError, match="标识"):
        registry.read_model("../../outside", root)
    directory = root / "bluesky-aaaaaaaaaaaaaaaa"
    directory.mkdir()
    source = root / result["manifest"]["modelId"]
    for name in ("features.json", "evaluation.json", result["manifest"]["modelFile"]):
        (directory / name).write_bytes((source / name).read_bytes())
    manifest = {**result["manifest"], "modelId": directory.name}
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (directory / "features.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="完整性"):
        registry.read_model(directory.name, root)
    assert len(registry.list_models(root)) == 1


def test_activation_scope_and_all_validation_gates():
    manifest = {
        "platform": "BLUESKY",
        "schemaVersion": SCHEMA_VERSION,
        "target": TARGET,
        "windowSeconds": 86400,
        "timezone": "UTC",
        "eligibility": "VALIDATED",
        "sources": ["ACCOUNT_API"],
        "trainedThrough": "2025-01-01T00:00:00Z",
        "scoreCalibration": {"low": 0, "high": 2},
    }
    report = {"checks": {key: True for key in registry.CHECKS}}
    assert registry.activation_reason(manifest, report, "BLUESKY") is None
    for key in registry.CHECKS:
        report["checks"][key] = False
        assert registry.activation_reason(manifest, report, "BLUESKY") == "VALIDATION_GATE_FAILED"
        report["checks"][key] = True
    assert registry.activation_reason(manifest, report, "MASTODON") == "PLATFORM_MISMATCH"
    assert registry.activation_reason({**manifest, "researchOnly": True}, report, "BLUESKY")
    assert (
        registry.activation_reason({**manifest, "sources": ["SIMULATED"]}, report, "BLUESKY")
        == "UNVERIFIED_SOURCE"
    )


def test_public_youtube_excludes_post_outcomes_deduplicates_and_is_retrospective(tmp_path):
    source = tmp_path / "RandomVideo_dataTable.csv"
    source.write_text(
        "video_id,duration,publishedAt,category_term,engagement,likeCount\n"
        "a,100,2015-01-01T00:00:00Z,Education,0.5,999999\n"
        "a,100,2015-01-01T00:00:00Z,Education,0.5,1\n"
        "b,0,2015-01-01T00:00:00Z,Music,0.5,2\n",
        encoding="utf-8",
    )
    exported = prepare_youtube(source, tmp_path / "datasets")
    rows, manifest = load_dataset(Path(exported["directory"]))
    assert len(rows) == 1 and rows[0]["label"] == 0.5
    assert "likeCount" not in rows[0] and rows[0]["observed_at"] is None
    assert rows[0]["account_known"] is False and rows[0]["retrospective"] is True
    assert manifest["sourceInfo"]["url"] == "https://github.com/sTechLab/YouTubeDurationData"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == manifest["sourceInfo"]["rawSha256"]
