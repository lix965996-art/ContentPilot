"""Immutable observations, publication features and durable read-only jobs."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261020_0024"
down_revision: str | None = "20261020_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "published_content_snapshot",
        sa.Column(
            "schedule_id",
            sa.Integer(),
            sa.ForeignKey("publish_schedule.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("platform", sa.String(30), nullable=False),
        sa.Column("account_ref", sa.String(64), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("feature_available_at", sa.DateTime(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "metric_collection_task",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "schedule_id",
            sa.Integer(),
            sa.ForeignKey("publish_schedule.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("window_seconds", sa.Integer(), nullable=False),
        sa.Column("request_key", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("due_at", sa.DateTime(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("claim_expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.String(255), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("schedule_id", "window_seconds", "request_key", name="uq_metric_task"),
    )
    for field in ("schedule_id", "status", "due_at"):
        op.create_index(f"ix_metric_collection_task_{field}", "metric_collection_task", [field])
    op.create_table(
        "engagement_observation",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "task_id",
            sa.String(36),
            sa.ForeignKey("metric_collection_task.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column(
            "schedule_id",
            sa.Integer(),
            sa.ForeignKey("publish_schedule.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("platform", sa.String(30), nullable=False),
        sa.Column("account_ref", sa.String(64), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("age_seconds", sa.Integer(), nullable=True),
        sa.Column("window_seconds", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        *[
            sa.Column(field, sa.Integer(), nullable=True)
            for field in ("likes", "replies", "reposts", "quotes", "http_status")
        ],
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("adapter_version", sa.String(30), nullable=False),
        sa.UniqueConstraint("task_id", "attempt", name="uq_observation_attempt"),
    )
    for field in ("task_id", "schedule_id", "platform", "observed_at"):
        op.create_index(f"ix_engagement_observation_{field}", "engagement_observation", [field])


def downgrade() -> None:
    op.drop_table("engagement_observation")
    op.drop_table("metric_collection_task")
    op.drop_table("published_content_snapshot")
