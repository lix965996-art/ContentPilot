import io
import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import SQLAlchemyError

from app.api.endpoints import schedules as schedules_endpoint
from app.core.config import settings
from app.db.session import SessionLocal, engine
from app.models.business import (
    ContentArticle,
    ContentVariant,
    EngagementHistory,
    PublishSchedule,
    TaskDispatch,
)
from app.scheduler import dispatch as dispatcher
from app.scheduler import runtime

pytestmark = pytest.mark.mysql_integration


def _require_mysql() -> None:
    if engine.dialect.name != "mysql":
        pytest.skip("set CONTENTPILOT_TEST_MYSQL_URL to a disposable MySQL database")


def _xhs_variant() -> tuple[int, int]:
    with SessionLocal() as db:
        article = db.scalar(select(ContentArticle).limit(1))
        assert article is not None
        variant = db.scalar(
            select(ContentVariant).where(
                ContentVariant.article_id == article.id,
                ContentVariant.platform == "XIAOHONGSHU",
            )
        )
        assert variant is not None
        return article.id, variant.id


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_mysql_schedule_dispatch_reschedule_cancel_and_cas(client, login_as) -> None:
    _require_mysql()
    auth = _headers(login_as("operator", "Operator@123456")["access_token"])
    article_id, variant_id = _xhs_variant()
    key = f"mysql-integration-{uuid.uuid4().hex}"
    first_time = (datetime.now() + timedelta(days=2)).replace(microsecond=0)
    payload = {
        "article_id": article_id,
        "variant_id": variant_id,
        "platform": "XIAOHONGSHU",
        "publish_mode": "MANUAL_CONFIRM",
        "scheduled_at": first_time.isoformat(),
        "idempotency_key": key,
    }

    first = client.post("/api/schedules", headers=auth, json=payload)
    second = client.post("/api/schedules", headers=auth, json=payload)
    assert first.status_code == second.status_code == 200
    schedule_id = first.json()["data"]["id"]
    assert second.json()["data"]["id"] == schedule_id

    with SessionLocal() as db:
        schedule = db.get(PublishSchedule, schedule_id)
        assert schedule is not None
        assert (schedule.publish_package_json or {}).get("scheduleRevision")
        dispatch = db.scalar(select(TaskDispatch).where(TaskDispatch.task_id == str(schedule_id)))
        assert dispatch is not None
        assert dispatch.status == "PENDING"
        assert dispatch.run_at == schedule.scheduled_at

    next_time = (first_time + timedelta(days=1)).replace(microsecond=0)
    updated = client.put(
        f"/api/schedules/{schedule_id}",
        headers=auth,
        json={"scheduled_at": next_time.isoformat(), "time_source": "CUSTOM"},
    )
    assert updated.status_code == 200, updated.text
    with SessionLocal() as db:
        schedule = db.get(PublishSchedule, schedule_id)
        dispatch = db.scalar(select(TaskDispatch).where(TaskDispatch.task_id == str(schedule_id)))
        assert schedule.scheduled_at == next_time
        assert dispatch.run_at == next_time
        assert dispatch.status == "PENDING"

        # CAS: another writer changes retry_count behind the loaded object; the
        # stale observed state must not overwrite it.
        db.execute(
            update(PublishSchedule)
            .where(PublishSchedule.id == schedule_id)
            .values(retry_count=PublishSchedule.retry_count + 1)
            .execution_options(synchronize_session=False)
        )
        db.commit()
        assert runtime._mark_recovery(db, schedule, "EXPIRED", "stale CAS") is False
        db.commit()

    cancelled = client.post(f"/api/schedules/{schedule_id}/cancel", headers=auth)
    assert cancelled.status_code == 200, cancelled.text
    with SessionLocal() as db:
        dispatch = db.scalar(select(TaskDispatch).where(TaskDispatch.task_id == str(schedule_id)))
        assert dispatch.status == "CANCELLED"


