import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.api.endpoints import schedules
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.business import (
    ContentVariant,
    PlatformAccount,
    PublishRecommendation,
    PublishSchedule,
)
from app.services.activity_service import business_now
from app.services.review_fingerprint import variant_fingerprint


@pytest.fixture
def setup_schedule(client, login_as, monkeypatch):
    auth = {"Authorization": "Bearer " + login_as("operator", "Operator@123456")["access_token"]}
    created = client.post(
        "/api/articles",
        headers=auth,
        json={
            "title": "排期请求边界验证",
            "source_text": "仅用于隔离测试数据库中的排期创建与重试验证。",
        },
    )
    assert created.status_code == 200, created.text
    article_id = created.json()["data"]["id"]
    moment = business_now().replace(second=0, microsecond=0) + timedelta(
        days=60, minutes=article_id * 5
    )
    with SessionLocal() as db:
        variants = [
            ContentVariant(
                article_id=article_id,
                platform="XIAOHONGSHU",
                version_no=index,
                title=f"隔离测试版本{index}",
                content_text="排期请求测试正文",
                review_status="APPROVED",
            )
            for index in (1, 2)
        ]
        accounts = [
            db.scalar(select(PlatformAccount).where(PlatformAccount.platform == platform))
            for platform in ("XIAOHONGSHU", "WEIBO")
        ]
        db.add_all(variants)
        db.flush()
        for variant in variants:
            variant.review_fingerprint = variant_fingerprint(variant)
        recommendation = PublishRecommendation(
            article_id=article_id,
            variant_id=variants[0].id,
            account_id=accounts[0].id,
            platform="XIAOHONGSHU",
            recommended_at=moment,
            score=50,
            confidence="LOW",
        )
        db.add(recommendation)
        db.commit()
        identifiers = {
            "variant": variants[0].id,
            "other_variant": variants[1].id,
            "account": accounts[0].id,
            "other_account": accounts[1].id,
            "recommendation": recommendation.id,
        }
    jobs = []
    monkeypatch.setattr(schedules, "add_schedule_job", lambda *args: jobs.append(args))
    payload = {
        "article_id": article_id,
        "variant_id": identifiers["variant"],
        "account_id": identifiers["account"],
        "platform": "XIAOHONGSHU",
        "publish_mode": "MANUAL_CONFIRM",
        "scheduled_at": moment.isoformat(),
        "idempotency_key": "replay-" + uuid.uuid4().hex,
    }
    return auth, payload, identifiers, jobs


@pytest.mark.parametrize(
    "changed_field",
    [
        "variant_id",
        "account_id",
        "scheduled_at",
        "publish_mode",
        "time_source",
        "content_type",
    ],
)
def test_same_key_rejects_changed_creation_intent(client, setup_schedule, changed_field):
    auth, payload, ids, jobs = setup_schedule
    first = client.post("/api/schedules", headers=auth, json=payload)
    assert first.status_code == 200, first.text
    changes = {
        "variant_id": ids["other_variant"],
        "account_id": ids["other_account"],
        "scheduled_at": (
            datetime.fromisoformat(payload["scheduled_at"]) + timedelta(hours=2)
        ).isoformat(),
        "publish_mode": "MCP_PUBLISH",
        "time_source": "ALTERNATIVE",
        "content_type": "KNOWLEDGE",
    }
    rejected = client.post(
        "/api/schedules", headers=auth, json={**payload, changed_field: changes[changed_field]}
    )
    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["code"] == 40902
    original = client.get(f"/api/schedules/{first.json()['data']['id']}", headers=auth).json()[
        "data"
    ]
    assert original["variantId"] == payload["variant_id"]
    assert original["accountId"] == payload["account_id"]
    assert original["scheduledAt"] == payload["scheduled_at"]
    assert len(jobs) == 1


def test_equivalent_timezone_replay_returns_same_task_without_rescheduling(client, setup_schedule):
    from zoneinfo import ZoneInfo

    auth, payload, _ids, jobs = setup_schedule
    first = client.post("/api/schedules", headers=auth, json=payload)
    local = datetime.fromisoformat(payload["scheduled_at"]).replace(
        tzinfo=ZoneInfo(settings.app_timezone)
    )
    replay = client.post(
        "/api/schedules",
        headers=auth,
        json={
            **payload,
            "scheduled_at": local.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        },
    )
    assert first.status_code == replay.status_code == 200, replay.text
    assert first.json()["data"]["id"] == replay.json()["data"]["id"]
    assert len(jobs) == 1


def test_batch_replay_validates_each_item_and_keeps_original(client, setup_schedule):
    auth, payload, ids, jobs = setup_schedule
    item = {
        key: value for key, value in payload.items() if key not in {"article_id", "idempotency_key"}
    }
    item.update(recommendation_id=ids["recommendation"], recommended_at=payload["scheduled_at"])
    batch = {
        "article_id": payload["article_id"],
        "idempotency_key": payload["idempotency_key"],
        "items": [item],
    }
    first = client.post("/api/schedules/batch", headers=auth, json=batch)
    assert first.status_code == 200 and first.json()["data"]["successCount"] == 1, first.text
    replay = client.post("/api/schedules/batch", headers=auth, json=batch)
    assert replay.json()["data"]["items"][0]["skipped"] is True, replay.text
    for change in (
        {"account_id": ids["other_account"]},
        {
            "scheduled_at": (
                datetime.fromisoformat(payload["scheduled_at"]) + timedelta(hours=2)
            ).isoformat()
        },
    ):
        rejected = client.post(
            "/api/schedules/batch", headers=auth, json={**batch, "items": [{**item, **change}]}
        )
        result = rejected.json()["data"]
        assert result["failureCount"] == 1 and result["items"][0]["code"] == 40902, rejected.text
    assert len(jobs) == 1
    with SessionLocal() as db:
        records = db.scalars(
            select(PublishSchedule).where(PublishSchedule.article_id == payload["article_id"])
        ).all()
        assert len(records) == 1
        assert records[0].account_id == ids["account"]


def test_legacy_key_only_replays_matching_stored_fields(client, setup_schedule):
    auth, payload, ids, _jobs = setup_schedule
    first = client.post("/api/schedules", headers=auth, json=payload)
    with SessionLocal() as db:
        row = db.get(PublishSchedule, first.json()["data"]["id"])
        row.publish_package_json = {}
        db.commit()
    assert client.post("/api/schedules", headers=auth, json=payload).status_code == 200
    changed = client.post(
        "/api/schedules", headers=auth, json={**payload, "variant_id": ids["other_variant"]}
    )
    assert changed.status_code == 409 and changed.json()["code"] == 40902
