from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_current_user
from app.core.exceptions import AppException
from app.db.session import get_db
from app.main import app
from app.ml import registry
from app.ml.dataset import SCHEMA_VERSION, TARGET
from app.ml.features import fit_schema
from app.models.business import SystemSetting, TaskDispatch
from app.models.learning import MetricCollectionTask
from app.publishers.metrics import utc_now
from app.scheduler import dispatch
from app.services import engagement_collection_service as collection
from app.services import ml_prediction_service as prediction
from app.tests import test_learning_collection as collection_tests
from app.tests.test_learning_collection import publication


@pytest.fixture(name="db")
def isolated_learning_database():
    yield from collection_tests.isolated_database()


@pytest.fixture
def api(db, monkeypatch):
    user = SimpleNamespace(id=1, roles=[SimpleNamespace(code="OPERATOR")])
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    monkeypatch.setattr(registry, "list_models", lambda: [])
    # No lifespan: these endpoint tests intentionally run no background publishing worker.
    client = TestClient(app)
    yield client, user
    client.close()
    app.dependency_overrides.clear()


def validated_manifest():
    return {
        "platform": "BLUESKY",
        "schemaVersion": SCHEMA_VERSION,
        "target": TARGET,
        "windowSeconds": 86400,
        "timezone": "UTC",
        "eligibility": "VALIDATED",
        "sources": ["ACCOUNT_API"],
        "trainedThrough": "2025-01-01T00:00:00Z",
        "scoreCalibration": {"low": 0, "high": 3},
        "algorithm": "lightgbm",
        "modelFile": "model.txt",
    }


def test_status_collection_owner_and_role_gates(api, db):
    client, user = api
    schedule, _, _ = publication(db)
    db.commit()
    response = client.get("/api/learning/status")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0 and body["data"]["readiness"]["accepted"] == 0
    assert body["data"]["items"][0]["likes"] is None
    assert body["data"]["exposureAvailable"] is False
    url = f"/api/learning/collect/{schedule.id}"
    first = client.post(url, json={"request_key": "same-click"})
    second = client.post(url, json={"request_key": "same-click"})
    third = client.post(url, json={"request_key": "another-click"})
    assert (
        first.json()["data"]["taskId"]
        == second.json()["data"]["taskId"]
        == third.json()["data"]["taskId"]
    )
    assert len(db.scalars(select(MetricCollectionTask)).all()) == 1
    user.id = 999
    assert client.post(url, json={"request_key": "forbidden"}).status_code == 403
    assert client.get("/api/learning/status").json()["data"]["items"] == []
    user.roles = [SimpleNamespace(code="VIEWER")]
    assert client.post(url, json={"request_key": "forbidden"}).status_code == 403
    assert (
        client.post("/api/learning/models/activate", json={"platform": "BLUESKY"}).status_code
        == 403
    )


def test_model_activation_integrity_and_audit_role(api, db, monkeypatch):
    client, user = api
    user.roles = [SimpleNamespace(code="ADMIN")]
    manifest = validated_manifest()
    report = {"checks": {key: True for key in registry.CHECKS}}
    monkeypatch.setattr(registry, "read_model", lambda _id: (Path("."), manifest, {}, report))
    url = "/api/learning/models/activate"
    model_id = "bluesky-aaaaaaaaaaaaaaaa"
    assert client.post(url, json={"platform": "BLUESKY", "model_id": model_id}).status_code == 200
    assert registry.active_id(db, "BLUESKY") == model_id
    manifest["researchOnly"] = True
    assert (
        client.post(url, json={"platform": "BLUESKY", "model_id": model_id}).json()["code"] == 40091
    )
    assert client.post(url, json={"platform": "BLUESKY", "model_id": None}).status_code == 200
    assert registry.active_id(db, "BLUESKY") is None
    assert len(db.scalars(select(SystemSetting)).all()) == 1


def test_collection_rejects_unsupported_unpublished_and_identity_changes(db):
    schedule, _, account = publication(db)
    schedule.status = "FAILED"
    with pytest.raises(AppException):
        collection.request_collection(db, schedule)
    schedule.status = "PUBLISHED"
    schedule.platform = "WEIBO"
    with pytest.raises(AppException):
        collection.request_collection(db, schedule)
    schedule.platform = "BLUESKY"
    with pytest.raises(AppException):
        collection.request_collection(db, schedule, window=10)
    assert collection.account_reference(schedule, account) == collection.account_reference(
        schedule, account
    )


