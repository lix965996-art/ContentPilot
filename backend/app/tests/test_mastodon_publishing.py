import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import httpx
import pytest
from sqlalchemy import select

from app.core.credentials import decrypt_json, encrypt_json, encrypt_secret
from app.core.exceptions import AppException
from app.core.paths import UPLOADS_DIR
from app.db.session import SessionLocal
from app.models.business import (
    ContentArticle,
    ContentVariant,
    PlatformAccount,
    PublishLog,
    PublishSchedule,
)
from app.publishers import mastodon as mastodon_module
from app.publishers.mastodon import ATTEMPT_FIELD, MAX_IMAGE_BYTES, MastodonPublisher
from app.services.publish_service import execute_publish
from app.services.review_fingerprint import variant_fingerprint

ORIGIN = "https://mastodon.social"
ACCOUNT_ID = "42"
STATUS_ID = "1234567890"
TOKEN = "mastodon-publishing-test-token"
PNG = b"\x89PNG\r\n\x1a\n" + b"test-image"


@pytest.fixture(autouse=True)
def prevent_real_network(monkeypatch):
    async def public_instance(value):
        assert value == ORIGIN
        return value

    async def unexpected_request(*_args, **_kwargs):
        pytest.fail("Mastodon tests must never reach a real network transport")

    monkeypatch.setattr(mastodon_module, "ensure_public_instance", public_instance)
    monkeypatch.setattr(httpx.AsyncClient, "request", unexpected_request)


def _response(method, url, data, status=200, *, headers=None):
    return httpx.Response(status, json=data, headers=headers, request=httpx.Request(method, url))


def _receipt(**overrides):
    return {
        "id": STATUS_ID,
        "url": f"{ORIGIN}/@test-user/{STATUS_ID}",
        "account": {"id": ACCOUNT_ID, "acct": "test-user"},
        "visibility": "public",
        **overrides,
    }


def _account(db, *, enabled=True):
    account = db.scalar(select(PlatformAccount).where(PlatformAccount.platform == "MASTODON"))
    if account is None:
        account = PlatformAccount(platform="MASTODON", user_id=1, account_name="Mastodon test")
        db.add(account)
    account.auth_type = "ACCESS_TOKEN"
    account.publish_mode = "REAL_API"
    account.status = "CONNECTED"
    account.capabilities_json = ["TEXT_PUBLISH", "IMAGE_PUBLISH", "STATUS_READ"]
    account.credentials_encrypted = encrypt_json(
        {
            "instance_url": ORIGIN,
            "mastodon_account_id": ACCOUNT_ID,
            "mastodon_acct": "test-user",
            "mastodon_max_characters": 500,
            "mastodon_characters_reserved_per_url": 23,
            "mastodon_max_media_attachments": 4,
            "mastodon_image_size_limit": MAX_IMAGE_BYTES,
            "allow_public_publish": enabled,
        }
    )
    account.access_token_encrypted = encrypt_secret(TOKEN)
    account.refresh_token_encrypted = None
    account.token_expires_at = None
    db.flush()
    return account


def _task(db, *, enabled=True):
    account = _account(db, enabled=enabled)
    article = ContentArticle(title="Mastodon 测试", source_text="测试原文", created_by=1)
    db.add(article)
    db.flush()
    variant = ContentVariant(
        article_id=article.id,
        platform="MASTODON",
        title="测试标题",
        content_text="测试正文",
        hashtags_json=["功能测试"],
        review_status="APPROVED",
    )
    db.add(variant)
    db.flush()
    variant.review_fingerprint = variant_fingerprint(variant)
    task = PublishSchedule(
        article_id=article.id,
        variant_id=variant.id,
        account_id=account.id,
        platform="MASTODON",
        publish_mode="REAL_API",
        scheduled_at=datetime.now() + timedelta(days=60),
        idempotency_key=str(uuid.uuid4()),
        created_by=1,
    )
    db.add(task)
    db.commit()
    return (
        account,
        task,
        {
            "schedule_id": task.id,
            "idempotency_key": task.idempotency_key,
            "title": variant.title,
            "content": variant.content_text,
            "hashtags": variant.hashtags_json,
            "images": [],
        },
    )


