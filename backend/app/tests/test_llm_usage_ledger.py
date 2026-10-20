import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.db.base import Base
from app.models.business import ContentArticle, ContentVariant, LlmUsageEntry, SystemSetting
from app.services import generation_service as generation
from app.services.llm_config_service import llm_usage
from app.services.llm_usage_service import begin_usage, ensure_legacy_usage, finish_usage

REAL_CHAT_COMPLETION = generation._chat_completion


@pytest.fixture()
def usage_engine(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'ledger.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        for key, value in {
            "llm.input_price_per_million": "1000",
            "llm.output_price_per_million": "1000",
            "llm.monthly_budget": "0",
        }.items():
            db.add(SystemSetting(setting_key=key, setting_value=value, is_secret=False))
        db.commit()
    yield engine
    engine.dispose()


def _runtime(engine):
    return generation.LlmRuntime("isolated", "mock", "https://example.invalid", "mock", engine)


def _setting(engine, key, value):
    with Session(engine) as db:
        row = db.scalar(select(SystemSetting).where(SystemSetting.setting_key == key))
        row.setting_value = value
        db.commit()


@pytest.mark.asyncio
async def test_review_and_keyword_usage_enter_independent_ledger(usage_engine, monkeypatch):
    runtime = _runtime(usage_engine)
    monkeypatch.setattr(generation, "load_llm_runtime", lambda _db: runtime)
    review = {
        "factual_consistency": 90,
        "information_completeness": 90,
        "platform_fit": 90,
        "readability": 90,
        "format_compliance": 90,
        "issues": [],
        "suggestions": [],
    }
    transport = AsyncMock(
        side_effect=[
            (json.dumps(review), 120, 80),
            (json.dumps({"keywords": [{"zh": "项目", "en": "project", "reason": "主题"}]}), 30, 20),
        ]
    )
    monkeypatch.setattr(generation, "_chat_completion", transport)
    with Session(usage_engine) as db:
        article = ContentArticle(title="项目", source_text="项目进度说明。", created_by=1)
        variant = ContentVariant(
            platform="WEIBO", title="项目", content_text="项目进度说明。", hashtags_json=[]
        )
        await generation.review_variant_quality(db, article, variant)
        await generation.extract_keywords_with_llm(db, "项目进度说明。")
        usage = llm_usage(db, 30)
    assert transport.await_count == 2
    assert usage["totalTokens"] == 250
    assert usage["estimatedCost"] == pytest.approx(0.25)
    assert {item["operation"] for item in usage["recent"]} == {"REVIEW", "KEYWORDS"}


def test_legacy_cost_survives_deletion_and_new_variants_are_not_double_counted(usage_engine):
    with Session(usage_engine) as db:
        article = ContentArticle(title="旧文", source_text="旧文", created_by=1)
        db.add(article)
        db.flush()
        old = ContentVariant(
            article_id=article.id,
            platform="WEIBO",
            title="旧稿",
            content_text="旧稿",
            prompt_tokens=120,
            completion_tokens=80,
            token_usage=200,
            estimated_cost=0.2,
        )
        db.add(old)
        db.commit()
        before = llm_usage(db, 30)
        db.delete(old)
        db.commit()
        assert llm_usage(db, 30)["totalTokens"] == before["totalTokens"] == 200
        ticket = begin_usage(_runtime(usage_engine), "GENERATION", prompt_text="hello")
        finish_usage(ticket, prompt_tokens=10, completion_tokens=10)
        db.add(
            ContentVariant(
                article_id=article.id,
                platform="WEIBO",
                title="新稿",
                content_text="新稿",
                prompt_tokens=10,
                completion_tokens=10,
                token_usage=20,
            )
        )
        db.commit()
        assert llm_usage(db, 30)["totalTokens"] == 220


@pytest.mark.asyncio
async def test_exhausted_budget_blocks_before_provider_call(usage_engine, monkeypatch):
    runtime = _runtime(usage_engine)
    ticket = begin_usage(runtime, "REVIEW", prompt_text="hello")
    finish_usage(ticket, prompt_tokens=600, completion_tokens=400)
    _setting(usage_engine, "llm.monthly_budget", "1")
    transport = AsyncMock(return_value=("{}", 1, 1))
    monkeypatch.setattr(generation, "_chat_completion", transport)
    with pytest.raises(AppException) as exc:
        await generation._tracked_chat_completion(runtime, "prompt", [])
    assert exc.value.code == 40963
    transport.assert_not_awaited()


