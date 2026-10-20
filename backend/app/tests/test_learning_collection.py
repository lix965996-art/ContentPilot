"""Collection never publishes; counters, identity, outbox and observation windows are evidence."""

import uuid
from datetime import datetime, timedelta

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.credentials import encrypt_json
from app.db.base import Base
from app.ml.dataset import audit_dataset, eligible_row, export_dataset, load_dataset
from app.models.business import (
    ContentArticle,
    ContentVariant,
    PlatformAccount,
    PublishSchedule,
    TaskDispatch,
)
from app.models.learning import (
    EngagementObservation,
    MetricCollectionTask,
    PublishedContentSnapshot,
)
from app.publishers.bluesky import BlueskyPublisher
from app.publishers.mastodon import MastodonPublisher
from app.publishers.metrics import MetricReadResult, counter, parse_utc, response_failure, utc_now
from app.services import engagement_collection_service as service


def isolated_database():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def db():
    yield from isolated_database()


def publication(db, platform="BLUESKY"):
    config = {
        "bluesky_did": "did:plc:test",
        "instance_url": "https://mastodon.social",
        "mastodon_account_id": "42",
    }
    account = PlatformAccount(
        platform=platform,
        user_id=1,
        account_name="test",
        status="CONNECTED",
        credentials_encrypted=encrypt_json(config),
    )
    article = ContentArticle(title="test", source_text="source", created_by=1)
    db.add_all([account, article])
    db.flush()
    variant = ContentVariant(
        article_id=article.id,
        platform=platform,
        title="标题",
        content_text="这是发布时的原始内容",
        hashtags_json=["test"],
    )
    db.add(variant)
    db.flush()
    now = service.utc_to_business(utc_now())
    schedule = PublishSchedule(
        article_id=article.id,
        variant_id=variant.id,
        platform=platform,
        account_id=account.id,
        status="PUBLISHED",
        actual_publish_at=now,
        scheduled_at=now,
        created_by=1,
        idempotency_key=str(uuid.uuid4()),
        external_id="at://did:plc:test/app.bsky.feed.post/abc" if platform == "BLUESKY" else "123",
        published_url="https://mastodon.social/@test/123",
    )
    db.add(schedule)
    db.flush()
    return schedule, variant, account


@pytest.mark.parametrize(
    "value, expected", [(0, 0), (None, None), (True, None), (-1, None), ("9", None), (2**35, None)]
)
def test_counter_preserves_unknown_and_true_zero(value, expected):
    assert counter(value) == expected


@pytest.mark.parametrize(
    "status, code, retry",
    [
        (401, "AUTH_REQUIRED", False),
        (403, "PERMISSION_DENIED", False),
        (404, "POST_UNAVAILABLE", False),
        (429, "RATE_LIMITED", True),
        (503, "UPSTREAM_UNAVAILABLE", True),
    ],
)
def test_read_failures_are_safe_and_rate_limit_is_honored(status, code, retry):
    result = response_failure(httpx.Response(status, headers={"Retry-After": "120"}))
    assert result.error_code == code
    assert result.retryable is retry
    if status == 429:
        assert result.retry_after == 120
    assert parse_utc("2026-10-01T08:00:00+08:00") == datetime(2026, 10, 1)
    assert parse_utc("2026-10-01T00:00:00") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["BLUESKY", "MASTODON"])
async def test_adapters_only_get_and_validate_owner(db, monkeypatch, platform):
    schedule, _, account = publication(db, platform)
    publisher_type = BlueskyPublisher if platform == "BLUESKY" else MastodonPublisher
    post = (
        {
            "uri": schedule.external_id,
            "author": {"did": "did:plc:test"},
            "record": {"createdAt": "2026-10-01T00:00:00Z"},
            "likeCount": 0,
            "replyCount": 2,
            "repostCount": 3,
        }
        if platform == "BLUESKY"
        else {
            "id": "123",
            "account": {"id": "42"},
            "created_at": "2026-10-01T00:00:00Z",
            "favourites_count": 0,
            "replies_count": 2,
            "reblogs_count": 3,
        }
    )

    async def request(_self, method, path, **kwargs):
        assert method == "GET"
        return httpx.Response(200, json={"posts": [post]} if platform == "BLUESKY" else post)

    monkeypatch.setattr(publisher_type, "_request", request)
    result = await publisher_type(db, account).read_metrics(schedule.external_id)
    assert result.status == "SUCCEEDED"
    assert result.counts == {"likes": 0, "replies": 2, "reposts": 3, "quotes": None}
    if platform == "BLUESKY":
        post["author"]["did"] = "did:plc:other"
    else:
        post["account"]["id"] = "99"
    assert (
        await publisher_type(db, account).read_metrics(schedule.external_id)
    ).error_code == "POST_IDENTITY_MISMATCH"


