"""share platform accounts across system users

Revision ID: 20260729_0011
Revises: 20260727_0010
Create Date: 2026-07-29
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260729_0011"
down_revision: str | None = "20260727_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _merge_duplicate_accounts() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT id, platform, user_id, status, updated_at
            FROM platform_account
            ORDER BY platform,
              CASE WHEN status = 'CONNECTED' THEN 0 ELSE 1 END,
              updated_at DESC,
              id DESC
            """
        )
    ).mappings()
    winners: dict[str, int] = {}
    for row in rows:
        platform = str(row["platform"])
        account_id = int(row["id"])
        winner_id = winners.setdefault(platform, account_id)
        if winner_id == account_id:
            continue
        connection.execute(
            sa.text(
                "UPDATE publish_schedule SET account_id = :winner_id WHERE account_id = :account_id"
            ),
            {"winner_id": winner_id, "account_id": account_id},
        )
        connection.execute(
            sa.text(
                """
                UPDATE platform_auth_log
                SET platform_account_id = :winner_id
                WHERE platform_account_id = :account_id
                """
            ),
            {"winner_id": winner_id, "account_id": account_id},
        )
        connection.execute(
            sa.text("DELETE FROM platform_account WHERE id = :account_id"),
            {"account_id": account_id},
        )


def upgrade() -> None:
    with op.batch_alter_table("platform_account") as batch_op:
        batch_op.add_column(sa.Column("updated_by", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_platform_account_updated_by", "sys_user", ["updated_by"], ["id"]
        )
        batch_op.create_index("ix_platform_account_updated_by", ["updated_by"], unique=False)
    op.execute(sa.text("UPDATE platform_account SET updated_by = user_id"))
    _merge_duplicate_accounts()
    with op.batch_alter_table("platform_account") as batch_op:
        batch_op.drop_constraint("uq_platform_account_user", type_="unique")
        batch_op.create_unique_constraint("uq_platform_account_platform", ["platform"])


def downgrade() -> None:
    with op.batch_alter_table("platform_account") as batch_op:
        batch_op.drop_constraint("uq_platform_account_platform", type_="unique")
        batch_op.create_unique_constraint("uq_platform_account_user", ["user_id", "platform"])
        batch_op.drop_index("ix_platform_account_updated_by")
        batch_op.drop_constraint("fk_platform_account_updated_by", type_="foreignkey")
        batch_op.drop_column("updated_by")
