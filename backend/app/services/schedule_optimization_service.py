"""Cross-platform publish-time optimisation with Google OR-Tools CP-SAT.

Each platform no longer picks its own argmax slot. Instead every platform gets a
set of future candidate slots, and one CP-SAT model chooses at most one slot per
platform under hard constraints while maximising a weighted soft objective.

Hard constraints
    H1 每个平台只能选择一个发布时间（AddExactlyOne / AtMostOne when skippable）
    H2 发布时间必须位于内容有效期内（freshness_hours）
    H3 不得使用用户禁用时段（forbidden hours）
    H4 不得与已有排期发生硬冲突（同平台 < CONFLICT_MINUTES）
    H5 同一账号发布必须满足最小间隔
    H6 缺少平台内容版本时不得创建任务（target dropped before solving）
    H7 紧急内容不得超出 freshness_hours（tightened window for IMMEDIATE/TIMELY）
    H8 用户手工锁定的时间不得修改（locked slot forced)

Soft objective (maximise)
    S1 用户活跃度
    S2 相似历史内容的时段表现
    S3 符合 LLM 跨平台发布策略（SIMULTANEOUS / STAGGERED / WATERFALL）
    S4 避免多个平台完全同时发布
    S5 保持合理的平台发布顺序（LLM platform_priority）
    S6 减少对用户已选择时间的调整
    S7 提高数据置信度

If OR-Tools is unavailable or the solver returns no feasible answer, the caller
falls back to the existing per-platform hybrid-v2 result.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.core.config import settings

try:  # pragma: no cover - import guard only
    from ortools.sat.python import cp_model

    ORTOOLS_AVAILABLE = True
except ImportError:  # pragma: no cover
    cp_model = None  # type: ignore[assignment]
    ORTOOLS_AVAILABLE = False

OPTIMIZER_VERSION = "cpsat-v1"
SLOT_MINUTES = 30
HORIZON_DAYS = 7
CONFLICT_MINUTES = 30
SIMULTANEOUS_TOLERANCE_MINUTES = 30
SOLVER_TIME_LIMIT_SECONDS = 6.0

# Soft objective weights. Values are scaled to integers inside the model because
# CP-SAT only optimises integer expressions.
OBJECTIVE_WEIGHTS = {
    "activity": 1.0,
    "semanticHistory": 0.8,
    "strategy": 0.5,
    "simultaneousPenalty": 0.9,
    "orderPenalty": 0.4,
    "userTimeDrift": 0.6,
    "confidence": 0.3,
}
SCALE = 100


@dataclass
class PlatformTarget:
    """One platform to be scheduled."""

    platform: str
    account_id: int | None
    variant_id: int | None
    # Baseline single-platform recommendation (hybrid-v2) used for S2/S6 anchors.
    original_best_time: datetime | None = None
    # Operator-locked time: the solver must keep it exactly.
    locked_time: datetime | None = None
    # Time the operator manually picked but did not lock (soft anchor for S6).
    preferred_time: datetime | None = None
    priority_rank: int = 0
    data_confidence: float = 0.0
    skippable: bool = False


@dataclass
class Candidate:
    platform: str
    at: datetime
    slot_index: int
    activity_score: float
    semantic_history_score: float
    content_scene_fit: float
    data_confidence: float
    existing_schedule_conflict: bool
    frequency_penalty: float
    candidate_status: str = "ELIGIBLE"
    reject_reason: str = ""

    def as_dict(self) -> dict:
        return {
            "platform": self.platform,
            "candidateTime": self.at.isoformat(),
            "activityScore": round(self.activity_score, 3),
            "semanticHistoryScore": round(self.semantic_history_score, 3),
            "contentSceneFit": round(self.content_scene_fit, 3),
            "dataConfidence": round(self.data_confidence, 3),
            "existingScheduleConflict": self.existing_schedule_conflict,
            "frequencyPenalty": round(self.frequency_penalty, 3),
            "candidateStatus": self.candidate_status,
            "rejectReason": self.reject_reason,
        }


@dataclass
class ExistingSchedule:
    platform: str
    account_id: int | None
    scheduled_at: datetime


@dataclass
class SolveContext:
    """Everything the optimiser needs besides per-platform candidates."""

    now: datetime
    freshness_hours: int
    urgency: str
    cross_platform_strategy: str
    minimum_gap_minutes: int
    platform_priority: list[str] = field(default_factory=list)
    forbidden_hours: list[int] = field(default_factory=list)
    min_account_gap_minutes: int = 60
    horizon_days: int = HORIZON_DAYS


def _scene_fit(hour: int, reading_mode: str, cognitive_load: str) -> float:
    """How well a slot matches the content's reading scenario (0-100)."""
    fragment_hours = {7, 8, 9, 12, 13, 17, 18, 19, 22}
    immersive_hours = {10, 11, 14, 15, 20, 21}
    reference_hours = {9, 10, 11, 14, 15, 16}
    if reading_mode == "FRAGMENT":
        base = 88.0 if hour in fragment_hours else 58.0
    elif reading_mode == "IMMERSIVE":
        base = 88.0 if hour in immersive_hours else 56.0
    else:
        base = 86.0 if hour in reference_hours else 60.0
    if cognitive_load == "HIGH" and hour in {0, 1, 2, 3, 4, 5, 23}:
        base -= 25.0
    return max(0.0, min(100.0, base))


