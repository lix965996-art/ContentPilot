"""semantic scheduling pipeline: content embeddings + recommendation artifacts

Revision ID: 20260804_0014
Revises: 20260803_0013
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260804_0014"
down_revision: str | None = "20260803_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "content_embedding",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ref_type", sa.String(length=20), nullable=False),
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=30), nullable=True),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("embedding_model", sa.String(length=100), nullable=False),
        sa.Column("embedding_version", sa.String(length=30), nullable=False, server_default="v1"),
        sa.Column("vector_json", sa.JSON(), nullable=True),
        sa.Column("text_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column(
            "embedding_created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("ref_type", "content_id", "embedding_version", name="uq_content_embed"),
    )
    op.create_index("ix_content_embedding_ref_type", "content_embedding", ["ref_type"])
    op.create_index("ix_content_embedding_content_id", "content_embedding", ["content_id"])
    op.create_index("ix_content_embedding_platform", "content_embedding", ["platform"])
    op.create_index("ix_content_embedding_account_id", "content_embedding", ["account_id"])

    with op.batch_alter_table("publish_recommendation") as batch_op:
        batch_op.add_column(sa.Column("profile_json", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column("profile_source", sa.String(length=20), nullable=False, server_default="")
        )
        batch_op.add_column(sa.Column("similar_history_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("activity_estimate_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("optimization_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("review_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("publish_recommendation") as batch_op:
        batch_op.drop_column("review_json")
        batch_op.drop_column("optimization_json")
        batch_op.drop_column("activity_estimate_json")
        batch_op.drop_column("similar_history_json")
        batch_op.drop_column("profile_source")
        batch_op.drop_column("profile_json")

    op.drop_index("ix_content_embedding_account_id", table_name="content_embedding")
    op.drop_index("ix_content_embedding_platform", table_name="content_embedding")
    op.drop_index("ix_content_embedding_content_id", table_name="content_embedding")
    op.drop_index("ix_content_embedding_ref_type", table_name="content_embedding")
    op.drop_table("content_embedding")
