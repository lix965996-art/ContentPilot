from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.exceptions import AppException
from app.db import session as db_session
from app.db.base import Base
from app.models.business import (
    ContentArticle,
    ContentVariant,
    GenerationTask,
    PublishLog,
    PublishSchedule,
    TaskDispatch,
)
from app.publishers.base import PublishResult
from app.scheduler import dispatch as dispatcher
from app.scheduler import runtime
from app.services import publish_service, task_dispatch_service
from app.services.review_fingerprint import variant_fingerprint
from app.services.task_dispatch_service import TASK_TYPE_GENERATION


@pytest.fixture()
def schedule_storage(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(runtime, "SessionLocal", sessions)
    fake_scheduler = Mock(running=False)
    monkeypatch.setattr(runtime, "scheduler", fake_scheduler)
    with sessions() as db:
        for schedule_id, status, delta in [
            (1, "PENDING", -1),
            (2, "PENDING", 1),
            (3, "PUBLISHING", -1),
        ]:
            db.add(
                PublishSchedule(
                    id=schedule_id,
                    article_id=1,
                    variant_id=1,
                    platform="XIAOHONGSHU",
                    publish_mode="MANUAL_CONFIRM",
                    created_by=1,
                    status=status,
                    scheduled_at=runtime.local_now() + timedelta(days=delta),
                    idempotency_key=f"isolated-recovery-{schedule_id}",
                )
            )
        db.commit()
    yield sessions, fake_scheduler
    engine.dispose()


def test_restart_expires_overdue_and_marks_uncertain_attempts(schedule_storage):
    sessions, scheduler = schedule_storage
    runtime.start_scheduler()
    with sessions() as db:
        assert db.get(PublishSchedule, 1).status == "EXPIRED"
        assert db.get(PublishSchedule, 2).status == "PENDING"
        assert db.get(PublishSchedule, 3).status == "INTERRUPTED"
        assert len(db.scalars(select(PublishLog)).all()) == 2
    scheduler.add_job.assert_called_once()
    args = scheduler.add_job.call_args.kwargs["args"]
    assert args[0] == 2 and args[1].state.status == "PENDING"
    assert str(scheduler.add_job.call_args.args[1].run_date.tzinfo) == "Asia/Shanghai"
    scheduler.start.assert_called_once()


def test_runtime_misfire_becomes_visible_without_republishing(schedule_storage):
    sessions, scheduler = schedule_storage
    with sessions() as db:
        row = db.get(PublishSchedule, 2)
        job = publish_service.ScheduleJob(publish_service.schedule_state(row), row.scheduled_at)
        missed = SimpleNamespace(job_id=runtime._job_id(row.id, job), scheduled_run_time=job.run_at)
    runtime._handle_missed_job(missed)
    runtime._handle_missed_job(missed)
    with sessions() as db:
        assert db.get(PublishSchedule, 2).status == "EXPIRED"
        assert len(db.scalars(select(PublishLog)).all()) == 1
    scheduler.add_job.assert_not_called()


def test_should_retry_requires_explicit_retryable_marker():
    def schedule(retryable, retry_count=1, max_retry_count=3):
        return SimpleNamespace(
            status="FAILED",
            retry_count=retry_count,
            max_retry_count=max_retry_count,
            publish_package_json={"lastFailureRetryable": retryable},
        )

    assert publish_service._should_retry(schedule(True)) is True
    assert publish_service._should_retry(schedule(False)) is False
    assert publish_service._should_retry(schedule(True, retry_count=4)) is False
    assert publish_service._should_retry(None) is False


def test_apply_failure_preserves_publish_context_and_retryable_flag():
    schedule = SimpleNamespace(
        platform="WEIBO",
        publish_mode="REAL_API",
        publish_package_json={"operationIp": "203.0.113.10"},
        status="PENDING",
        published_url=None,
        external_id=None,
        result_mode=None,
        actual_publish_at=None,
        retry_count=0,
        error_message=None,
    )
    result = PublishResult(
        False, "WEIBO", "REAL_API", "FAILED", retryable=False, error_message="网络错误"
    )
    publish_service._apply_result(schedule, result)

    assert schedule.status == "FAILED"
    assert schedule.publish_package_json["operationIp"] == "203.0.113.10"
    assert schedule.publish_package_json["lastFailureRetryable"] is False
    assert schedule.retry_count == 1
    assert schedule.error_message == "网络错误"


def test_apply_success_clears_retryable_marker_and_stamps_business_time():
    schedule = SimpleNamespace(
        platform="WEIBO",
        publish_mode="REAL_API",
        publish_package_json={
            "operationIp": "203.0.113.10",
            "lastFailureRetryable": True,
        },
        status="PUBLISHING",
        published_url=None,
        external_id=None,
        result_mode=None,
        actual_publish_at=None,
        retry_count=1,
        error_message="旧错误",
    )
    result = PublishResult(
        True,
        "WEIBO",
        "REAL_API",
        "PUBLISHED",
        external_id="42",
        published_url="https://weibo.example/42",
    )
    publish_service._apply_result(schedule, result)

    assert schedule.status == "PUBLISHED"
    assert schedule.published_url == "https://weibo.example/42"
    assert schedule.actual_publish_at is not None
    assert "lastFailureRetryable" not in schedule.publish_package_json
    assert schedule.publish_package_json["operationIp"] == "203.0.113.10"
    assert schedule.error_message is None


@pytest.mark.asyncio
async def test_uncertain_attempt_cannot_be_published_until_rescheduled(schedule_storage):
    sessions, _ = schedule_storage
    with sessions() as db:
        row = db.get(PublishSchedule, 3)
        row.status = "INTERRUPTED"
        db.commit()
        with pytest.raises(AppException, match="重新排期"):
            await publish_service.execute_publish(db, 3)
        assert row.status == "INTERRUPTED"


def test_precondition_failure_does_not_queue_unlimited_retry(schedule_storage, monkeypatch):
    sessions, _ = schedule_storage
    with sessions() as db:
        db.add(
            ContentArticle(
                id=1, title="测试原文", source_text="仅用于无账号发布检查的测试原文。", created_by=1
            )
        )
        db.add(
            ContentVariant(
                id=1,
                article_id=1,
                platform="WEIBO",
                title="测试",
                content_text="测试正文",
                review_status="APPROVED",
            )
        )
        db.flush()
        variant = db.get(ContentVariant, 1)
        variant.review_fingerprint = variant_fingerprint(variant)
        row = db.get(PublishSchedule, 2)
        row.platform = "WEIBO"
        row.publish_mode = "REAL_API"
        db.commit()
    monkeypatch.setattr(db_session, "SessionLocal", sessions)
    queue = Mock()
    monkeypatch.setattr(runtime, "add_schedule_job", queue)
    publish_service.execute_publish_sync(2)
    queue.assert_not_called()
    with sessions() as db:
        row = db.get(PublishSchedule, 2)
        assert row.status == "FAILED" and row.retry_count == 1
        assert "选择平台账号" in row.error_message
        assert len(db.scalars(select(PublishLog)).all()) == 1


def test_dispatch_intents_backfill_and_rearm_pending_tasks(schedule_storage):
    sessions, _ = schedule_storage
    with sessions() as db:
        assert task_dispatch_service.ensure_dispatch_intents(db) == 2
        db.commit()
        rows = {row.task_id: row for row in db.scalars(select(TaskDispatch)).all()}
        assert rows["1"].status == "PENDING"
        assert rows["2"].status == "PENDING"

        rows["2"].status = "DONE"
        db.commit()
        assert task_dispatch_service.ensure_dispatch_intents(db) == 1
        db.commit()
        row = db.scalar(select(TaskDispatch).where(TaskDispatch.task_id == "2"))
        assert row.status == "PENDING"


def test_dispatcher_reinstalls_schedule_job_and_expires_overdue(schedule_storage, monkeypatch):
    sessions, _ = schedule_storage
    with sessions() as db:
        task_dispatch_service.ensure_dispatch_intents(db)
        db.commit()
    monkeypatch.setattr(dispatcher, "SessionLocal", sessions)
    added = Mock()
    monkeypatch.setattr(runtime, "add_schedule_job", added)

    dispatcher.dispatch_pending()

    added.assert_called_once()
    assert added.call_args.args[0] == 2
    with sessions() as db:
        rows = {row.task_id: row for row in db.scalars(select(TaskDispatch)).all()}
        assert rows["2"].status == "DONE"
        assert db.get(PublishSchedule, 1).status == "EXPIRED"


def test_dispatcher_submits_pending_generation_once(schedule_storage, monkeypatch):
    sessions, _ = schedule_storage
    with sessions() as db:
        db.add(
            GenerationTask(
                id="gen-dispatch-1",
                article_id=1,
                status="PENDING",
                platforms_json=["WEIBO"],
                options_json={},
            )
        )
        task_dispatch_service.upsert_dispatch(
            db,
            task_type=TASK_TYPE_GENERATION,
            task_id="gen-dispatch-1",
            revision="gen-dispatch-1",
            run_at=runtime.local_now(),
        )
        db.commit()
    monkeypatch.setattr(dispatcher, "SessionLocal", sessions)
    monkeypatch.setattr(runtime, "add_schedule_job", Mock())
    submit = Mock()
    monkeypatch.setattr(dispatcher._generation_executor, "submit", submit)

    dispatcher.dispatch_pending()

    submit.assert_called_once()
    with sessions() as db:
        row = db.scalar(select(TaskDispatch).where(TaskDispatch.task_id == "gen-dispatch-1"))
        assert row.status == "DONE"


def test_dispatcher_exhaustion_marks_schedule_failed_with_recovery_entry(
    schedule_storage, monkeypatch
):
    sessions, _ = schedule_storage
    with sessions() as db:
        task_dispatch_service.ensure_dispatch_intents(db)
        db.commit()
        row = db.scalar(select(TaskDispatch).where(TaskDispatch.task_id == "2"))
        row.attempts = settings.dispatch_max_attempts - 1
        db.commit()
    monkeypatch.setattr(dispatcher, "SessionLocal", sessions)
    monkeypatch.setattr(
        runtime,
        "add_schedule_job",
        Mock(side_effect=RuntimeError("scheduler unavailable")),
    )

    dispatcher.dispatch_pending()

    with sessions() as db:
        schedule = db.get(PublishSchedule, 2)
        assert schedule.status == "FAILED"
        assert "排期派发失败" in (schedule.error_message or "")
        dispatch = db.scalar(select(TaskDispatch).where(TaskDispatch.task_id == "2"))
        assert dispatch.status == "FAILED"
        assert dispatch.attempts == settings.dispatch_max_attempts
        logs = db.scalars(select(PublishLog).where(PublishLog.schedule_id == 2)).all()
        assert any(log.step == "RECOVERY" and log.status == "FAILED" for log in logs)


def test_dispatcher_exhaustion_marks_generation_failed(schedule_storage, monkeypatch):
    sessions, _ = schedule_storage
    with sessions() as db:
        db.add(
            GenerationTask(
                id="gen-fail-1",
                article_id=1,
                status="PENDING",
                platforms_json=["WEIBO"],
                platform_status_json={"WEIBO": {"status": "PENDING", "progress": 0}},
                options_json={},
            )
        )
        task_dispatch_service.upsert_dispatch(
            db,
            task_type=TASK_TYPE_GENERATION,
            task_id="gen-fail-1",
            revision="gen-fail-1",
            run_at=runtime.local_now(),
        )
        dispatch = db.scalar(select(TaskDispatch).where(TaskDispatch.task_id == "gen-fail-1"))
        dispatch.attempts = settings.dispatch_max_attempts - 1
        db.commit()
    monkeypatch.setattr(dispatcher, "SessionLocal", sessions)
    monkeypatch.setattr(runtime, "add_schedule_job", Mock())
    monkeypatch.setattr(
        dispatcher._generation_executor,
        "submit",
        Mock(side_effect=RuntimeError("executor unavailable")),
    )

    dispatcher.dispatch_pending()

    with sessions() as db:
        task = db.get(GenerationTask, "gen-fail-1")
        assert task.status == "FAILED"
        assert task.progress == 100
        assert "派发失败" in (task.error_message or "")
        assert (task.platform_status_json or {})["WEIBO"]["status"] == "FAILED"
        dispatch = db.scalar(select(TaskDispatch).where(TaskDispatch.task_id == "gen-fail-1"))
        assert dispatch.status == "FAILED"


def test_uncertain_schedule_is_not_redispatched(schedule_storage, monkeypatch):
    sessions, _ = schedule_storage
    with sessions() as db:
        row = db.get(PublishSchedule, 2)
        row.status = "PUBLISH_UNCERTAIN"
        task_dispatch_service.upsert_dispatch(
            db,
            task_type="PUBLISH_SCHEDULE",
            task_id="2",
            revision="uncertain",
            run_at=runtime.local_now(),
        )
        db.commit()
    monkeypatch.setattr(dispatcher, "SessionLocal", sessions)
    added = Mock()
    monkeypatch.setattr(runtime, "add_schedule_job", added)

    dispatcher.dispatch_pending()

    added.assert_not_called()
    with sessions() as db:
        dispatch = db.scalar(select(TaskDispatch).where(TaskDispatch.task_id == "2"))
        assert dispatch.status == "DONE"


def test_repeated_dispatcher_runs_do_not_duplicate_a_schedule_job(schedule_storage, monkeypatch):
    sessions, _ = schedule_storage
    with sessions() as db:
        task_dispatch_service.ensure_dispatch_intents(db)
        db.commit()
    monkeypatch.setattr(dispatcher, "SessionLocal", sessions)
    added = Mock()
    monkeypatch.setattr(runtime, "add_schedule_job", added)

    dispatcher.dispatch_pending()
    dispatcher.dispatch_pending()

    # Schedule 2 is dispatched once; schedule 1 is expired. A completed intent
    # is not scanned again.
    assert added.call_count == 1
    assert added.call_args.args[0] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["REAL_API", "DRAFT_ONLY"])
async def test_wechat_uses_the_requested_publisher(mode, monkeypatch):
    public = Mock()
    draft = Mock()
    from unittest.mock import AsyncMock

    public.return_value.publish = AsyncMock(return_value="published")
    draft.return_value.publish = AsyncMock(return_value="draft")
    monkeypatch.setattr(publish_service, "WechatPublishPublisher", public)
    monkeypatch.setattr(publish_service, "WechatDraftPublisher", draft)
    result = await publish_service._publish_wechat_api(
        None,
        SimpleNamespace(
            id=1, platform="WECHAT_OFFICIAL", publish_mode=mode, idempotency_key="test"
        ),
        None,
        SimpleNamespace(title="测试", content_text="测试正文", content_html="", hashtags_json=[]),
        [],
    )
    assert result == ("published" if mode == "REAL_API" else "draft")
    assert public.call_count == int(mode == "REAL_API")
    assert draft.call_count == int(mode == "DRAFT_ONLY")