def build_candidates(
    target: PlatformTarget,
    context: SolveContext,
    *,
    activity_slot_score,
    semantic_slot_score,
    reading_mode: str,
    cognitive_load: str,
    existing: list[ExistingSchedule],
) -> list[Candidate]:
    """Generate 30-minute candidate slots for the next 7 days for one platform.

    ``activity_slot_score(weekday, hour)`` and ``semantic_slot_score(weekday,
    hour)`` are callables so the caller can plug in the estimation service
    without this module importing it.
    """
    start = context.now.replace(second=0, microsecond=0, minute=0) + timedelta(hours=1)
    deadline = context.now + timedelta(hours=max(1, context.freshness_hours))
    horizon_end = context.now + timedelta(days=max(1, context.horizon_days))
    limit = min(deadline, horizon_end)

    candidates: list[Candidate] = []
    slot_index = 0
    moment = start
    while moment <= horizon_end:
        weekday, hour = moment.weekday(), moment.hour
        status, reason = "ELIGIBLE", ""
        # H2 / H7: content validity window.
        if moment > limit:
            status, reason = (
                "OUT_OF_FRESHNESS",
                (f"超出内容有效期（{context.freshness_hours} 小时，urgency={context.urgency}）"),
            )
        # H3: operator-disabled hours.
        elif hour in context.forbidden_hours:
            status, reason = "FORBIDDEN_HOUR", f"{hour:02d} 点属于禁用时段"

        same_platform = [
            item
            for item in existing
            if item.platform == target.platform
            and abs((item.scheduled_at - moment).total_seconds()) / 60 < CONFLICT_MINUTES
        ]
        # H5 support: same-account density becomes a hard constraint below.
        same_account = [
            item
            for item in existing
            if target.account_id
            and item.account_id == target.account_id
            and abs((item.scheduled_at - moment).total_seconds()) / 60
            < context.min_account_gap_minutes
        ]
        if same_platform and status == "ELIGIBLE":
            status, reason = "SCHEDULE_CONFLICT", "该平台同一时段已有排期"
        elif same_account and status == "ELIGIBLE":
            status, reason = (
                "ACCOUNT_GAP",
                (f"同账号 {context.min_account_gap_minutes} 分钟内已有排期"),
            )

        candidates.append(
            Candidate(
                platform=target.platform,
                at=moment,
                slot_index=slot_index,
                activity_score=float(activity_slot_score(weekday, hour)),
                semantic_history_score=float(semantic_slot_score(weekday, hour)),
                content_scene_fit=_scene_fit(hour, reading_mode, cognitive_load),
                data_confidence=target.data_confidence,
                existing_schedule_conflict=bool(same_platform),
                frequency_penalty=float(len(same_account) * 20),
                candidate_status=status,
                reject_reason=reason,
            )
        )
        slot_index += 1
        moment += timedelta(minutes=SLOT_MINUTES)

    # H8: a locked time must remain available even if the generic rules reject it.
    if target.locked_time:
        locked = target.locked_time.replace(second=0, microsecond=0)
        for candidate in candidates:
            if abs((candidate.at - locked).total_seconds()) < 60:
                candidate.candidate_status = "LOCKED"
                candidate.reject_reason = ""
                break
        else:
            candidates.append(
                Candidate(
                    platform=target.platform,
                    at=locked,
                    slot_index=slot_index,
                    activity_score=float(activity_slot_score(locked.weekday(), locked.hour)),
                    semantic_history_score=float(
                        semantic_slot_score(locked.weekday(), locked.hour)
                    ),
                    content_scene_fit=_scene_fit(locked.hour, reading_mode, cognitive_load),
                    data_confidence=target.data_confidence,
                    existing_schedule_conflict=False,
                    frequency_penalty=0.0,
                    candidate_status="LOCKED",
                    reject_reason="",
                )
            )
    return candidates


