"""Review decisions must describe the committed content, including its source."""

import uuid
from datetime import timedelta

import pytest

from app.api.endpoints import articles, generation
from app.core.exceptions import AppException
from app.db.session import SessionLocal
from app.models.business import ContentArticle, ContentVariant, PublishSchedule
from app.models.user import User
from app.schemas.business import ArticleUpdate, VariantUpdate
from app.services.activity_service import business_now
from app.services.publish_service import execute_publish
from app.services.review_fingerprint import variant_fingerprint


def _variant(platform="BLUESKY", *, approved=False):
    with SessionLocal() as db:
        article = ContentArticle(
            title=f"审核并发-{uuid.uuid4().hex[:8]}",
            source_text="原文预算为 100 万元，活动日期是 10 月 20 日。",
            created_by=2,
            status="APPROVED" if approved else "GENERATED",
        )
        db.add(article)
        db.flush()
        variant = ContentVariant(
            article_id=article.id,
            platform=platform,
            title="原稿标题",
            content_text="预算 100 万元，活动日期 10 月 20 日。",
            hashtags_json=[],
            review_status="APPROVED" if approved else "PENDING",
            quality_score=95 if approved else 0,
        )
        db.add(variant)
        db.flush()
        fingerprint = variant_fingerprint(variant)
        if approved:
            variant.review_fingerprint = fingerprint
        db.commit()
        return article.id, variant.id, fingerprint


def _auth(login_as, *, viewer=False):
    credentials = ("viewer", "Viewer@123456") if viewer else ("operator", "Operator@123456")
    return {"Authorization": "Bearer " + login_as(*credentials)["access_token"]}


@pytest.mark.parametrize("platform", ["BLUESKY", "MASTODON"])
def test_source_change_invalidates_review_and_preserves_published_snapshot(
    client, login_as, platform
):
    auth = _auth(login_as)
    article_id, variant_id, _ = _variant(platform, approved=True)
    snapshot = {"title": "已发布的历史标题", "content": "已发布的历史正文"}
    with SessionLocal() as db:
        schedule = PublishSchedule(
            article_id=article_id,
            variant_id=variant_id,
            platform=platform,
            scheduled_at=business_now(),
            status="PUBLISHED",
            publish_mode="REAL_API",
            idempotency_key=uuid.uuid4().hex,
            publish_package_json=snapshot,
            created_by=2,
        )
        db.add(schedule)
        db.commit()
        schedule_id = schedule.id
    response = client.put(
        f"/api/articles/{article_id}",
        headers=auth,
        json={
            "title": "更正后的原文",
            "source_text": "更正后的原文预算为 10000 万元。",
            "status": "APPROVED",
        },
    )
    assert response.status_code == 200
    with SessionLocal() as db:
        variant = db.get(ContentVariant, variant_id)
        assert variant.review_status == "PENDING"
        assert variant.review_fingerprint is None
        assert variant.quality_score == 0
        assert variant.review_detail_json["stale"] is True
        assert variant.article.status == "GENERATED"
        assert db.get(PublishSchedule, schedule_id).publish_package_json == snapshot
    scheduled = client.post(
        "/api/schedules",
        headers=auth,
        json={
            "article_id": article_id,
            "variant_id": variant_id,
            "platform": platform,
            "publish_mode": "REAL_API",
            "scheduled_at": (business_now() + timedelta(hours=2)).isoformat(),
        },
    )
    assert scheduled.status_code == 409
    assert scheduled.json()["code"] == 40909


@pytest.mark.parametrize("platform", ["BLUESKY", "MASTODON"])
@pytest.mark.asyncio
async def test_publish_rechecks_current_approval_before_adapter(platform):
    article_id, variant_id, _ = _variant(platform, approved=True)
    with SessionLocal() as db:
        variant = db.get(ContentVariant, variant_id)
        # Simulate an old/third-party writer that missed invalidating its review.
        variant.article.source_text = "原文已更正，而旧审核还没有被撤销。"
        row = PublishSchedule(
            article_id=article_id,
            variant_id=variant_id,
            platform=platform,
            scheduled_at=business_now(),
            status="PENDING",
            publish_mode="REAL_API",
            idempotency_key=uuid.uuid4().hex,
            created_by=2,
        )
        db.add(row)
        db.commit()
        with pytest.raises(AppException) as failure:
            await execute_publish(db, row.id)
        assert failure.value.code == 40909
        assert row.status == "FAILED"


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_manual_decision_requires_the_seen_fingerprint(client, login_as, decision):
    auth = _auth(login_as)
    _, variant_id, _ = _variant()
    response = client.post(f"/api/variants/{variant_id}/{decision}", headers=auth)
    assert response.status_code == 422
    with SessionLocal() as db:
        assert db.get(ContentVariant, variant_id).review_status == "PENDING"


