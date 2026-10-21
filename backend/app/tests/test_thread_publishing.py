import uuid
from datetime import datetime, timedelta

import httpx
import pytest

from app.core.exceptions import AppException
from app.db.session import SessionLocal
from app.models.business import ContentArticle, ContentVariant, MediaAsset, PublishSchedule
from app.publishers.base import PublishResult
from app.publishers.bluesky import BlueskyPublisher, new_bluesky_record_key
from app.publishers.mastodon import MastodonPublisher
from app.services.publish_service import execute_publish
from app.services.review_fingerprint import variant_fingerprint
from app.services.thread_publishing import (
    filter_thread_assets,
    freeze_thread_definition,
    freeze_thread_reply,
    prepare_thread_publish,
    validate_thread_context,
)
from app.tests.test_bluesky_publishing import DID
from app.tests.test_bluesky_publishing import _account as blue_account
from app.tests.test_mastodon_publishing import ACCOUNT_ID, ORIGIN
from app.tests.test_mastodon_publishing import _account as masto_account


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    async def unexpected(*_args, **_kwargs):
        pytest.fail("Thread tests must never contact a real network")

    monkeypatch.setattr(httpx.AsyncClient, "request", unexpected)


def _response(method, url, data, status=200):
    return httpx.Response(status, json=data, request=httpx.Request(method, url))


def _thread(db, platform, count=3):
    account = blue_account(db) if platform == "BLUESKY" else masto_account(db)
    article = ContentArticle(title="串帖测试", source_text="原始全文", created_by=1)
    db.add(article)
    db.flush()
    rows = []
    for index in range(1, count + 1):
        variant = ContentVariant(
            article_id=article.id,
            platform=platform,
            version_no=index,
            title="",
            content_text=f"第 {index} 段正文",
            review_status="APPROVED",
        )
        db.add(variant)
        db.flush()
        variant.review_fingerprint = variant_fingerprint(variant)
        key = new_bluesky_record_key(uuid.uuid4().hex)
        external = (
            f"at://{DID}/app.bsky.feed.post/{key}" if platform == "BLUESKY" else str(9000 + index)
        )
        url = (
            f"https://bsky.app/profile/{DID}/post/{key}"
            if platform == "BLUESKY"
            else f"{ORIGIN}/@test-user/{external}"
        )
        descriptor = {"partIndex": index, "partCount": count}
        if rows:
            descriptor.update(rootScheduleId=rows[0].id, parentScheduleId=rows[-1].id)
        row = PublishSchedule(
            article_id=article.id,
            variant_id=variant.id,
            account_id=account.id,
            platform=platform,
            publish_mode="REAL_API",
            status="PUBLISHED" if index < count else "PENDING",
            result_mode="REAL_API" if index < count else None,
            external_id=external if index < count else None,
            published_url=url if index < count else None,
            scheduled_at=datetime.now() + timedelta(days=70),
            idempotency_key=uuid.uuid4().hex,
            created_by=1,
            publish_package_json={"thread": descriptor},
        )
        db.add(row)
        db.flush()
        if index > 1 and index < count:
            root, parent = rows[0], rows[-1]
            reply = (
                {
                    "root": {"uri": root.external_id, "cid": "cid-" + root.external_id},
                    "parent": {"uri": parent.external_id, "cid": "cid-" + parent.external_id},
                }
                if platform == "BLUESKY"
                else {"inReplyToId": parent.external_id}
            )
            row.publish_package_json = {**row.publish_package_json, "threadReply": reply}
        rows.append(row)
    db.commit()
    return account, rows


@pytest.mark.parametrize("platform", ["BLUESKY", "MASTODON"])
def test_thread_root_and_complete_ancestor_chain_and_no_cover_on_replies(platform):
    with SessionLocal() as db:
        _, rows = _thread(db, platform)
        root = validate_thread_context(db, rows[0])
        reply = validate_thread_context(db, rows[-1])
        assert root is not None and not root.is_reply and root.targets() is None
        assert reply is not None and reply.parent is rows[-2] and reply.root is rows[0]
        asset = MediaAsset(image_url="/uploads/test.png")
        assert filter_thread_assets(root, [asset]) == [asset]
        assert filter_thread_assets(reply, [asset]) == []
        assert prepare_thread_publish(db, rows[-1])[1] == reply.targets()


