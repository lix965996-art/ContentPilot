import re
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.core.credentials import decrypt_json, decrypt_secret, encrypt_json, encrypt_secret
from app.db.session import SessionLocal
from app.models.business import ContentVariant, PlatformAccount, PublishSchedule
from app.publishers.bluesky import BlueskyPublisher, _facets, new_bluesky_record_key
from app.services.review_fingerprint import variant_fingerprint

DID = "did:plc:bluesky-test-user"
RECORD_KEY = "3jzfcijpj2z2a"


def test_bluesky_record_key_is_tid_with_current_timestamp_and_unique_sequence():
    alphabet = "234567abcdefghijklmnopqrstuvwxyz"
    before = datetime.now(UTC).timestamp()
    keys = [new_bluesky_record_key("same-schedule") for _ in range(5)]
    after = datetime.now(UTC).timestamp()
    assert len(set(keys)) == len(keys)
    assert keys == sorted(keys)
    for key in keys:
        assert re.fullmatch(r"[234567abcdefghij][234567abcdefghijklmnopqrstuvwxyz]{12}", key)
        value = 0
        for character in key:
            value = value * 32 + alphabet.index(character)
        # The monotonic sequence may advance a few microseconds past a coarse OS clock.
        assert before - 0.001 <= (value >> 10) / 1_000_000 <= after + 0.001


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "record_key", [None, "cp" + "a" * 40, "z" * 13, "0" * 13, RECORD_KEY.upper()]
)
async def test_bluesky_missing_or_invalid_persisted_tid_cannot_call_network(
    monkeypatch, record_key
):
    async def unexpected(*args, **kwargs):
        pytest.fail("Missing or invalid TID must not call the API")

    monkeypatch.setattr(httpx.AsyncClient, "request", unexpected)
    with SessionLocal() as db:
        result = await BlueskyPublisher(db, _account(db)).publish(
            {"content": "测试正文", "record_key": record_key}
        )
        assert result.error_code == "INVALID_RECORD_KEY"


def test_bluesky_api_error_retains_only_safe_upstream_code():
    with SessionLocal() as db:
        publisher = BlueskyPublisher(db, _account(db))
        result = publisher._api_failure(
            _response(
                "POST",
                "https://bsky.test/createRecord",
                {"error": "InvalidRecord", "message": "secret token should never appear"},
                400,
            )
        )
        assert result.error_code == "API_ERROR"
        assert "InvalidRecord" in result.error_message
        assert result.detail["upstream_error"] == "InvalidRecord"
        assert "secret token" not in str(result.as_dict())
        unsafe = publisher._api_failure(
            _response(
                "POST",
                "https://bsky.test/createRecord",
                {"error": "InvalidRecord token=secret", "message": "secret"},
                400,
            )
        )
        assert "upstream_error" not in unsafe.detail
        assert "secret" not in str(unsafe.as_dict())


def _account(db, *, enabled=True):
    account = db.scalar(select(PlatformAccount).where(PlatformAccount.platform == "BLUESKY"))
    if account is None:
        account = PlatformAccount(platform="BLUESKY", user_id=1, account_name="Bluesky test")
        db.add(account)
    account.auth_type = "APP_PASSWORD"
    account.publish_mode = "REAL_API"
    account.status = "CONNECTED"
    account.capabilities_json = ["TEXT_PUBLISH", "IMAGE_PUBLISH", "STATUS_READ"]
    account.credentials_encrypted = encrypt_json(
        {
            "identifier": "example.bsky.social",
            "app_password": "test-only-app-password",
            "allow_public_publish": enabled,
            "bluesky_did": DID,
            "bluesky_handle": "example.bsky.social",
        }
    )
    account.access_token_encrypted = encrypt_secret("test-access")
    account.refresh_token_encrypted = encrypt_secret("test-refresh")
    account.token_expires_at = datetime.now() + timedelta(hours=1)
    db.commit()
    return account


def _response(method, url, data, status=200):
    return httpx.Response(status, json=data, request=httpx.Request(method, url))


