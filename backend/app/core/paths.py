"""Project storage paths shared by the API, publishers and local tools."""

from pathlib import Path
from urllib.parse import unquote, urlsplit

from sqlalchemy.engine import make_url

from app.core.config import BACKEND_DIR, settings

PROJECT_ROOT = BACKEND_DIR.parent


def resolve_var_dir(value: str = "") -> Path:
    root = Path(value).expanduser() if value.strip() else PROJECT_ROOT / "var"
    if not root.is_absolute():
        root = PROJECT_ROOT / root
    return root.resolve()


VAR_DIR = resolve_var_dir(settings.contentpilot_var_dir)
RUN_DIR = VAR_DIR / "run"
LOGS_DIR = VAR_DIR / "logs"
UPLOADS_DIR = VAR_DIR / "uploads"
MEDIA_UPLOAD_DIR = UPLOADS_DIR / "media"
SESSIONS_DIR = VAR_DIR / "sessions"
TOOLS_DIR = VAR_DIR / "tools"
CACHE_DIR = VAR_DIR / "cache"
REPORTS_DIR = VAR_DIR / "reports"
TMP_DIR = VAR_DIR / "tmp"
DATABASE_DIR = VAR_DIR / "db"
TESTS_DIR = VAR_DIR / "tests"
XHS_SESSION_DIR = SESSIONS_DIR / "xiaohongshu"
XHS_COOKIE_PATH = XHS_SESSION_DIR / "cookies.json"
PUBLIC_MEDIA_DIR = PROJECT_ROOT / "frontend" / "public" / "media"


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_sqlite_directory(database_url: str) -> None:
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite" and url.database and url.database != ":memory:":
        ensure_directory(Path(url.database).expanduser().parent)


def local_media_path(value: str, *, local_hosts_only: bool = False) -> Path | None:
    """Resolve stored media URLs without letting URL paths escape their roots.

    Publishers can receive absolute file paths, but only uploaded or bundled
    media is eligible. The browser publisher additionally limits HTTP URLs to
    loopback hosts so a remote image URL cannot be mistaken for a local file.
    """
    if not value:
        return None
    roots = (UPLOADS_DIR, PUBLIC_MEDIA_DIR)
    try:
        direct = Path(value)
        if direct.is_absolute() and direct.is_file():
            candidate = direct.resolve()
            if any(candidate.is_relative_to(root.resolve()) for root in roots):
                return candidate
            return None
        parsed = urlsplit(value)
        if parsed.scheme:
            if parsed.scheme not in {"http", "https"}:
                return None
            if local_hosts_only and (parsed.hostname or "").lower() not in {
                "127.0.0.1",
                "localhost",
                "::1",
            }:
                return None
        elif parsed.netloc:
            return None
        url_path = unquote(parsed.path).replace("\\", "/")
        if ".." in url_path.split("/") or "\x00" in url_path:
            return None
        for prefix, root in (("/uploads/", UPLOADS_DIR), ("/media/", PUBLIC_MEDIA_DIR)):
            if url_path.startswith(prefix):
                relative = url_path[len(prefix) :]
                if not relative or relative.startswith("/"):
                    return None
                candidate = (root / relative).resolve()
                if candidate.is_relative_to(root.resolve()) and candidate.is_file():
                    return candidate
                return None
    except (OSError, ValueError):
        return None
    return None