@pytest.mark.parametrize(
    "field,value",
    [
        ("article_id", -1),
        ("platform", "BLUESKY"),
        ("account_id", None),
        ("created_by", -1),
        ("publish_mode", "SIMULATED"),
        ("status", "FAILED"),
        ("result_mode", "SIMULATED"),
        ("external_id", None),
        ("published_url", "http://unsafe.test/9002"),
    ],
)
def test_thread_invalid_parent_is_rejected_without_network(field, value):
    with SessionLocal() as db:
        _, rows = _thread(db, "MASTODON")
        if field == "article_id":
            other = ContentArticle(title="其他文章", source_text="原文", created_by=1)
            db.add(other)
            db.flush()
            value = other.id
        if field == "created_by":
            value = 2
        setattr(rows[-2], field, value)
        db.flush()
        with pytest.raises(AppException, match="串帖"):
            validate_thread_context(db, rows[-1])
        db.rollback()


@pytest.mark.parametrize(
    "descriptor", [{}, {"partIndex": True, "partCount": 3}, {"partIndex": 1, "partCount": 21}]
)
def test_thread_invalid_metadata_is_rejected(descriptor):
    with SessionLocal() as db:
        _, rows = _thread(db, "MASTODON")
        rows[-1].publish_package_json = {"thread": descriptor}
        with pytest.raises(AppException):
            validate_thread_context(db, rows[-1])


def test_thread_chain_and_frozen_target_cannot_change():
    with SessionLocal() as db:
        _, rows = _thread(db, "MASTODON")
        current = rows[-1]
        freeze_thread_definition(db, current)
        frozen = {"inReplyToId": rows[-2].external_id}
        assert freeze_thread_reply(db, current, frozen) == frozen
        with pytest.raises(AppException):
            freeze_thread_reply(db, current, {"inReplyToId": rows[0].external_id})
        current.publish_package_json = {
            **current.publish_package_json,
            "thread": {
                "partIndex": 2,
                "partCount": 3,
                "rootScheduleId": rows[0].id,
                "parentScheduleId": rows[0].id,
            },
        }
        with pytest.raises(AppException, match="不能更换"):
            validate_thread_context(db, current)


@pytest.mark.asyncio
async def test_failed_parent_prevents_service_platform_write(monkeypatch):
    async def unexpected(*_args, **_kwargs):
        pytest.fail("Invalid thread must be rejected before invoking the publisher")

    monkeypatch.setattr(MastodonPublisher, "publish", unexpected)
    with SessionLocal() as db:
        _, rows = _thread(db, "MASTODON")
        rows[-2].status = "FAILED"
        db.commit()
        with pytest.raises(AppException, match="前一段"):
            await execute_publish(db, rows[-1].id)
        assert rows[-1].status == "FAILED"


@pytest.mark.asyncio
async def test_service_freezes_empty_media_for_reply_and_keeps_reply_target(monkeypatch):
    calls = []

    async def fake_publish(_self, request):
        calls.append(request)
        return PublishResult(
            True,
            "MASTODON",
            "REAL_API",
            "PUBLISHED",
            "9900",
            f"{ORIGIN}/@test-user/9900",
        )

    monkeypatch.setattr(MastodonPublisher, "publish", fake_publish)
    with SessionLocal() as db:
        _, rows = _thread(db, "MASTODON")
        current = rows[-1]
        db.add(
            MediaAsset(
                article_id=current.article_id,
                source="UPLOAD",
                image_url="/uploads/root-only.png",
                thumbnail_url="/uploads/root-only.png",
                photographer_name="",
                photographer_url="",
                search_keyword="",
                usage_type="COVER",
                selected=True,
                alt_text="只在首段显示的配图",
            )
        )
        db.commit()
        result = await execute_publish(db, current.id)
        assert result.status == "PUBLISHED"
        assert calls[0]["images"] == []
        assert calls[0]["image_alt_texts"] == []
        assert calls[0]["thread_reply"] == {"inReplyToId": rows[-2].external_id}
        assert current.publish_package_json["imageDescriptions"] == []
        assert current.publish_package_json["threadDefinition"]["partIndex"] == 3
        # The completed schedule is never submitted to the publisher a second time.
        assert (await execute_publish(db, current.id)).status == "PUBLISHED"
        assert len(calls) == 1