@pytest.mark.asyncio
async def test_bluesky_login_only_creates_session_and_encrypts_tokens(monkeypatch):
    calls = []

    async def fake_request(_self, method, url, **kwargs):
        calls.append(url.rsplit("/", 1)[-1])
        assert kwargs["json"]["password"] == "test-only-app-password"
        return _response(
            method,
            url,
            {
                "did": DID,
                "handle": "example.bsky.social",
                "accessJwt": "new-access",
                "refreshJwt": "new-refresh",
                "active": True,
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)
    with SessionLocal() as db:
        account = _account(db, enabled=False)
        result = await BlueskyPublisher(db, account).validate_credentials()
        assert result.success and result.status == "CONNECTED"
        assert result.external_id == DID
        assert calls == ["com.atproto.server.createSession"]
        assert decrypt_secret(account.access_token_encrypted) == "new-access"
        assert "new-access" not in account.access_token_encrypted
        assert "test-only-app-password" not in str(result.as_dict())
        assert decrypt_json(account.credentials_encrypted)["allow_public_publish"] is False


@pytest.mark.asyncio
async def test_bluesky_gate_and_length_prevent_any_network_write(monkeypatch):
    async def unexpected(*args, **kwargs):
        pytest.fail("Invalid content or disabled publishing must not call the API")

    monkeypatch.setattr(httpx.AsyncClient, "request", unexpected)
    with SessionLocal() as db:
        account = _account(db, enabled=False)
        result = await BlueskyPublisher(db, account).publish({"content": "短文"})
        assert result.error_code == "PUBLIC_PUBLISH_DISABLED"
        account = _account(db, enabled=True)
        result = await BlueskyPublisher(db, account).publish({"content": "字" * 301})
        assert result.error_code == "CONTENT_INVALID"


@pytest.mark.asyncio
async def test_bluesky_timeout_recovers_receipt_and_retry_does_not_duplicate(monkeypatch):
    records = {}
    creates = []

    async def fake_request(_self, method, url, **kwargs):
        if url.endswith("getRecord"):
            key = kwargs["params"]["rkey"]
            if key in records:
                return _response(method, url, records[key])
            return _response(method, url, {"error": "RecordNotFound"}, 400)
        assert url.endswith("createRecord")
        body = kwargs["json"]
        key = body["rkey"]
        assert re.fullmatch(r"[234567abcdefghij][234567abcdefghijklmnopqrstuvwxyz]{12}", key)
        creates.append(key)
        records[key] = {
            "uri": f"at://{DID}/app.bsky.feed.post/{key}",
            "cid": "cid1",
            "value": body["record"],
        }
        raise httpx.ReadTimeout("response lost", request=httpx.Request(method, url))

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)
    with SessionLocal() as db:
        publisher = BlueskyPublisher(db, _account(db))
        request = {
            "content": "中文摘要 #内容运营",
            "idempotency_key": "same-schedule",
            "record_key": RECORD_KEY,
        }
        first = await publisher.publish(request)
        again = await publisher.publish(request)
        changed = await publisher.publish({**request, "content": "修改后内容"})
        assert first.success and again.success
        assert first.external_id == again.external_id
        assert first.published_url.startswith("https://bsky.app/profile/did:plc:")
        assert len(creates) == 1
        assert changed.error_code == "TASK_ALREADY_PUBLISHED"


