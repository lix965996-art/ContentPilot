import json
import time
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from app.models.business import ContentArticle
from app.prompts.profiles import build_generation_prompt
from app.services.fact_check_service import factual_conflicts as _contradictions
from app.services.generation_service import _baseline_variant, edit_ratio
from app.services.platform_content import build_x_post, x_weighted_length

CASES_PATH = Path(__file__).with_name("cases.json")
PLATFORMS = ("WEIBO", "X", "XIAOHONGSHU", "WECHAT_OFFICIAL", "TOUTIAO")


@dataclass(frozen=True)
class PromptMetrics:
    platform_format_compliance: float
    factual_consistency: float | None
    information_completeness: float | None
    average_duration_ms: float
    token_usage: float
    manual_edit_ratio: float

    def as_dict(self) -> dict[str, float | None]:
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
    if platform == "X":
        post = build_x_post(title, content, output.get("hashtags", []))
        return x_weighted_length(post) <= 280 and len(output.get("hashtags", [])) <= 4
    if platform == "XIAOHONGSHU":
        return len(title) <= 20 and len(output.get("hashtags", [])) <= 10 and "\n" in content
    if platform == "TOUTIAO":
        return (
            2 <= len(title) <= 30
            and "\n" in content
            and bool(output.get("summary"))
            and "cover_prompt" in output
        )
    return (
        len(title) <= 64
        and "\n" in content
        and bool(output.get("summary"))
        and "cover_prompt" in output
    )


def _score(
    case: dict[str, Any], output: dict[str, Any]
) -> tuple[float | None, float | None, float, dict[str, Any]]:
    content = output.get("content", "")
    facts = case.get("expected_facts", [])
    present = [fact for fact in facts if fact in content]
    missing = [fact for fact in facts if fact not in content]
    completeness = (len(present) / len(facts) * 100) if facts else None
    contradictions = _contradictions(case.get("source", ""), content, facts)
    if not facts:
        factual = None
    elif contradictions:
        factual = max(0.0, 100.0 - 50.0 * len(contradictions))
    elif not present:
        # No expected fact is covered: there is no positive evidence that the
        # output is correct. Do not turn an empty intersection into "100".
        factual = None
    else:
        factual = 100.0
    preferred = "。".join(facts)
    manual_ratio = edit_ratio(content, preferred)
    evidence = {
        "presentFacts": present,
        "missingFacts": missing,
        "contradictions": contradictions,
    }
    return factual, completeness, manual_ratio, evidence


def run_regression() -> dict[str, Any]:
    cases = load_cases()
    buckets: dict[str, list[float | None]] = {
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
    issues: list[dict[str, Any]] = []
    for case in cases:
        for platform in PLATFORMS:
            old_started = time.perf_counter()
            old = _legacy_output(case, platform)
            old_duration = (time.perf_counter() - old_started) * 1000
            new_started = time.perf_counter()
            new, new_tokens = _new_output(case, platform)
            new_duration = (time.perf_counter() - new_started) * 1000
            old_fact, old_complete, old_edit, old_evidence = _score(case, old)
            new_fact, new_complete, new_edit, new_evidence = _score(case, new)
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
            for prompt_name, factual, completeness, evidence in (
                ("oldPrompt", old_fact, old_complete, old_evidence),
                ("newPrompt", new_fact, new_complete, new_evidence),
            ):
                if factual is None or evidence["contradictions"] or evidence["missingFacts"]:
                    issues.append(
                        {
                            "caseId": case["id"],
                            "platform": platform,
                            "prompt": prompt_name,
                            "factualConsistency": factual,
                            "informationCompleteness": completeness,
                            **evidence,
                        }
                    )

    def metrics(prefix: str) -> PromptMetrics:
        def values(key: str) -> list[float]:
            return [value for value in buckets[key] if value is not None]

        fact_values = values(f"{prefix}_fact")
        complete_values = values(f"{prefix}_complete")
        return PromptMetrics(
            round(mean(values(f"{prefix}_format")), 2),
            round(mean(fact_values), 2) if fact_values else None,
            round(mean(complete_values), 2) if complete_values else None,
            round(mean(values(f"{prefix}_duration")), 3),
            round(sum(values(f"{prefix}_tokens")), 2),
            round(mean(values(f"{prefix}_edit")), 2),
        )

    return {
        "caseCount": len(cases),
        "evaluationCount": len(cases) * len(PLATFORMS),
        "oldPrompt": metrics("old").as_dict(),
        "newPrompt": metrics("new").as_dict(),
        "factualUnknownCount": sum(
            1 for value in buckets["old_fact"] + buckets["new_fact"] if value is None
        ),
        "contradictionCount": sum(1 for issue in issues if issue["contradictions"]),
        "issues": issues,
    }