def _image(content=PNG):
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    image = UPLOADS_DIR / f"mastodon-{uuid.uuid4().hex}.png"
    image.write_bytes(content)
    return image, f"/uploads/{image.name}"


@pytest.mark.asyncio
async def test_mastodon_validation_only_reads_identity_and_instance_limits(monkeypatch):
    calls = []

    async def transport(_self, method, url, **kwargs):
        calls.append((method, urlsplit(url).path))
        assert method == "GET"
        if url.endswith("verify_credentials"):
            assert kwargs["headers"]["Authorization"] == f"Bearer {TOKEN}"
            return _response(method, url, {"id": ACCOUNT_ID, "acct": "test-user"})
        assert "Authorization" not in kwargs["headers"]
        return _response(
            method,
            url,
            {
                "configuration": {
                    "statuses": {
                        "max_characters": 600,
                        "characters_reserved_per_url": 25,
                        "max_media_attachments": 3,
                    },
                    "media_attachments": {"image_size_limit": 2_000_000},
                }
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "request", transport)
    with SessionLocal() as db:
        account = _account(db, enabled=False)
        result = await MastodonPublisher(db, account).validate_credentials()
        assert result.success and result.status == "CONNECTED"
        assert result.detail == {
            "account_id": ACCOUNT_ID,
            "acct": "test-user",
            "max_characters": 600,
            "characters_reserved_per_url": 25,
            "max_media_attachments": 3,
            "image_size_limit": 2_000_000,
        }
        assert calls == [
            ("GET", "/api/v1/accounts/verify_credentials"),
            ("GET", "/api/v2/instance"),
        ]
        assert TOKEN not in str(result.as_dict())
        assert decrypt_json(account.credentials_encrypted)["allow_public_publish"] is False


@pytest.mark.asyncio
async def test_mastodon_gate_task_binding_and_content_reject_before_network():
    with SessionLocal() as db:
        account, task, request = _task(db, enabled=False)
        publisher = MastodonPublisher(db, account)
        assert (await publisher.publish(request)).error_code == "PUBLIC_PUBLISH_DISABLED"
        _account(db, enabled=True)
        assert (
            await publisher.publish({**request, "schedule_id": None})
        ).error_code == "TASK_REQUIRED"
        assert (
            await publisher.publish({**request, "idempotency_key": "another-task"})
        ).error_code == "TASK_REQUIRED"
        task.account_id = None
        db.flush()
        assert (await publisher.publish(request)).error_code == "TASK_REQUIRED"
        task.account_id = account.id
        db.flush()
        assert (
            await publisher.publish({**request, "content": "字" * 501})
        ).error_code == "CONTENT_INVALID"


@pytest.mark.asyncio
async def test_mastodon_existing_schedule_cannot_bypass_disabled_gate():
    with SessionLocal() as db:
        _account_row, task, _request = _task(db, enabled=False)
        with pytest.raises(AppException) as failure:
            await execute_publish(db, task.id)
        assert failure.value.code == 40086
        db.refresh(task)
        assert task.status == "FAILED"
        log = db.scalar(select(PublishLog).where(PublishLog.schedule_id == task.id))
        assert log.step == "PRECHECK" and log.error_code == "40086"


@pytest.mark.asyncio
async def test_mastodon_timeout_retry_reuses_key_and_completed_task_only_reads(monkeypatch):
    server_posts = {}
    calls = []
    lost_response = True

    async def transport(_self, method, url, **kwargs):
        nonlocal lost_response
        calls.append((method, urlsplit(url).path))
        if method == "GET":
            assert "Authorization" not in kwargs["headers"]
            assert url.endswith(f"/statuses/{STATUS_ID}")
            return _response(method, url, _receipt())
        assert kwargs["headers"]["Authorization"] == f"Bearer {TOKEN}"
        assert url.endswith("/api/v1/statuses")
        key = kwargs["headers"]["Idempotency-Key"]
        server_posts.setdefault(key, _receipt())
        if lost_response:
            lost_response = False
            raise httpx.ReadTimeout("response lost", request=httpx.Request(method, url))
        return _response(method, url, server_posts[key])

    monkeypatch.setattr(httpx.AsyncClient, "request", transport)
    with SessionLocal() as db:
        account, task, request = _task(db)
        publisher = MastodonPublisher(db, account)
        first = await publisher.publish(request)
        assert first.error_code == "PUBLISH_UNCERTAIN"
        assert task.publish_package_json[ATTEMPT_FIELD]["uncertain"] is True
        second = await publisher.publish(request)
        assert second.success and second.external_id == STATUS_ID
        third = await publisher.publish(request)
        assert third.success and third.external_id == STATUS_ID
        assert len(server_posts) == 1
        assert [method for method, _path in calls] == ["POST", "POST", "GET"]
        assert task.publish_package_json[ATTEMPT_FIELD]["statusId"] == STATUS_ID


@pytest.mark.asyncio
async def test_mastodon_uncertain_post_older_than_hour_never_writes_again(monkeypatch):
    writes = []

    async def transport(_self, method, url, **_kwargs):
        writes.append(method)
        raise httpx.ReadTimeout("response lost", request=httpx.Request(method, url))

    monkeypatch.setattr(httpx.AsyncClient, "request", transport)
    with SessionLocal() as db:
        account, task, request = _task(db)
        publisher = MastodonPublisher(db, account)
        assert (await publisher.publish(request)).error_code == "PUBLISH_UNCERTAIN"
        package = dict(task.publish_package_json)
        attempt = dict(package[ATTEMPT_FIELD])
        attempt["sentAt"] = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        package[ATTEMPT_FIELD] = attempt
        task.publish_package_json = package
        db.commit()
        result = await publisher.publish(request)
        assert result.error_code == "PUBLISH_UNCERTAIN"
        assert writes == ["POST"]


@pytest.mark.asyncio
async def test_mastodon_rate_limit_cannot_reset_uncertain_post_retry_deadline(monkeypatch):
    posts = []

    async def transport(_self, method, url, **kwargs):
        posts.append(kwargs["headers"]["Idempotency-Key"])
        if len(posts) == 1:
            raise httpx.ReadTimeout("response lost", request=httpx.Request(method, url))
        return _response(method, url, {"error": "do not expose upstream details"}, 429)

    monkeypatch.setattr(httpx.AsyncClient, "request", transport)
    with SessionLocal() as db:
        account, task, request = _task(db)
        publisher = MastodonPublisher(db, account)
        assert (await publisher.publish(request)).error_code == "PUBLISH_UNCERTAIN"
        first_sent_at = task.publish_package_json[ATTEMPT_FIELD]["sentAt"]
        limited = await publisher.publish(request)
        assert limited.error_code == "RATE_LIMITED"
        attempt = task.publish_package_json[ATTEMPT_FIELD]
        assert attempt["uncertain"] is True
        assert attempt["sentAt"] == first_sent_at
        package = dict(task.publish_package_json)
        package[ATTEMPT_FIELD] = {
            **attempt,
            "sentAt": (datetime.now(UTC) - timedelta(minutes=56)).isoformat(),
        }
        task.publish_package_json = package
        db.commit()
        expired = await publisher.publish(request)
        assert expired.error_code == "PUBLISH_UNCERTAIN"
        assert len(posts) == 2 and posts[0] == posts[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["text", "image_bytes", "account"])
async def test_mastodon_attempt_binds_content_image_bytes_and_remote_identity(monkeypatch, change):
    calls = []

    async def transport(_self, method, url, **_kwargs):
        calls.append((method, urlsplit(url).path))
        if url.endswith("/media"):
            return _response(method, url, {"id": "1", "url": "https://cdn.example.org/image.png"})
        return _response(method, url, _receipt())

    monkeypatch.setattr(httpx.AsyncClient, "request", transport)
    with SessionLocal() as db:
        account, _task_row, request = _task(db)
        path, image_url = _image()
        request["images"] = [image_url]
        publisher = MastodonPublisher(db, account)
        assert (await publisher.publish(request)).success
        calls_before = len(calls)
        if change == "text":
            request["content"] = "改后的正文"
        elif change == "image_bytes":
            path.write_bytes(PNG + b"changed")
        else:
            config = decrypt_json(account.credentials_encrypted)
            config["mastodon_account_id"] = "43"
            account.credentials_encrypted = encrypt_json(config)
            db.commit()
        changed = await publisher.publish(request)
        assert changed.error_code == "TASK_CONTENT_CHANGED"
        assert len(calls) == calls_before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("image_kind", "error_code"),
    [
        ("remote", "IMAGE_UNAVAILABLE"),
        ("oversize", "IMAGE_TOO_LARGE"),
        ("unsupported", "IMAGE_FORMAT"),
    ],
)
async def test_mastodon_unsafe_or_invalid_images_never_reach_network(image_kind, error_code):
    if image_kind == "remote":
        image_url = "https://example.org/external.png"
    else:
        content = PNG + b"x" * MAX_IMAGE_BYTES if image_kind == "oversize" else b"not an image"
        _path, image_url = _image(content)
    with SessionLocal() as db:
        account, _task_row, request = _task(db)
        request["images"] = [image_url]
        result = await MastodonPublisher(db, account).publish(request)
        assert result.error_code == error_code