def _strategy_bonus(
    strategy: str,
    minutes_from_first: int,
    minimum_gap_minutes: int,
) -> float:
    """S3: how well a platform's offset matches the LLM's cross-platform plan."""
    if strategy == "SIMULTANEOUS":
        return max(0.0, 100.0 - minutes_from_first * 1.5)
    if strategy == "WATERFALL":
        ideal = minimum_gap_minutes or 60
        return max(0.0, 100.0 - abs(minutes_from_first - ideal) * 0.6)
    # STAGGERED: reward any separation up to a few hours.
    if minutes_from_first < minimum_gap_minutes:
        return max(0.0, 40.0 * minutes_from_first / max(1, minimum_gap_minutes))
    return max(0.0, 100.0 - (minutes_from_first - minimum_gap_minutes) * 0.25)


def optimize(
    targets: list[PlatformTarget],
    candidates_by_platform: dict[str, list[Candidate]],
    context: SolveContext,
    *,
    extra_min_gap_minutes: int | None = None,
) -> dict:
    """Solve the joint cross-platform scheduling problem.

    ``extra_min_gap_minutes`` lets the LLM plan reviewer request a re-solve with
    a stricter separation requirement without ever choosing a time itself.
    """
    started = time.perf_counter()
    if not ORTOOLS_AVAILABLE:
        return {
            "solverStatus": "ORTOOLS_UNAVAILABLE",
            "optimizerVersion": OPTIMIZER_VERSION,
            "assignments": [],
            "solveDurationMs": 0,
            "hardConstraints": [],
            "softObjectiveBreakdown": {},
            "message": "OR-Tools 不可用，已回退到 hybrid-v2 单平台推荐",
        }

    minimum_gap = max(
        context.minimum_gap_minutes,
        extra_min_gap_minutes or 0,
    )

    model = cp_model.CpModel()
    # x[(platform, index)] == 1 means that platform publishes at that candidate.
    x: dict[tuple[str, int], object] = {}
    eligible: dict[str, list[Candidate]] = {}

    hard_constraints: list[dict] = []
    for target in targets:
        pool = [
            item
            for item in candidates_by_platform.get(target.platform, [])
            if item.candidate_status in ("ELIGIBLE", "LOCKED")
        ]
        if target.locked_time:
            locked = [item for item in pool if item.candidate_status == "LOCKED"]
            pool = locked or pool
        eligible[target.platform] = pool
        for index in range(len(pool)):
            x[(target.platform, index)] = model.NewBoolVar(f"x_{target.platform}_{index}")
        if not pool:
            hard_constraints.append(
                {
                    "code": "H1",
                    "platform": target.platform,
                    "satisfied": False,
                    "description": "该平台没有可用候选时段（有效期 / 禁用时段 / 冲突全部排除）",
                }
            )
            continue
        variables = [x[(target.platform, index)] for index in range(len(pool))]
        if target.skippable:
            model.AddAtMostOne(variables)
        else:
            model.AddExactlyOne(variables)
        hard_constraints.append(
            {
                "code": "H1",
                "platform": target.platform,
                "satisfied": True,
                "description": f"{target.platform} 只能选择一个发布时间（候选 {len(pool)} 个）",
            }
        )
        if target.locked_time:
            hard_constraints.append(
                {
                    "code": "H8",
                    "platform": target.platform,
                    "satisfied": True,
                    "description": (
                        f"用户锁定时间 {target.locked_time:%Y-%m-%d %H:%M} 不参与优化调整"
                    ),
                }
            )

    solvable = [target for target in targets if eligible.get(target.platform)]
    if not solvable:
        return {
            "solverStatus": "NO_CANDIDATE",
            "optimizerVersion": OPTIMIZER_VERSION,
            "assignments": [],
            "solveDurationMs": int((time.perf_counter() - started) * 1000),
            "hardConstraints": hard_constraints,
            "softObjectiveBreakdown": {},
            "message": "所有候选时段都被硬约束排除",
        }

    # H5: same-account minimum interval between two scheduled platforms.
    for i, left in enumerate(solvable):
        for right in solvable[i + 1 :]:
            if not left.account_id or left.account_id != right.account_id:
                continue
            for li, lc in enumerate(eligible[left.platform]):
                for ri, rc in enumerate(eligible[right.platform]):
                    gap = abs((lc.at - rc.at).total_seconds()) / 60
                    if gap < context.min_account_gap_minutes:
                        model.AddBoolOr(
                            [
                                x[(left.platform, li)].Not(),
                                x[(right.platform, ri)].Not(),
                            ]
                        )
            hard_constraints.append(
                {
                    "code": "H5",
                    "platform": f"{left.platform}/{right.platform}",
                    "satisfied": True,
                    "description": (f"同账号发布间隔不少于 {context.min_account_gap_minutes} 分钟"),
                }
            )

    hard_constraints.extend(
        [
            {
                "code": "H2",
                "platform": "ALL",
                "satisfied": True,
                "description": f"发布时间必须在内容有效期 {context.freshness_hours} 小时内",
            },
            {
                "code": "H3",
                "platform": "ALL",
                "satisfied": True,
                "description": (f"禁用时段 {context.forbidden_hours or '无'} 已从候选中剔除"),
            },
            {
                "code": "H4",
                "platform": "ALL",
                "satisfied": True,
                "description": f"与已有排期相差 {CONFLICT_MINUTES} 分钟内的候选已剔除",
            },
            {
                "code": "H6",
                "platform": "ALL",
                "satisfied": True,
                "description": "缺少平台内容版本的目标在求解前已被移除",
            },
            {
                "code": "H7",
                "platform": "ALL",
                "satisfied": True,
                "description": (
                    f"urgency={context.urgency}，紧急内容不得超出 "
                    f"{context.freshness_hours} 小时窗口"
                ),
            },
        ]
    )

    # ---- Soft objective ------------------------------------------------------
    priority_index = {platform: rank for rank, platform in enumerate(context.platform_priority)}
    reference = min(candidate.at for target in solvable for candidate in eligible[target.platform])

    terms = []
    for target in solvable:
        for index, candidate in enumerate(eligible[target.platform]):
            var = x[(target.platform, index)]
            minutes_from_reference = int((candidate.at - reference).total_seconds() // 60)
            strategy = _strategy_bonus(
                context.cross_platform_strategy, minutes_from_reference, minimum_gap
            )
            drift_penalty = 0.0
            anchor = target.locked_time or target.preferred_time or target.original_best_time
            if anchor:
                drift_minutes = abs((candidate.at - anchor).total_seconds()) / 60
                # S6: keep changes to an operator-chosen time small.
                drift_penalty = min(100.0, drift_minutes / 6.0)
            order_penalty = 0.0
            rank = priority_index.get(target.platform)
            if rank is not None:
                # S5: earlier priority should publish earlier; punish inversion.
                expected_offset = rank * max(minimum_gap, 30)
                order_penalty = min(100.0, abs(minutes_from_reference - expected_offset) / 6.0)

            value = (
                OBJECTIVE_WEIGHTS["activity"] * candidate.activity_score
                + OBJECTIVE_WEIGHTS["semanticHistory"] * candidate.semantic_history_score
                + OBJECTIVE_WEIGHTS["strategy"] * strategy
                + OBJECTIVE_WEIGHTS["confidence"] * candidate.data_confidence
                - OBJECTIVE_WEIGHTS["userTimeDrift"] * drift_penalty
                - OBJECTIVE_WEIGHTS["orderPenalty"] * order_penalty
                - candidate.frequency_penalty
                + 0.25 * candidate.content_scene_fit
            )
            terms.append(int(round(value * SCALE)) * var)

    # S4: penalise two platforms publishing at (almost) the same moment.
    simultaneous_penalties = []
    for i, left in enumerate(solvable):
        for right in solvable[i + 1 :]:
            for li, lc in enumerate(eligible[left.platform]):
                for ri, rc in enumerate(eligible[right.platform]):
                    gap = abs((lc.at - rc.at).total_seconds()) / 60
                    if gap >= SIMULTANEOUS_TOLERANCE_MINUTES:
                        continue
                    if left.locked_time and right.locked_time:
                        continue
                    both = model.NewBoolVar(f"same_{left.platform}_{li}_{right.platform}_{ri}")
                    model.AddBoolOr(
                        [x[(left.platform, li)].Not(), x[(right.platform, ri)].Not(), both]
                    )
                    model.Add(both <= x[(left.platform, li)])
                    model.Add(both <= x[(right.platform, ri)])
                    simultaneous_penalties.append(both)
    penalty_weight = int(round(OBJECTIVE_WEIGHTS["simultaneousPenalty"] * 60 * SCALE))
    model.Maximize(
        sum(terms) - penalty_weight * sum(simultaneous_penalties)
        if simultaneous_penalties
        else sum(terms)
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = SOLVER_TIME_LIMIT_SECONDS
    solver.parameters.num_search_workers = 4
    status = solver.Solve(model)
    duration_ms = int((time.perf_counter() - started) * 1000)
    status_name = solver.StatusName(status)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return {
            "solverStatus": status_name,
            "optimizerVersion": OPTIMIZER_VERSION,
            "assignments": [],
            "solveDurationMs": duration_ms,
            "hardConstraints": hard_constraints,
            "softObjectiveBreakdown": {},
            "message": f"CP-SAT 未找到可行解（{status_name}）",
        }

    assignments: list[dict] = []
    chosen_times: list[datetime] = []
    for target in solvable:
        pool = eligible[target.platform]
        picked = next(
            (
                candidate
                for index, candidate in enumerate(pool)
                if solver.Value(x[(target.platform, index)])
            ),
            None,
        )
        if picked is None:
            assignments.append(
                {
                    "platform": target.platform,
                    "selectedTime": None,
                    "originalBestTime": (
                        target.original_best_time.isoformat() if target.original_best_time else None
                    ),
                    "optimizationAdjusted": False,
                    "adjustmentReason": "联合求解后该平台未安排发布（可选目标）",
                    "activityScore": None,
                    "semanticHistoryScore": None,
                    "dataConfidence": target.data_confidence,
                }
            )
            continue
        chosen_times.append(picked.at)
        original = target.original_best_time
        # H8: a locked slot is never treated as an optimisation adjustment.
        adjusted = bool(
            not target.locked_time
            and original
            and abs((picked.at - original).total_seconds()) >= SLOT_MINUTES * 60
        )
        if target.locked_time:
            reason = "用户锁定时间，未做优化调整"
        elif adjusted:
            drift = int((picked.at - original).total_seconds() // 60)
            reason = (
                f"为满足跨平台约束（策略 {context.cross_platform_strategy}、"
                f"最小间隔 {minimum_gap} 分钟）相对单平台最佳时间调整 {drift:+d} 分钟"
            )
        else:
            reason = "与单平台最佳时间一致，无需调整"
        assignments.append(
            {
                "platform": target.platform,
                "selectedTime": picked.at.isoformat(),
                "originalBestTime": original.isoformat() if original else None,
                "optimizationAdjusted": adjusted,
                "adjustmentReason": reason,
                "activityScore": round(picked.activity_score, 3),
                "semanticHistoryScore": round(picked.semantic_history_score, 3),
                "contentSceneFit": round(picked.content_scene_fit, 3),
                "dataConfidence": round(picked.data_confidence, 3),
                "locked": bool(target.locked_time),
                "candidateStatus": picked.candidate_status,
            }
        )

    overlap_count = 0
    for i in range(len(chosen_times)):
        for j in range(i + 1, len(chosen_times)):
            if (
                abs((chosen_times[i] - chosen_times[j]).total_seconds()) / 60
                < SIMULTANEOUS_TOLERANCE_MINUTES
            ):
                overlap_count += 1

    return {
        "solverStatus": status_name,
        "optimizerVersion": OPTIMIZER_VERSION,
        "assignments": assignments,
        "solveDurationMs": duration_ms,
        "objectiveValue": round(solver.ObjectiveValue() / SCALE, 3),
        "hardConstraints": hard_constraints,
        "candidateCounts": {platform: len(pool) for platform, pool in eligible.items()},
        "softObjectiveBreakdown": {
            "weights": OBJECTIVE_WEIGHTS,
            "strategy": context.cross_platform_strategy,
            "minimumGapMinutes": minimum_gap,
            "platformPriority": context.platform_priority,
            "simultaneousPairs": overlap_count,
            "objectives": [
                {"code": "S1", "name": "最大化用户活跃度"},
                {"code": "S2", "name": "最大化相似历史内容时段表现"},
                {"code": "S3", "name": "符合 LLM 跨平台发布策略"},
                {"code": "S4", "name": "避免多个平台完全同时发布"},
                {"code": "S5", "name": "保持合理的平台发布顺序"},
                {"code": "S6", "name": "减少对用户已选择时间的调整"},
                {"code": "S7", "name": "提高数据置信度"},
            ],
        },
    }


def default_context(
    *,
    now: datetime,
    freshness_hours: int,
    urgency: str,
    cross_platform_strategy: str,
    minimum_gap_minutes: int,
    platform_priority: list[str],
    horizon_days: int = HORIZON_DAYS,
) -> SolveContext:
    return SolveContext(
        now=now,
        freshness_hours=freshness_hours,
        urgency=urgency,
        cross_platform_strategy=cross_platform_strategy,
        minimum_gap_minutes=minimum_gap_minutes,
        platform_priority=platform_priority,
        forbidden_hours=settings.schedule_forbidden_hour_list,
        min_account_gap_minutes=settings.schedule_min_account_gap_minutes,
        horizon_days=max(HORIZON_DAYS, horizon_days),
    )
