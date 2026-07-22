"""enhance generation pipeline

Revision ID: 20260721_0005
Revises: 20260721_0004
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260721_0005"
down_revision: str | None = "20260721_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    def add_column(table: str, column: sa.Column) -> None:
        existing = {item["name"] for item in sa.inspect(bind).get_columns(table)}
        if column.name not in existing:
            op.add_column(table, column)

    add_column("content_variant", sa.Column("review_detail_json", sa.JSON(), nullable=True))
    add_column(
        "generation_task",
        sa.Column("provider", sa.String(length=50), nullable=False, server_default=""),
    )
    add_column(
        "generation_task",
        sa.Column("prompt_version", sa.String(length=30), nullable=False, server_default=""),
    )
    add_column(
        "generation_task",
        sa.Column("token_usage", sa.Integer(), nullable=False, server_default="0"),
    )
    add_column(
        "generation_task",
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
    )
    add_column("generation_task", sa.Column("platform_status_json", sa.JSON(), nullable=True))
    add_column("generation_task", sa.Column("options_json", sa.JSON(), nullable=True))
    empty_object = "JSON_OBJECT()" if bind.dialect.name == "mysql" else "'{}'"
    op.execute(
        f"UPDATE content_variant SET review_detail_json = {empty_object} "
        "WHERE review_detail_json IS NULL"
    )
    op.execute(
        f"UPDATE generation_task SET platform_status_json = {empty_object} "
        "WHERE platform_status_json IS NULL"
    )
    op.execute(
        f"UPDATE generation_task SET options_json = {empty_object} WHERE options_json IS NULL"
    )
    op.alter_column(
        "content_variant", "review_detail_json", existing_type=sa.JSON(), nullable=False
    )
    op.alter_column(
        "generation_task", "platform_status_json", existing_type=sa.JSON(), nullable=False
    )
    op.alter_column("generation_task", "options_json", existing_type=sa.JSON(), nullable=False)


def downgrade() -> None:
    op.drop_column("generation_task", "options_json")
    op.drop_column("generation_task", "platform_status_json")
    op.drop_column("generation_task", "duration_ms")
    op.drop_column("generation_task", "token_usage")
    op.drop_column("generation_task", "prompt_version")
    op.drop_column("generation_task", "provider")
    op.drop_column("content_variant", "review_detail_json")
