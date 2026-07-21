"""add llm token usage billing

Revision ID: 20260721_0003
Revises: d7bc40428afb
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260721_0003"
down_revision: str | None = "d7bc40428afb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "content_variant",
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "content_variant",
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "content_variant",
        sa.Column("estimated_cost", sa.Float(), nullable=False, server_default="0"),
    )

    settings_table = sa.table(
        "system_setting",
        sa.column("setting_key", sa.String()),
        sa.column("setting_value", sa.Text()),
        sa.column("is_secret", sa.Boolean()),
        sa.column("description", sa.String()),
    )
    op.bulk_insert(
        settings_table,
        [
            {
                "setting_key": "llm.input_price_per_million",
                "setting_value": "0",
                "is_secret": False,
                "description": "每百万输入 Token 价格",
            },
            {
                "setting_key": "llm.output_price_per_million",
                "setting_value": "0",
                "is_secret": False,
                "description": "每百万输出 Token 价格",
            },
            {
                "setting_key": "llm.currency",
                "setting_value": "CNY",
                "is_secret": False,
                "description": "计费币种",
            },
        ],
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM system_setting WHERE setting_key IN "
        "('llm.input_price_per_million', 'llm.output_price_per_million', 'llm.currency')"
    )
    op.drop_column("content_variant", "estimated_cost")
    op.drop_column("content_variant", "completion_tokens")
    op.drop_column("content_variant", "prompt_tokens")
