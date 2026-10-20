import pytest
from pydantic import ValidationError

from app.models.business import ContentArticle
from app.prompts.profiles import PLATFORM_PROFILES, build_generation_prompt
from app.schemas.generation import (
    DEEP_DRAFT_MODELS,
    DEEP_FINAL_MODELS,
    OUTPUT_MODELS,
    MastodonGenerationOutput,
)
from app.services import activity_estimation_service
from app.services.activity_prior_service import PLATFORM_HOUR_PEAKS, default_prior_score
from app.services.content_schedule_profile_service import rule_based_profile
from app.services.generation_service import _baseline_variant, compact_mastodon_payload
from app.services.history_import_service import parse_rows
from app.services.platform_content import (
    build_mastodon_post,
    mastodon_text_length,
    validate_platform_publish,
)


def test_mastodon_builds_exact_plain_text_without_duplicate_hook():
    assert build_mastodon_post("首句", "正文", ["#AI#", " AI ", "内容运营"]) == (
        "首句\n\n正文\n\n#AI #内容运营"
    )
    assert build_mastodon_post("首句", "首句\n正文", []) == "首句\n正文"


def test_mastodon_count_uses_graphemes_and_instance_url_reservation():
    assert mastodon_text_length("中文e\u0301👨‍👩‍👧‍👦🇨🇳") == 5
    assert mastodon_text_length("https://example.org/" + "x" * 1000) == 23
    assert mastodon_text_length("（https://example.org/a）。") == 26
    assert mastodon_text_length("https://a.example。 https://b.example!", 10) == 23
    assert mastodon_text_length("中文 https://example.org?a=b&c=d", 30) == 33
    # Keep remote domains conservatively rather than claiming exact mention extraction.
    assert mastodon_text_length("@user@example.org") == len("@user@example.org")


def test_mastodon_preflight_checks_combined_post_and_media_without_truncation():
    content = "中" * 500
    assert not validate_platform_publish(
        platform="MASTODON", title="", content=content, hashtags=[], images=[]
    )
    errors = validate_platform_publish(
        platform="MASTODON", title="", content=content, hashtags=["x"], images=["a"] * 5
    )
    assert any("504" in error for error in errors)
    assert "Mastodon 帖子默认最多允许 4 张图片" in errors
    assert build_mastodon_post("", content, []) == content
    assert not validate_platform_publish(
        platform="MASTODON",
        title="",
        content="中" * 476 + " " + "https://example.org/" + "x" * 600,
        hashtags=[],
        images=[],
    )


def test_mastodon_generation_models_validate_and_compact_whole_graphemes_and_urls():
    assert OUTPUT_MODELS["MASTODON"] is MastodonGenerationOutput
    assert "MASTODON" in DEEP_DRAFT_MODELS and "MASTODON" in DEEP_FINAL_MODELS
    with pytest.raises(ValidationError, match="500"):
        MastodonGenerationOutput(title="首句", content="中" * 500, hashtags=[])
    url = "https://example.org/" + "x" * 1000
    generated = compact_mastodon_payload(
        {"title": "事实摘要", "content": url + " " + "👨‍👩‍👧‍👦" * 600, "hashtags": ["话题"]}
    )
    MastodonGenerationOutput.model_validate(generated)
    assert generated["warnings"]
    assert generated["content"].startswith(url)
    assert generated["content"].removeprefix(url).strip().replace("👨‍👩‍👧‍👦", "") == ""


def test_mastodon_profile_baseline_and_import_preserve_platform_identity():
    article = ContentArticle(title="项目试点", source_text="项目持续八周。参与者共 320 人。")
    options = {"length": "LONG", "include_hashtags": True}
    prompt = build_generation_prompt(article, "MASTODON", options)
    assert "500 个计数字符" in prompt and "23 个字符" in prompt
    assert PLATFORM_PROFILES["MASTODON"].name == "Mastodon"
    MastodonGenerationOutput.model_validate(_baseline_variant(article, "MASTODON", options))
    profile = rule_based_profile(article, [], ["MASTODON", "BLUESKY"])
    assert profile.platform_priority == ["MASTODON", "BLUESKY"]
    imported = parse_rows(
        [{"platform": "MASTODON", "publish_time": "2026-10-18 10:00:00", "likes": "5"}],
        {"platform": "platform", "publish_time": "publish_time", "likes": "likes"},
    )
    assert imported["validRows"] == 1
    assert imported["rows"][0]["platform"] == "MASTODON"
    assert PLATFORM_HOUR_PEAKS["MASTODON"] == {}
    assert default_prior_score("MASTODON", 0, 20) == default_prior_score("MASTODON", 1, 20)


def test_mastodon_empty_history_does_not_claim_platform_statistics(monkeypatch):
    monkeypatch.setattr(activity_estimation_service, "load_rows", lambda *_args, **_kwargs: [])
    result = activity_estimation_service.estimate(
        None, platform="MASTODON", account_id=None, similarity_by_row={}
    )
    assert result["platformSampleCount"] == 0
    assert result["accountSampleCount"] == 0
    assert result["confidence"] == "LOW"
    assert result["primaryLevel"] == "SYSTEM_DEFAULT"
    assert "人工规则" in result["primaryLevelLabel"]
    assert "尚未导入 Mastodon" in result["platformEvidenceNote"]
    assert all(entry["observationWeight"] == 0 for entry in result["slots"].values())


def test_mastodon_generation_and_edit_rejects_over_limit_draft(client, login_as):
    token = login_as("operator", "Operator@123456")["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    article = client.post(
        "/api/articles",
        headers=headers,
        json={"title": "Mastodon 流程测试", "source_text": "项目持续八周，参与者共 320 人。"},
    ).json()["data"]
    response = client.post(
        "/api/generation/content",
        headers=headers,
        json={"article_id": article["id"], "platforms": ["MASTODON"]},
    )
    assert response.status_code == 200, response.text
    task_id = response.json()["data"]["taskId"]
    variants = client.get(f"/api/generation/tasks/{task_id}", headers=headers).json()["data"][
        "variants"
    ]
    variant = next(item for item in variants if item["platform"] == "MASTODON")
    rejected = client.put(
        f"/api/variants/{variant['id']}",
        headers=headers,
        json={"title": "首句", "content_text": "中" * 501, "hashtags": []},
    )
    assert rejected.status_code == 400, rejected.text
    assert "500" in rejected.json()["message"]
