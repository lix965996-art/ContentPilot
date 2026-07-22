"""add WeChat formatting profile

Revision ID: 20260722_0006
Revises: 20260721_0005
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260722_0006"
down_revision: str | None = "20260721_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {item["name"] for item in sa.inspect(bind).get_columns("content_variant")}
    if "format_profile_json" not in columns:
        op.add_column("content_variant", sa.Column("format_profile_json", sa.JSON(), nullable=True))
    empty_object = "JSON_OBJECT()" if bind.dialect.name == "mysql" else "'{}'"
    op.execute(
        f"UPDATE content_variant SET format_profile_json = {empty_object} "
        "WHERE format_profile_json IS NULL"
    )
    op.alter_column(
        "content_variant", "format_profile_json", existing_type=sa.JSON(), nullable=False
    )


def downgrade() -> None:
    op.drop_column("content_variant", "format_profile_json")