def test_inflight_reservations_prevent_concurrent_budget_bypass(usage_engine):
    _setting(usage_engine, "llm.monthly_budget", "1.1")
    runtime = _runtime(usage_engine)
    first = begin_usage(runtime, "CHAT", prompt_text="hello")
    with pytest.raises(AppException) as exc:
        begin_usage(runtime, "CHAT", prompt_text="hello")
    assert exc.value.code == 40963
    finish_usage(first, prompt_tokens=1, completion_tokens=1)
    second = begin_usage(runtime, "CHAT", prompt_text="hello")
    finish_usage(second, prompt_tokens=1, completion_tokens=1)


def test_two_threads_cannot_both_reserve_the_last_budget(usage_engine):
    _setting(usage_engine, "llm.monthly_budget", "1.1")
    ensure_legacy_usage(usage_engine)
    barrier = Barrier(2)

    def admit():
        barrier.wait(timeout=10)
        try:
            return begin_usage(_runtime(usage_engine), "CHAT", prompt_text="hello")
        except AppException as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: admit(), range(2)))
    assert results.count(40963) == 1
    ticket = next(result for result in results if not isinstance(result, int))
    finish_usage(ticket, prompt_tokens=1, completion_tokens=1)


def test_crashed_call_remains_unknown_and_does_not_hold_reservation_forever(usage_engine):
    _setting(usage_engine, "llm.monthly_budget", "2")
    ticket = begin_usage(_runtime(usage_engine), "CHAT")
    assert ticket is not None
    with Session(ticket.bind) as db:
        row = db.get(LlmUsageEntry, ticket.id)
        row.created_at = datetime.now() - timedelta(hours=1)
        db.commit()
    with Session(usage_engine) as db:
        usage = llm_usage(db, 30)
    assert usage["monthlyReservedCost"] == 0
    assert usage["monthlyUnknownCalls"] == 1
    assert usage["recent"][0]["status"] == "UNCERTAIN"
    with pytest.raises(AppException) as exc:
        begin_usage(_runtime(usage_engine), "CHAT")
    assert exc.value.code == 40962
    # A late authoritative response can still settle that original call.
    finish_usage(ticket, prompt_tokens=120, completion_tokens=80)
    with Session(usage_engine) as db:
        assert llm_usage(db, 30)["monthlyUnknownCalls"] == 0


@pytest.mark.asyncio
async def test_invalid_response_retry_and_network_failure_are_retained(usage_engine, monkeypatch):
    transport = AsyncMock(side_effect=[("not json", 12, 8), ("{}", 10, 5)])
    monkeypatch.setattr(generation, "_chat_completion", transport)
    with pytest.raises(AppException):
        await generation._validated_completion(
            _runtime(usage_engine),
            "关键词",
            "test",
            generation.KeywordExtractionOutput,
            max_attempts=2,
        )
    with Session(usage_engine) as db:
        usage = llm_usage(db, 30)
        assert usage["generations"] == 2 and usage["totalTokens"] == 35
    monkeypatch.setattr(
        generation, "_chat_completion", AsyncMock(side_effect=httpx.ReadTimeout("x"))
    )
    with pytest.raises(httpx.ReadTimeout):
        await generation._tracked_chat_completion(_runtime(usage_engine), "test", [])
    with Session(ensure_legacy_usage(usage_engine)) as db:
        row = db.scalars(select(LlmUsageEntry).where(LlmUsageEntry.status == "FAILED")).one()
        assert row.estimated_cost is None and row.pricing_status == "UNKNOWN_USAGE"
        assert row.prompt_tokens is None


