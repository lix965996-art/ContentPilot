"""time-window aware recommendations and auto experiment grouping

Revision ID: 20260803_0013
Revises: 20260803_0012
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260803_0013"
down_revision: str | None = "20260803_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("publish_recommendation") as batch_op:
        batch_op.add_column(sa.Column("window_json", sa.JSON(), nullable=True))

    with op.batch_alter_table("experiment_sample") as batch_op:
        batch_op.add_column(
            sa.Column(
                "assignment_source", sa.String(length=20), nullable=False, server_default="AUTO"
            )
        )
        batch_op.add_column(sa.Column("assignment_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("experiment_sample") as batch_op:
        batch_op.drop_column("assignment_reason")
        batch_op.drop_column("assignment_source")

    with op.batch_alter_table("publish_recommendation") as batch_op:
        batch_op.drop_column("window_json")
