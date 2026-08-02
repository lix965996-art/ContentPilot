"""Start an isolated, disposable API server for Playwright tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))
E2E_DATABASE = (BACKEND_DIR / "app" / "tests" / ".e2e_socialflow.db").resolve()
EXPECTED_DATABASE_URL = "sqlite:///./app/tests/.e2e_socialflow.db"


def prepare_database() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if database_url != EXPECTED_DATABASE_URL:
        raise RuntimeError("Refusing to reset a database outside the dedicated E2E path")
    if E2E_DATABASE.parent != (BACKEND_DIR / "app" / "tests").resolve():
        raise RuntimeError("Resolved E2E database path is outside the test directory")
    E2E_DATABASE.unlink(missing_ok=True)

    from app import models  # noqa: F401
    from app.db.base import Base
    from app.db.session import engine

    Base.metadata.create_all(bind=engine)
    from app.db.seed import main as seed_database

    seed_database()

    from app.db.session import SessionLocal
    from app.schemas.business import LlmConfigUpdate
    from app.services.llm_config_service import save_llm_config

    with SessionLocal() as db:
        save_llm_config(
            db,
            LlmConfigUpdate(
                provider="siliconflow",
                base_url="https://api.siliconflow.cn/v1",
                api_key="e2e-only-api-key",
                model="e2e-chat-model",
            ),
        )
        db.commit()


if __name__ == "__main__":
    os.chdir(BACKEND_DIR)
    prepare_database()
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=int(os.environ.get("E2E_API_PORT", "8001")),
    )
