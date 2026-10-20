import pytest
from pydantic import ValidationError

from app.models.business import ContentArticle
from app.prompts.profiles import PLATFORM_PROFILES, build_generation_prompt
from app.schemas.generation import (
    DEEP_DRAFT_MODELS,
    DEEP_FINAL_MODELS,
    OUTPUT_MODELS,
    BlueskyGenerationOutput,
)
from app.services.activity_prior_service import PLATFORM_HOUR_PEAKS, default_prior_score
from app.services.generation_service import _baseline_variant, compact_bluesky_payload
from app.services.platform_content import (
    bluesky_grapheme_length,
    build_bluesky_post,
    validate_platform_publish,
)


def test_bluesky_text_matches_preview_and_uses_plain_topics():
    assert build_bluesky_post("首句", "正文", ["#AI#", " AI ", "内容运营"]) == (
        "首句\n\n正文\n\n#AI #内容运营"
    )
    assert build_bluesky_post("首句", "首句\n正文", []) == "首句\n正文"


def test_bluesky_counts_unicode_graphemes_instead_of_codepoints():
    assert bluesky_grapheme_length("中文") == 2
    assert bluesky_grapheme_length("e\u0301👨‍👩‍👧‍👦🇨🇳") == 3
    emoji_post = "👨‍👩‍👧‍👦" * 100
    assert not validate_platform_publish(
        platform="BLUESKY", title="", content=emoji_post, hashtags=[], images=[]
    )
    assert not validate_platform_publish(
        platform="BLUESKY", title="", content="中" * 300, hashtags=[], images=[]
    )


def test_bluesky_preflight_enforces_complete_post_bytes_and_images_without_truncation():
    content = "中" * 300
    assert (
        "304 个可见字符"
        in validate_platform_publish(
            platform="BLUESKY", title="", content=content, hashtags=["x"], images=[]
        )[0]
    )
    assert build_bluesky_post("", content, []) == content
    errors = validate_platform_publish(
        platform="BLUESKY", title="", content="👨‍👩‍👧‍👦" * 121, hashtags=[], images=["a"] * 5
    )
    assert "Bluesky 帖子 UTF-8 编码最多允许 3000 字节" in errors
    assert "Bluesky 帖子最多允许 4 张图片" in errors


def test_bluesky_generation_models_require_combined_post_to_fit():
    assert OUTPUT_MODELS["BLUESKY"] is BlueskyGenerationOutput
    assert "BLUESKY" in DEEP_DRAFT_MODELS and "BLUESKY" in DEEP_FINAL_MODELS
    with pytest.raises(ValidationError, match="300"):
        BlueskyGenerationOutput(title="首句", content="中" * 300, hashtags=[])
    generated = compact_bluesky_payload(
        {"title": "正文摘要", "content": "👨‍👩‍👧‍👦" * 180, "hashtags": ["话题"]}
    )
    BlueskyGenerationOutput.model_validate(generated)
    assert generated["warnings"]
    # Every remaining family emoji must still be a complete grapheme.
    assert generated["content"].replace("👨‍👩‍👧‍👦", "") == ""


def test_bluesky_profile_baseline_and_neutral_recommendation_fallback():
    article = ContentArticle(title="项目试点", source_text="项目持续八周。参与者共 320 人。")
    options = {"length": "LONG", "include_hashtags": True}
    prompt = build_generation_prompt(article, "BLUESKY", options)
    assert "300 个 Unicode 可见字符" in prompt
    assert PLATFORM_PROFILES["BLUESKY"].name == "Bluesky"
    BlueskyGenerationOutput.model_validate(_baseline_variant(article, "BLUESKY", options))
    assert PLATFORM_HOUR_PEAKS["BLUESKY"] == {}
    assert default_prior_score("BLUESKY", 0, 20) == default_prior_score("BLUESKY", 1, 20)


def test_bluesky_generate_and_edit_rejects_over_limit_draft(client, login_as):
    token = login_as("operator", "Operator@123456")["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    article = client.post(
        "/api/articles",
        headers=headers,
        json={"title": "Bluesky 流程测试", "source_text": "项目持续八周，参与者共 320 人。"},
    ).json()["data"]
    response = client.post(
        "/api/generation/content",
        headers=headers,
        json={"article_id": article["id"], "platforms": ["BLUESKY"]},
    )
    assert response.status_code == 200, response.text
    task_id = response.json()["data"]["taskId"]
    variants = client.get(f"/api/generation/tasks/{task_id}", headers=headers).json()["data"][
        "variants"
    ]
    variant = next(item for item in variants if item["platform"] == "BLUESKY")
    rejected = client.put(
        f"/api/variants/{variant['id']}",
        headers=headers,
        json={"title": "首句", "content_text": "中" * 301, "hashtags": []},
    )
    assert rejected.status_code == 400, rejected.text
    assert "300" in rejected.json()["message"]
