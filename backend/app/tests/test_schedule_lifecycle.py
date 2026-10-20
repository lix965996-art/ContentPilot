"""Real isolated sessions and job callbacks; all platform writes are mocked."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event, get_ident
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.endpoints import schedules
from app.core.exceptions import AppException
from app.db import session as db_session
from app.db.base import Base
from app.models.business import PublishLog, PublishSchedule
from app.publishers.base import PublishResult
from app.scheduler import runtime
from app.schemas.business import ScheduleUpdate
from app.schemas.platform_account import ManualConfirmRequest
from app.services import publish_service
from app.services.activity_service import business_now
from app.tests.test_publish_safety import _task


class IsolatedScheduler:
    running = False

    def __init__(self):
        self.jobs = {}
        self.queued = []

    def add_job(self, function, trigger, **kwargs):
        job = SimpleNamespace(id=kwargs["id"], args=kwargs["args"], function=function)
        self.jobs[job.id] = job
        self.queued.append(job)

    def get_jobs(self):
        return list(self.jobs.values())

    def remove_job(self, job_id):
        self.jobs.pop(job_id)

    def start(self):
        self.running = True


@pytest.fixture
def lifecycle(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{(tmp_path / 'lifecycle.db').as_posix()}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    _task(sessions, "WEIBO")
    scheduler = IsolatedScheduler()
    monkeypatch.setattr(runtime, "scheduler", scheduler)
    monkeypatch.setattr(runtime, "SessionLocal", sessions)
    monkeypatch.setattr(db_session, "SessionLocal", sessions)
    monkeypatch.setattr(schedules, "record_audit", lambda *_args: None)
    writes = []

    async def no_network(*_args, **_kwargs):
        pytest.fail("Lifecycle regressions must never reach the network")

    async def publish(request):
        writes.append(request)
        return PublishResult(
            True, "WEIBO", "REAL_API", "PUBLISHED", f"stub-{len(writes)}", "https://example.test/p"
        )

    publisher = SimpleNamespace(publish=publish)
    monkeypatch.setattr(httpx.AsyncClient, "request", no_network)
    monkeypatch.setattr(publish_service, "resolve_publisher", lambda *_args: publisher)
    yield SimpleNamespace(
        engine=engine,
        sessions=sessions,
        scheduler=scheduler,
        publisher=publisher,
        publish=publish,
        writes=writes,
        user=SimpleNamespace(id=1),
        request=Request({"type": "http", "method": "POST", "path": "/", "headers": []}),
    )
    engine.dispose()


def _change(env, action, db):
    if action == "update":
        return schedules.update_schedule(
            1,
            ScheduleUpdate(scheduled_at=business_now() + timedelta(days=2)),
            env.request,
            db,
            env.user,
        )
    function = schedules.cancel_schedule if action == "cancel" else schedules.delete_schedule
    return function(1, env.request, db, env.user)


@pytest.mark.parametrize("action", ["cancel", "update", "delete"])
@pytest.mark.parametrize("publisher_finished", [False, True])
def test_management_cannot_overwrite_a_concurrent_publisher(lifecycle, action, publisher_finished):
    env = lifecycle
    if action == "update":
        with env.sessions() as db:
            db.get(PublishSchedule, 1).status = "FAILED"
            db.commit()
    operator_waiting, operator_release = Event(), Event()
    publisher_entered, publisher_release = Event(), Event()
    operator_thread = []

    async def blocked_publish(request):
        publisher_entered.set()
        assert await asyncio.to_thread(publisher_release.wait, 10)
        return await env.publish(request)

    env.publisher.publish = blocked_publish

    def before_write(_conn, _cursor, statement, _params, _context, _many):
        if (
            operator_thread
            and get_ident() == operator_thread[0]
            and statement.startswith("UPDATE publish_schedule SET")
        ):
            operator_waiting.set()
            assert operator_release.wait(10)

    event.listen(env.engine, "before_cursor_execute", before_write)

    def manage():
        operator_thread.append(get_ident())
        with env.sessions() as db:
            with pytest.raises(AppException) as failed:
                _change(env, action, db)
            assert failed.value.code == 40903

    def execute():
        with env.sessions() as db:
            return asyncio.run(publish_service.execute_publish(db, 1)).status

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            operator = executor.submit(manage)
            assert operator_waiting.wait(10)
            worker = executor.submit(execute)
            assert publisher_entered.wait(10)
            if publisher_finished:
                publisher_release.set()
                assert worker.result(timeout=10) == "PUBLISHED"
            operator_release.set()
            operator.result(timeout=10)
            publisher_release.set()
            assert worker.result(timeout=10) == "PUBLISHED"
    finally:
        operator_release.set()
        publisher_release.set()
        event.remove(env.engine, "before_cursor_execute", before_write)
    with env.sessions() as db:
        row = db.get(PublishSchedule, 1)
        assert row.status == "PUBLISHED" and row.external_id == "stub-1"
        assert len(db.scalars(select(PublishLog)).all()) == 1
    assert len(env.writes) == 1 and not env.scheduler.queued


def _queue_due_job(env):
    with env.sessions() as db:
        row = db.get(PublishSchedule, 1)
        row.scheduled_at = business_now() - timedelta(seconds=2)
        db.commit()
        runtime.add_schedule_job(row.id, row.scheduled_at, publish_service.schedule_state(row))
    return env.scheduler.queued[-1]


@pytest.mark.parametrize("same_time", [False, True])
def test_dequeued_job_cannot_publish_after_rescheduling(lifecycle, monkeypatch, same_time):
    env = lifecycle
    old_job = _queue_due_job(env)
    with env.sessions() as db:
        payload = (
            ScheduleUpdate(time_source="RECOMMENDED")
            if same_time
            else ScheduleUpdate(scheduled_at=business_now() + timedelta(days=2))
        )
        result = schedules.update_schedule(1, payload, env.request, db, env.user)
        new_time = db.get(PublishSchedule, 1).scheduled_at
    assert result["code"] == 0
    current_job = env.scheduler.queued[-1]
    assert current_job.id != old_job.id
    # A late registration of the old snapshot cannot replace the new timer.
    runtime.add_schedule_job(1, old_job.args[1].run_at, old_job.args[1].state)
    assert current_job.id in env.scheduler.jobs
    old_job.function(*old_job.args)
    with env.sessions() as db:
        assert db.get(PublishSchedule, 1).status == "PENDING"
    assert not env.writes
    monkeypatch.setattr(publish_service, "business_now", lambda: new_time + timedelta(seconds=1))
    current_job.function(*current_job.args)
    assert len(env.writes) == 1


def test_immediate_publish_still_allows_a_future_schedule(lifecycle):
    env = lifecycle
    with env.sessions() as db:
        assert db.get(PublishSchedule, 1).scheduled_at > business_now()
        result = asyncio.run(schedules.publish_now(1, env.request, db, env.user))
    assert result["code"] == 0 and result["data"]["status"] == "PUBLISHED"
    assert len(env.writes) == 1


def test_retry_job_binds_the_failed_attempt_and_uses_its_own_run_time(lifecycle, monkeypatch):
    env = lifecycle
    initial_job = _queue_due_job(env)
    attempts = []

    async def publish(request):
        attempts.append(request)
        if len(attempts) == 1:
            return PublishResult(False, "WEIBO", "REAL_API", "FAILED", retryable=True)
        return await env.publish(request)

    env.publisher.publish = publish
    initial_job.function(*initial_job.args)
    retry_job = env.scheduler.queued[-1]
    assert retry_job.args[1].state.status == "FAILED"
    assert retry_job.args[1].state.retry_count == 1
    assert retry_job.args[1].state.scheduled_at == initial_job.args[1].state.scheduled_at
    assert retry_job.args[1].run_at > business_now()
    # The obsolete initial job must neither write nor queue another retry.
    initial_job.function(*initial_job.args)
    assert len(attempts) == 1 and len(env.scheduler.queued) == 2
    retry_job.function(*retry_job.args)
    assert len(attempts) == 1
    monkeypatch.setattr(
        publish_service, "business_now", lambda: retry_job.args[1].run_at + timedelta(seconds=1)
    )
    retry_job.function(*retry_job.args)
    assert len(attempts) == 2 and len(env.writes) == 1


@pytest.mark.parametrize("same_time", [False, True])
def test_old_misfire_does_not_expire_the_current_schedule(lifecycle, same_time):
    env = lifecycle
    old_job = _queue_due_job(env)
    with env.sessions() as db:
        payload = (
            ScheduleUpdate(time_source="RECOMMENDED")
            if same_time
            else ScheduleUpdate(scheduled_at=business_now() + timedelta(days=2))
        )
        schedules.update_schedule(1, payload, env.request, db, env.user)
    runtime._handle_missed_job(
        SimpleNamespace(job_id=old_job.id, scheduled_run_time=old_job.args[1].run_at)
    )
    with env.sessions() as db:
        assert db.get(PublishSchedule, 1).status == "PENDING"
        assert not db.scalars(select(PublishLog)).all()


def test_recovery_cannot_overwrite_a_concurrent_reschedule(lifecycle):
    env = lifecycle
    _queue_due_job(env)
    with env.sessions() as recovery, env.sessions() as operator:
        stale = recovery.get(PublishSchedule, 1)
        schedules.update_schedule(
            1,
            ScheduleUpdate(scheduled_at=business_now() + timedelta(days=2)),
            env.request,
            operator,
            env.user,
        )
        assert runtime._mark_recovery(recovery, stale, "EXPIRED", "obsolete recovery") is False
        recovery.commit()
    with env.sessions() as db:
        assert db.get(PublishSchedule, 1).status == "PENDING"
        assert not db.scalars(select(PublishLog)).all()


def test_manual_confirmation_cannot_override_a_concurrent_cancel(lifecycle, monkeypatch):
    env = lifecycle
    with env.sessions() as db:
        db.get(PublishSchedule, 1).status = "WAITING_MANUAL_CONFIRM"
        db.commit()
    original_change = schedules._change_schedule

    def cancel_before_confirmation(db, row, observed, values):
        with env.sessions() as operator:
            monkeypatch.setattr(schedules, "_change_schedule", original_change)
            schedules.cancel_schedule(1, env.request, operator, env.user)
        original_change(db, row, observed, values)

    monkeypatch.setattr(schedules, "_change_schedule", cancel_before_confirmation)
    with env.sessions() as db:
        with pytest.raises(AppException) as failed:
            asyncio.run(
                schedules.manual_confirm(
                    1,
                    ManualConfirmRequest(published_url="https://example.test/published"),
                    env.request,
                    db,
                    env.user,
                )
            )
        assert failed.value.code == 40903
    with env.sessions() as db:
        assert db.get(PublishSchedule, 1).status == "CANCELLED"
        assert not db.scalars(select(PublishLog)).all()
