"""The publish → measure → recommend loop actually closes.

Anything the system publishes itself only ever produced ``engagement_metric``
rows, which the recommender never reads. These tests pin the bridge that turns
a measured publish into ``engagement_history`` evidence.
"""

from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.business import EngagementHistory, PlatformAccount
from app.publishers.base import PublishResult
from app.publishers.official import WeiboPublisher
from app.services.engagement_feedback_service import FEEDBACK_SOURCE_NOTE, feedback_row_hash

PUBLISH_HOUR = 15


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def publish_one(client: TestClient, auth: dict, admin_auth: dict, monkeypatch) -> int:
    """Create an article, generate a Weibo variant, schedule it and publish it."""
    article = client.post(
        "/api/articles",
        headers=auth,
        json={
            "title": "发布效果回流验证文章",
            "source_text": "用于验证发布之后的实测数据能否回流成为下一次推荐的历史依据。",
            "topic": "系统验证",
            "keywords": ["回流", "内容运营"],
        },
    ).json()["data"]
    task = client.post(
        "/api/generation/content",
        headers=auth,
        json={"article_id": article["id"], "platforms": ["WEIBO"]},
    ).json()["data"]
    variant = client.get(f"/api/generation/tasks/{task['taskId']}", headers=auth).json()["data"][
        "variants"
    ][0]

    accounts = client.get("/api/platform-accounts", headers=auth).json()["data"]
    account_id = next(item["id"] for item in accounts if item["platform"] == "WEIBO")
    client.put(
        "/api/platform-accounts/WEIBO",
        headers=admin_auth,
        json={
            "account_name": "回流验证微博",
            "auth_type": "OAUTH2",
            "publish_mode": "REAL_API",
            "client_id": "test-client-id",
            "app_secret": "test-client-secret",
            "access_token": "test-access-token",
        },
    )
    with SessionLocal() as db:
        account = db.get(PlatformAccount, account_id)
        account.status = "CONNECTED"
        account.token_expires_at = datetime.now() + timedelta(hours=1)
        db.commit()

    async def official_publish(_self, _request):
        return PublishResult(
            True,
            "WEIBO",
            "REAL_API",
            "PUBLISHED",
            external_id="feedback-weibo-id",
            published_url="https://weibo.com/test/feedback-weibo-id",
            detail={"real": True},
        )

    monkeypatch.setattr(WeiboPublisher, "publish", official_publish)
    scheduled = client.post(
        "/api/schedules",
        headers=auth,
        json={
            "article_id": article["id"],
            "variant_id": variant["id"],
            "platform": "WEIBO",
            "account_id": account_id,
            "scheduled_at": (datetime.now() + timedelta(days=2)).isoformat(timespec="seconds"),
            "publish_mode": "REAL_API",
        },
    )
    assert scheduled.status_code == 200, scheduled.text
    schedule_id = scheduled.json()["data"]["id"]
    published = client.post(f"/api/schedules/{schedule_id}/publish-now", headers=auth)
    assert published.status_code == 200, published.text

    # Pin the publish moment so the derived slot is deterministic.
    with SessionLocal() as db:
        from app.models.business import PublishSchedule

        row = db.get(PublishSchedule, schedule_id)
        row.actual_publish_at = datetime.now().replace(
            hour=PUBLISH_HOUR, minute=0, second=0, microsecond=0
        )
        db.commit()
    return schedule_id


def record_metric(client: TestClient, auth: dict, schedule_id: int, *, likes: int, day: int = 0):
    return client.post(
        "/api/analytics/manual",
        headers=auth,
        json={
            "schedule_id": schedule_id,
            "platform": "WEIBO",
            "metric_date": (date.today() + timedelta(days=day)).isoformat(),
            "group_type": "RECOMMENDED_TIME",
            "impressions": 42000,
            "likes": likes,
            "comments": 260,
            "collects": 340,
            "shares": 180,
            "followers": 51000,
            "metric_basis": "IMPRESSIONS",
            "data_source": "MANUAL",
        },
    )


def test_measured_publish_becomes_recommendation_evidence(
    client: TestClient, login_as, monkeypatch
) -> None:
    auth = headers(login_as("operator", "Operator@123456")["access_token"])
    admin_auth = headers(login_as("admin", "Admin@123456")["access_token"])
    schedule_id = publish_one(client, auth, admin_auth, monkeypatch)

    response = record_metric(client, auth, schedule_id, likes=1900)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["feedbackHistoryId"] is not None

    with SessionLocal() as db:
        row = db.scalar(
            select(EngagementHistory).where(
                EngagementHistory.row_hash == feedback_row_hash(schedule_id)
            )
        )
        assert row is not None
        assert row.platform == "WEIBO"
        assert row.source_type == "ACCOUNT_HISTORY"
        assert row.source_note == FEEDBACK_SOURCE_NOTE
        assert row.hour_of_day == PUBLISH_HOUR
        assert row.likes == 1900
        assert row.engagement_rate > 0
        # The published variant's own text travels with the row, which is what
        # gives semantic retrieval something real to match on.
        detail = row.metric_detail_json
        assert detail["title"]
        assert detail["scheduleId"] == schedule_id


def test_newer_measurement_updates_instead_of_duplicating(
    client: TestClient, login_as, monkeypatch
) -> None:
    auth = headers(login_as("operator", "Operator@123456")["access_token"])
    admin_auth = headers(login_as("admin", "Admin@123456")["access_token"])
    schedule_id = publish_one(client, auth, admin_auth, monkeypatch)

    assert record_metric(client, auth, schedule_id, likes=800).status_code == 200
    assert record_metric(client, auth, schedule_id, likes=2400, day=1).status_code == 200

    with SessionLocal() as db:
        rows = list(
            db.scalars(
                select(EngagementHistory).where(
                    EngagementHistory.row_hash == feedback_row_hash(schedule_id)
                )
            ).all()
        )
    assert len(rows) == 1
    # The latest snapshot wins, so cumulative metrics are not double counted.
    assert rows[0].likes == 2400


def test_unpublished_schedule_produces_no_evidence(client: TestClient, login_as) -> None:
    auth = headers(login_as("operator", "Operator@123456")["access_token"])
    schedules = client.get("/api/schedules", headers=auth).json()["data"]
    pending = next(item for item in schedules if item["status"] not in ("PUBLISHED", "SUCCESS"))

    response = record_metric(client, auth, pending["id"], likes=500, day=2)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["feedbackHistoryId"] is None


def test_backfill_endpoint_is_idempotent(client: TestClient, login_as, monkeypatch) -> None:
    auth = headers(login_as("operator", "Operator@123456")["access_token"])
    admin_auth = headers(login_as("admin", "Admin@123456")["access_token"])
    schedule_id = publish_one(client, auth, admin_auth, monkeypatch)
    assert record_metric(client, auth, schedule_id, likes=1500).status_code == 200

    first = client.post("/api/analytics/feedback/sync", headers=auth)
    assert first.status_code == 200, first.text
    assert first.json()["data"]["syncedRows"] >= 1

    with SessionLocal() as db:
        before = len(list(db.scalars(select(EngagementHistory)).all()))
    assert client.post("/api/analytics/feedback/sync", headers=auth).status_code == 200
    with SessionLocal() as db:
        after = len(list(db.scalars(select(EngagementHistory)).all()))
    assert before == after
