"""persistent task dispatch intents

Revision ID: 20261020_0017
Revises: 20261011_0016
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261020_0017"
down_revision: str | None = "20261011_0016_auth_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "task_dispatch",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_type", sa.String(length=40), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("run_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_type", "task_id", name="uq_task_dispatch_task"),
    )
    op.create_index(
        "ix_task_dispatch_status_run_at",
        "task_dispatch",
        ["status", "run_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_task_dispatch_status_run_at", table_name="task_dispatch")
    op.drop_table("task_dispatch")
