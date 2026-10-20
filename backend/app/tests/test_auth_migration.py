import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, text

from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_token_version_migration_backfills_existing_users_and_is_reversible(tmp_path) -> None:
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "20261011_0016_auth_sessions.py"
    )
    spec = importlib.util.spec_from_file_location("auth_sessions_migration", migration_path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine(f"sqlite:///{(tmp_path / 'auth-migration.db').as_posix()}")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE sys_user (id INTEGER PRIMARY KEY, username VARCHAR(50) NOT NULL)"
                )
            )
            connection.execute(text("INSERT INTO sys_user (id, username) VALUES (1, 'existing')"))
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()
            assert connection.execute(text("SELECT token_version FROM sys_user")).scalar_one() == 0
            connection.execute(text("INSERT INTO sys_user (id, username) VALUES (2, 'new')"))
            assert (
                connection.execute(
                    text("SELECT token_version FROM sys_user WHERE id = 2")
                ).scalar_one()
                == 0
            )
            migration.downgrade()
            assert connection.execute(text("SELECT username FROM sys_user ORDER BY id")).all() == [
                ("existing",),
                ("new",),
            ]
    finally:
        engine.dispose()
