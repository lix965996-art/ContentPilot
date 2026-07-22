import json

import pytest

from app.models.business import ContentArticle
from app.schemas.generation import (
    WeiboDeepDraftOutput,
)
from app.services import generation_service, trend_service
from app.services.generation_service import LlmRuntime, generate_deep_variant_data
from app.services.trend_service import aggregate_trends, parse_baidu_html


def test_parse_real_baidu_payload_shape() -> None:
    payload = {
        "data": {
            "cards": [
                {
                    "component": "hotList",
                    "content": [
                        {
                            "word": "真实热点标题",
                            "desc": "来自榜单的真实摘要字段",
                            "hotScore": "98765",
                            "rawUrl": "https://example.com/source",
                            "hotTag": "热",
                        }
                    ],
                }
            ]
        }
    }
    items = parse_baidu_html(f"<!--s-data:{json.dumps(payload, ensure_ascii=False)}-->")
    assert items[0]["title"] == "真实热点标题"
    assert items[0]["heat"] == 98765
    assert items[0]["url"] == "https://example.com/source"


@pytest.mark.asyncio
async def test_trend_source_failure_does_not_discard_other_source(monkeypatch) -> None:
    async def baidu(_limit):
        return [{"title": "仍然保留的热点", "summary": "", "source": "BAIDU"}]

    async def hacker_news(_limit):
        raise RuntimeError("来源临时不可用")

    trend_service._cache.clear()
    monkeypatch.setattr(trend_service, "fetch_baidu", baidu)
    monkeypatch.setattr(trend_service, "fetch_hacker_news", hacker_news)
    result = await aggregate_trends(refresh=True)
    assert result["items"][0]["title"] == "仍然保留的热点"
    assert [item["status"] for item in result["sources"]] == ["SUCCESS", "FAILED"]


@pytest.mark.asyncio
async def test_deep_creation_generates_candidates_then_reviews(monkeypatch) -> None:
    events: list[str] = []

    async def fake_completion(_runtime, _system, _prompt, output_model, **_kwargs):
        if output_model is WeiboDeepDraftOutput:
            payload = {
                "strategy": {
                    "angle": "从试点边界切入",
                    "hook": "结果重要，边界同样重要",
                    "reader_value": "了解如何谨慎解读试点结果",
                    "structure": ["事实", "边界"],
                    "cta": "欢迎讨论",
                },
                "candidates": [
                    {
                        "title": "候选一",
                        "content": "三个社区开展了持续八周的试点项目。",
                        "hashtags": [],
                        "warnings": [],
                    },
                    {
                        "title": "候选二",
                        "content": "320 人参与试点，结果仍需要独立复核。",
                        "hashtags": [],
                        "warnings": [],
                    },
                ],
            }
        else:
            payload = {
                "selected_candidate": 1,
                "factual_consistency": 96,
                "information_completeness": 93,
                "platform_fit": 91,
                "readability": 92,
                "format_compliance": 95,
                "non_genericness": 90,
                "issues": [],
                "improvements": ["保留独立复核限定"],
                "final": {
                    "title": "审慎看试点",
                    "content": "320 人参与了八周试点，结果仍需独立复核。",
                    "hashtags": [],
                    "warnings": [],
                },
            }
        return output_model.model_validate(payload), 30, 20, 1

    async def callback(_status, detail):
        events.append(detail["stage"])

    monkeypatch.setattr(generation_service, "_validated_completion", fake_completion)
    article = ContentArticle(
        title="试点项目",
        source_text="项目在三个社区开展试点，持续八周，参与者 320 人，结果仍需独立复核。",
        keywords_json=[],
        created_by=1,
    )
    result = await generate_deep_variant_data(
        object(),
        article,
        "WEIBO",
        {"generation_mode": "DEEP", "creative_goal": "知识分享"},
        {"core_thesis": "试点结果需谨慎解读"},
        status_callback=callback,
        runtime=LlmRuntime("test", "key", "https://example.test", "model"),
    )
    assert result.data["title"] == "审慎看试点"
    assert result.candidate_titles == ["候选一", "候选二"]
    assert result.selected_candidate == 1
    assert "PLANNING_STRATEGY" in events
    assert "REVIEWING_AND_REFINING" in events
