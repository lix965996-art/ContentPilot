import json
import os
import re
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
configured_var = os.environ.get("CONTENTPILOT_VAR_DIR", "").strip()
TEST_STORAGE_PARENT = Path(configured_var).expanduser() if configured_var else PROJECT_ROOT / "var"
if not TEST_STORAGE_PARENT.is_absolute():
    TEST_STORAGE_PARENT = PROJECT_ROOT / TEST_STORAGE_PARENT
TEST_STORAGE_PARENT = TEST_STORAGE_PARENT.resolve() / "tests"
TEST_STORAGE_PARENT.mkdir(parents=True, exist_ok=True)
TEST_STORAGE = tempfile.TemporaryDirectory(prefix="pytest-", dir=TEST_STORAGE_PARENT)
TEST_VAR_DIR = Path(TEST_STORAGE.name)
os.environ["CONTENTPILOT_VAR_DIR"] = str(TEST_VAR_DIR)
TEST_DATABASE_PATH = TEST_VAR_DIR / "db" / ".test_socialflow.db"
MYSQL_TEST_URL = os.environ.get("CONTENTPILOT_TEST_MYSQL_URL", "").strip()
os.environ["DATABASE_URL"] = (
    MYSQL_TEST_URL if MYSQL_TEST_URL else f"sqlite:///{TEST_DATABASE_PATH.as_posix()}"
)
os.environ["JWT_SECRET"] = "test-secret-that-is-long-enough-for-jwt-signing"
os.environ["APP_DEMO_MODE"] = "true"
os.environ["APP_ENV"] = "test"
os.environ["LLM_PROVIDER"] = "openai-compatible"
os.environ["LLM_BASE_URL"] = "https://llm.test/v1"
os.environ["LLM_API_KEY"] = "test-only-api-key"
os.environ["LLM_MODEL"] = "test-chat-model"
os.environ["PUBLISH_MODE"] = "official"
os.environ["OUTBOUND_DNS_OVER_HTTPS"] = "false"

from app.db.base import Base  # noqa: E402
from app.db.seed import seed_database  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services import generation_service  # noqa: E402


def pytest_configure(config) -> None:
    if config.option.basetemp is None:
        (TEST_VAR_DIR / "tmp").mkdir(parents=True, exist_ok=True)
        config.option.basetemp = str(TEST_VAR_DIR / "tmp" / "pytest")


@pytest.fixture(scope="session", autouse=True)
def database() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_database(db)
    yield
    engine.dispose()
    TEST_STORAGE.cleanup()


@pytest.fixture()
def client(database: None) -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def isolate_metric_background_transport(monkeypatch):
    """Collection behavior is tested directly; generic API tests never read live social APIs."""
    from app.scheduler import dispatch

    monkeypatch.setattr(dispatch, "_run_metric_in_thread", lambda _task_id: None)


@pytest.fixture(autouse=True)
def intercept_llm_transport(monkeypatch):
    """Intercept the external LLM transport; product code still uses the real provider path."""

    async def fake_chat(_runtime, system_prompt, messages, **_kwargs):
        prompt = messages[-1]["content"]
        if "社交媒体内容排期分析师" in system_prompt:
            payload = {
                "topic": "内容运营工作流",
                "content_type": "KNOWLEDGE",
                "target_audience": "校园新媒体团队",
                "reading_mode": "IMMERSIVE",
                "estimated_reading_minutes": 6,
                "urgency": "NORMAL",
                "freshness_hours": 96,
                "cognitive_load": "MEDIUM",
                "platform_priority": [
                    "WEIBO",
                    "XIAOHONGSHU",
                    "WECHAT_OFFICIAL",
                    "TOUTIAO",
                ],
                "cross_platform_strategy": "STAGGERED",
                "minimum_cross_platform_gap_minutes": 45,
                "reason_evidence": ["正文属于方法论科普", "适合完整阅读的时段"],
            }
        elif "内容相似度评审员" in system_prompt:
            # Score every candidate the retriever offered, highest first.
            ids = re.findall(r'"candidate_id":\s*(\d+)', prompt)
            payload = {
                "items": [
                    {
                        "candidate_id": int(item),
                        "relevance": max(10, 95 - index * 5),
                        "reason": "主题与受众接近",
                    }
                    for index, item in enumerate(ids)
                ]
            }
        elif "跨平台发布排期的审查员" in system_prompt:
            payload = {
                "verdict": "APPROVE",
                "summary": "跨平台时间分布合理，硬约束全部满足。",
                "risks": [],
                "resolve_request": None,
            }
        elif "只做分类" in system_prompt:
            payload = {
                "content_type": "KNOWLEDGE",
                "topic": "内容运营",
                "audience": "校园新媒体团队",
            }
        elif "统计结果由系统计算完成" in system_prompt:
            payload = {"narrative": "统计显示该时段的历史互动表现最好，建议按推荐时间发布。"}
        elif "关键词" in system_prompt:
            payload = {
                "keywords": [
                    {"zh": "内容运营", "en": "content operations", "reason": "文章核心主题"}
                ]
            }
        elif "事实一致性" in system_prompt:
            payload = {
                "factual_consistency": 92,
                "information_completeness": 90,
                "platform_fit": 88,
                "readability": 90,
                "format_compliance": 91,
                "issues": [],
                "suggestions": ["发布前复核原文事实"],
            }
        elif "目标平台：微信公众号" in prompt:
            payload = {
                "title": "真实模型测试公众号文章",
                "summary": "依据原文生成的结构化摘要",
                "content": (
                    "一、核心信息\n\n这是依据原文生成的公众号测试正文。\n\n结语\n\n发布前请复核。"
                ),
                "author": "",
                "hashtags": [],
                "cover_prompt": "内容运营编辑配图",
                "warnings": [],
            }
        elif "目标平台：小红书" in prompt:
            payload = {
                "title": "内容运营重点整理",
                "content": "这是依据原文整理的小红书测试正文，包含必要事实且不虚构个人体验。",
                "hashtags": [],
                "cover_text": "内容运营重点",
                "warnings": [],
            }
        elif "目标平台：今日头条" in prompt:
            payload = {
                "title": "内容运营如何形成稳定工作流",
                "summary": "依据原文梳理内容运营的主要事实、执行步骤与必要限制。",
                "content": (
                    "一、核心信息\n\n这是依据原文生成的今日头条测试正文，保留主要事实。"
                    "\n\n二、执行建议\n\n发布前仍需由编辑复核来源和限定条件。"
                ),
                "hashtags": [],
                "cover_prompt": "内容运营工作台，真实编辑场景",
                "warnings": [],
            }
        else:
            payload = {
                "title": "内容运营信息速览",
                "content": "这是依据原文生成的微博测试正文，保留原文中的主要事实和必要信息。",
                "hashtags": [],
                "warnings": [],
            }
        return json.dumps(payload, ensure_ascii=False), 120, 60

    monkeypatch.setattr(generation_service, "_chat_completion", fake_chat)


@pytest.fixture()
def login_as(client: TestClient):
    def login(username: str, password: str) -> dict:
        response = client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
        )
        assert response.status_code == 200
        return response.json()["data"]

    return login
