"""Acceptance coverage for the semantic cross-platform scheduling pipeline.

LLM profile → FAISS semantic retrieval → weighted activity estimation →
candidate slots → CP-SAT joint solve → LLM plan review.
"""

from __future__ import annotations

import io
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.models.business import ContentArticle, ContentVariant, EngagementHistory
from app.services import (
    activity_estimation_service,
    content_schedule_profile_service,
    schedule_optimization_service,
    schedule_plan_review_service,
)
from app.services.content_schedule_profile_service import ContentScheduleProfile

PLATFORMS = ("WEIBO", "XIAOHONGSHU", "WECHAT_OFFICIAL")
# The test database is shared for the whole session, so cold-start assertions
# need a platform that no other test ever imports history for.
COLD_START_PLATFORM = "BILIBILI"


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def semantic_history_csv(platform: str, account: str) -> bytes:
    """History export carrying real text columns so retrieval has semantic signal.

    Two clearly different topics are seeded at different hours: the AI/content
    operations posts peak at 20:00, the unrelated cooking posts at 11:00.
    """
    header = (
        "platform,account_id,content_type,title,summary,tags,publish_time,views,"
        "impressions,likes,comments,shares,favorites,followers,source_type"
    )
    rows = [header]
    now = datetime.now()
    days_since_tuesday = ((now.weekday() - 1) % 7) or 7
    anchor = (now - timedelta(days=days_since_tuesday)).replace(
        hour=20, minute=0, second=0, microsecond=0
    )
    for week in range(6):
        peak = anchor - timedelta(days=7 * week)
        rows.append(
            f"{platform},{account},KNOWLEDGE,人工智能内容运营方法论,"
            f"人工智能如何改造内容运营工作流,人工智能 内容运营,{peak:%Y-%m-%d %H:%M},"
            "20000,22000,900,180,140,260,50000,ACCOUNT_HISTORY"
        )
        off_topic = peak.replace(hour=11) + timedelta(days=1)
        rows.append(
            f"{platform},{account},LIFESTYLE,家常菜快手食谱,"
            f"十分钟做好的家常菜清单,美食 菜谱,{off_topic:%Y-%m-%d %H:%M},"
            "18000,21000,700,120,90,200,50000,ACCOUNT_HISTORY"
        )
    return ("\n".join(rows) + "\n").encode("utf-8")


def upload(client: TestClient, auth: dict, payload: bytes) -> None:
    response = client.post(
        "/api/activity/history/import",
        headers=auth,
        files={"file": ("history.csv", io.BytesIO(payload), "text/csv")},
        data={"default_source_type": "ACCOUNT_HISTORY"},
    )
    assert response.status_code == 200, response.text


@pytest.fixture()
def semantic_setup(client: TestClient, login_as):
    """Seed history with text, create an article and its platform variants."""
    auth = headers(login_as("operator", "Operator@123456")["access_token"])
    for platform in PLATFORMS:
        upload(client, auth, semantic_history_csv(platform, f"{platform.lower()}-semantic"))

    accounts = {
        row["platform"]: row["id"]
        for row in client.get("/api/platform-accounts", headers=auth).json()["data"]
        if row.get("id")
    }
    article = client.post(
        "/api/articles",
        headers=auth,
        json={
            "title": "人工智能如何重塑内容运营工作流",
            "source_text": (
                "人工智能正在改变内容运营的日常工作流。本文梳理选题、生成、审核与复盘"
                "四个环节的变化，并给出可落地的内容运营方法论建议。"
            ),
            "keywords": ["人工智能", "内容运营"],
        },
    ).json()["data"]
    task = client.post(
        "/api/generation/content",
        headers=auth,
        json={"article_id": article["id"], "platforms": list(PLATFORMS)},
    ).json()["data"]
    variants = client.get(f"/api/generation/tasks/{task['taskId']}", headers=auth).json()["data"][
        "variants"
    ]
    for variant in variants:
        approved = client.post(
            f"/api/variants/{variant['id']}/approve",
            headers=auth,
            json={"expected_fingerprint": variant["contentFingerprint"]},
        )
        assert approved.status_code == 200, approved.text
    return {
        "auth": auth,
        "accounts": accounts,
        "article": article,
        "variants": {item["platform"]: item for item in variants},
    }


