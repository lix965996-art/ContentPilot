"""Isolated transport and stale-session regressions; never publish to live accounts."""

import asyncio
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timedelta
from threading import Barrier, Event, Lock
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.credentials import encrypt_json, encrypt_secret
from app.core.exceptions import AppException
from app.db.base import Base
from app.models.business import (
    ContentArticle,
    ContentVariant,
    PlatformAccount,
    PublishLog,
    PublishSchedule,
)
from app.publishers import official
from app.publishers.base import PublishResult
from app.publishers.official import WECHAT_ATTEMPT_FIELD, WechatPublishPublisher, WeiboPublisher
from app.services import publish_service
from app.services.review_fingerprint import variant_fingerprint


@pytest.fixture()
def isolated_publish_db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{(tmp_path / 'publish-safety.db').as_posix()}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)

    async def no_network(*_args, **_kwargs):
        pytest.fail("Publish safety regressions must never reach a network transport")

    monkeypatch.setattr(httpx.AsyncClient, "request", no_network)
    yield sessions
    engine.dispose()


def _task(sessions, platform="BLUESKY"):
    with sessions() as db:
        account = PlatformAccount(
            id=1,
            user_id=1,
            platform=platform,
            account_name="isolated test account",
            app_id="wx-isolated",
            auth_type="APP_PASSWORD" if platform == "BLUESKY" else "APP_SECRET",
            publish_mode="SUBMIT_PUBLISH" if platform == "WECHAT_OFFICIAL" else "REAL_API",
            status="CONNECTED",
            capabilities_json=["TEXT_PUBLISH", "SUBMIT_PUBLISH", "DRAFT_CREATE"],
            access_token_encrypted=encrypt_secret("isolated-token"),
            token_expires_at=datetime.now() + timedelta(hours=1),
            credentials_encrypted=encrypt_json(
                {
                    "allow_public_publish": True,
                    "allow_submit_publish": True,
                    "default_cover_media_id": "isolated-cover",
                    "operation_ip": "8.8.8.8",
                }
            ),
        )
        db.add(account)
        db.add(
            ContentArticle(
                id=1,
                title="隔离原文",
                source_text="仅用于发布安全回归的隔离原文。",
                created_by=1,
            )
        )
        db.add(
            ContentVariant(
                id=1,
                article_id=1,
                platform=platform,
                title="隔离发布测试",
                content_text="用于验证网络中断、状态刷新和重试边界的测试正文。",
                review_status="APPROVED",
            )
        )
        db.add(
            PublishSchedule(
                id=1,
                article_id=1,
                variant_id=1,
                account_id=account.id,
                platform=platform,
                publish_mode="REAL_API",
                scheduled_at=datetime.now() + timedelta(days=1),
                created_by=1,
                status="PENDING",
                idempotency_key="isolated-publish-task",
                publish_package_json={"operationIp": "8.8.8.8"},
            )
        )
        db.flush()
        variant = db.get(ContentVariant, 1)
        variant.review_fingerprint = variant_fingerprint(variant)
        db.commit()


@pytest.mark.asyncio
async def test_two_preloaded_sessions_publish_only_once(isolated_publish_db, monkeypatch):
    sessions = isolated_publish_db
    _task(sessions)
    calls = []

    async def publish(request):
        calls.append(request)
        return PublishResult(
            True, "BLUESKY", "REAL_API", "PUBLISHED", "at://isolated/post", "https://bsky.test/post"
        )

    publisher = AsyncMock()
    publisher.publish = publish
    monkeypatch.setattr(publish_service, "resolve_publisher", lambda *_args: publisher)
    with sessions() as first, sessions() as second:
        stale = second.get(PublishSchedule, 1)
        assert stale.status == "PENDING" and "blueskyRkey" not in stale.publish_package_json
        completed = await publish_service.execute_publish(first, 1)
        key = completed.publish_package_json["blueskyRkey"]
        # The second Session has retained the original PENDING object in its
        # identity map even though the first committed a completed attempt.
        assert stale.status == "PENDING"
        repeated = await publish_service.execute_publish(second, 1)
        assert repeated is stale and repeated.status == "PUBLISHED"
        assert repeated.publish_package_json["blueskyRkey"] == key
        assert len(calls) == 1 and calls[0]["record_key"] == key
        assert len(second.scalars(select(PublishLog)).all()) == 1