def test_stale_approved_record_can_be_explicitly_reviewed_again(client, login_as):
    auth = _auth(login_as)
    _, variant_id, _ = _variant(approved=True)
    with SessionLocal() as db:
        variant = db.get(ContentVariant, variant_id)
        variant.article.source_text = "旧数据中被其他入口修改过的原文内容。"
        db.commit()
        current = variant_fingerprint(variant)
    response = client.post(
        f"/api/variants/{variant_id}/approve",
        headers=auth,
        json={"expected_fingerprint": current},
    )
    assert response.status_code == 200
    assert response.json()["data"]["reviewFingerprint"] == current
    assert response.json()["data"]["qualityScore"] == 0


@pytest.mark.parametrize("change_source", [False, True])
def test_manual_approval_compare_and_commit_are_atomic(
    client, login_as, monkeypatch, change_source
):
    auth = _auth(login_as)
    article_id, variant_id, fingerprint = _variant()
    original_audit = articles.record_audit

    def inject_edit(db, request, user, action, *args, **kwargs):
        # This runs after the decision's fingerprint check, before its commit.
        if action == "APPROVE":
            with SessionLocal() as concurrent:
                actor = concurrent.get(User, user.id)
                if change_source:
                    articles.update_article(
                        article_id,
                        ArticleUpdate(
                            title="原文更正", source_text="另一个操作已经更正了原文的关键事实。"
                        ),
                        request,
                        concurrent,
                        actor,
                    )
                else:
                    articles.update_variant(
                        variant_id,
                        VariantUpdate(
                            title="新稿标题", content_text="另一个操作保存的新稿正文。", hashtags=[]
                        ),
                        request,
                        concurrent,
                        actor,
                    )
        original_audit(db, request, user, action, *args, **kwargs)

    monkeypatch.setattr(articles, "record_audit", inject_edit)
    response = client.post(
        f"/api/variants/{variant_id}/approve",
        headers=auth,
        json={"expected_fingerprint": fingerprint},
    )
    assert response.status_code == 409
    assert response.json()["code"] == 40908
    with SessionLocal() as db:
        variant = db.get(ContentVariant, variant_id)
        assert variant.review_status == "PENDING"
        assert variant.review_fingerprint is None
        if change_source:
            assert "更正" in variant.article.source_text
        else:
            assert variant.content_text == "另一个操作保存的新稿正文。"


def test_ai_review_commit_cannot_overwrite_a_later_edit(client, login_as, monkeypatch):
    auth = _auth(login_as)
    _, variant_id, _ = _variant()
    original_commit = generation.commit_content_change

    def inject_edit(db, *, code):
        with SessionLocal() as concurrent:
            variant = concurrent.get(ContentVariant, variant_id)
            variant.content_text = "评审校验之后、提交之前保存的新正文。"
            concurrent.commit()
        original_commit(db, code=code)

    monkeypatch.setattr(generation, "commit_content_change", inject_edit)
    response = client.post("/api/generation/review", headers=auth, json={"article_id": variant_id})
    assert response.status_code == 409
    assert response.json()["code"] == 40907
    with SessionLocal() as db:
        variant = db.get(ContentVariant, variant_id)
        assert variant.content_text == "评审校验之后、提交之前保存的新正文。"
        assert variant.quality_score == 0
        assert variant.review_fingerprint is None


@pytest.mark.parametrize("endpoint", ["keywords", "review"])
def test_viewer_cannot_start_paid_or_mutating_ai_actions(client, login_as, monkeypatch, endpoint):
    auth = _auth(login_as, viewer=True)
    article_id, variant_id, _ = _variant()

    async def unexpected(*args, **kwargs):
        pytest.fail("VIEWER requests must be denied before invoking the model")

    monkeypatch.setattr(generation, "extract_keywords_with_llm", unexpected)
    monkeypatch.setattr(generation, "review_variant_quality", unexpected)
    response = client.post(
        f"/api/generation/{endpoint}",
        headers=auth,
        json={"article_id": variant_id if endpoint == "review" else article_id},
    )
    assert response.status_code == 403
    assert response.json()["code"] == 40301
