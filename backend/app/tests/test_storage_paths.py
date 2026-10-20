import base64
import io
import json
import os
import subprocess
import sys
import uuid
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.api.endpoints.schedules import _package_image_path
from app.core import paths
from app.core.config import Settings, settings
from app.db.session import SessionLocal, engine
from app.models.business import ContentVariant, PublishSchedule
from app.models.user import User
from app.publishers import cdp, official, toutiao_browser, wechat_browser, xhs_mcp

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def test_test_storage_never_uses_business_uploads_or_database() -> None:
    assert paths.VAR_DIR.parent.name == "tests"
    assert paths.VAR_DIR.name.startswith("pytest-")
    assert paths.VAR_DIR != paths.PROJECT_ROOT / "var"
    assert paths.MEDIA_UPLOAD_DIR.is_relative_to(paths.VAR_DIR)
    assert Path(engine.url.database).is_relative_to(paths.VAR_DIR)
    assert settings.sqlite_fallback_url.endswith("/db/contentpilot.db")
    assert cdp.USER_DATA_ROOT.is_relative_to(paths.VAR_DIR)


def test_storage_override_and_sqlite_parent_are_resolved(tmp_path) -> None:
    assert paths.resolve_var_dir("custom-storage") == paths.PROJECT_ROOT / "custom-storage"
    assert paths.resolve_var_dir(str(tmp_path)) == tmp_path.resolve()
    configured = Settings(
        _env_file=None, contentpilot_var_dir=str(tmp_path), sqlite_fallback_url=""
    )
    assert configured.sqlite_fallback_url == f"sqlite:///{tmp_path.as_posix()}/db/contentpilot.db"
    database = tmp_path / "nested" / "db" / "fallback.db"
    paths.ensure_sqlite_directory(f"sqlite:///{database.as_posix()}")
    assert database.parent.is_dir()


def test_e2e_database_and_uploads_ignore_inherited_business_database(tmp_path) -> None:
    business = tmp_path / "business.db"
    business.write_bytes(b"existing-business-data-must-stay-untouched")
    e2e_root = tmp_path / "run" / "e2e"
    script = paths.PROJECT_ROOT / "backend" / "app" / "tests" / "e2e_server.py"
    command = (
        "import json, runpy; "
        f"module = runpy.run_path({str(script)!r}); "
        "module['prepare_database'](); "
        "from app.core.paths import VAR_DIR, UPLOADS_DIR; "
        "from app.core.config import settings; "
        "from app.db.session import engine, SessionLocal; "
        "from app.services.llm_config_service import read_llm_config; "
        "from app.services.generation_service import load_llm_runtime; "
        "from app.services.content_embedding_service import load_embedding_runtime; "
        "db = SessionLocal(); config = read_llm_config(db); runtime = load_llm_runtime(db); "
        "embedding = load_embedding_runtime(db); "
        "print(json.dumps({'var': str(VAR_DIR), 'uploads': str(UPLOADS_DIR), "
        "'database': engine.url.database, 'provider': config['provider'], "
        "'seedBaseUrl': config['baseUrl'], 'runtimeBaseUrl': runtime.base_url, "
        "'settingsBaseUrl': settings.llm_base_url, 'timeout': settings.llm_timeout_seconds, "
        "'settingsKeyIsTestOnly': settings.llm_api_key == 'e2e-only-api-key', "
        "'runtimeKeyIsTestOnly': runtime.api_key == 'e2e-only-api-key', "
        "'embeddingIsOffline': not embedding.usable})); db.close(); engine.dispose()"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", command],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "CONTENTPILOT_VAR_DIR": str(e2e_root),
            "DATABASE_URL": f"sqlite:///{business.as_posix()}",
            "LLM_BASE_URL": "https://business-model.invalid/v1",
            "LLM_API_KEY": "inherited-business-key-must-not-be-used",
            "LLM_MODEL": "business-model-must-not-be-used",
            "LLM_PROVIDER": "business-provider-must-not-be-used",
            "EMBEDDING_MODEL": "business-embedding-must-not-be-used",
            "LLM_TIMEOUT_SECONDS": "60",
        },
        timeout=30,
        check=True,
    )
    storage = json.loads(result.stdout.strip().splitlines()[-1])
    assert Path(storage["var"]) == e2e_root
    assert Path(storage["uploads"]) == e2e_root / "uploads"
    assert Path(storage["database"]) == e2e_root / "db" / ".e2e_socialflow.db"
    assert storage["provider"] == "siliconflow"
    assert storage["seedBaseUrl"] == "http://127.0.0.1:1/v1"
    assert storage["runtimeBaseUrl"] == storage["settingsBaseUrl"] == storage["seedBaseUrl"]
    assert storage["settingsKeyIsTestOnly"] is True
    assert storage["runtimeKeyIsTestOnly"] is True
    assert storage["embeddingIsOffline"] is True
    assert storage["timeout"] == 2
    assert business.read_bytes() == b"existing-business-data-must-stay-untouched"


