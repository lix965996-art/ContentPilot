"""make media_asset.article_id use ON DELETE SET NULL

The original SQLite migration rebuilt the table with CASCADE, while the model
has always declared SET NULL. Deleting an article must not delete reusable
media assets. This migration rebuilds the SQLite table and repairs the MySQL
foreign key if a legacy database still has CASCADE.

Revision ID: 20261020_0020
Revises: 20261020_0019
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261020_0020"
down_revision: str | None = "20261020_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = (
    "id",
    "article_id",
    "variant_id",
    "source",
    "source_id",
    "image_url",
    "thumbnail_url",
    "photographer_name",
    "photographer_url",
    "alt_text",
    "search_keyword",
    "usage_type",
    "selected",
    "title",
    "collection",
    "tags_json",
    "favorite",
    "license_type",
    "license_note",
    "file_hash",
    "created_at",
)


def _article_fk(bind) -> dict | None:
    for fk in sa.inspect(bind).get_foreign_keys("media_asset"):
        if fk.get("constrained_columns") == ["article_id"]:
            return fk
    return None


def _create_table(name: str, ondelete: str) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=True),
        sa.Column("variant_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("source_id", sa.String(length=100), nullable=True),
        sa.Column("image_url", sa.String(length=1000), nullable=False),
        sa.Column("thumbnail_url", sa.String(length=1000), nullable=False),
        sa.Column("photographer_name", sa.String(length=100), nullable=True),
        sa.Column("photographer_url", sa.String(length=500), nullable=True),
        sa.Column("alt_text", sa.String(length=500), nullable=True),
        sa.Column("search_keyword", sa.String(length=100), nullable=True),
        sa.Column("usage_type", sa.String(length=30), nullable=False),
        sa.Column("selected", sa.Boolean(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("collection", sa.String(length=100), nullable=True),
        sa.Column("tags_json", sa.JSON(), nullable=False),
        sa.Column("favorite", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("license_type", sa.String(length=80), nullable=True),
        sa.Column("license_note", sa.String(length=500), nullable=True),
        sa.Column("file_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["content_article.id"],
            name=f"fk_media_asset_article_{ondelete.lower().replace(' ', '_')}",
            ondelete=ondelete,
        ),
        sa.ForeignKeyConstraint(
            ["variant_id"],
            ["content_variant.id"],
            name="fk_media_asset_variant",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def _create_indexes() -> None:
    op.create_index("ix_media_asset_article_id", "media_asset", ["article_id"])
    op.create_index("ix_media_asset_collection", "media_asset", ["collection"])
    op.create_index("ix_media_asset_favorite", "media_asset", ["favorite"])
    op.create_index("ix_media_asset_file_hash", "media_asset", ["file_hash"])


def _copy_rows(new_table: str) -> None:
    column_list = ", ".join(COLUMNS)
    op.execute(f"INSERT INTO {new_table} ({column_list}) SELECT {column_list} FROM media_asset")


def _rebuild_sqlite(ondelete: str) -> None:
    _create_table("media_asset_new", ondelete)
    _copy_rows("media_asset_new")
    op.drop_table("media_asset")
    op.rename_table("media_asset_new", "media_asset")
    _create_indexes()


def upgrade() -> None:
    bind = op.get_bind()
    fk = _article_fk(bind)
    if fk and fk.get("options", {}).get("ondelete") == "SET NULL":
        return
    if bind.dialect.name == "sqlite":
        _rebuild_sqlite("SET NULL")
        return
    name = fk["name"] if fk else None
    if name:
        op.drop_constraint(name, "media_asset", type_="foreignkey")
    op.create_foreign_key(
        "fk_media_asset_article",
        "media_asset",
        "content_article",
        ["article_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    bind = op.get_bind()
    fk = _article_fk(bind)
    if fk and fk.get("options", {}).get("ondelete") == "CASCADE":
        return
    if bind.dialect.name == "sqlite":
        _rebuild_sqlite("CASCADE")
        return
    name = fk["name"] if fk else None
    if name:
        op.drop_constraint(name, "media_asset", type_="foreignkey")
    op.create_foreign_key(
        "fk_media_asset_article",
        "media_asset",
        "content_article",
        ["article_id"],
        ["id"],
        ondelete="CASCADE",
    )