def test_mysql_history_import_persists_rows(client, login_as) -> None:
    _require_mysql()
    auth = _headers(login_as("operator", "Operator@123456")["access_token"])
    account = f"mysql-import-{uuid.uuid4().hex[:10]}"
    published = (datetime.now() - timedelta(days=1)).replace(second=0, microsecond=0)
    payload = (
        "platform,account_id,content_type,publish_time,views,impressions,"
        "likes,comments,shares,favorites,followers,source_type\n"
        f"WEIBO,{account},KNOWLEDGE,{published:%Y-%m-%d %H:%M},"
        "20000,22000,900,180,140,260,50000,ACCOUNT_HISTORY\n"
    ).encode()

    preview = client.post(
        "/api/activity/history/preview",
        headers=auth,
        files={"file": ("history.csv", io.BytesIO(payload), "text/csv")},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["data"]["validRows"] == 1

    imported = client.post(
        "/api/activity/history/import",
        headers=auth,
        files={"file": ("history.csv", io.BytesIO(payload), "text/csv")},
        data={"default_source_type": "ACCOUNT_HISTORY"},
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["data"]["successCount"] == 1
    with SessionLocal() as db:
        row = db.scalar(select(EngagementHistory).where(EngagementHistory.account_ref == account))
        assert row is not None
        assert row.publish_time == published


def test_mysql_dispatch_failure_then_reschedule_succeeds(client, login_as, monkeypatch) -> None:
    _require_mysql()
    auth = _headers(login_as("operator", "Operator@123456")["access_token"])
    article_id, variant_id = _xhs_variant()
    key = f"mysql-dispatch-{uuid.uuid4().hex}"
    first_time = (datetime.now() + timedelta(days=10)).replace(microsecond=0)
    created = client.post(
        "/api/schedules",
        headers=auth,
        json={
            "article_id": article_id,
            "variant_id": variant_id,
            "platform": "XIAOHONGSHU",
            "publish_mode": "MANUAL_CONFIRM",
            "scheduled_at": first_time.isoformat(),
            "idempotency_key": key,
        },
    )
    assert created.status_code == 200, created.text
    schedule_id = created.json()["data"]["id"]
    with SessionLocal() as db:
        dispatch = db.scalar(select(TaskDispatch).where(TaskDispatch.task_id == str(schedule_id)))
        dispatch.attempts = settings.dispatch_max_attempts - 1
        db.commit()

    monkeypatch.setattr(dispatcher, "SessionLocal", SessionLocal)
    monkeypatch.setattr(
        runtime,
        "add_schedule_job",
        Mock(side_effect=RuntimeError("scheduler down")),
    )
    dispatcher.dispatch_pending()
    with SessionLocal() as db:
        assert db.get(PublishSchedule, schedule_id).status == "FAILED"
        dispatch = db.scalar(select(TaskDispatch).where(TaskDispatch.task_id == str(schedule_id)))
        assert dispatch.status == "FAILED"

    added = Mock()
    monkeypatch.setattr(schedules_endpoint, "add_schedule_job", added)
    new_time = first_time + timedelta(days=1)
    rescheduled = client.put(
        f"/api/schedules/{schedule_id}",
        headers=auth,
        json={"scheduled_at": new_time.isoformat(), "time_source": "CUSTOM"},
    )
    assert rescheduled.status_code == 200, rescheduled.text
    monkeypatch.setattr(runtime, "add_schedule_job", added)
    dispatcher.dispatch_pending()

    schedule_calls = [call for call in added.call_args_list if call.args[0] == schedule_id]
    assert len(schedule_calls) == 2
    assert all(call.args[1] == new_time for call in schedule_calls)
    with SessionLocal() as db:
        schedule = db.get(PublishSchedule, schedule_id)
        assert schedule.status == "PENDING"
        assert schedule.scheduled_at == new_time
        dispatch = db.scalar(select(TaskDispatch).where(TaskDispatch.task_id == str(schedule_id)))
        assert dispatch.status == "DONE"
        assert dispatch.run_at == new_time


def test_mysql_conflicting_schedule_does_not_create_a_second_dispatch(client, login_as) -> None:
    _require_mysql()
    auth = _headers(login_as("operator", "Operator@123456")["access_token"])
    article_id, variant_id = _xhs_variant()
    at = (datetime.now() + timedelta(days=4)).replace(microsecond=0)
    base = {
        "article_id": article_id,
        "variant_id": variant_id,
        "platform": "XIAOHONGSHU",
        "publish_mode": "MANUAL_CONFIRM",
        "scheduled_at": at.isoformat(),
    }

    first = client.post(
        "/api/schedules",
        headers=auth,
        json={**base, "idempotency_key": f"mysql-conflict-a-{uuid.uuid4().hex}"},
    )
    second = client.post(
        "/api/schedules",
        headers=auth,
        json={**base, "idempotency_key": f"mysql-conflict-b-{uuid.uuid4().hex}"},
    )

    assert first.status_code == 200
    assert second.status_code == 409
    with SessionLocal() as db:
        rows = db.scalars(
            select(PublishSchedule).where(
                PublishSchedule.platform == "XIAOHONGSHU",
                PublishSchedule.scheduled_at == at,
            )
        ).all()
        assert len(rows) == 1
        dispatches = db.scalars(
            select(TaskDispatch).where(TaskDispatch.task_id == str(rows[0].id))
        ).all()
        assert len(dispatches) == 1


def test_mysql_connection_loss_rolls_back_pending_write() -> None:
    """A killed connection must not leave a partially committed business row."""
    _require_mysql()
    table = f"fault_probe_{uuid.uuid4().hex[:12]}"
    with engine.begin() as conn:
        conn.execute(text(f"CREATE TABLE {table} (id INT PRIMARY KEY, note VARCHAR(20))"))

    session = SessionLocal()
    try:
        session.execute(text(f"INSERT INTO {table} (id, note) VALUES (1, 'pending')"))
        connection_id = session.execute(text("SELECT CONNECTION_ID()")).scalar_one()
        with engine.connect() as killer:
            killer.execute(text(f"KILL CONNECTION {int(connection_id)}"))
        with pytest.raises(SQLAlchemyError):
            session.commit()
    finally:
        try:
            session.rollback()
        except SQLAlchemyError:
            pass
        session.close()

    try:
        with SessionLocal() as verify:
            remaining = verify.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
        assert remaining == 0
    finally:
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