def public_dataset_csv(platform: str = "YOUTUBE") -> bytes:
    """Public research sample shaped like the imported YouTube dataset.

    Carries no title column - just the category the dataset actually ships -
    so it exercises the same thin-text path as the real import.
    """
    header = (
        "platform,account_id,content_type,publish_time,views,"
        "impressions,likes,comments,shares,favorites,followers,source_type"
    )
    rows = [header]
    now = datetime.now()
    days_since_wednesday = ((now.weekday() - 2) % 7) or 7
    anchor = (now - timedelta(days=days_since_wednesday)).replace(
        hour=21, minute=0, second=0, microsecond=0
    )
    for week in range(6):
        peak = anchor - timedelta(days=7 * week)
        rows.append(
            f"{platform},video-{week}a,Education,{peak:%Y-%m-%d %H:%M},"
            "310000,320000,9400,1800,1400,2600,120000,YOUTUBE_PUBLIC_SAMPLE"
        )
        quiet = peak.replace(hour=4) + timedelta(days=1)
        rows.append(
            f"{platform},video-{week}b,Education,{quiet:%Y-%m-%d %H:%M},"
            "280000,300000,320,40,25,60,120000,YOUTUBE_PUBLIC_SAMPLE"
        )
    return ("\n".join(rows) + "\n").encode("utf-8")