@pytest.mark.parametrize("platform", ["wechat", "toutiao"])
def test_browser_sessions_use_stable_platform_paths_and_preserve_override(
    platform, tmp_path, monkeypatch
) -> None:
    module = wechat_browser if platform == "wechat" else toutiao_browser
    setting = f"{platform}_browser_profile_root"
    monkeypatch.setattr(settings, setting, "")
    assert module._manager._profile_root() == paths.SESSIONS_DIR / platform
    configured = tmp_path / "explicit-profile"
    monkeypatch.setattr(settings, setting, str(configured))
    assert module._manager._profile_root() == configured
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, setting, "relative-profile")
    assert module._manager._profile_root() == tmp_path / "relative-profile"


@pytest.mark.parametrize(
    "value",
    [
        "/uploads/../outside.png",
        "/uploads/%2e%2e/outside.png",
        "/uploads/media/%2e%2e/%2e%2e/outside.png",
        "/uploads/media/..\\..\\outside.png",
        "/uploads//outside.png",
        "/uploads/C:/outside.png",
        "/media/../outside.png",
        "/uploads/media/%00.png",
    ],
)
def test_media_urls_cannot_escape_storage_roots(value, tmp_path, monkeypatch) -> None:
    uploads = tmp_path / "uploads"
    public = tmp_path / "public" / "media"
    uploads.mkdir()
    public.mkdir(parents=True)
    (tmp_path / "outside.png").write_bytes(PNG_BYTES)
    monkeypatch.setattr(paths, "UPLOADS_DIR", uploads)
    monkeypatch.setattr(paths, "PUBLIC_MEDIA_DIR", public)
    assert paths.local_media_path(value) is None
    assert _package_image_path(value) is None
    assert official._local_image(value) is None
    assert wechat_browser._local_image(value) is None


def test_upload_is_served_and_read_by_publishers_and_download_zip(client, login_as) -> None:
    token = login_as("operator", "Operator@123456")["access_token"]
    auth = {"Authorization": f"Bearer {token}"}
    response = client.post(
        "/api/media/upload",
        headers=auth,
        data={"usage_type": "BODY"},
        files={"file": ("storage-verification.png", PNG_BYTES, "image/png")},
    )
    assert response.status_code == 200, response.text
    asset = response.json()["data"]
    media_url = asset["imageUrl"]
    image = paths.MEDIA_UPLOAD_DIR / asset["sourceId"]
    assert image.read_bytes() == PNG_BYTES
    served = client.get(media_url)
    assert served.status_code == 200
    assert served.content == PNG_BYTES
    assert official._local_image(media_url) == image
    loopback_url = "http://127.0.0.1:8000/uploads/media/" + image.name
    assert wechat_browser._local_image(loopback_url) == image
    assert wechat_browser._local_image("https://example.com/uploads/media/" + image.name) is None

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "operator"))
        variant = db.scalar(select(ContentVariant).where(ContentVariant.platform == "XIAOHONGSHU"))
        schedule = PublishSchedule(
            article_id=variant.article_id,
            variant_id=variant.id,
            platform="XIAOHONGSHU",
            scheduled_at=datetime.now() + timedelta(days=30),
            status="CANCELLED",
            publish_mode="MANUAL",
            created_by=user.id,
            idempotency_key=uuid.uuid4().hex,
            publish_package_json={
                "title": "媒体路径测试",
                "content": "仅下载本地发布包",
                "images": [media_url],
            },
        )
        db.add(schedule)
        db.commit()
        schedule_id = schedule.id
    package = client.get(
        f"/api/schedules/{schedule_id}/publish-package/download",
        headers=auth,
    )
    assert package.status_code == 200
    with zipfile.ZipFile(io.BytesIO(package.content)) as archive:
        assert archive.read("images/01.png") == PNG_BYTES


@pytest.mark.asyncio
async def test_mcp_starts_with_separate_cookie_session_and_logs(tmp_path, monkeypatch) -> None:
    session = tmp_path / "sessions" / "xiaohongshu"
    logs = tmp_path / "logs"
    binary = tmp_path / "tools" / "xiaohongshu-mcp" / "v2.2.6" / "mcp.exe"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"test-placeholder-no-execution")
    captured = {}
    port_checks = iter([False, False, True])

    async def port_is_open(*_args):
        return next(port_checks)

    class FakeProcess:
        def poll(self):
            return None

    def start_process(arguments, **kwargs):
        captured.update(arguments=arguments, **kwargs)
        return FakeProcess()

    monkeypatch.setattr(xhs_mcp, "LOGS_DIR", logs)
    monkeypatch.setattr(xhs_mcp, "XHS_SESSION_DIR", session)
    monkeypatch.setattr(xhs_mcp, "XHS_COOKIE_PATH", session / "cookies.json")
    monkeypatch.setattr(xhs_mcp, "_local_process", None)
    monkeypatch.setattr(xhs_mcp, "_port_is_open", port_is_open)
    monkeypatch.setattr(xhs_mcp, "_find_local_binary", lambda: binary)
    monkeypatch.setattr(xhs_mcp.subprocess, "Popen", start_process)
    await xhs_mcp._ensure_local_service()
    assert captured["cwd"] == str(session)
    assert captured["env"]["COOKIES_PATH"] == str(session / "cookies.json")
    assert captured["arguments"][0] == str(binary)
    assert Path(captured["stdout"].name).parent == logs
    assert Path(captured["stderr"].name).parent == logs
    assert os.environ["CONTENTPILOT_VAR_DIR"] == str(paths.VAR_DIR)
