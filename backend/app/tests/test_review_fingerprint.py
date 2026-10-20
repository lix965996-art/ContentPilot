import uuid

from fastapi.testclient import TestClient

from app.api.endpoints import generation as generation_endpoint
from app.db.session import SessionLocal
from app.models.business import ContentArticle, ContentVariant
from app.services.review_fingerprint import content_fingerprint


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _make_variant(*, status="APPROVED", fingerprint: str | None = None) -> int:
    with SessionLocal() as db:
        article = ContentArticle(
            title=f"评审指纹文章-{uuid.uuid4().hex[:8]}",
            source_text="原文预算 100 万元，活动日期为 10 月 20 日。",
            created_by=1,
            status="APPROVED",
        )
        db.add(article)
        db.flush()
        variant = ContentVariant(
            article_id=article.id,
            platform="WEIBO",
            title="原标题",
            content_text="原正文",
            hashtags_json=["标签"],
            review_status=status,
            quality_score=95.0,
            review_detail_json={"factual_consistency": 100},
            review_fingerprint=fingerprint
            if fingerprint is not None
            else content_fingerprint(
                platform="WEIBO",
                title="原标题",
                content="原正文",
                hashtags=["标签"],
                source_text=article.source_text,
            ),
        )
        db.add(variant)
        db.commit()
        return variant.id


def test_normalized_save_keeps_review_and_real_edit_invalidates(client: TestClient, login_as):
    auth = _headers(login_as("operator", "Operator@123456")["access_token"])
    variant_id = _make_variant()

    normalized = client.put(
        f"/api/variants/{variant_id}",
        headers=auth,
        json={"title": "原标题", "content_text": "原正文   ", "hashtags": ["#标签"]},
    )
    assert normalized.status_code == 200
    assert normalized.json()["data"]["reviewStatus"] == "APPROVED"

    changed = client.put(
        f"/api/variants/{variant_id}",
        headers=auth,
        json={"title": "改后的标题", "content_text": "完全不同的正文", "hashtags": ["标签"]},
    )
    assert changed.status_code == 200
    data = changed.json()["data"]
    assert data["reviewStatus"] == "PENDING"
    assert data["qualityScore"] == 0
    assert data["reviewDetailJson"]["stale"] is True
    assert data["reviewFingerprint"] is None


def test_legacy_approved_without_fingerprint_is_invalidated_on_save(client: TestClient, login_as):
    auth = _headers(login_as("operator", "Operator@123456")["access_token"])
    variant_id = _make_variant(fingerprint="")

    response = client.put(
        f"/api/variants/{variant_id}",
        headers=auth,
        json={"title": "原标题", "content_text": "原正文", "hashtags": ["标签"]},
    )

    assert response.status_code == 200
    assert response.json()["data"]["reviewStatus"] == "PENDING"


def test_manual_approval_binds_the_current_content(client: TestClient, login_as):
    auth = _headers(login_as("operator", "Operator@123456")["access_token"])
    variant_id = _make_variant(status="PENDING", fingerprint="")

    with SessionLocal() as db:
        variant = db.get(ContentVariant, variant_id)
        expected = content_fingerprint(
            platform=variant.platform,
            title=variant.title,
            content=variant.content_text,
            hashtags=variant.hashtags_json,
            source_text=variant.article.source_text,
        )
    response = client.post(
        f"/api/variants/{variant_id}/approve",
        headers=auth,
        json={"expected_fingerprint": expected},
    )

    assert response.status_code == 200
    assert response.json()["data"]["reviewStatus"] == "APPROVED"
    assert response.json()["data"]["reviewFingerprint"]


def test_manual_approval_rejects_a_stale_expected_fingerprint(client: TestClient, login_as):
    auth = _headers(login_as("operator", "Operator@123456")["access_token"])
    variant_id = _make_variant(status="PENDING", fingerprint="")

    response = client.post(
        f"/api/variants/{variant_id}/approve",
        headers=auth,
        json={"expected_fingerprint": "0" * 64},
    )

    assert response.status_code == 409
    assert response.json()["code"] == 40908
    with SessionLocal() as db:
        assert db.get(ContentVariant, variant_id).review_status == "PENDING"