def run_batch(client: TestClient, setup: dict, **overrides):
    targets = [
        {
            "platform": platform,
            "account_id": setup["accounts"][platform],
            "variant_id": setup["variants"][platform]["id"],
        }
        for platform in PLATFORMS
    ]
    body = {
        "article_id": setup["article"]["id"],
        "window": "90D",
        "targets": overrides.pop("targets", targets),
        **overrides,
    }
    response = client.post(
        "/api/recommendations/publish-time/batch", headers=setup["auth"], json=body
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


# --- 1 / 3 / 6 / 8 / 12: end-to-end pipeline -------------------------------


def test_pipeline_produces_llm_profile_and_cpsat_plan(client: TestClient, semantic_setup) -> None:
    data = run_batch(client, semantic_setup)

    plan = data["plan"]
    assert plan is not None
    # 1. LLM schedule profile is structured and came from the model.
    assert plan["profileSource"] == "LLM"
    profile = plan["profile"]
    for field in (
        "topic",
        "content_type",
        "target_audience",
        "reading_mode",
        "estimated_reading_minutes",
        "urgency",
        "freshness_hours",
        "cognitive_load",
        "platform_priority",
        "cross_platform_strategy",
        "minimum_cross_platform_gap_minutes",
        "reason_evidence",
    ):
        assert field in profile, field
    assert profile["urgency"] in ("IMMEDIATE", "TIMELY", "NORMAL", "EVERGREEN")

    # CP-SAT actually solved the joint problem.
    assert plan["solverStatus"] in ("OPTIMAL", "FEASIBLE")
    assert plan["optimizationApplied"] is True
    assert plan["solveDurationMs"] >= 0
    assert plan["hardConstraints"]
    assert plan["softObjectiveBreakdown"]["objectives"]

    # 3. Semantically similar history is retrieved and re-ranked.
    for item in data["items"]:
        detail = item["data"]
        assert detail["similarHistoryCount"] > 0
        assert detail["algorithmVersion"] == "semantic-cpsat-v1"
        assert detail["optimization"]["selectedTime"]
        assert detail["originalBestTime"]
        top = detail["similarHistory"][0]
        assert top["combinedScore"] is not None
        assert top["vectorSimilarity"] is not None
        assert top["selectionReason"]
        # Every candidate records which path ranked it. llmRelevance stays null
        # for candidates the re-ranker did not score, instead of being faked.
        assert detail["retrievalProvider"]
        assert all(
            row["llmRelevance"] is None or 0 <= row["llmRelevance"] <= 100
            for row in detail["similarHistory"]
        )
        if detail["retrievalProvider"] == "VECTOR_ONLY":
            assert all(row["llmRelevance"] is None for row in detail["similarHistory"])
        else:
            assert any(row["llmRelevance"] is not None for row in detail["similarHistory"])
        # The off-topic cooking posts must never win the ranking. The exact
        # winner is not pinned, because any measured publish fed back into
        # history is also a legitimate match.
        assert "家常菜" not in str(top["title"])

    # 6. Platforms do not all collapse onto the same moment.
    times = [item["data"]["recommendedAt"] for item in data["items"]]
    assert len(set(times)) == len(times)

    # 11. The LLM review only issues a verdict; it never sets a time.
    review = plan["review"]
    assert review["verdict"] in ("APPROVE", "REQUEST_RESOLVE", "MANUAL_REVIEW")
    assert "selectedTime" not in review


def test_cold_start_borrows_public_dataset_from_another_platform(
    client: TestClient, login_as
) -> None:
    """A platform with no history of its own still gets evidence, clearly labelled.

    ``COLD_START_PLATFORM`` is deliberately a platform no other test imports
    data for, because the test database is shared across the whole session.
    """
    import asyncio

    from app.db.session import SessionLocal
    from app.services.semantic_history_retrieval_service import retrieve_similar_history

    auth = headers(login_as("operator", "Operator@123456")["access_token"])
    upload(client, auth, public_dataset_csv())

    with SessionLocal() as db:
        estimate = activity_estimation_service.estimate(
            db,
            platform=COLD_START_PLATFORM,
            account_id=None,
            similarity_by_row={},
        )
        retrieval = asyncio.run(
            retrieve_similar_history(
                db,
                platform=COLD_START_PLATFORM,
                account_id=None,
                query_text="在线教育课程如何做内容分发",
                profile={},
            )
        )

    assert estimate["crossPlatformSampleCount"] > 0
    levels = {item["level"] for item in estimate["priorChain"]}
    assert "CROSS_PLATFORM_PUBLIC" in levels
    # Nothing native exists, so the borrowed dataset has to be the primary level.
    assert estimate["primaryLevel"] == "CROSS_PLATFORM_PUBLIC"
    # The borrowed level still has to beat a flat default on shape.
    scores = {key: entry["score"] for key, entry in estimate["slots"].items()}
    assert len(set(scores.values())) > 1

    borrowed = [row for row in retrieval["items"] if row.get("crossPlatform")]
    assert borrowed, retrieval["items"]
    assert all(row["platform"] == "YOUTUBE" for row in borrowed)
    assert all("跨平台代理" in row["selectionReason"] for row in borrowed)


def test_platform_data_outranks_borrowed_data(client: TestClient, semantic_setup) -> None:
    """Once a platform has its own history, the cross-platform proxy steps aside."""
    setup = semantic_setup
    upload(client, setup["auth"], public_dataset_csv())
    data = run_batch(client, setup)
    for item in data["items"]:
        activity = item["data"]["activityEstimate"]
        assert activity["primaryLevel"] != "CROSS_PLATFORM_PUBLIC"
        assert all(not row.get("crossPlatform") for row in item["data"]["similarHistory"])


def test_calendar_and_batch_schedule_still_work(client: TestClient, semantic_setup) -> None:
    """12. Batch scheduling and the calendar main flow stay intact."""
    data = run_batch(client, semantic_setup)
    setup = semantic_setup
    mode_by_platform = {
        "WEIBO": "REAL_API",
        "XIAOHONGSHU": "MANUAL_CONFIRM",
        "WECHAT_OFFICIAL": "DRAFT_ONLY",
    }
    created = client.post(
        "/api/schedules/batch",
        headers=setup["auth"],
        json={
            "article_id": setup["article"]["id"],
            "idempotency_key": f"semantic-{setup['article']['id']}",
            "items": [
                {
                    "platform": item["platform"],
                    "variant_id": setup["variants"][item["platform"]]["id"],
                    "account_id": setup["accounts"][item["platform"]],
                    "scheduled_at": item["data"]["recommendedAt"],
                    "recommended_at": item["data"]["recommendedAt"],
                    "recommendation_id": item["data"]["id"],
                    "time_source": "RECOMMENDED",
                    "publish_mode": mode_by_platform[item["platform"]],
                }
                for item in data["items"]
            ],
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["data"]["successCount"] == len(PLATFORMS)

    calendar = client.get("/api/schedules", headers=setup["auth"])
    assert calendar.status_code == 200
    scheduled_ids = {row["id"] for row in calendar.json()["data"]}
    assert set(created.json()["data"]["createdScheduleIds"]) <= scheduled_ids


# --- 8 / 9: existing schedules constrain, locked times are preserved -------


def test_existing_schedule_constrains_and_lock_is_respected(
    client: TestClient, semantic_setup
) -> None:
    setup = semantic_setup
    first = run_batch(client, semantic_setup)
    weibo = next(item for item in first["items"] if item["platform"] == "WEIBO")

    client.post(
        "/api/schedules/batch",
        headers=setup["auth"],
        json={
            "article_id": setup["article"]["id"],
            "idempotency_key": f"lock-{setup['article']['id']}",
            "items": [
                {
                    "platform": "WEIBO",
                    "variant_id": setup["variants"]["WEIBO"]["id"],
                    "account_id": setup["accounts"]["WEIBO"],
                    "scheduled_at": weibo["data"]["recommendedAt"],
                    "recommended_at": weibo["data"]["recommendedAt"],
                    "recommendation_id": weibo["data"]["id"],
                    "time_source": "RECOMMENDED",
                    "publish_mode": "REAL_API",
                }
            ],
        },
    )

    # 9. A locked time survives the optimiser untouched.
    locked_at = (datetime.now() + timedelta(days=2)).replace(
        hour=15, minute=30, second=0, microsecond=0
    )
    second = run_batch(
        client,
        setup,
        targets=[
            {
                "platform": "XIAOHONGSHU",
                "account_id": setup["accounts"]["XIAOHONGSHU"],
                "variant_id": setup["variants"]["XIAOHONGSHU"]["id"],
                "locked_at": locked_at.isoformat(),
            },
            {
                "platform": "WECHAT_OFFICIAL",
                "account_id": setup["accounts"]["WECHAT_OFFICIAL"],
                "variant_id": setup["variants"]["WECHAT_OFFICIAL"]["id"],
            },
        ],
    )
    xhs = next(item for item in second["items"] if item["platform"] == "XIAOHONGSHU")
    assert xhs["data"]["recommendedAt"].startswith(locked_at.strftime("%Y-%m-%dT%H:%M"))
    assert xhs["data"]["optimization"]["locked"] is True

    # 8. The already-scheduled WEIBO slot is excluded from later WEIBO candidates.
    third = run_batch(client, setup)
    weibo_again = next(item for item in third["items"] if item["platform"] == "WEIBO")
    conflicting = [
        candidate
        for candidate in weibo_again["data"]["optimization"]["candidates"]
        if candidate["candidateTime"] == weibo["data"]["recommendedAt"]
    ]
    assert all(item["candidateStatus"] != "ELIGIBLE" for item in conflicting)


# --- 2: LLM failure degrades to rules --------------------------------------


def test_profile_falls_back_when_llm_fails(client: TestClient, semantic_setup, monkeypatch) -> None:
    async def broken_chat(*_args, **_kwargs):
        raise ValueError("模型不可用")

    from app.services import generation_service

    monkeypatch.setattr(generation_service, "_chat_completion", broken_chat)

    data = run_batch(client, semantic_setup)
    plan = data["plan"]
    assert plan["profileSource"] == "FALLBACK"
    assert any("FALLBACK" in item for item in plan["profile"]["reason_evidence"])
    # The rest of the pipeline still runs on rules.
    assert plan["solverStatus"] in ("OPTIMAL", "FEASIBLE")
    assert plan["review"]["provider"] in ("RULE_BASED", "RULE_FALLBACK")
    for item in data["items"]:
        assert item["data"]["retrievalProvider"] == "VECTOR_ONLY"


# --- 4 / 5: weighting rules -------------------------------------------------


def test_older_samples_weigh_less_than_recent_ones() -> None:
    now = datetime(2026, 8, 1, 12, 0)
    fresh = activity_estimation_service.time_weight(now - timedelta(days=1), now=now)
    old = activity_estimation_service.time_weight(now - timedelta(days=180), now=now)
    assert fresh > old
    # exp(-age/decay): a sample one decay period old keeps ~1/e of its weight.
    decayed = activity_estimation_service.time_weight(
        now - timedelta(days=settings.activity_decay_days), now=now
    )
    assert 0.3 < decayed < 0.4


def test_incomplete_rows_get_lower_weight() -> None:
    complete = EngagementHistory(
        platform="WEIBO",
        publish_time=datetime(2026, 7, 1, 20, 0),
        day_of_week=2,
        hour_of_day=20,
        views=1000,
        impressions=1200,
        likes=100,
        comments=20,
        shares=10,
        favorites=30,
        followers=5000,
        source_type="ACCOUNT_HISTORY",
    )
    sparse = EngagementHistory(
        platform="WEIBO",
        publish_time=datetime(2026, 7, 1, 20, 0),
        day_of_week=2,
        hour_of_day=20,
        views=0,
        impressions=0,
        likes=3,
        comments=0,
        shares=0,
        favorites=0,
        followers=0,
        source_type="ACCOUNT_HISTORY",
    )
    assert activity_estimation_service.data_quality(complete) > (
        activity_estimation_service.data_quality(sparse)
    )
    # Public baselines are trusted less than the account's own history.
    assert (
        activity_estimation_service.SOURCE_RELIABILITY["ACCOUNT_HISTORY"]
        > activity_estimation_service.SOURCE_RELIABILITY["PUBLIC_BASELINE"]
    )


# --- 7: urgent content never leaves its freshness window --------------------


def _profile(**overrides) -> ContentScheduleProfile:
    base = {
        "topic": "紧急公告",
        "content_type": "NEWS",
        "target_audience": "关注该话题的读者",
        "reading_mode": "FRAGMENT",
        "estimated_reading_minutes": 1.5,
        "urgency": "IMMEDIATE",
        "freshness_hours": 12,
        "cognitive_load": "LOW",
        "platform_priority": ["WEIBO", "XIAOHONGSHU"],
        "cross_platform_strategy": "STAGGERED",
        "minimum_cross_platform_gap_minutes": 45,
        "reason_evidence": ["时效性内容"],
    }
    base.update(overrides)
    return ContentScheduleProfile(**base)


def test_urgent_content_stays_inside_freshness_window() -> None:
    now = datetime(2026, 8, 4, 9, 0)
    profile = _profile()
    context = schedule_optimization_service.default_context(
        now=now,
        freshness_hours=profile.freshness_hours,
        urgency=profile.urgency,
        cross_platform_strategy=profile.cross_platform_strategy,
        minimum_gap_minutes=profile.minimum_cross_platform_gap_minutes,
        platform_priority=profile.platform_priority,
    )
    target = schedule_optimization_service.PlatformTarget(
        platform="WEIBO", account_id=1, variant_id=1
    )
    candidates = schedule_optimization_service.build_candidates(
        target,
        context,
        activity_slot_score=lambda _w, _h: 70.0,
        semantic_slot_score=lambda _w, _h: 50.0,
        reading_mode=profile.reading_mode,
        cognitive_load=profile.cognitive_load,
        existing=[],
    )
    deadline = now + timedelta(hours=profile.freshness_hours)
    eligible = [item for item in candidates if item.candidate_status == "ELIGIBLE"]
    assert eligible
    assert all(item.at <= deadline for item in eligible)
    assert any(
        item.candidate_status == "OUT_OF_FRESHNESS" for item in candidates if item.at > deadline
    )


def test_freshness_hours_cannot_exceed_urgency_cap() -> None:
    # The validator clamps an over-long freshness window for urgent content.
    profile = _profile(freshness_hours=720)
    assert profile.freshness_hours == 24


def _context(profile: ContentScheduleProfile, now: datetime):
    return schedule_optimization_service.default_context(
        now=now,
        freshness_hours=profile.freshness_hours,
        urgency=profile.urgency,
        cross_platform_strategy=profile.cross_platform_strategy,
        minimum_gap_minutes=profile.minimum_cross_platform_gap_minutes,
        platform_priority=profile.platform_priority,
    )


def test_forbidden_hours_are_never_eligible() -> None:
    """Hard constraint H3: operator-disabled hours drop out of the candidate pool."""
    now = datetime(2026, 8, 4, 9, 0)
    profile = _profile(urgency="NORMAL", freshness_hours=168)
    context = _context(profile, now)
    assert context.forbidden_hours, "测试依赖默认禁用时段配置"
    candidates = schedule_optimization_service.build_candidates(
        schedule_optimization_service.PlatformTarget(platform="WEIBO", account_id=1, variant_id=1),
        context,
        activity_slot_score=lambda _w, _h: 80.0,
        semantic_slot_score=lambda _w, _h: 60.0,
        reading_mode=profile.reading_mode,
        cognitive_load=profile.cognitive_load,
        existing=[],
    )
    eligible = [item for item in candidates if item.candidate_status == "ELIGIBLE"]
    assert eligible
    assert all(item.at.hour not in context.forbidden_hours for item in eligible)


def test_same_account_minimum_interval_is_enforced() -> None:
    """Hard constraint H5: an existing same-account post blocks nearby slots."""
    now = datetime(2026, 8, 4, 9, 0)
    profile = _profile(urgency="NORMAL", freshness_hours=168)
    context = _context(profile, now)
    booked = now + timedelta(days=1, hours=11)
    candidates = schedule_optimization_service.build_candidates(
        schedule_optimization_service.PlatformTarget(
            platform="XIAOHONGSHU", account_id=7, variant_id=1
        ),
        context,
        activity_slot_score=lambda _w, _h: 80.0,
        semantic_slot_score=lambda _w, _h: 60.0,
        reading_mode=profile.reading_mode,
        cognitive_load=profile.cognitive_load,
        existing=[
            schedule_optimization_service.ExistingSchedule(
                platform="WEIBO", account_id=7, scheduled_at=booked
            )
        ],
    )
    for item in candidates:
        gap = abs((item.at - booked).total_seconds()) / 60
        if gap < context.min_account_gap_minutes:
            assert item.candidate_status != "ELIGIBLE"


def test_bayesian_smoothing_borrows_from_the_prior_chain(client: TestClient, semantic_setup):
    """Slots without personal evidence are filled from broader priors, not zeros."""
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        estimate = activity_estimation_service.estimate(
            db,
            platform="WEIBO",
            account_id=semantic_setup["accounts"]["WEIBO"],
            similarity_by_row={},
        )
    levels = {item["level"] for item in estimate["priorChain"]}
    assert "SYSTEM_DEFAULT" in levels
    empty_slots = [entry for entry in estimate["slots"].values() if entry["observedScore"] is None]
    assert empty_slots, "应存在没有直接样本的时段"
    for entry in empty_slots:
        # No observation → the score is exactly the prior, with zero observation weight.
        assert entry["observationWeight"] == 0.0
        assert entry["score"] == entry["priorScore"]
        assert entry["priorLevel"] in {
            "ACCOUNT_SIMILAR",
            "ACCOUNT_ALL",
            "PLATFORM_SIMILAR",
            "PLATFORM_ALL",
            "CROSS_PLATFORM_PUBLIC",
            "SYSTEM_DEFAULT",
        }
    observed = [entry for entry in estimate["slots"].values() if entry["observedScore"] is not None]
    assert observed, "应存在有直接样本的时段"
    for entry in observed:
        # Shrinkage keeps the estimate between the observation and its prior.
        low, high = sorted([entry["observedScore"], entry["priorScore"]])
        assert low - 0.01 <= entry["score"] <= high + 0.01
        assert 0 < entry["observationWeight"] <= 1


# --- 10: OR-Tools failure falls back to the existing recommendation ---------


def test_falls_back_to_hybrid_v2_when_ortools_unavailable(
    client: TestClient, semantic_setup, monkeypatch
) -> None:
    monkeypatch.setattr(schedule_optimization_service, "ORTOOLS_AVAILABLE", False)
    data = run_batch(client, semantic_setup)
    plan = data["plan"]
    assert plan["solverStatus"] == "ORTOOLS_UNAVAILABLE"
    assert plan["optimizationApplied"] is False
    for item in data["items"]:
        detail = item["data"]
        # hybrid-v2 result is preserved untouched.
        assert detail["algorithmVersion"] == "hybrid-v2"
        assert detail["optimizationAdjusted"] is False
        assert detail["recommendedAt"]
        # The semantic evidence is still attached for explanation.
        assert detail["profile"]
        assert detail["activityEstimate"]


def test_batch_can_opt_out_of_optimization(client: TestClient, semantic_setup) -> None:
    """9 (compatibility): the endpoint still serves pure hybrid-v2 on request."""
    data = run_batch(client, semantic_setup, optimize=False)
    assert data["plan"] is None
    for item in data["items"]:
        assert item["data"]["algorithmVersion"] == "hybrid-v2"


# --- 11: the reviewer cannot set times -------------------------------------


def test_review_rejects_resolve_without_constraints() -> None:
    with pytest.raises(ValueError):
        schedule_plan_review_service.PlanReview(
            verdict="REQUEST_RESOLVE", summary="需要重新求解", risks=[]
        )


def test_review_model_has_no_time_field() -> None:
    fields = set(schedule_plan_review_service.PlanReview.model_fields)
    assert fields == {"verdict", "summary", "risks", "resolve_request"}
    resolve_fields = set(schedule_plan_review_service.ResolveRequest.model_fields)
    assert resolve_fields == {
        "minimum_cross_platform_gap_minutes",
        "platform_order",
        "note",
    }


def test_llm_resolve_request_triggers_exactly_one_resolve(
    client: TestClient, semantic_setup, monkeypatch
) -> None:
    """A reviewer that always asks for a re-solve must not loop."""
    calls = {"review": 0, "solve": 0}
    original_optimize = schedule_optimization_service.optimize

    def counting_optimize(*args, **kwargs):
        calls["solve"] += 1
        return original_optimize(*args, **kwargs)

    monkeypatch.setattr(schedule_optimization_service, "optimize", counting_optimize)

    from app.services import generation_service

    original_chat = generation_service._chat_completion

    async def resolve_chat(runtime, system_prompt, messages, **kwargs):
        if "跨平台发布排期的审查员" in system_prompt:
            calls["review"] += 1
            return (
                '{"verdict":"REQUEST_RESOLVE","summary":"平台间隔过近",'
                '"risks":["间隔不足"],'
                '"resolve_request":{"minimum_cross_platform_gap_minutes":180,'
                '"platform_order":[],"note":"拉大间隔"}}',
                50,
                20,
            )
        return await original_chat(runtime, system_prompt, messages, **kwargs)

    monkeypatch.setattr(generation_service, "_chat_completion", resolve_chat)

    data = run_batch(client, semantic_setup)
    plan = data["plan"]
    assert plan["review"]["verdict"] == "REQUEST_RESOLVE"
    assert calls["review"] == 1
    # Exactly one initial solve plus one re-solve.
    assert calls["solve"] == 2
    assert plan["review"]["resolveRounds"] == schedule_plan_review_service.MAX_RESOLVE_ROUNDS


# --- 3 (unit): semantic ordering beats content-type-only matching ----------


def test_semantic_retrieval_prefers_topic_match_over_content_type(
    client: TestClient, semantic_setup
) -> None:
    data = run_batch(client, semantic_setup)
    weibo = next(item for item in data["items"] if item["platform"] == "WEIBO")
    selected = weibo["data"]["similarHistory"]
    history_items = [item for item in selected if item["refType"] == "HISTORY"]
    assert history_items
    ai_ranks = [
        index for index, item in enumerate(history_items) if "人工智能" in (item["title"] or "")
    ]
    food_ranks = [
        index for index, item in enumerate(history_items) if "家常菜" in (item["title"] or "")
    ]
    assert ai_ranks, "语义相似的人工智能历史内容应被检索到"
    if food_ranks:
        assert min(ai_ranks) < min(food_ranks), "同主题历史内容应排在无关主题之前"


def test_profile_rule_fallback_is_deterministic(client: TestClient, semantic_setup) -> None:
    """The rule fallback fills every required field without an LLM."""
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        article = db.get(ContentArticle, semantic_setup["article"]["id"])
        variants = list(
            db.query(ContentVariant).filter(ContentVariant.article_id == article.id).all()
        )
        profile = content_schedule_profile_service.rule_based_profile(
            article, variants, list(PLATFORMS)
        )
    assert profile.platform_priority == list(PLATFORMS)
    assert profile.freshness_hours > 0
    assert profile.minimum_cross_platform_gap_minutes >= 0
    assert profile.reason_evidence
