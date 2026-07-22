import json
import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_DATABASE_PATH = Path(__file__).resolve().parent / ".test_socialflow.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE_PATH.as_posix()}"
os.environ["JWT_SECRET"] = "test-secret-that-is-long-enough-for-jwt-signing"
os.environ["APP_DEMO_MODE"] = "true"
os.environ["APP_ENV"] = "test"
os.environ["LLM_PROVIDER"] = "openai-compatible"
os.environ["LLM_BASE_URL"] = "https://llm.test/v1"
os.environ["LLM_API_KEY"] = "test-only-api-key"
os.environ["LLM_MODEL"] = "test-chat-model"
os.environ["PUBLISH_MODE"] = "official"

from app.db.base import Base  # noqa: E402
from app.db.seed import seed_database  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services import generation_service  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def database() -> Generator[None, None, None]:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_database(db)
    yield
    engine.dispose()
    if TEST_DATABASE_PATH.exists():
        TEST_DATABASE_PATH.unlink()


@pytest.fixture()
def client(database: None) -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def intercept_llm_transport(monkeypatch):
    """Intercept the external LLM transport; product code still uses the real provider path."""

    async def fake_chat(_runtime, system_prompt, messages):
        prompt = messages[-1]["content"]
        if "关键词" in system_prompt:
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
                    "## 核心信息\n\n这是依据原文生成的公众号测试正文。\n\n## 结语\n\n发布前请复核。"
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
