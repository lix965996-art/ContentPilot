import time

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import AppException
from app.models.business import ContentArticle, ContentVariant
from app.prompts.profiles import PLATFORM_PROFILES, PROMPT_VERSION, build_generation_prompt
from app.schemas.generation import QualityReviewOutput, WeiboGenerationOutput
from app.services import generation_service
from app.services.generation_service import (
    GenerationResult,
    LlmRuntime,
    _validated_completion,
    count_emoji,
    edit_ratio,
    extract_keywords_with_llm,
    markdown_to_safe_html,
    review_variant_quality,
)


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_article(client: TestClient, auth: dict[str, str], suffix: str) -> int:
    response = client.post(
        "/api/articles",
        headers=auth,
        json={
            "title": f"生成管线测试 {suffix}",
            "source_text": (
                "项目在三个社区开展试点。试点持续八周。参与者共 320 人。"
                "项目方强调结果仍需独立复核。"
            ),
            "target_audience": "社区运营者",
            "tone": "专业自然",
        },
    )
    assert response.status_code == 200
    return response.json()["data"]["id"]


def test_user_options_are_written_into_prompt() -> None:
    article = ContentArticle(
        title="提示词参数测试",
        source_text="原文包含明确事实，不应被模型改写成虚构经历。",
        target_audience="默认读者",
        keywords_json=[],
        created_by=1,
    )
    prompt = build_generation_prompt(
        article,
        "WEIBO",
        {
            "style": "轻松亲切",
            "length": "LONG",
            "preserve_meaning": 95,
            "target_audience": "高校新媒体编辑",
            "include_emoji": False,
            "include_hashtags": False,
        },
    )
    for expected in (
        "style（表达风格）：轻松亲切",
        "length（内容长度）：LONG",
        "preserve_meaning（原意保留程度）：95/100",
        "target_audience（目标受众）：高校新媒体编辑",
        "emoji（是否使用 Emoji）：禁止使用",
        "hashtags（是否生成标签）：禁止生成",
    ):
        assert expected in prompt
    assert len(PLATFORM_PROFILES) == 3
    assert PROMPT_VERSION == "2.0.0"


@pytest.mark.asyncio
async def test_structured_output_validation_retries(monkeypatch) -> None:
    responses = iter(
        [
            ('{"title":"缺少正文"}', 10, 2),
            (
                '{"title":"有效标题","content":"这是通过字段校验的有效微博正文。",'
                '"hashtags":["#测试#"],"warnings":[]}',
                12,
                8,
            ),
        ]
    )

    async def fake_chat(*_args, **_kwargs):
        return next(responses)

    monkeypatch.setattr(generation_service, "_chat_completion", fake_chat)
    result, prompt_tokens, completion_tokens, attempts = await _validated_completion(
        LlmRuntime("openai-compatible", "key", "https://example.test", "model"),
        "system",
        "user",
        WeiboGenerationOutput,
    )
    assert result.content.startswith("这是")
    assert attempts == 2
    assert prompt_tokens == 22
    assert completion_tokens == 10


def test_three_platforms_generate_in_parallel(client: TestClient, login_as, monkeypatch) -> None:
    token = login_as("operator", "Operator@123456")["access_token"]
    auth = headers(token)
    article_id = create_article(client, auth, "parallel")

    async def slow_generate(_db, article, platform, _options, *, status_callback, runtime):
        await status_callback("RUNNING", {"attempt": 1})
        await generation_service.asyncio.sleep(0.12)
        return GenerationResult(
            {
                "title": article.title,
                "content": f"{platform} 并行生成结果，保留三个社区、八周和 320 人等事实。",
                "hashtags": [],
                "warnings": [],
            },
            "parallel-test",
            runtime.provider,
            120,
            20,
            10,
            1,
        )

    monkeypatch.setattr("app.api.endpoints.generation.generate_variant_data", slow_generate)
    started = time.perf_counter()
    response = client.post(
        "/api/generation/content",
        headers=auth,
        json={
            "article_id": article_id,
            "platforms": ["WEIBO", "XIAOHONGSHU", "WECHAT_OFFICIAL"],
        },
    )
    elapsed = time.perf_counter() - started
    assert response.status_code == 200
    task = client.get(
        f"/api/generation/tasks/{response.json()['data']['taskId']}", headers=auth
    ).json()["data"]
    assert task["status"] == "SUCCESS"
    assert len(task["variants"]) == 3
    assert all(item["status"] == "SUCCESS" for item in task["platformStatusJson"].values())
    assert elapsed < 0.32


