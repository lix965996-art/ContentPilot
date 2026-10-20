"""bind reviews to the reviewed content fingerprint

Revision ID: 20261020_0018
Revises: 20261020_0017
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261020_0018"
down_revision: str | None = "20261020_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("content_variant") as batch_op:
        batch_op.add_column(sa.Column("review_fingerprint", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("content_variant") as batch_op:
        batch_op.drop_column("review_fingerprint")