def test_manual_approval_accepts_the_fingerprint_the_operator_saw(client: TestClient, login_as):
    auth = _headers(login_as("operator", "Operator@123456")["access_token"])
    variant_id = _make_variant(status="PENDING", fingerprint="")
    expected = content_fingerprint(
        platform="WEIBO",
        title="原标题",
        content="原正文",
        hashtags=["标签"],
        source_text="原文预算 100 万元，活动日期为 10 月 20 日。",
    )

    response = client.post(
        f"/api/variants/{variant_id}/approve",
        headers=auth,
        json={"expected_fingerprint": expected},
    )

    assert response.status_code == 200
    assert response.json()["data"]["reviewStatus"] == "APPROVED"


def test_stale_manual_decision_cannot_overwrite_a_newer_edit(client: TestClient, login_as):
    auth = _headers(login_as("operator", "Operator@123456")["access_token"])
    variant_id = _make_variant(status="PENDING", fingerprint="")
    confirmed = content_fingerprint(
        platform="WEIBO",
        title="原标题",
        content="原正文",
        hashtags=["标签"],
        source_text="原文预算 100 万元，活动日期为 10 月 20 日。",
    )
    approved = client.post(
        f"/api/variants/{variant_id}/approve",
        headers=auth,
        json={"expected_fingerprint": confirmed},
    )
    assert approved.status_code == 200

    edited = client.put(
        f"/api/variants/{variant_id}",
        headers=auth,
        json={"title": "原标题", "content_text": "修改后的正文", "hashtags": ["标签"]},
    )
    assert edited.status_code == 200
    assert edited.json()["data"]["reviewStatus"] == "PENDING"

    stale = client.post(
        f"/api/variants/{variant_id}/approve",
        headers=auth,
        json={"expected_fingerprint": confirmed},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == 40908
    with SessionLocal() as db:
        assert db.get(ContentVariant, variant_id).review_status == "PENDING"

    current = content_fingerprint(
        platform="WEIBO",
        title="原标题",
        content="修改后的正文",
        hashtags=["标签"],
        source_text="原文预算 100 万元，活动日期为 10 月 20 日。",
    )
    fresh = client.post(
        f"/api/variants/{variant_id}/approve",
        headers=auth,
        json={"expected_fingerprint": current},
    )
    assert fresh.status_code == 200
    assert fresh.json()["data"]["reviewStatus"] == "APPROVED"


def test_variant_list_exposes_the_content_fingerprint(client: TestClient, login_as):
    auth = _headers(login_as("operator", "Operator@123456")["access_token"])
    variant_id = _make_variant(status="PENDING", fingerprint="")
    with SessionLocal() as db:
        article_id = db.get(ContentVariant, variant_id).article_id

    response = client.get(f"/api/articles/{article_id}/variants", headers=auth)

    assert response.status_code == 200
    item = next(row for row in response.json()["data"] if row["id"] == variant_id)
    assert item["contentFingerprint"] == content_fingerprint(
        platform="WEIBO",
        title="原标题",
        content="原正文",
        hashtags=["标签"],
        source_text="原文预算 100 万元，活动日期为 10 月 20 日。",
    )


def test_review_result_is_rejected_when_content_changes_mid_review(
    client: TestClient, login_as, monkeypatch
):
    auth = _headers(login_as("operator", "Operator@123456")["access_token"])
    variant_id = _make_variant(status="PENDING")

    async def fake_review(db, _article, variant):
        variant.content_text = "评审期间被并发修改的正文"
        db.commit()
        return {
            "factual_consistency": 100,
            "information_completeness": 100,
            "platform_fit": 100,
            "readability": 100,
            "format_compliance": 100,
            "issues": [],
            "suggestions": [],
        }, "RULE_BASED"

    monkeypatch.setattr(generation_endpoint, "review_variant_quality", fake_review)

    response = client.post(
        "/api/generation/review",
        headers=auth,
        json={"article_id": variant_id},
    )

    assert response.status_code == 409
    assert response.json()["code"] == 40907
