import os
from datetime import datetime, timedelta

import pytest
from sqlalchemy import inspect, select

from app.db.session import SessionLocal
from app.ml.dataset import audit_dataset
from app.models.business import TaskDispatch
from app.models.learning import EngagementObservation
from app.publishers.metrics import MetricReadResult
from app.services import engagement_collection_service as service
from app.tests.test_learning_collection import publication

pytestmark = [
    pytest.mark.mysql_integration,
    pytest.mark.skipif(
        not os.environ.get("CONTENTPILOT_TEST_MYSQL_URL"),
        reason="requires disposable MySQL database",
    ),
]


@pytest.mark.asyncio
async def test_mysql_microseconds_survive_full_collection_dataset_roundtrip(monkeypatch):
    published = datetime(2026, 10, 19, 12, 0, 0, 987654)
    observed = datetime(2026, 10, 20, 12, 0, 10, 123456)
    monkeypatch.setattr(service, "utc_now", lambda: observed)
    with SessionLocal() as db:
        for table, names in {
            "published_content_snapshot": ("feature_available_at", "published_at"),
            "engagement_observation": ("observed_at", "published_at"),
        }.items():
            columns = {c["name"]: c for c in inspect(db.get_bind()).get_columns(table)}
            assert all(columns[name]["type"].fsp == 6 for name in names)
        schedule, variant, account = publication(db)
        try:
            schedule.actual_publish_at = service.utc_to_business(published)
            features = service.content_features(variant, 0, schedule, account)
            features["featureAvailableAt"] = (published - timedelta(seconds=1)).isoformat()
            service.capture_publication(db, schedule, features)
            task = service.request_collection(db, schedule, window=86400)
            db.commit()

            async def read(*args):
                return MetricReadResult(
                    "SUCCEEDED",
                    counts={"likes": 0, "replies": 2, "reposts": 3},
                    published_at=published,
                )

            monkeypatch.setattr(service, "_read", read)
            await service.collect_task(db, task.id)
            db.expire_all()
            observation = db.scalar(
                select(EngagementObservation).where(EngagementObservation.task_id == task.id)
            )
            assert observation.published_at == published and observation.observed_at == observed
            assert observation.age_seconds == 86409
            rows, _ = audit_dataset(db, platform="BLUESKY")
            assert len(rows) == 1 and rows[0]["interactions"] == 5
        finally:
            db.rollback()
            intents = db.scalars(
                select(TaskDispatch).where(TaskDispatch.task_type == service.TASK_TYPE_METRIC)
            ).all()
            for row in intents:
                db.delete(row)
            db.delete(schedule)
            db.flush()
            db.delete(variant)
            db.flush()
            db.delete(account)
            db.commit()