def test_snapshot_is_immutable_and_collection_intents_are_transactional(db):
    schedule, variant, account = publication(db)
    features = service.content_features(variant, 1, schedule, account)
    service.capture_publication(db, schedule, features)
    variant.content_text = "编辑后的内容"
    service.capture_publication(
        db, schedule, service.content_features(variant, 2, schedule, account)
    )
    db.flush()
    assert db.get(PublishedContentSnapshot, schedule.id).content_json["text"] == features["text"]
    assert len(db.scalars(select(MetricCollectionTask)).all()) == 3
    assert len(db.scalars(select(TaskDispatch)).all()) == 3
    db.rollback()
    assert not db.scalars(select(MetricCollectionTask)).all()
    assert not db.scalars(select(TaskDispatch)).all()


def test_retry_reuses_features_that_existed_before_original_publication(db):
    schedule, variant, account = publication(db)
    first = service.content_features(variant, 1, schedule, account)
    frozen = service.freeze_attempt_features(db, schedule, first)
    later = {**first, "featureAvailableAt": (utc_now() + timedelta(hours=2)).isoformat()}
    assert service.freeze_attempt_features(db, schedule, later) == frozen
    db.expire_all()
    assert schedule.publish_package_json["learningFeatureVersions"]


@pytest.mark.asyncio
async def test_confirmed_publish_atomically_creates_snapshot_and_all_three_windows(db, monkeypatch):
    from app.publishers.base import PublishResult
    from app.services.publish_service import execute_publish
    from app.tests.test_mastodon_publishing import _task

    _, schedule, request = _task(db)
    created = []

    async def publish(self, payload):
        assert self.db.get(PublishSchedule, schedule.id).publish_package_json[
            "learningFeatureVersions"
        ]
        when = utc_now()
        created.append(when)
        return PublishResult(
            True,
            "MASTODON",
            "REAL_API",
            "PUBLISHED",
            "123",
            "https://mastodon.social/@test-user/123",
            detail={"publishedAtUTC": when.isoformat() + "Z"},
        )

    monkeypatch.setattr(MastodonPublisher, "publish", publish)
    await execute_publish(db, schedule.id)
    snapshot = db.get(PublishedContentSnapshot, schedule.id)
    assert snapshot.content_json["text"] == request["content"]
    assert snapshot.published_at == created[0]
    assert snapshot.feature_available_at <= snapshot.published_at
    tasks = db.scalars(select(MetricCollectionTask)).all()
    assert {task.window_seconds for task in tasks} == {3600, 86400, 259200}
    assert all(task.due_at == created[0] + timedelta(seconds=task.window_seconds) for task in tasks)
    assert len(db.scalars(select(TaskDispatch)).all()) == 3


@pytest.mark.asyncio
async def test_collection_claim_duplicate_retry_recovery_and_deadletter(db, monkeypatch):
    schedule, _, _ = publication(db)
    task = service.request_collection(db, schedule, request_key="manual")
    assert service.request_collection(db, schedule, request_key="manual").id == task.id
    db.commit()
    calls = []

    async def limited(*args):
        calls.append(1)
        return MetricReadResult(
            "FAILED", error_code="RATE_LIMITED", retryable=True, retry_after=120
        )

    monkeypatch.setattr(service, "_read", limited)
    await service.collect_task(db, task.id)
    assert task.status == "PENDING" and task.attempts == 1
    assert task.due_at > utc_now() + timedelta(seconds=110)
    await service.collect_task(db, task.id)
    assert len(calls) == 1
    task.status = "RUNNING"
    task.claim_expires_at = utc_now() - timedelta(seconds=1)
    db.commit()
    service.recover_collection_tasks(db)
    assert task.status == "PENDING"
    task.attempts = service.MAX_ATTEMPTS - 1
    task.due_at = utc_now() - timedelta(seconds=1)
    db.commit()
    await service.collect_task(db, task.id)
    assert task.status == "FAILED"
    assert db.scalar(select(TaskDispatch)).status == "FAILED"
    assert len(db.scalars(select(EngagementObservation)).all()) == 2