def test_sqlite_simultaneous_workers_atomically_claim_one_publish(isolated_publish_db, monkeypatch):
    sessions = isolated_publish_db
    _task(sessions)
    both_read_pending = Barrier(2)
    publish_started = Event()
    release_publish = Event()
    calls_lock = Lock()
    calls = []

    def claim_together(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("UPDATE publish_schedule SET") and (
            "publish_schedule.retry_count =" in statement
        ):
            both_read_pending.wait(timeout=10)

    async def publish(request):
        with calls_lock:
            calls.append(request["record_key"])
        publish_started.set()
        assert release_publish.wait(timeout=10)
        return PublishResult(True, "BLUESKY", "REAL_API", "PUBLISHED", "one-real-write")

    publisher = AsyncMock()
    publisher.publish = publish
    event.listen(sessions.kw["bind"], "before_cursor_execute", claim_together)
    monkeypatch.setattr(publish_service, "resolve_publisher", lambda *_args: publisher)

    def run_worker():
        with sessions() as db:
            return asyncio.run(publish_service.execute_publish(db, 1))

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run_worker) for _ in range(2)]
        try:
            assert publish_started.wait(timeout=10)
            done, _pending = wait(futures, timeout=10, return_when=FIRST_COMPLETED)
            assert len(done) == 1
            completed = done.pop()
            with pytest.raises(AppException) as error:
                completed.result()
            assert error.value.code == 40901
        finally:
            release_publish.set()
        remaining = next(future for future in futures if future is not completed)
        assert remaining.result(timeout=10).status == "PUBLISHED"
    assert len(calls) == 1
    with sessions() as db:
        row = db.get(PublishSchedule, 1)
        assert row.publish_package_json["blueskyRkey"] == calls[0]
        assert row.status == "PUBLISHED" and len(db.scalars(select(PublishLog)).all()) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("next_failure", ["exception", "none", "account", "content"])
async def test_new_failure_does_not_inherit_rate_limit_retry(
    isolated_publish_db, monkeypatch, next_failure
):
    sessions = isolated_publish_db
    _task(sessions)
    outcomes = [
        PublishResult(False, "BLUESKY", "REAL_API", "FAILED", retryable=True, error_code="429"),
        None,
    ]

    async def publish(_request):
        if len(outcomes) == 1 and next_failure == "exception":
            raise RuntimeError("uncertain transport outcome")
        return outcomes.pop(0)

    publisher = AsyncMock()
    publisher.publish = publish
    monkeypatch.setattr(publish_service, "resolve_publisher", lambda *_args: publisher)
    with sessions() as db:
        failed = await publish_service.execute_publish(db, 1)
        assert publish_service._should_retry(failed)
        key = failed.publish_package_json["blueskyRkey"]
        if next_failure in {"account", "content"}:
            if next_failure == "account":
                db.get(PlatformAccount, 1).status = "NOT_CONFIGURED"
            else:
                db.get(ContentVariant, 1).content_text = ""
            db.commit()
            with pytest.raises(AppException):
                await publish_service.execute_publish(db, 1)
        else:
            await publish_service.execute_publish(db, 1)
        db.refresh(failed)
        assert failed.status == "FAILED" and failed.retry_count == 2
        assert not publish_service._should_retry(failed)
        assert failed.publish_package_json["lastFailureRetryable"] is False
        assert failed.publish_package_json["operationIp"] == "8.8.8.8"
        assert failed.publish_package_json["blueskyRkey"] == key


def _response(url, payload, status=200):
    return httpx.Response(status, json=payload, request=httpx.Request("POST", url))


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", [None, RuntimeError("response lost; 48001 in debug text")])
async def test_wechat_unknown_outcome_cannot_trigger_cli_fallback(
    isolated_publish_db, monkeypatch, outcome
):
    sessions = isolated_publish_db
    _task(sessions, "WECHAT_OFFICIAL")
    monkeypatch.setattr(settings, "wechatsync_cli_enabled", True)
    api = (
        AsyncMock(side_effect=outcome)
        if isinstance(outcome, Exception)
        else AsyncMock(return_value=outcome)
    )
    cli = AsyncMock(side_effect=AssertionError("Unknown official outcome must not use CLI"))
    monkeypatch.setattr(publish_service, "_publish_wechat_api", api)
    monkeypatch.setattr(publish_service, "_publish_wechat_cli", cli)
    with sessions() as db:
        row = db.get(PublishSchedule, 1)
        row.publish_package_json = {"lastFailureRetryable": True}
        db.commit()
        failed = await publish_service.execute_publish(db, 1)
        assert failed.status == "FAILED"
        assert not publish_service._should_retry(failed)
    cli.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("error_code", ["WECHATSYNC_TIMEOUT", "WECHATSYNC_FAILED"])