@pytest.mark.asyncio
async def test_bluesky_expired_session_refreshes_without_password_login(monkeypatch):
    calls = []

    async def fake_request(_self, method, url, **kwargs):
        calls.append(url.rsplit("/", 1)[-1])
        assert kwargs["headers"]["Authorization"] == "Bearer test-refresh"
        return _response(
            method,
            url,
            {
                "did": DID,
                "handle": "example.bsky.social",
                "accessJwt": "fresh-access",
                "refreshJwt": "fresh-refresh",
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)
    with SessionLocal() as db:
        account = _account(db)
        account.token_expires_at = datetime.now() - timedelta(minutes=1)
        token, failure = await BlueskyPublisher(db, account)._token()
        assert failure is None and token == "fresh-access"
        assert calls == ["com.atproto.server.refreshSession"]


@pytest.mark.asyncio
async def test_bluesky_refresh_cannot_switch_account_identity(monkeypatch):
    async def fake_request(_self, method, url, **kwargs):
        return _response(
            method,
            url,
            {
                "did": "did:plc:other",
                "handle": "other.bsky.social",
                "accessJwt": "other-token",
                "refreshJwt": "other-refresh",
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)
    with SessionLocal() as db:
        account = _account(db)
        account.token_expires_at = datetime.now() - timedelta(minutes=1)
        _, failure = await BlueskyPublisher(db, account)._token()
        assert failure.error_code == "INVALID_SESSION"
        assert decrypt_secret(account.access_token_encrypted) == "test-access"


@pytest.mark.asyncio
async def test_bluesky_uploads_local_image_before_record_and_rejects_remote(monkeypatch):
    from app.core.paths import UPLOADS_DIR

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    image = UPLOADS_DIR / "bluesky-test.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"test-image")
    methods = []

    async def fake_request(_self, method, url, **kwargs):
        methods.append(url.rsplit("/", 1)[-1])
        if url.endswith("getRecord"):
            return _response(method, url, {"error": "RecordNotFound"}, 400)
        if url.endswith("uploadBlob"):
            assert kwargs["headers"]["Content-Type"] == "image/png"
            assert kwargs["content"].startswith(b"\x89PNG")
            return _response(
                method,
                url,
                {"blob": {"ref": {"$link": "blobcid"}, "mimeType": "image/png", "size": 18}},
            )
        record = kwargs["json"]["record"]
        assert record["embed"]["images"][0]["image"]["ref"]["$link"] == "blobcid"
        assert record["embed"]["images"][0]["alt"] == "学生桌上的笔记本与手写笔记"
        return _response(
            method,
            url,
            {"uri": f"at://{DID}/app.bsky.feed.post/{kwargs['json']['rkey']}", "cid": "cid"},
        )

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)
    with SessionLocal() as db:
        publisher = BlueskyPublisher(db, _account(db))
        result = await publisher.publish(
            {
                "content": "图片正文",
                "images": ["/uploads/bluesky-test.png"],
                "image_alt_texts": ["学生桌上的笔记本与手写笔记"],
                "record_key": RECORD_KEY,
            }
        )
        assert result.success
        assert methods == [
            "com.atproto.repo.uploadBlob",
            "com.atproto.repo.getRecord",
            "com.atproto.repo.createRecord",
        ]
        methods.clear()
        remote = await publisher.publish(
            {
                "content": "远程图片",
                "images": ["https://example.org/photo.png"],
                "record_key": RECORD_KEY,
            }
        )
        assert remote.error_code == "IMAGE_UNAVAILABLE"
        assert "com.atproto.repo.createRecord" not in methods


@pytest.mark.asyncio
@pytest.mark.parametrize("descriptions", [[], ["说明", "错位"], [None], ["字" * 501]])
async def test_bluesky_rejects_invalid_image_descriptions_before_network(monkeypatch, descriptions):
    async def unexpected(*_args, **_kwargs):
        pytest.fail("Invalid descriptions must not reach the platform")

    monkeypatch.setattr(httpx.AsyncClient, "request", unexpected)
    with SessionLocal() as db:
        result = await BlueskyPublisher(db, _account(db)).publish(
            {
                "content": "图文正文",
                "images": ["/uploads/unused.png"],
                "image_alt_texts": descriptions,
                "record_key": RECORD_KEY,
            }
        )
        assert result.error_code == "CONTENT_INVALID"


def test_bluesky_facets_use_utf8_offsets_and_ignore_link_fragment_tag():
    text = "中文 https://example.org/#anchor #话题"
    facets = _facets(text)
    assert len(facets) == 2
    encoded = text.encode("utf-8")
    tag = facets[1]
    assert encoded[tag["index"]["byteStart"] : tag["index"]["byteEnd"]].decode() == "#话题"
    assert tag["features"][0]["tag"] == "话题"


def test_bluesky_schedule_routes_to_real_adapter_and_enforces_gate(client, login_as, monkeypatch):
    auth = {"Authorization": "Bearer " + login_as("operator", "Operator@123456")["access_token"]}
    created_article = client.post(
        "/api/articles",
        headers=auth,
        json={"title": "Bluesky 排期", "source_text": "用于验证图文排期的原始内容。"},
    )
    assert created_article.status_code == 200, created_article.text
    assert created_article.json()["data"], created_article.text
    article = created_article.json()["data"]
    with SessionLocal() as db:
        account = _account(db, enabled=False)
        variant = ContentVariant(
            article_id=article["id"],
            platform="BLUESKY",
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
            "platform": "BLUESKY",
            "account_id": account.id,
            "scheduled_at": (datetime.now() + timedelta(days=30)).isoformat(),
            "publish_mode": "REAL_API",
        }
    disabled = client.post("/api/schedules", headers=auth, json=payload)
    assert disabled.status_code == 400 and disabled.json()["code"] == 40085
    with SessionLocal() as db:
        _account(db, enabled=True)
    created = client.post("/api/schedules", headers=auth, json=payload)
    assert created.status_code == 200, created.text

    record_keys = []
    schedule_id = created.json()["data"]["id"]

    async def fake_publish(_self, request):
        from app.publishers.base import PublishResult

        assert request["idempotency_key"]
        record_key = request["record_key"]
        assert re.fullmatch(r"[234567abcdefghij][234567abcdefghijklmnopqrstuvwxyz]{12}", record_key)
        record_keys.append(record_key)
        with SessionLocal() as verification_db:
            persisted = verification_db.get(PublishSchedule, schedule_id)
            assert persisted.publish_package_json["blueskyRkey"] == record_key
        if len(record_keys) == 1:
            return PublishResult(False, "BLUESKY", "REAL_API", "FAILED", error_code="NETWORK_ERROR")
        return PublishResult(
            True,
            "BLUESKY",
            "REAL_API",
            "PUBLISHED",
            external_id=f"at://{DID}/app.bsky.feed.post/receipt",
            published_url="https://bsky.app/profile/example.bsky.social/post/receipt",
        )

    monkeypatch.setattr(BlueskyPublisher, "publish", fake_publish)
    failed = client.post(f"/api/schedules/{schedule_id}/publish-now", headers=auth)
    assert failed.status_code == 200, failed.text
    assert failed.json()["data"]["status"] == "FAILED"
    with SessionLocal() as db:
        assert (
            db.get(PublishSchedule, schedule_id).publish_package_json["blueskyRkey"]
            == record_keys[0]
        )
    published = client.post(f"/api/schedules/{schedule_id}/retry", headers=auth)
    assert published.status_code == 200, published.text
    assert published.json()["data"]["status"] == "PUBLISHED"
    assert published.json()["data"]["externalId"].startswith("at://")
    assert len(record_keys) == 2 and record_keys[0] == record_keys[1]
    with SessionLocal() as db:
        assert (
            db.get(PublishSchedule, schedule_id).publish_package_json["blueskyRkey"]
            == record_keys[0]
        )


@pytest.mark.asyncio
async def test_bluesky_rejects_malformed_session_and_other_accounts_receipt(monkeypatch):
    async def fake_request(_self, method, url, **kwargs):
        return _response(method, url, [])

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)
    with SessionLocal() as db:
        publisher = BlueskyPublisher(db, _account(db))
        result = await publisher.validate_credentials()
        assert result.error_code == "INVALID_SESSION"
        receipt = publisher._published(
            {"uri": "at://did:plc:other/app.bsky.feed.post/key", "cid": "cid"}, DID, "key"
        )
        assert receipt.error_code == "INVALID_RECEIPT"


@pytest.mark.asyncio
async def test_bluesky_retry_rejects_previously_published_different_image(monkeypatch):
    async def fake_request(_self, method, url, **kwargs):
        return _response(
            method,
            url,
            {
                "uri": f"at://{DID}/app.bsky.feed.post/key",
                "cid": "cid",
                "value": {
                    "text": "正文",
                    "embed": {"images": [{"alt": "", "image": {"ref": {"$link": "old-image"}}}]},
                },
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)
    with SessionLocal() as db:
        publisher = BlueskyPublisher(db, _account(db))
        result = await publisher._existing(
            DID, "key", "正文", [{"alt": "", "image": {"ref": {"$link": "new-image"}}}]
        )
        assert result.error_code == "TASK_ALREADY_PUBLISHED"