@pytest.mark.asyncio
async def test_error_response_usage_is_kept_and_missing_usage_is_not_zero(
    usage_engine, monkeypatch
):
    monkeypatch.setattr(generation, "_chat_completion", REAL_CHAT_COMPLETION)
    response = httpx.Response(
        500,
        json={
            "error": {"code": "provider_error"},
            "usage": {"prompt_tokens": 120, "completion_tokens": 80},
        },
        request=httpx.Request("POST", "https://example.invalid/chat/completions"),
    )
    monkeypatch.setattr(httpx.AsyncClient, "post", AsyncMock(return_value=response))
    with pytest.raises(httpx.HTTPStatusError):
        await generation._tracked_chat_completion(_runtime(usage_engine), "test", [])
    with Session(ensure_legacy_usage(usage_engine)) as db:
        row = db.scalars(select(LlmUsageEntry)).one()
        assert row.status == "FAILED"
        assert row.prompt_tokens == 120 and row.completion_tokens == 80
        assert row.estimated_cost == pytest.approx(0.2)
    missing = httpx.Response(
        200,
        json={"choices": [{"message": {"content": "{}"}}]},
        request=httpx.Request("POST", "https://example.invalid/chat/completions"),
    )
    monkeypatch.setattr(httpx.AsyncClient, "post", AsyncMock(return_value=missing))
    await generation._tracked_chat_completion(_runtime(usage_engine), "test", [])
    with Session(usage_engine) as db:
        usage = llm_usage(db, 30)
        assert usage["monthlyUnknownCalls"] == 1


@pytest.mark.asyncio
async def test_image_attempts_are_logged_without_inventing_a_token_price(usage_engine, monkeypatch):
    from app.services.image_service import _post_image_request

    response = httpx.Response(400, json={"error": {"message": "bad request"}})
    transport = AsyncMock(return_value=response)
    monkeypatch.setattr(httpx.AsyncClient, "post", transport)
    await _post_image_request(_runtime(usage_engine), {"model": "image-model", "prompt": "test"})
    with Session(ensure_legacy_usage(usage_engine)) as db:
        row = db.scalars(select(LlmUsageEntry)).one()
        assert row.status == "FAILED" and row.operation == "IMAGE_GENERATION"
        assert row.estimated_cost is None and row.model == "image-model"
    _setting(usage_engine, "llm.monthly_budget", "10")
    with pytest.raises(AppException) as exc:
        await _post_image_request(_runtime(usage_engine), {"model": "image-model"})
    assert exc.value.code == 40961
    assert transport.await_count == 1


def test_price_snapshot_and_unknown_image_cost_are_explicit(usage_engine):
    ticket = begin_usage(_runtime(usage_engine), "CHAT")
    finish_usage(ticket, prompt_tokens=120, completion_tokens=80)
    _setting(usage_engine, "llm.input_price_per_million", "2000")
    unknown = begin_usage(_runtime(usage_engine), "IMAGE", token_priced=False)
    finish_usage(unknown)
    with Session(usage_engine) as db:
        usage = llm_usage(db, 30)
        assert usage["estimatedCost"] == pytest.approx(0.2)
        assert usage["unpricedGenerations"] == 1
        assert usage["monthlyUnknownCalls"] == 1
    _setting(usage_engine, "llm.monthly_budget", "100")
    with pytest.raises(AppException) as exc:
        begin_usage(_runtime(usage_engine), "IMAGE", token_priced=False)
    assert exc.value.code == 40961
    with pytest.raises(AppException) as exc:
        begin_usage(_runtime(usage_engine), "CHAT")
    assert exc.value.code == 40962


def test_bootstrap_is_idempotent_and_keeps_original_dates(usage_engine):
    ensure_legacy_usage(usage_engine)
    ensure_legacy_usage(usage_engine)
    with Session(ensure_legacy_usage(usage_engine)) as db:
        assert (
            len(
                db.scalars(
                    select(SystemSetting).where(
                        SystemSetting.setting_key == "llm.usage_ledger_initialized"
                    )
                ).all()
            )
            == 1
        )
        assert len(db.scalars(select(LlmUsageEntry)).all()) == 0


@pytest.mark.asyncio
async def test_business_rollback_does_not_erase_provider_usage_or_lock_sqlite(
    usage_engine, monkeypatch
):
    with Session(usage_engine) as db:
        db.add(ContentArticle(title="会回滚", source_text="测试", created_by=1))
        db.flush()  # Hold the business SQLite writer while the provider runs.
        runtime = generation.LlmRuntime(
            "isolated", "mock", "https://example.invalid", "mock", usage_engine, db
        )
        monkeypatch.setattr(generation, "_chat_completion", AsyncMock(return_value=("{}", 120, 80)))
        await generation._tracked_chat_completion(runtime, "test", [])
        db.rollback()
    with Session(usage_engine) as db:
        assert db.scalars(select(ContentArticle)).all() == []
        assert llm_usage(db, 30)["totalTokens"] == 200
