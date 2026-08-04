"""historical engagement data, activity analysis and recommendation-aware scheduling

Revision ID: 20260803_0012
Revises: 20260729_0011
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260803_0012"
down_revision: str | None = "20260729_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "history_import_batch",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename", sa.String(length=255), nullable=False, server_default=""),
        sa.Column(
            "source_type", sa.String(length=40), nullable=False, server_default="ACCOUNT_HISTORY"
        ),
        sa.Column("source_note", sa.String(length=255), nullable=True),
        sa.Column("platform_hint", sa.String(length=30), nullable=True),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("missing_value_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("field_mapping_json", sa.JSON(), nullable=True),
        sa.Column("errors_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="COMPLETED"),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["sys_user.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_history_import_batch_source_type", "history_import_batch", ["source_type"])
    op.create_index("ix_history_import_batch_created_at", "history_import_batch", ["created_at"])

    op.create_table(
        "engagement_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(), nullable=True),
        sa.Column("platform", sa.String(length=30), nullable=False),
        sa.Column("account_ref", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("content_type", sa.String(length=50), nullable=False, server_default="UNKNOWN"),
        sa.Column("publish_time", sa.DateTime(), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("hour_of_day", sa.Integer(), nullable=False),
        sa.Column("views", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("impressions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("likes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("comments", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("shares", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("favorites", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("followers", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("engagement_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("engagement_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("engagement_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("metric_detail_json", sa.JSON(), nullable=True),
        sa.Column(
            "source_type", sa.String(length=40), nullable=False, server_default="ACCOUNT_HISTORY"
        ),
        sa.Column("source_note", sa.String(length=255), nullable=True),
        sa.Column("row_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["batch_id"], ["history_import_batch.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["account_id"], ["platform_account.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["sys_user.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("row_hash", name="uq_engagement_history_row"),
    )
    for column in (
        "batch_id",
        "platform",
        "account_ref",
        "account_id",
        "content_type",
        "publish_time",
        "day_of_week",
        "hour_of_day",
        "engagement_score",
        "source_type",
    ):
        op.create_index(f"ix_engagement_history_{column}", "engagement_history", [column])

    with op.batch_alter_table("publish_recommendation") as batch_op:
        batch_op.add_column(sa.Column("account_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("content_type", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("target_date", sa.Date(), nullable=True))
        batch_op.add_column(
            sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("account_sample_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("baseline_sample_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("weights_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("data_source_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("warnings_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("conflicts_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("narrative", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "narrative_provider",
                sa.String(length=30),
                nullable=False,
                server_default="RULE_BASED",
            )
        )
        batch_op.create_foreign_key(
            "fk_publish_recommendation_account",
            "platform_account",
            ["account_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("publish_schedule") as batch_op:
        batch_op.add_column(sa.Column("recommendation_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("recommended_at", sa.DateTime(), nullable=True))
        batch_op.add_column(
            sa.Column("time_source", sa.String(length=30), nullable=False, server_default="CUSTOM")
        )
        batch_op.add_column(sa.Column("content_type", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("recommendation_snapshot_json", sa.JSON(), nullable=True))
        batch_op.create_index("ix_publish_schedule_recommendation_id", ["recommendation_id"])
        batch_op.create_index("ix_publish_schedule_time_source", ["time_source"])
        batch_op.create_foreign_key(
            "fk_publish_schedule_recommendation",
            "publish_recommendation",
            ["recommendation_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("publish_schedule") as batch_op:
        batch_op.drop_constraint("fk_publish_schedule_recommendation", type_="foreignkey")
        batch_op.drop_index("ix_publish_schedule_time_source")
        batch_op.drop_index("ix_publish_schedule_recommendation_id")
        batch_op.drop_column("recommendation_snapshot_json")
        batch_op.drop_column("content_type")
        batch_op.drop_column("time_source")
        batch_op.drop_column("recommended_at")
        batch_op.drop_column("recommendation_id")

    with op.batch_alter_table("publish_recommendation") as batch_op:
        batch_op.drop_constraint("fk_publish_recommendation_account", type_="foreignkey")
        batch_op.drop_column("narrative_provider")
        batch_op.drop_column("narrative")
        batch_op.drop_column("conflicts_json")
        batch_op.drop_column("warnings_json")
        batch_op.drop_column("data_source_json")
        batch_op.drop_column("weights_json")
        batch_op.drop_column("baseline_sample_count")
        batch_op.drop_column("account_sample_count")
        batch_op.drop_column("sample_count")
        batch_op.drop_column("target_date")
        batch_op.drop_column("content_type")
        batch_op.drop_column("account_id")

    op.drop_table("engagement_history")
    op.drop_index("ix_history_import_batch_created_at", table_name="history_import_batch")
    op.drop_index("ix_history_import_batch_source_type", table_name="history_import_batch")
    op.drop_table("history_import_batch")
