"""Persist metric basis and label only proven historical simulation provenance.

Revision ID: 20261011_0015_data_integrity
Revises: 20260804_0014
"""

import hashlib

import sqlalchemy as sa

from alembic import op

revision = "20261011_0015_data_integrity"
down_revision = "20260804_0014"
branch_labels = None
depends_on = None

SIMULATED_NOTE = "SIMULATED 演示账号历史（自动生成，非真实平台数据）"
FEEDBACK_NOTE = "系统内发布效果回流（PUBLISH_FEEDBACK）"


def upgrade() -> None:
    # There is no trustworthy way to infer which denominator a legacy caller
    # selected from counters or its stored rate. Keep its data, label UNKNOWN.
    op.add_column(
        "engagement_metric",
        sa.Column("metric_basis", sa.String(30), nullable=False, server_default="UNKNOWN"),
    )
    connection = op.get_bind()
    metadata = sa.MetaData()
    history = sa.Table("engagement_history", metadata, autoload_with=connection)
    batches = sa.Table("history_import_batch", metadata, autoload_with=connection)
    simulated_batches = set(
        connection.execute(
            sa.select(batches.c.id).where(batches.c.source_note == SIMULATED_NOTE)
        ).scalars()
    )
    source_sets: dict[int, set[str]] = {}
    public_history: dict[tuple, list[dict]] = {}
    for records in connection.execute(sa.select(history)).mappings().partitions(500):
        for row in records:
            detail = dict(row["metric_detail_json"] or {})
            source = row["source_type"]
            proven_simulated = (
                str(detail.get("dataSource", "")).upper() == "SIMULATED"
                or row["source_note"] == SIMULATED_NOTE
                or row["batch_id"] in simulated_batches
            )
            changes = {}
            if proven_simulated:
                source = "SIMULATED"
                changes["source_type"] = source
                detail["dataSource"] = "SIMULATED"
                if row["batch_id"] is not None and row["source_type"] != "SIMULATED":
                    changes["row_hash"] = hashlib.sha256(
                        f"{row['row_hash']}|SIMULATED".encode()
                    ).hexdigest()
            if row["source_note"] == FEEDBACK_NOTE and detail.get("scheduleId") is not None:
                detail["legacyMetricBasis"] = detail.get("metricBasis", "UNKNOWN")
                detail["metricBasis"] = "UNKNOWN"
                detail["rateAvailable"] = False
            if detail != (row["metric_detail_json"] or {}):
                changes["metric_detail_json"] = detail
            if changes:
                connection.execute(
                    history.update().where(history.c.id == row["id"]).values(**changes)
                )
            if row["batch_id"] is not None:
                source_sets.setdefault(row["batch_id"], set()).add(source)
            if (
                source == "YOUTUBE_PUBLIC_SAMPLE"
                and row["platform"] == "YOUTUBE"
                and detail.get("metricBasis") in {"IMPRESSIONS", "VIEWS", "FOLLOWERS"}
            ):
                key = (
                    row["account_ref"],
                    row["views"],
                    row["likes"],
                    row["comments"],
                    row["shares"],
                )
                public_history.setdefault(key, []).append(
                    {
                        "id": row["id"],
                        "basis": detail["metricBasis"],
                        "available": bool(detail.get("reach")),
                    }
                )
    for batch_id, sources in source_sets.items():
        source = next(iter(sources)) if len(sources) == 1 else "MIXED"
        connection.execute(
            batches.update().where(batches.c.id == batch_id).values(source_type=source)
        )
    samples = sa.Table("experiment_sample", metadata, autoload_with=connection)
    for records in (
        connection.execute(sa.select(samples.c.id, samples.c.metric_value_json))
        .mappings()
        .partitions(500)
    ):
        for row in records:
            values = dict(row["metric_value_json"] or {})
            if values.get("dataSource") != "YOUTUBE_PUBLIC_SAMPLE" or values.get("metricBasis") in {
                "IMPRESSIONS",
                "VIEWS",
                "FOLLOWERS",
            }:
                continue
            key = (
                values.get("videoId"),
                values.get("views"),
                values.get("likes"),
                values.get("comments"),
                values.get("shares"),
            )
            matches = public_history.get(key, [])
            if len(matches) == 1:
                values.update(
                    metricBasis=matches[0]["basis"],
                    rateAvailable=matches[0]["available"],
                    historyRowId=matches[0]["id"],
                )
                connection.execute(
                    samples.update()
                    .where(samples.c.id == row["id"])
                    .values(metric_value_json=values)
                )


def downgrade() -> None:
    # Provenance corrections are retained on downgrade; reverting them would
    # present confirmed simulation as real observations again.
    op.drop_column("engagement_metric", "metric_basis")
