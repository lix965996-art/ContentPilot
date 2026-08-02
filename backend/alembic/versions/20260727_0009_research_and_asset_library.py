"""research library and global media assets

Revision ID: 20260727_0009
Revises: 20260722_0008
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260727_0009"
down_revision: str | None = "20260722_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    with op.batch_alter_table("media_asset") as batch_op:
        batch_op.alter_column("article_id", existing_type=sa.Integer(), nullable=True)
        if dialect == "mysql":
            batch_op.drop_constraint("media_asset_ibfk_1", type_="foreignkey")
            batch_op.create_foreign_key(
                "fk_media_asset_article",
                "content_article",
                ["article_id"],
                ["id"],
                ondelete="SET NULL",
            )
        batch_op.add_column(sa.Column("title", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("collection", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("tags_json", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column("favorite", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(sa.Column("license_type", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("license_note", sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column("file_hash", sa.String(length=64), nullable=True))
        batch_op.create_index("ix_media_asset_collection", ["collection"], unique=False)
        batch_op.create_index("ix_media_asset_favorite", ["favorite"], unique=False)
        batch_op.create_index("ix_media_asset_file_hash", ["file_hash"], unique=False)
    op.execute(sa.text("UPDATE media_asset SET tags_json = '[]' WHERE tags_json IS NULL"))
    with op.batch_alter_table("media_asset") as batch_op:
        batch_op.alter_column("tags_json", existing_type=sa.JSON(), nullable=False)

    op.create_table(
        "research_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("image_url", sa.String(length=1000), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("source_name", sa.String(length=100), nullable=True),
        sa.Column("source_id", sa.String(length=150), nullable=True),
        sa.Column("topic_cluster", sa.String(length=100), nullable=True),
        sa.Column("tags_json", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["sys_user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_item_title", "research_item", ["title"], unique=False)
    op.create_index("ix_research_item_source", "research_item", ["source"], unique=False)
    op.create_index(
        "ix_research_item_topic_cluster", "research_item", ["topic_cluster"], unique=False
    )
    op.create_index("ix_research_item_status", "research_item", ["status"], unique=False)
    op.create_index("ix_research_item_archived", "research_item", ["archived"], unique=False)
    op.create_index("ix_research_item_created_by", "research_item", ["created_by"], unique=False)


def downgrade() -> None:
    dialect = op.get_bind().dialect.name
    op.drop_table("research_item")
    with op.batch_alter_table("media_asset") as batch_op:
        batch_op.drop_index("ix_media_asset_file_hash")
        batch_op.drop_index("ix_media_asset_favorite")
        batch_op.drop_index("ix_media_asset_collection")
        batch_op.drop_column("file_hash")
        batch_op.drop_column("license_note")
        batch_op.drop_column("license_type")
        batch_op.drop_column("favorite")
        batch_op.drop_column("tags_json")
        batch_op.drop_column("collection")
        batch_op.drop_column("title")
        if dialect == "mysql":
            batch_op.drop_constraint("fk_media_asset_article", type_="foreignkey")
            batch_op.create_foreign_key(
                "media_asset_ibfk_1",
                "content_article",
                ["article_id"],
                ["id"],
                ondelete="CASCADE",
            )
        batch_op.alter_column("article_id", existing_type=sa.Integer(), nullable=False)
