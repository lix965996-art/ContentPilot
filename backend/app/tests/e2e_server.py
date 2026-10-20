"""Start an isolated, disposable API server for Playwright tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))
configured_var = os.environ.get("CONTENTPILOT_VAR_DIR", "").strip()
E2E_VAR_DIR = (
    Path(configured_var).expanduser()
    if configured_var
    else BACKEND_DIR.parent / "var" / "run" / "e2e"
)
if not E2E_VAR_DIR.is_absolute():
    E2E_VAR_DIR = BACKEND_DIR.parent / E2E_VAR_DIR
E2E_VAR_DIR = E2E_VAR_DIR.resolve()
E2E_DATABASE = (E2E_VAR_DIR / "db" / ".e2e_socialflow.db").resolve()
EXPECTED_DATABASE_URL = f"sqlite:///{E2E_DATABASE.as_posix()}"
E2E_LLM_BASE_URL = "http://127.0.0.1:1/v1"


def prepare_database() -> None:
    if E2E_VAR_DIR.name != "e2e" or E2E_VAR_DIR.parent.name != "run":
        raise RuntimeError("E2E storage must be a dedicated run/e2e directory")
    if E2E_DATABASE.parent != E2E_VAR_DIR / "db":
        raise RuntimeError("Resolved E2E database path is outside the test directory")
    os.environ["CONTENTPILOT_VAR_DIR"] = str(E2E_VAR_DIR)
    os.environ["DATABASE_URL"] = EXPECTED_DATABASE_URL
    os.environ.update(
        APP_ENV="test",
        LLM_PROVIDER="siliconflow",
        LLM_BASE_URL=E2E_LLM_BASE_URL,
        LLM_API_KEY="e2e-only-api-key",
        LLM_MODEL="e2e-chat-model",
        LLM_TIMEOUT_SECONDS="2",
        EMBEDDING_MODEL="",
    )
    # A proxy must not turn an intentionally offline loopback model into an
    # outbound request. Semantic tests exercise the normal unavailable-model fallback.
    no_proxy = ",".join(
        filter(
            None,
            (
                os.environ.get("NO_PROXY"),
                os.environ.get("no_proxy"),
                "127.0.0.1",
                "localhost",
                "::1",
            ),
        )
    )
    os.environ["NO_PROXY"] = os.environ["no_proxy"] = no_proxy
    E2E_DATABASE.parent.mkdir(parents=True, exist_ok=True)
    E2E_DATABASE.unlink(missing_ok=True)
    # The SQLite accounting store is independent so business rollbacks cannot
    # erase paid usage. It belongs to this disposable E2E run as well.
    ledger = E2E_DATABASE.with_suffix(E2E_DATABASE.suffix + ".llm-usage.sqlite")
    if ledger.parent != E2E_DATABASE.parent:
        raise RuntimeError("Resolved E2E ledger path is outside the test directory")
    ledger.unlink(missing_ok=True)

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
                base_url=E2E_LLM_BASE_URL,
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
