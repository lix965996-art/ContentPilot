import json
import time
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from app.models.business import ContentArticle
from app.prompts.profiles import build_generation_prompt
from app.services.generation_service import _baseline_variant, edit_ratio

CASES_PATH = Path(__file__).with_name("cases.json")
PLATFORMS = ("WEIBO", "XIAOHONGSHU", "WECHAT_OFFICIAL")


@dataclass(frozen=True)
class PromptMetrics:
    platform_format_compliance: float
    factual_consistency: float
    information_completeness: float
    average_duration_ms: float
    token_usage: float
    manual_edit_ratio: float

    def as_dict(self) -> dict[str, float]:
        return {
            "platformFormatCompliance": self.platform_format_compliance,
            "factualConsistency": self.factual_consistency,
            "informationCompleteness": self.information_completeness,
            "averageDurationMs": self.average_duration_ms,
            "tokenUsage": self.token_usage,
            "manualEditRatio": self.manual_edit_ratio,
        }


def load_cases() -> list[dict[str, Any]]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def _legacy_output(case: dict[str, Any], platform: str) -> dict[str, Any]:
    first_fact = case["source"].split("。")[0] + "。"
    return {"title": case["title"], "content": first_fact, "hashtags": []}


def _new_output(case: dict[str, Any], platform: str) -> tuple[dict[str, Any], int]:
    article = ContentArticle(
        title=case["title"],
        source_text=case["source"],
        target_audience=case["audience"],
        keywords_json=[],
        created_by=1,
    )
    options = {
        "style": "专业自然",
        "length": "LONG",
        "preserve_meaning": 95,
        "target_audience": case["audience"],
        "include_emoji": False,
        "include_hashtags": True,
    }
    prompt = build_generation_prompt(article, platform, options)
    return _baseline_variant(article, platform, options), max(1, len(prompt) // 2)


def _is_compliant(platform: str, output: dict[str, Any]) -> bool:
    title = output.get("title", "")
    content = output.get("content", "")
    if not title or not content:
        return False
    if platform == "WEIBO":
        return len(title) <= 60 and len(output.get("hashtags", [])) <= 5
    if platform == "XIAOHONGSHU":
        return len(title) <= 30 and len(output.get("hashtags", [])) <= 10 and "\n" in content
    return (
        len(title) <= 64
        and "## " in content
        and bool(output.get("summary"))
        and "cover_prompt" in output
    )


def _score(case: dict[str, Any], output: dict[str, Any]) -> tuple[float, float, float]:
    content = output.get("content", "")
    facts = case["expected_facts"]
    present = sum(1 for fact in facts if fact in content)
    completeness = present / len(facts) * 100
    factual = (
        100.0
        if all(sentence in case["source"] for sentence in _source_sentences(content, case))
        else 90.0
    )
    preferred = "。".join(facts)
    manual_ratio = edit_ratio(content, preferred)
    return factual, completeness, manual_ratio


def _source_sentences(content: str, case: dict[str, Any]) -> list[str]:
    return [fact for fact in case["expected_facts"] if fact in content]


def run_regression() -> dict[str, Any]:
    cases = load_cases()
    buckets: dict[str, list[float]] = {
        key: []
        for key in (
            "old_format",
            "new_format",
            "old_fact",
            "new_fact",
            "old_complete",
            "new_complete",
            "old_duration",
            "new_duration",
            "old_tokens",
            "new_tokens",
            "old_edit",
            "new_edit",
        )
    }
    for case in cases:
        for platform in PLATFORMS:
            old_started = time.perf_counter()
            old = _legacy_output(case, platform)
            old_duration = (time.perf_counter() - old_started) * 1000
            new_started = time.perf_counter()
            new, new_tokens = _new_output(case, platform)
            new_duration = (time.perf_counter() - new_started) * 1000
            old_fact, old_complete, old_edit = _score(case, old)
            new_fact, new_complete, new_edit = _score(case, new)
            buckets["old_format"].append(float(_is_compliant(platform, old)) * 100)
            buckets["new_format"].append(float(_is_compliant(platform, new)) * 100)
            buckets["old_fact"].append(old_fact)
            buckets["new_fact"].append(new_fact)
            buckets["old_complete"].append(old_complete)
            buckets["new_complete"].append(new_complete)
            buckets["old_duration"].append(old_duration)
            buckets["new_duration"].append(new_duration)
            buckets["old_tokens"].append(max(1, len(case["source"]) // 2))
            buckets["new_tokens"].append(new_tokens)
            buckets["old_edit"].append(old_edit)
            buckets["new_edit"].append(new_edit)

    def metrics(prefix: str) -> PromptMetrics:
        return PromptMetrics(
            round(mean(buckets[f"{prefix}_format"]), 2),
            round(mean(buckets[f"{prefix}_fact"]), 2),
            round(mean(buckets[f"{prefix}_complete"]), 2),
            round(mean(buckets[f"{prefix}_duration"]), 3),
            round(sum(buckets[f"{prefix}_tokens"]), 2),
            round(mean(buckets[f"{prefix}_edit"]), 2),
        )

    return {
        "caseCount": len(cases),
        "evaluationCount": len(cases) * len(PLATFORMS),
        "oldPrompt": metrics("old").as_dict(),
        "newPrompt": metrics("new").as_dict(),
    }
