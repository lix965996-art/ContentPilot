"""LLM review of a solved cross-platform schedule plan.

The reviewer sees structured facts only (profile, per-platform content traits,
activity results, final times, constraint adjustments) and may return exactly
one of three verdicts:

    APPROVE         plan is acceptable
    REQUEST_RESOLVE plan should be re-solved under a stricter soft constraint
    MANUAL_REVIEW   an operator has to look at it

It can never emit a publish time and never writes to the database. When it asks
for a re-solve it must supply concrete new constraints (minimum gap and/or a
platform order), which the caller feeds back into CP-SAT at most once.
"""

from __future__ import annotations

import json
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.services.generation_service import _validated_completion, load_llm_runtime

REVIEW_VERSION = "plan-review-v1"
MAX_RESOLVE_ROUNDS = 1

Verdict = Literal["APPROVE", "REQUEST_RESOLVE", "MANUAL_REVIEW"]


class ResolveRequest(BaseModel):
    """New soft constraints the reviewer wants applied on the next solve."""

    minimum_cross_platform_gap_minutes: int | None = Field(default=None, ge=0, le=24 * 60)
    platform_order: list[str] = Field(default_factory=list, max_length=5)
    note: str = Field(default="", max_length=300)

    @field_validator("platform_order")
    @classmethod
    def normalize(cls, value: list[str]) -> list[str]:
        allowed = {"WEIBO", "XIAOHONGSHU", "WECHAT_OFFICIAL", "TOUTIAO", "X"}
        return [item.strip().upper() for item in value if item.strip().upper() in allowed]


class PlanReview(BaseModel):
    verdict: Verdict
    summary: str = Field(min_length=1, max_length=400)
    risks: list[str] = Field(default_factory=list, max_length=6)
    resolve_request: ResolveRequest | None = None

    @model_validator(mode="after")
    def resolve_needs_constraints(self) -> PlanReview:
        """A re-solve request is only actionable with a concrete new constraint."""
        if self.verdict != "REQUEST_RESOLVE":
            return self
        request = self.resolve_request
        if request is None or (
            request.minimum_cross_platform_gap_minutes is None and not request.platform_order
        ):
            raise ValueError("REQUEST_RESOLVE 必须提供新的最小间隔或平台顺序约束")
        return self


REVIEW_SYSTEM_PROMPT = """你是跨平台发布排期的审查员。
你会收到内容排期画像、各平台内容特点、活跃度结果、最终跨平台发布时间以及约束调整原因。

你只能做三件事之一，通过 verdict 字段表达：
- APPROVE：方案合理，可以交给用户确认
- REQUEST_RESOLVE：方案存在结构性问题，需要用更严格的软约束重新求解
- MANUAL_REVIEW：信息不足或风险较高，需要人工检查

严格禁止：
- 不要自己给出任何具体发布时间
- 不要要求修改数据库
- 不要新增 JSON 字段

只返回 JSON：
{"verdict": "...", "summary": "一段结论", "risks": ["风险点"],
 "resolve_request": {"minimum_cross_platform_gap_minutes": 数字或null,
 "platform_order": ["平台标识"], "note": "原因"}}
verdict 为 REQUEST_RESOLVE 时，resolve_request 必须给出 minimum_cross_platform_gap_minutes
或 platform_order 中至少一项。其他情况 resolve_request 可以为 null。"""


def rule_based_review(plan_facts: dict) -> PlanReview:
    """Deterministic verdict used when the LLM is unavailable."""
    scheduled = [item for item in plan_facts.get("assignments", []) if item.get("selectedTime")]
    risks: list[str] = []
    if not scheduled:
        return PlanReview(
            verdict="MANUAL_REVIEW",
            summary="联合求解没有为任何平台安排发布时间，需要人工检查约束设置。",
            risks=["所有平台候选时段均被硬约束排除"],
        )
    simultaneous = plan_facts.get("softObjectiveBreakdown", {}).get("simultaneousPairs", 0)
    if simultaneous:
        risks.append(f"仍有 {simultaneous} 对平台发布时间过于接近")
    low_confidence = [
        item["platform"] for item in scheduled if (item.get("dataConfidence") or 0) < 30
    ]
    if low_confidence:
        risks.append(f"{'、'.join(low_confidence)} 的数据置信度较低")
    return PlanReview(
        verdict="APPROVE",
        summary=(
            f"已为 {len(scheduled)} 个平台安排发布时间，硬约束全部满足；"
            "LLM 不可用，本结论由规则审查生成。"
        ),
        risks=risks,
    )


def build_plan_facts(
    *,
    profile: dict,
    platform_contents: list[dict],
    activity_summaries: list[dict],
    optimization: dict,
) -> dict:
    """Structured, time-free-decision facts handed to the reviewer."""
    return {
        "profile": profile,
        "platformContents": platform_contents,
        "activity": activity_summaries,
        "assignments": optimization.get("assignments", []),
        "hardConstraints": optimization.get("hardConstraints", []),
        "softObjectiveBreakdown": optimization.get("softObjectiveBreakdown", {}),
        "solverStatus": optimization.get("solverStatus"),
    }


async def review_plan(db: Session, plan_facts: dict) -> dict:
    """Return the serialised review verdict; never raises."""
    runtime = load_llm_runtime(db)
    if not all([runtime.api_key, runtime.base_url, runtime.model_name]):
        review = rule_based_review(plan_facts)
        return {**review.model_dump(), "provider": "RULE_BASED", "reviewVersion": REVIEW_VERSION}
    try:
        result, _, _, _ = await _validated_completion(
            runtime,
            REVIEW_SYSTEM_PROMPT,
            json.dumps(plan_facts, ensure_ascii=False, default=str),
            PlanReview,
            max_attempts=2,
            temperature=0.1,
        )
        return {
            **result.model_dump(),
            "provider": runtime.provider,
            "reviewVersion": REVIEW_VERSION,
        }
    except (AppException, httpx.HTTPError, ValidationError, ValueError, json.JSONDecodeError):
        review = rule_based_review(plan_facts)
        return {
            **review.model_dump(),
            "provider": "RULE_FALLBACK",
            "reviewVersion": REVIEW_VERSION,
        }