@pytest.mark.asyncio
async def test_mastodon_waits_for_async_media_url_before_status_write(monkeypatch):
    calls = []
    media_polls = 0

    async def no_sleep(_seconds):
        return None

    async def transport(_self, method, url, **kwargs):
        nonlocal media_polls
        path = urlsplit(url).path
        calls.append((method, path))
        if path == "/api/v2/media":
            assert kwargs["files"]["file"][2] == "image/png"
            return _response(method, url, {"id": "7", "url": None}, 202)
        if path == "/api/v1/media/7":
            media_polls += 1
            if media_polls == 1:
                return _response(method, url, {"id": "7", "url": None}, 206)
            return _response(method, url, {"id": "7", "url": "https://cdn.example.org/7.png"})
        assert path == "/api/v1/statuses"
        assert kwargs["json"]["media_ids"] == ["7"]
        assert media_polls == 2
        return _response(method, url, _receipt())

    monkeypatch.setattr(mastodon_module.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(httpx.AsyncClient, "request", transport)
    with SessionLocal() as db:
        account, _task_row, request = _task(db)
        _path, image_url = _image()
        request["images"] = [image_url]
        result = await MastodonPublisher(db, account).publish(request)
        assert result.success
        assert calls == [
            ("POST", "/api/v2/media"),
            ("GET", "/api/v1/media/7"),
            ("GET", "/api/v1/media/7"),
            ("POST", "/api/v1/statuses"),
        ]


@pytest.mark.asyncio
async def test_mastodon_retry_reuses_processing_media_without_uploading_again(monkeypatch):
    calls = []
    polls = 0

    async def no_sleep(_seconds):
        return None

    async def transport(_self, method, url, **kwargs):
        nonlocal polls
        path = urlsplit(url).path
        calls.append((method, path))
        if path == "/api/v2/media":
            return _response(method, url, {"id": "7", "url": None}, 202)
        if path == "/api/v1/media/7":
            polls += 1
            if polls <= 5:
                return _response(method, url, {}, 206)
            return _response(method, url, {"id": "7", "url": "https://cdn.example.org/7.png"})
        assert path == "/api/v1/statuses"
        assert kwargs["json"]["media_ids"] == ["7"]
        return _response(method, url, _receipt())

    monkeypatch.setattr(mastodon_module.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(httpx.AsyncClient, "request", transport)
    with SessionLocal() as db:
        account, task, request = _task(db)
        _path, image_url = _image()
        request["images"] = [image_url]
        publisher = MastodonPublisher(db, account)
        first = await publisher.publish(request)
        assert first.error_code == "MEDIA_PROCESSING"
        assert task.publish_package_json[ATTEMPT_FIELD]["mediaIds"] == ["7"]
        assert "sentAt" not in task.publish_package_json[ATTEMPT_FIELD]
        second = await publisher.publish(request)
        assert second.success
        assert calls.count(("POST", "/api/v2/media")) == 1
        assert calls.count(("GET", "/api/v1/media/7")) == 6
        assert calls.count(("POST", "/api/v1/statuses")) == 1


@pytest.mark.asyncio
async def test_mastodon_rejects_changed_media_processing_identity(monkeypatch):
    calls = []

    async def no_sleep(_seconds):
        return None

    async def transport(_self, method, url, **_kwargs):
        path = urlsplit(url).path
        calls.append(path)
        if path == "/api/v2/media":
            return _response(method, url, {"id": "7", "url": None}, 202)
        assert path == "/api/v1/media/7"
        return _response(method, url, {"id": "8", "url": "https://cdn.example.org/8.png"})

    monkeypatch.setattr(mastodon_module.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(httpx.AsyncClient, "request", transport)
    with SessionLocal() as db:
        account, _task_row, request = _task(db)
        _path, image_url = _image()
        request["images"] = [image_url]
        result = await MastodonPublisher(db, account).publish(request)
        assert result.error_code == "INVALID_IMAGE_RECEIPT"
        assert calls == ["/api/v2/media", "/api/v1/media/7"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"account": {"id": "999"}},
        {"url": f"https://evil.example.org/@test-user/{STATUS_ID}"},
        {"url": f"http://mastodon.social/@test-user/{STATUS_ID}"},
        {"visibility": "private"},
    ],
)
async def test_mastodon_foreign_or_private_receipts_are_never_success(monkeypatch, overrides):
    async def transport(_self, method, url, **_kwargs):
        return _response(method, url, _receipt(**overrides))

    monkeypatch.setattr(httpx.AsyncClient, "request", transport)
    with SessionLocal() as db:
        account, task, request = _task(db)
        result = await MastodonPublisher(db, account).publish(request)
        assert not result.success and result.error_code == "INVALID_RECEIPT"
        assert task.publish_package_json[ATTEMPT_FIELD]["uncertain"] is True
        assert "statusId" not in task.publish_package_json[ATTEMPT_FIELD]


@pytest.mark.asyncio
async def test_mastodon_private_dns_never_sends_token(monkeypatch):
    from app.core import mastodon as mastodon_core

    def private_dns(*_args, **_kwargs):
        return [(2, 1, 6, "", ("192.168.1.5", 443))]

    monkeypatch.setattr(mastodon_core.socket, "getaddrinfo", private_dns)
    monkeypatch.setattr(
        mastodon_module, "ensure_public_instance", mastodon_core.ensure_public_instance
    )
    with SessionLocal() as db:
        result = await MastodonPublisher(db, _account(db)).validate_credentials()
        assert result.error_code == "INVALID_INSTANCE"
        assert TOKEN not in str(result.as_dict())


@pytest.mark.asyncio
async def test_mastodon_redirect_is_not_followed_or_forwarded_credentials(monkeypatch):
    calls = []

    async def transport(client, method, url, **kwargs):
        assert client.follow_redirects is False
        calls.append(url)
        assert url.startswith(ORIGIN)
        assert kwargs["headers"]["Authorization"] == f"Bearer {TOKEN}"
        return _response(method, url, {}, 302, headers={"Location": "https://evil.example.org"})

    monkeypatch.setattr(httpx.AsyncClient, "request", transport)
    with SessionLocal() as db:
        result = await MastodonPublisher(db, _account(db)).validate_credentials()
        assert not result.success
        assert len(calls) == 1
        assert TOKEN not in str(result.as_dict())


def test_mastodon_pipeline_gate_retry_and_persisted_real_receipt(client, login_as, monkeypatch):
    auth = {"Authorization": "Bearer " + login_as("operator", "Operator@123456")["access_token"]}
    article_response = client.post(
        "/api/articles",
        headers=auth,
        json={"title": "Mastodon 排期", "source_text": "用于验证真实发布接口的测试原文。"},
    )
    assert article_response.status_code == 200, article_response.text
    article = article_response.json()["data"]
    with SessionLocal() as db:
        account = _account(db, enabled=False)
        variant = ContentVariant(
            article_id=article["id"],
            platform="MASTODON",
            version_no=1,
            title="排期",
            content_text="正文",
            hashtags_json=[],
            review_status="APPROVED",
        )
        db.add(variant)
        db.flush()
        variant.review_fingerprint = variant_fingerprint(variant)
        db.commit()
        payload = {
            "article_id": article["id"],
            "variant_id": variant.id,
            "platform": "MASTODON",
            "account_id": account.id,
            "scheduled_at": (datetime.now() + timedelta(days=30)).isoformat(),
            "publish_mode": "REAL_API",
        }
    closed = client.post("/api/schedules", headers=auth, json=payload)
    assert closed.status_code == 400 and closed.json()["code"] == 40086
    with SessionLocal() as db:
        _account(db, enabled=True)
        db.commit()
    scheduled = client.post("/api/schedules", headers=auth, json=payload)
    assert scheduled.status_code == 200, scheduled.text
    schedule_id = scheduled.json()["data"]["id"]
    keys = []
    posts = {}

    async def transport(_self, method, url, **kwargs):
        assert method == "POST" and url.endswith("/api/v1/statuses")
        key = kwargs["headers"]["Idempotency-Key"]
        keys.append(key)
        posts.setdefault(key, _receipt())
        if len(keys) == 1:
            raise httpx.ReadTimeout("response lost", request=httpx.Request(method, url))
        return _response(method, url, posts[key])

    monkeypatch.setattr(httpx.AsyncClient, "request", transport)
    failed = client.post(f"/api/schedules/{schedule_id}/publish-now", headers=auth)
    assert failed.status_code == 200, failed.text
    assert failed.json()["data"]["status"] == "FAILED"
    with SessionLocal() as db:
        task = db.get(PublishSchedule, schedule_id)
        assert task.publish_package_json[ATTEMPT_FIELD]["uncertain"] is True
    published = client.post(f"/api/schedules/{schedule_id}/retry", headers=auth)
    assert published.status_code == 200, published.text
    data = published.json()["data"]
    assert data["status"] == "PUBLISHED"
    assert data["externalId"] == STATUS_ID
    assert data["publishedUrl"] == _receipt()["url"]
    assert len(posts) == 1 and len(keys) == 2 and keys[0] == keys[1]
    with SessionLocal() as db:
        task = db.get(PublishSchedule, schedule_id)
        assert task.result_mode == "REAL_API"
        assert task.actual_publish_at is not None
        assert task.publish_package_json[ATTEMPT_FIELD]["statusId"] == STATUS_ID
        logs = db.scalars(select(PublishLog).where(PublishLog.schedule_id == schedule_id)).all()
        assert [log.status for log in logs] == ["FAILED", "PUBLISHED"]
        assert TOKEN not in str([(log.response_summary, log.error_message) for log in logs])
