"""Persist the account token version for logout and password-change revocation.

Revision ID: 20261011_0016_auth_sessions
Revises: 20261011_0015_data_integrity
Create Date: 2026-10-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261011_0016_auth_sessions"
down_revision: str | None = "20261011_0015_data_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("sys_user") as batch_op:
        batch_op.add_column(
            sa.Column("token_version", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("sys_user") as batch_op:
        batch_op.drop_column("token_version")
