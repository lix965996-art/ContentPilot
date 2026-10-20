"""Two real adapter workflows with isolated storage and mocked HTTP only."""

import struct
import uuid
import zlib
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import httpx
import pytest
from sqlalchemy import select

from app.core.credentials import encrypt_json, encrypt_secret
from app.db.session import SessionLocal
from app.models.business import PlatformAccount, PublishSchedule
from app.publishers import mastodon as mastodon_module


def _png():
    def chunk(kind, body):
        return (
            struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00\xff"))
        + chunk(b"IEND", b"")
    )


def _configure(platform):
    with SessionLocal() as db:
        account = db.scalar(select(PlatformAccount).where(PlatformAccount.platform == platform))
        if not account:
            account = PlatformAccount(platform=platform, user_id=1, account_name="API test")
            db.add(account)
        account.status = "CONNECTED"
        account.publish_mode = "REAL_API"
        account.capabilities_json = ["TEXT_PUBLISH", "IMAGE_PUBLISH", "STATUS_READ"]
        account.access_token_encrypted = encrypt_secret("isolated-api-test-token")
        account.token_expires_at = datetime.now() + timedelta(days=1)
        config = {"allow_public_publish": True}
        if platform == "BLUESKY":
            account.auth_type = "APP_PASSWORD"
            config.update(bluesky_did="did:plc:workflow", bluesky_handle="workflow.bsky.social")
        else:
            account.auth_type = "ACCESS_TOKEN"
            config.update(instance_url="https://mastodon.social", mastodon_account_id="42")
        account.credentials_encrypted = encrypt_json(config)
        db.commit()
        return account.id


@pytest.mark.parametrize("platform", ["BLUESKY", "MASTODON"])
def test_generated_approved_image_post_and_lost_response_do_not_duplicate(
    client, login_as, monkeypatch, platform
):
    client.base_url = "http://127.0.0.1"
    auth = {"Authorization": "Bearer " + login_as("operator", "Operator@123456")["access_token"]}
    account_id = _configure(platform)
    calls, posts = [], {}

    async def public_instance(value):
        assert value == "https://mastodon.social"
        return value

    async def transport(_self, method, url, **kwargs):
        path = urlsplit(str(url)).path
        calls.append((method, path))

        def response(body, status=200):
            return httpx.Response(status, json=body, request=httpx.Request(method, url))

        if path.endswith("uploadBlob"):
            assert kwargs["content"] == _png()
            return response({"blob": {"ref": {"$link": "test-blob"}, "mimeType": "image/png"}})
        if path.endswith("getRecord"):
            key = kwargs["params"]["rkey"]
            return (
                response(posts[key]) if key in posts else response({"error": "RecordNotFound"}, 400)
            )
        if path.endswith("createRecord"):
            payload = kwargs["json"]
            key = payload["rkey"]
            assert key not in posts
            posts[key] = {
                "uri": f"at://did:plc:workflow/app.bsky.feed.post/{key}",
                "cid": "test-cid",
                "value": payload["record"],
            }
            assert payload["record"]["embed"]["images"]
            raise httpx.ReadTimeout("receipt lost", request=httpx.Request(method, url))
        if path == "/api/v2/media":
            assert kwargs["files"]["file"][1] == _png()
            return response({"id": "8", "url": "https://mastodon.social/media/test.png"})
        if path == "/api/v1/statuses":
            key = kwargs["headers"]["Idempotency-Key"]
            assert kwargs["json"]["media_ids"] == ["8"]
            if key not in posts:
                posts[key] = {
                    "id": "1234567",
                    "url": "https://mastodon.social/@workflow/1234567",
                    "account": {"id": "42"},
                    "visibility": "public",
                }
                raise httpx.ReadTimeout("receipt lost", request=httpx.Request(method, url))
            return response(posts[key])
        if path == "/api/v1/media/8":
            return response({"id": "8", "url": "https://mastodon.social/media/test.png"})
        pytest.fail(f"Unexpected external request: {method} {path}")

    monkeypatch.setattr(mastodon_module, "ensure_public_instance", public_instance)
    monkeypatch.setattr(httpx.AsyncClient, "request", transport)
    created = client.post(
        "/api/articles",
        headers=auth,
        json={
            "title": "完整发布验证",
            "source_text": "这是一篇用于验证内容生成和图文发布的原创文章。",
        },
    )
    assert created.status_code == 200, created.text
    article_id = created.json()["data"]["id"]
    generated = client.post(
        "/api/generation/content",
        headers=auth,
        json={"article_id": article_id, "platforms": [platform]},
    )
    assert generated.status_code == 200, generated.text
    variants = client.get(f"/api/articles/{article_id}/variants", headers=auth).json()["data"]
    assert len(variants) == 1
    variant = variants[0]
    approved = client.post(
        f"/api/variants/{variant['id']}/approve",
        headers=auth,
        json={"expected_fingerprint": variant["contentFingerprint"]},
    )
    assert approved.status_code == 200, approved.text
    uploaded = client.post(
        "/api/media/upload",
        headers=auth,
        data={"article_id": str(article_id), "usage_type": "COVER"},
        files={"file": ("test.png", _png(), "image/png")},
    )
    assert uploaded.status_code == 200, uploaded.text
    payload = {
        "article_id": article_id,
        "variant_id": variant["id"],
        "platform": platform,
        "account_id": account_id,
        "publish_mode": "REAL_API",
        "scheduled_at": (datetime.now() + timedelta(days=90)).isoformat(),
        "idempotency_key": str(uuid.uuid4()),
    }
    scheduled = client.post("/api/schedules", headers=auth, json=payload)
    assert scheduled.status_code == 200, scheduled.text
    task_id = scheduled.json()["data"]["id"]
    replay = client.post("/api/schedules", headers=auth, json=payload)
    assert replay.status_code == 200 and replay.json()["data"]["id"] == task_id
    published = client.post(f"/api/schedules/{task_id}/publish-now", headers=auth)
    assert published.status_code == 200, published.text
    if platform == "MASTODON":
        assert published.json()["data"]["status"] == "FAILED"
        published = client.post(f"/api/schedules/{task_id}/retry", headers=auth)
    assert published.status_code == 200, published.text
    assert published.json()["data"]["status"] == "PUBLISHED"
    assert published.json()["data"]["publishedUrl"].startswith("https://")
    before = len(calls)
    duplicate = client.post(f"/api/schedules/{task_id}/publish-now", headers=auth)
    assert duplicate.status_code == 200 and duplicate.json()["data"]["status"] == "PUBLISHED"
    assert len(calls) == before
    assert len(posts) == 1
    with SessionLocal() as db:
        saved = db.get(PublishSchedule, task_id)
        assert saved.actual_publish_at is not None
        assert saved.external_id and saved.result_mode == "REAL_API"
