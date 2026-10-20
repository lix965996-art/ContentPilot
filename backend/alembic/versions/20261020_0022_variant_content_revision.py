"""Guard concurrent content and review writes with a persisted revision.

Revision ID: 20261020_0022
Revises: 20261020_0021
"""

import sqlalchemy as sa

from alembic import op

revision = "20261020_0022"
down_revision = "20261020_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "content_variant",
        sa.Column("content_revision", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    with op.batch_alter_table("content_variant") as batch:
        batch.drop_column("content_revision")
