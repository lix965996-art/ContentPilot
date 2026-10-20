from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.paths import ensure_sqlite_directory

ensure_sqlite_directory(settings.database_url)
ensure_sqlite_directory(settings.sqlite_fallback_url)
engine_options: dict[str, object] = {"pool_pre_ping": True}
if settings.database_url.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
else:
    # Production-grade pool sizing for concurrent requests + background tasks.
    engine_options["pool_size"] = 20
    engine_options["max_overflow"] = 30
    engine_options["pool_recycle"] = 3600  # recycle before MySQL wait_timeout

engine = create_engine(settings.database_url, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