def test_executor_failure_becomes_visible_terminal_task(db, monkeypatch):
    schedule, _, _ = publication(db)
    task = collection.request_collection(db, schedule)
    db.commit()
    row = db.scalar(select(TaskDispatch))
    row.attempts = dispatch.settings.dispatch_max_attempts - 1

    def fail(*args):
        raise RuntimeError("executor down")

    monkeypatch.setattr(dispatch._metric_executor, "submit", fail)
    dispatch._dispatch_metric(db, row, collection.utc_to_business(utc_now() + timedelta(seconds=1)))
    assert row.status == "FAILED" and task.status == "FAILED"
    assert task.last_error == "DISPATCH_EXHAUSTED"
    assert collection.recover_collection_tasks(db) == 0


def test_prediction_uses_168_utc_encoded_business_slots_and_calibration(db, monkeypatch):
    schedule, variant, account = publication(db)
    manifest = validated_manifest()
    manifest["trainingAccounts"] = [collection.account_reference(schedule, account)]
    schema = fit_schema([], semantic=False)
    report = {"checks": {key: True for key in registry.CHECKS}}
    monkeypatch.setattr(registry, "active_id", lambda *_args: "bluesky-aaaaaaaaaaaaaaaa")
    monkeypatch.setattr(
        registry, "read_model", lambda *_args: (Path("."), manifest, schema, report)
    )
    monkeypatch.setattr(prediction, "audit_dataset", lambda *_args, **_kwargs: ([], {}))
    monkeypatch.setattr(prediction.native, "load", lambda *_args: object())

    def predict(_model, values):
        assert len(values) == 168 and len(values[0]) == len(schema["names"])
        return np.linspace(0, 3, 168)

    monkeypatch.setattr(prediction.native, "predict", predict)
    monkeypatch.setattr(
        prediction.native, "contributions", lambda *_args: [0.1] * len(schema["names"])
    )
    now = collection.utc_to_business(utc_now())
    scores, info = prediction.candidate_scores(
        db, platform="BLUESKY", account_id=account.id, variant=variant, now=now
    )
    assert len(scores) == 168 and min(scores.values()) == 0 and max(scores.values()) == 100
    assert all(0 <= weekday <= 6 for weekday, _ in scores)
    assert info["mode"] == "MACHINE_LEARNING" and len(info["explanations"]) == 5
    manifest["trainingAccounts"] = []
    assert (
        prediction.candidate_scores(
            db, platform="BLUESKY", account_id=account.id, variant=variant, now=now
        )[1]["reason"]
        == "COLD_ACCOUNT"
    )
    manifest["trainingAccounts"] = [collection.account_reference(schedule, account)]
    manifest["trainedThrough"] = "2099-01-01T00:00:00Z"
    assert (
        prediction.candidate_scores(
            db, platform="BLUESKY", account_id=account.id, variant=variant, now=now
        )[1]["reason"]
        == "MODEL_NOT_AVAILABLE_ASOF_DECISION"
    )
    manifest["trainedThrough"] = "2025-01-01T00:00:00Z"
    account.status = "NOT_CONFIGURED"
    assert (
        prediction.candidate_scores(
            db, platform="BLUESKY", account_id=account.id, variant=variant, now=now
        )[1]["reason"]
        == "ACCOUNT_NOT_CONNECTED"
    )
    account.status = "CONNECTED"
    manifest["researchOnly"] = True
    assert (
        prediction.candidate_scores(
            db, platform="BLUESKY", account_id=account.id, variant=variant, now=now
        )[1]["reason"]
        == "RESEARCH_OR_TEST_ONLY"
    )


def test_prediction_fails_closed_without_blocking_existing_scheduling(db, monkeypatch):
    _, variant, account = publication(db)
    now = collection.utc_to_business(utc_now())
    assert (
        prediction.candidate_scores(
            db, platform="BLUESKY", account_id=account.id, variant=variant, now=now
        )[1]["reason"]
        == "NO_VALIDATED_MODEL"
    )
    assert (
        prediction.candidate_scores(
            db, platform="WEIBO", account_id=account.id, variant=variant, now=now
        )[1]["reason"]
        == "PLATFORM_UNSUPPORTED"
    )
    monkeypatch.setattr(registry, "active_id", lambda *_args: "broken")
    assert (
        prediction.candidate_scores(
            db, platform="BLUESKY", account_id=account.id, variant=variant, now=now
        )[1]["reason"]
        == "MODEL_UNAVAILABLE"
    )
