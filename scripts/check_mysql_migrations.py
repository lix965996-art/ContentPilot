"""Verify the MySQL schema after applying all migrations.

Used by the Linux CI job; run locally against a disposable database only.
"""

from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, inspect, text


def main(url: str) -> None:
    engine = create_engine(url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert "task_dispatch" in tables, "task_dispatch table is missing"
    assert {"llm_usage_entry", "llm_budget_month"} <= tables, "usage ledger tables are missing"
    assert "refresh_session" not in tables, "unexpected refresh_session table"
    variant_columns = {column["name"] for column in inspector.get_columns("content_variant")}
    assert "review_fingerprint" in variant_columns, "review_fingerprint column is missing"
    assert "content_revision" in variant_columns, "content_revision column is missing"
    indexes = {index["name"] for index in inspector.get_indexes("platform_auth_log")}
    assert "ix_platform_auth_log_platform_account_id" in indexes
    assert "ix_platform_auth_log_created_at" in indexes
    with engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        users = [
            row[0]
            for row in connection.execute(text("SELECT username FROM sys_user ORDER BY id"))
        ]
    print("alembic_version:", version)
    print("users:", users)
    print("mysql schema check OK")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.environ["DATABASE_URL"])
