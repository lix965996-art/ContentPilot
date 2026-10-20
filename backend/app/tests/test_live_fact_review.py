import pytest

from app.db.session import SessionLocal
from app.models.business import ContentArticle, ContentVariant
from app.schemas.generation import QualityReviewOutput
from app.services import generation_service
from app.services.fact_check_service import factual_conflicts
from app.services.generation_service import LlmRuntime, review_variant_quality, rule_quality_review

SOURCE = "项目预算为100万元，发布日期为10月20日。项目面向校园师生开展人工智能课程。"
WRONG = SOURCE.replace("100", "900").replace("10月20日", "12月31日")


@pytest.mark.parametrize("platform", ["BLUESKY", "MASTODON", "WEIBO"])
def test_actual_review_flags_changed_numbers_and_dates(platform):
    review = rule_quality_review(
        ContentArticle(title="课程项目", source_text=SOURCE),
        platform,
        {"title": "课程项目", "content": WRONG, "hashtags": []},
    )
    assert review["factual_consistency"] == 0
    assert review["factCheckStatus"] == "CONFLICT"
    assert review["needHumanReview"] is True
    assert any("900万元" in issue for issue in review["issues"])
    assert any("12月" in issue for issue in review["issues"])


def test_equivalent_currency_units_are_not_a_conflict():
    assert not factual_conflicts("预算为100万元。", "预算为1000000元。")
    assert factual_conflicts("预算为100万元。", "预算为100美元。")
    assert factual_conflicts("比例为10%。", "增长了10个百分点。")


def test_negation_and_new_numbers_require_review():
    assert factual_conflicts("活动不收取报名费。", "活动收取报名费。")
    assert factual_conflicts("项目仍在筹备。", "项目已有300人参加。")


@pytest.mark.asyncio
async def test_rule_fallback_never_claims_semantic_verification(monkeypatch):
    monkeypatch.setattr(
        generation_service, "load_llm_runtime", lambda _: LlmRuntime("", "", "", "")
    )
    article = ContentArticle(title="课程项目", source_text=SOURCE)
    variant = ContentVariant(platform="BLUESKY", title="课程项目", content_text=SOURCE)
    result, provider = await review_variant_quality(object(), article, variant)
    assert provider == "RULE_FALLBACK"
    assert result["factual_consistency"] < 100
    assert result["needHumanReview"] is True
    assert result["reviewSource"] == "RULES"


@pytest.mark.asyncio
async def test_optimistic_model_cannot_cancel_detected_conflict(monkeypatch):
    monkeypatch.setattr(
        generation_service,
        "load_llm_runtime",
        lambda _: LlmRuntime("mock", "key", "https://model.test", "test-model"),
    )

    async def optimistic_model(*args, **kwargs):
        return (
            QualityReviewOutput(
                factual_consistency=100,
                information_completeness=100,
                platform_fit=100,
                readability=100,
                format_compliance=100,
                issues=[],
                suggestions=[],
            ),
            10,
            10,
            1,
        )

    monkeypatch.setattr(generation_service, "_validated_completion", optimistic_model)
    article = ContentArticle(title="课程项目", source_text=SOURCE)
    variant = ContentVariant(platform="MASTODON", title="课程项目", content_text=WRONG)
    result, provider = await review_variant_quality(object(), article, variant)
    assert provider == "mock"
    assert result["factual_consistency"] == 0
    assert result["semanticReview"]["factual_consistency"] == 100
    assert result["needHumanReview"] is True
    assert result["factCheckIssues"]


@pytest.mark.parametrize("platform", ["BLUESKY", "MASTODON"])
def test_actual_review_endpoint_persists_conflict_and_requires_human(
    client, login_as, monkeypatch, platform
):
    monkeypatch.setattr(
        generation_service, "load_llm_runtime", lambda _: LlmRuntime("", "", "", "")
    )
    auth = {"Authorization": "Bearer " + login_as("operator", "Operator@123456")["access_token"]}
    with SessionLocal() as db:
        article = ContentArticle(title="课程项目", source_text=SOURCE, created_by=2)
        db.add(article)
        db.flush()
        variant = ContentVariant(
            article_id=article.id,
            platform=platform,
            title="课程项目",
            content_text=WRONG,
        )
        db.add(variant)
        db.commit()
        variant_id = variant.id
    response = client.post("/api/generation/review", headers=auth, json={"article_id": variant_id})
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["factualConsistency"] == 0
    assert data["needHumanReview"] is True
    assert data["factCheckStatus"] == "CONFLICT"
    with SessionLocal() as db:
        detail = db.get(ContentVariant, variant_id).review_detail_json
        assert detail["provider"] == "RULE_FALLBACK"
        assert detail["factCheckIssues"] and detail["needHumanReview"] is True


def test_deep_generation_saved_review_cannot_average_away_a_conflict():
    with SessionLocal() as db:
        article = ContentArticle(title="课程项目", source_text=SOURCE, created_by=2)
        db.add(article)
        db.flush()
        result = generation_service.GenerationResult(
            data={"title": "课程项目", "content": WRONG, "hashtags": []},
            model_name="mock",
            provider="mock",
            duration_ms=1,
            prompt_tokens=10,
            completion_tokens=10,
            attempts=1,
            review_detail={
                "factual_consistency": 100,
                "information_completeness": 100,
                "platform_fit": 100,
                "readability": 100,
                "format_compliance": 100,
                "issues": [],
                "improvements": [],
            },
        )
        saved = generation_service.save_variant(db, article, "BLUESKY", result)
        assert saved.review_detail_json["factual_consistency"] == 0
        assert saved.review_detail_json["needHumanReview"] is True
        assert saved.review_detail_json["reviewSource"] == "MODEL_AND_RULES"
        db.rollback()