async def test_wechat_cli_failure_cannot_schedule_automatic_retry(
    isolated_publish_db, monkeypatch, error_code
):
    sessions = isolated_publish_db
    _task(sessions, "WECHAT_OFFICIAL")
    monkeypatch.setattr(settings, "wechatsync_cli_enabled", True)
    api = AsyncMock(
        return_value=PublishResult(
            False, "WECHAT_OFFICIAL", "REAL_API", "FAILED", error_code="48001"
        )
    )
    cli_result = PublishResult(
        False,
        "WECHAT_OFFICIAL",
        "WECHATSYNC_CLI",
        "FAILED",
        error_code=error_code,
        retryable=True,
        error_message="CLI draft outcome unknown",
    )
    cli = AsyncMock(return_value=cli_result)
    monkeypatch.setattr(publish_service, "_publish_wechat_api", api)
    monkeypatch.setattr(publish_service, "_publish_wechat_cli", cli)
    with sessions() as db:
        failed = await publish_service.execute_publish(db, 1)
        assert failed.status == "FAILED"
        assert failed.result_mode == "WECHATSYNC_CLI"
        assert failed.publish_package_json["lastFailureRetryable"] is False
        assert not publish_service._should_retry(failed)
        assert not cli_result.retryable and "核对" in cli_result.suggested_action
    cli.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "invalid_json", "missing_id", "server_error"])
async def test_unknown_wechat_submit_never_creates_or_submits_again(
    isolated_publish_db, monkeypatch, failure
):
    sessions = isolated_publish_db
    _task(sessions, "WECHAT_OFFICIAL")
    calls = []
    monkeypatch.setattr(settings, "wechatsync_cli_enabled", True)
    cli = AsyncMock(side_effect=AssertionError("An uncertain write must not use CLI fallback"))
    monkeypatch.setattr(publish_service, "_publish_wechat_cli", cli)

    async def post(_self, url, **_kwargs):
        endpoint = url.split("/cgi-bin/")[-1]
        calls.append(endpoint)
        # Verify durability using another Session before simulating acceptance.
        with sessions() as observer:
            attempt = observer.get(PublishSchedule, 1).publish_package_json[WECHAT_ATTEMPT_FIELD]
            if endpoint == "draft/add":
                assert attempt["stage"] == "DRAFT_CREATING"
                return _response(url, {"media_id": "original-draft"})
            assert endpoint == "freepublish/submit"
            assert attempt["stage"] == "SUBMITTING" and attempt["draftId"] == "original-draft"
        if failure == "timeout":
            raise httpx.ReadTimeout("accepted before connection was lost")
        if failure == "invalid_json":
            return httpx.Response(200, text="not JSON", request=httpx.Request("POST", url))
        return _response(url, {}, 500 if failure == "server_error" else 200)

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    with sessions() as db:
        failed = await publish_service.execute_publish(db, 1)
        assert failed.status == "FAILED" and not publish_service._should_retry(failed)
        attempt = failed.publish_package_json[WECHAT_ATTEMPT_FIELD]
        assert attempt["stage"] == "SUBMITTING" and attempt["draftId"] == "original-draft"
    # A fresh process/Session must see the persisted submission stage, too.
    with sessions() as db:
        failed = await publish_service.execute_publish(db, 1)
        assert failed.status == "FAILED" and not publish_service._should_retry(failed)
    assert calls == ["draft/add", "freepublish/submit"]
    cli.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_wechat_draft_never_adds_another_draft(isolated_publish_db, monkeypatch):
    sessions = isolated_publish_db
    _task(sessions, "WECHAT_OFFICIAL")
    calls = []

    async def post(_self, url, **_kwargs):
        calls.append(url)
        assert url.endswith("/draft/add")
        raise httpx.ReadTimeout("draft accepted before response was lost")

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    with sessions() as db:
        first = await publish_service.execute_publish(db, 1)
        assert first.publish_package_json[WECHAT_ATTEMPT_FIELD]["stage"] == "DRAFT_CREATING"
        assert not publish_service._should_retry(first)
    with sessions() as db:
        second = await publish_service.execute_publish(db, 1)
        assert second.status == "FAILED" and not publish_service._should_retry(second)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_wechat_explicit_submit_rejection_reuses_and_checks_original_draft(
    isolated_publish_db, monkeypatch
):
    sessions = isolated_publish_db
    _task(sessions, "WECHAT_OFFICIAL")
    calls = []

    async def post(_self, url, **kwargs):
        endpoint = url.split("/cgi-bin/")[-1]
        calls.append(endpoint)
        if endpoint == "draft/add":
            return _response(url, {"media_id": "original-draft"})
        if endpoint == "draft/get":
            assert kwargs["json"] == {"media_id": "original-draft"}
            return _response(url, {"news_item": [{"title": "隔离发布测试"}]})
        assert endpoint == "freepublish/submit"
        assert kwargs["json"] == {"media_id": "original-draft"}
        if calls.count(endpoint) == 1:
            return _response(url, {"errcode": 45009, "errmsg": "rate limited"})
        return _response(url, {"errcode": 0, "publish_id": "confirmed-publish"})

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    with sessions() as db:
        failed = await publish_service.execute_publish(db, 1)
        assert publish_service._should_retry(failed)
        assert failed.publish_package_json[WECHAT_ATTEMPT_FIELD]["stage"] == "SUBMIT_REJECTED"
    with sessions() as db:
        submitted = await publish_service.execute_publish(db, 1)
        assert submitted.status == "PUBLISH_SUBMITTED"
        assert submitted.external_id == "confirmed-publish"
        assert submitted.publish_package_json[WECHAT_ATTEMPT_FIELD]["stage"] == "SUBMITTED"
        assert "lastFailureRetryable" not in submitted.publish_package_json
    assert calls == ["draft/add", "freepublish/submit", "draft/get", "freepublish/submit"]