def test_platform_failure_preserves_other_results(
    client: TestClient, login_as, monkeypatch
) -> None:
    token = login_as("operator", "Operator@123456")["access_token"]
    auth = headers(token)
    article_id = create_article(client, auth, "partial")

    async def partly_failing(_db, article, platform, _options, *, status_callback, runtime):
        await status_callback("RUNNING", {"attempt": 1})
        if platform == "XIAOHONGSHU":
            raise RuntimeError("isolated platform failure")
        return GenerationResult(
            {
                "title": article.title,
                "content": f"{platform} 成功结果，其他平台失败不影响本结果。",
                "hashtags": [],
                "warnings": [],
            },
            "partial-test",
            runtime.provider,
            10,
            10,
            10,
            1,
        )

    monkeypatch.setattr("app.api.endpoints.generation.generate_variant_data", partly_failing)
    response = client.post(
        "/api/generation/content",
        headers=auth,
        json={
            "article_id": article_id,
            "platforms": ["WEIBO", "XIAOHONGSHU", "WECHAT_OFFICIAL"],
        },
    )
    task_id = response.json()["data"]["taskId"]
    task = client.get(f"/api/generation/tasks/{task_id}", headers=auth).json()["data"]
    assert task["status"] == "PARTIAL_SUCCESS"
    assert len(task["variants"]) == 2
    assert task["platformStatusJson"]["XIAOHONGSHU"]["status"] == "FAILED"
    assert task["platformStatusJson"]["WEIBO"]["status"] == "SUCCESS"


@pytest.mark.asyncio
async def test_quality_review_combines_rules_and_real_semantic_result(monkeypatch) -> None:
    article = ContentArticle(
        title="质量评审",
        source_text="项目覆盖三个社区，持续八周，参与者 320 人。",
        target_audience="运营者",
        keywords_json=[],
        created_by=1,
    )
    variant = ContentVariant(
        article=article,
        platform="WEIBO",
        title="项目试点结果",
        content_text="项目覆盖三个社区，持续八周，参与者 320 人。",
        hashtags_json=[],
    )
    semantic = QualityReviewOutput(
        factual_consistency=96,
        information_completeness=92,
        platform_fit=88,
        readability=90,
        format_compliance=94,
        issues=[],
        suggestions=["核对最终数据"],
    )

    monkeypatch.setattr(
        generation_service,
        "load_llm_runtime",
        lambda _db: LlmRuntime("real-provider", "key", "https://example.test", "model"),
    )

    async def fake_validated(*_args, **_kwargs):
        return semantic, 10, 10, 1

    monkeypatch.setattr(generation_service, "_validated_completion", fake_validated)
    result, provider = await review_variant_quality(object(), article, variant)
    assert provider == "real-provider"
    assert result["semanticReview"]["factual_consistency"] == 96
    assert set(result) >= {
        "factual_consistency",
        "information_completeness",
        "platform_fit",
        "readability",
        "format_compliance",
    }


@pytest.mark.asyncio
async def test_keyword_extraction_falls_back_to_local_rules(monkeypatch) -> None:
    monkeypatch.setattr(
        generation_service,
        "load_llm_runtime",
        lambda _db: LlmRuntime("real-provider", "key", "https://example.test", "model"),
    )

    async def fail_validation(*_args, **_kwargs):
        raise AppException(50201, "invalid output", 502)

    monkeypatch.setattr(generation_service, "_validated_completion", fail_validation)
    keywords, provider = await extract_keywords_with_llm(object(), "人工智能用于校园内容创作")
    assert provider == "RULE_FALLBACK"
    assert keywords[0]["zh"] == "人工智能"


def test_edit_ratio_safe_html_and_emoji_count() -> None:
    assert edit_ratio("完全相同", "完全相同") == 0
    assert edit_ratio("原始内容", "彻底修改") > 50
    rendered = markdown_to_safe_html("# 标题\n\n<script>alert(1)</script>\n\n- **安全**")
    assert "<h1>标题</h1>" in rendered
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert count_emoji("你好 👨‍💻✨，测试✅") == 3


def test_history_delete_reject_and_single_platform_retry(client: TestClient, login_as) -> None:
    token = login_as("operator", "Operator@123456")["access_token"]
    auth = headers(token)
    article_id = create_article(client, auth, "history")
    task_ids = []
    for _ in range(2):
        generated = client.post(
            "/api/generation/content",
            headers=auth,
            json={"article_id": article_id, "platforms": ["WEIBO"]},
        )
        task_ids.append(generated.json()["data"]["taskId"])
    history = client.get(f"/api/articles/{article_id}/variants", headers=auth).json()["data"]
    weibo_history = [item for item in history if item["platform"] == "WEIBO"]
    assert [item["versionNo"] for item in weibo_history] == [2, 1]

    rejected = client.post(f"/api/variants/{weibo_history[0]['id']}/reject", headers=auth)
    assert rejected.json()["data"]["reviewStatus"] == "REJECTED"
    deleted = client.delete(f"/api/variants/{weibo_history[1]['id']}", headers=auth)
    assert deleted.status_code == 200

    retried = client.post(
        f"/api/generation/tasks/{task_ids[-1]}/platforms/WEIBO/retry", headers=auth
    )
    assert retried.status_code == 200
    retry_task = client.get(
        f"/api/generation/tasks/{retried.json()['data']['taskId']}", headers=auth
    ).json()["data"]
    assert retry_task["platformsJson"] == ["WEIBO"]
    assert retry_task["status"] == "SUCCESS"
    assert retry_task["provider"] == "mock"
    assert retry_task["promptVersion"] == PROMPT_VERSION
    assert retry_task["tokenUsage"] > 0
    assert retry_task["durationMs"] >= 0