def test_recovery_does_not_starve_behind_healthy_future_jobs_and_honors_handoff_lease(db):
    schedule, _, _ = publication(db)
    for i in range(501):
        task = MetricCollectionTask(
            id=str(uuid.uuid4()),
            schedule_id=schedule.id,
            window_seconds=3600,
            request_key=str(i),
            status="PENDING",
            due_at=utc_now() + timedelta(days=2),
        )
        db.add(task)
        db.flush()
        service._arm(db, task)
    missing = MetricCollectionTask(
        id=str(uuid.uuid4()),
        schedule_id=schedule.id,
        window_seconds=86400,
        request_key="lost",
        status="PENDING",
        due_at=utc_now() - timedelta(minutes=1),
    )
    db.add(missing)
    db.commit()
    assert service.recover_collection_tasks(db) == 1
    intent = db.scalar(select(TaskDispatch).where(TaskDispatch.task_id == missing.id))
    intent.status = "CLAIMED"
    missing.claim_expires_at = utc_now() + timedelta(minutes=4)
    db.commit()
    assert service.recover_collection_tasks(db) == 0
    missing.claim_expires_at = utc_now() - timedelta(seconds=1)
    db.commit()
    assert service.recover_collection_tasks(db) == 1
    missing.status = "RUNNING"
    missing.attempts = service.MAX_ATTEMPTS
    missing.claim_expires_at = utc_now() - timedelta(seconds=1)
    db.commit()
    service.recover_collection_tasks(db)
    assert missing.status == "FAILED" and intent.status == "FAILED"


@pytest.mark.asyncio
async def test_fixed_window_dataset_chain_unknown_is_not_zero(db, monkeypatch, tmp_path):
    schedule, variant, account = publication(db)
    published = utc_now() - timedelta(hours=24, seconds=5)
    schedule.actual_publish_at = service.utc_to_business(published)
    features = service.content_features(variant, 1, schedule, account)
    features["featureAvailableAt"] = (published - timedelta(seconds=1)).isoformat()
    service.capture_publication(db, schedule, features)
    task = service.request_collection(db, schedule, window=86400)
    db.commit()

    async def result(*args):
        return MetricReadResult(
            "SUCCEEDED", counts={"likes": 0, "replies": 0, "reposts": 0}, published_at=published
        )

    monkeypatch.setattr(service, "_read", result)
    await service.collect_task(db, task.id)
    await service.collect_task(db, task.id)
    assert len(db.scalars(select(EngagementObservation)).all()) == 1
    rows, report = audit_dataset(db)
    assert report["accepted"] == 1 and rows[0]["interactions"] == 0
    exported = export_dataset(db, tmp_path)
    loaded, _ = load_dataset(tmp_path / exported["datasetId"])
    assert loaded == rows
    obs = db.scalar(select(EngagementObservation))
    snapshot = db.get(PublishedContentSnapshot, schedule.id)
    obs.likes = None
    assert eligible_row(obs, snapshot)[1] == "MISSING_COUNTS"
    obs.likes = 0
    obs.age_seconds = 86399
    assert eligible_row(obs, snapshot)[1] == "OUTSIDE_24H_WINDOW"
    obs.age_seconds = 87301
    assert eligible_row(obs, snapshot)[1] == "OUTSIDE_24H_WINDOW"
    obs.age_seconds = 86405
    assert eligible_row(obs, None)[1] == "NO_PUBLICATION_SNAPSHOT"
    data_file = tmp_path / exported["datasetId"] / "data.jsonl"
    data_file.write_bytes(data_file.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="哈希"):
        load_dataset(data_file.parent)