@pytest.mark.asyncio
async def test_bluesky_reply_payload_replay_and_changed_remote_cid_fail_closed(monkeypatch):
    with SessionLocal() as db:
        account, rows = _thread(db, "BLUESKY")
        current = rows[-1]
        context = validate_thread_context(db, current)
        assert context is not None
        rkey = new_bluesky_record_key(current.idempotency_key)
        records = {
            row.external_id: {
                "uri": row.external_id,
                "cid": "cid-" + str(row.external_id),
                "value": {
                    "text": "已发正文",
                    **(
                        {"reply": row.publish_package_json["threadReply"]}
                        if "threadReply" in row.publish_package_json
                        else {}
                    ),
                },
            }
            for row in rows[:-1]
        }
        writes = []

        async def fake(_self, method, name, **kwargs):
            if name == "com.atproto.repo.getRecord":
                uri = f"at://{DID}/app.bsky.feed.post/{kwargs['params']['rkey']}"
                return _response(
                    method,
                    "https://bsky.test/getRecord",
                    records.get(uri, {"error": "RecordNotFound"}),
                    200 if uri in records else 400,
                )
            assert name == "com.atproto.repo.createRecord"
            record = kwargs["json"]["record"]
            uri = f"at://{DID}/app.bsky.feed.post/{rkey}"
            writes.append(record)
            records[uri] = {"uri": uri, "cid": "cid-current", "value": record}
            return _response(
                method, "https://bsky.test/createRecord", {"uri": uri, "cid": "cid-current"}
            )

        monkeypatch.setattr(BlueskyPublisher, "_request", fake)
        request = {
            "schedule_id": current.id,
            "idempotency_key": current.idempotency_key,
            "record_key": rkey,
            "content": "续篇正文",
            "images": [],
            "thread_reply": context.targets(),
        }
        publisher = BlueskyPublisher(db, account)
        assert (await publisher.publish(request)).success
        assert writes[0]["reply"] == current.publish_package_json["threadReply"]
        assert (await publisher.publish(request)).success
        assert len(writes) == 1
        records[rows[0].external_id]["cid"] = "changed-cid"
        assert (await publisher.publish(request)).error_code == "THREAD_INVALID"
        assert len(writes) == 1


@pytest.mark.asyncio
async def test_mastodon_reply_payload_receipt_replay_and_wrong_target_rejected(monkeypatch):
    with SessionLocal() as db:
        account, rows = _thread(db, "MASTODON")
        current = rows[-1]
        context = validate_thread_context(db, current)
        assert context is not None
        writes = []
        wrong_reply = False

        def receipt(status_id, parent=None):
            return {
                "id": status_id,
                "url": f"{ORIGIN}/@test-user/{status_id}",
                "account": {"id": ACCOUNT_ID},
                "visibility": "public",
                "in_reply_to_id": parent,
            }

        async def fake(_self, method, name, **kwargs):
            if method == "GET":
                status_id = name.rsplit("/", 1)[-1]
                if status_id == "9001":
                    data = receipt(status_id)
                else:
                    data = receipt(status_id, "9001" if status_id == "9002" else "9002")
                if wrong_reply and status_id == "9010":
                    data["in_reply_to_id"] = "1234"
                return _response(method, ORIGIN + name, data)
            assert name == "/api/v1/statuses"
            writes.append(kwargs)
            return _response(method, ORIGIN + name, receipt("9010", "9002"))

        monkeypatch.setattr(MastodonPublisher, "_request", fake)
        request = {
            "schedule_id": current.id,
            "idempotency_key": current.idempotency_key,
            "content": "续篇正文",
            "images": [],
            "thread_reply": context.targets(),
        }
        publisher = MastodonPublisher(db, account)
        assert (await publisher.publish(request)).success
        assert writes[0]["json"]["in_reply_to_id"] == "9002"
        assert current.publish_package_json["threadReply"] == {"inReplyToId": "9002"}
        assert (await publisher.publish(request)).success
        assert len(writes) == 1
        wrong_reply = True
        assert (await publisher.publish(request)).error_code == "INVALID_RECEIPT"
        assert len(writes) == 1