@pytest.mark.asyncio
async def test_wechat_saved_receipt_can_only_be_read_not_resubmitted(
    isolated_publish_db, monkeypatch
):
    sessions = isolated_publish_db
    _task(sessions, "WECHAT_OFFICIAL")
    calls = []

    async def post(_self, url, **_kwargs):
        endpoint = url.split("/cgi-bin/")[-1]
        calls.append(endpoint)
        return _response(
            url,
            {
                "draft/add": {"media_id": "draft"},
                "freepublish/submit": {"publish_id": "published"},
                "freepublish/get": {"publish_status": 0},
            }[endpoint],
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    request = {
        "schedule_id": 1,
        "idempotency_key": "isolated-publish-task",
        "title": "测试",
        "content": "正文",
        "images": [],
    }
    with sessions() as db:
        publisher = WechatPublishPublisher(db, db.get(PlatformAccount, 1))
        first = await publisher.publish(request)
        assert first.success and first.external_id == "published"
    with sessions() as db:
        publisher = WechatPublishPublisher(db, db.get(PlatformAccount, 1))
        repeated = await publisher.publish(request)
        assert repeated.success and repeated.external_id == "published"
    assert calls == ["draft/add", "freepublish/submit", "freepublish/get"]


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["content", "cover", "account", "image_bytes"])
async def test_wechat_cannot_reuse_draft_after_content_account_or_cover_changes(
    isolated_publish_db, tmp_path, monkeypatch, change
):
    sessions = isolated_publish_db
    _task(sessions, "WECHAT_OFFICIAL")
    calls = []
    image = tmp_path / "same-upload.png"
    image.write_bytes(b"original image")
    monkeypatch.setattr(official, "_local_image", lambda value: image if value == "image" else None)

    async def post(_self, url, **_kwargs):
        endpoint = url.split("/cgi-bin/")[-1]
        calls.append(endpoint)
        return _response(
            url,
            {"media_id": "original-draft"}
            if endpoint == "draft/add"
            else {"errcode": 45009, "errmsg": "explicit rejection"},
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    request = {
        "schedule_id": 1,
        "idempotency_key": "isolated-publish-task",
        "title": "测试",
        "content": "原始正文",
        "images": ["image"],
    }
    with sessions() as db:
        account = db.get(PlatformAccount, 1)
        publisher = WechatPublishPublisher(db, account)
        rejected = await publisher.publish(request)
        assert rejected.retryable
        if change == "content":
            request["content"] = "修改后的正文"
        elif change == "cover":
            publisher.config["default_cover_media_id"] = "different-cover"
        elif change == "image_bytes":
            image.write_bytes(b"different image at the same URL")
        else:
            account.app_id = "wx-different"
            db.commit()
            publisher = WechatPublishPublisher(db, account)
        stopped = await publisher.publish(request)
        assert stopped.error_code == "TASK_CONTENT_CHANGED" and not stopped.retryable
    assert calls == ["draft/add", "freepublish/submit"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "invalid_json", "server_error", "rate_limit"])
async def test_weibo_unknown_write_is_not_automatically_retryable(
    isolated_publish_db, monkeypatch, failure
):
    sessions = isolated_publish_db
    _task(sessions, "WEIBO")

    async def post(_self, url, **_kwargs):
        if failure == "timeout":
            raise httpx.ReadTimeout("response lost after write")
        if failure == "invalid_json":
            return httpx.Response(200, text="not JSON", request=httpx.Request("POST", url))
        return _response(url, {"error": "rejected"}, 429 if failure == "rate_limit" else 500)

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    with sessions() as db:
        result = await WeiboPublisher(db, db.get(PlatformAccount, 1)).publish(
            {"title": "隔离测试", "content": "正文", "images": []}
        )
        assert not result.success
        assert result.retryable is (failure == "rate_limit")
