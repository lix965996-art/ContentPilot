"""align JSON nullability and platform_auth_log index names with the models

Revision ID: 20261020_0019
Revises: 20261020_0018
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261020_0019"
down_revision: str | None = "20261020_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _fill(table: str, column: str, value: str) -> None:
    op.execute(f"UPDATE {table} SET {column} = {value} WHERE {column} IS NULL")


def upgrade() -> None:
    # Backfill before tightening the columns to NOT NULL.
    _fill("content_embedding", "vector_json", "'[]'")
    _fill("engagement_history", "metric_detail_json", "'{}'")
    _fill("engagement_history", "created_at", "CURRENT_TIMESTAMP")
    _fill("history_import_batch", "field_mapping_json", "'{}'")
    _fill("history_import_batch", "errors_json", "'[]'")
    _fill("history_import_batch", "created_at", "CURRENT_TIMESTAMP")
    _fill("platform_auth_log", "created_at", "CURRENT_TIMESTAMP")
    for column in (
        "weights_json",
        "data_source_json",
        "window_json",
        "profile_json",
        "activity_estimate_json",
        "optimization_json",
        "review_json",
    ):
        _fill("publish_recommendation", column, "'{}'")
    for column in ("warnings_json", "conflicts_json", "similar_history_json"):
        _fill("publish_recommendation", column, "'[]'")
    _fill("publish_schedule", "recommendation_snapshot_json", "'{}'")

    with op.batch_alter_table("content_embedding") as batch_op:
        batch_op.alter_column("vector_json", existing_type=sa.JSON(), nullable=False)
    with op.batch_alter_table("engagement_history") as batch_op:
        batch_op.alter_column("metric_detail_json", existing_type=sa.JSON(), nullable=False)
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(),
            existing_server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        )
    with op.batch_alter_table("history_import_batch") as batch_op:
        batch_op.alter_column("field_mapping_json", existing_type=sa.JSON(), nullable=False)
        batch_op.alter_column("errors_json", existing_type=sa.JSON(), nullable=False)
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(),
            existing_server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        )
    with op.batch_alter_table("platform_auth_log") as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(),
            existing_server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        )
    with op.batch_alter_table("publish_recommendation") as batch_op:
        for column in (
            "weights_json",
            "data_source_json",
            "warnings_json",
            "conflicts_json",
            "window_json",
            "profile_json",
            "similar_history_json",
            "activity_estimate_json",
            "optimization_json",
            "review_json",
        ):
            batch_op.alter_column(column, existing_type=sa.JSON(), nullable=False)
    with op.batch_alter_table("publish_schedule") as batch_op:
        batch_op.alter_column(
            "recommendation_snapshot_json", existing_type=sa.JSON(), nullable=False
        )

    existing = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("platform_auth_log")}
    if "ix_platform_auth_log_platform_account_id" not in existing:
        op.create_index(
            "ix_platform_auth_log_platform_account_id",
            "platform_auth_log",
            ["platform_account_id"],
        )
    if "ix_platform_auth_log_created_at" not in existing:
        op.create_index(
            "ix_platform_auth_log_created_at",
            "platform_auth_log",
            ["created_at"],
        )
    # Create replacements before dropping the old index: MySQL refuses to drop
    # the index currently backing the foreign key.
    if "ix_platform_auth_log_account" in existing:
        op.drop_index("ix_platform_auth_log_account", table_name="platform_auth_log")
    if "ix_platform_auth_log_created" in existing:
        op.drop_index("ix_platform_auth_log_created", table_name="platform_auth_log")


def downgrade() -> None:
    existing = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("platform_auth_log")}
    if "ix_platform_auth_log_account" not in existing:
        op.create_index(
            "ix_platform_auth_log_account", "platform_auth_log", ["platform_account_id"]
        )
    if "ix_platform_auth_log_created" not in existing:
        op.create_index("ix_platform_auth_log_created", "platform_auth_log", ["created_at"])
    # Same ordering rule as upgrade: create the replacement before dropping the
    # index that currently backs the foreign key.
    if "ix_platform_auth_log_platform_account_id" in existing:
        op.drop_index("ix_platform_auth_log_platform_account_id", table_name="platform_auth_log")
    if "ix_platform_auth_log_created_at" in existing:
        op.drop_index("ix_platform_auth_log_created_at", table_name="platform_auth_log")

    for table, columns in (
        ("content_embedding", ["vector_json"]),
        ("engagement_history", ["metric_detail_json", "created_at"]),
        ("history_import_batch", ["field_mapping_json", "errors_json", "created_at"]),
        ("platform_auth_log", ["created_at"]),
        (
            "publish_recommendation",
            [
                "weights_json",
                "data_source_json",
                "warnings_json",
                "conflicts_json",
                "window_json",
                "profile_json",
                "similar_history_json",
                "activity_estimate_json",
                "optimization_json",
                "review_json",
            ],
        ),
        ("publish_schedule", ["recommendation_snapshot_json"]),
    ):
        with op.batch_alter_table(table) as batch_op:
            for column in columns:
                batch_op.alter_column(
                    column,
                    existing_type=sa.DateTime() if column == "created_at" else sa.JSON(),
                    nullable=True,
                )
