"""Preserve observation timestamp precision on MySQL instead of truncating microseconds."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME

from alembic import op

revision: str = "20261020_0025"
down_revision: str | None = "20261020_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMES = {
    "published_content_snapshot": ("feature_available_at", "published_at", "created_at"),
    "metric_collection_task": ("due_at", "claim_expires_at", "completed_at", "created_at"),
    "engagement_observation": ("observed_at", "published_at"),
}


def _precision(fsp: int) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return
    inspector = sa.inspect(bind)
    for table, names in TIMES.items():
        columns = {column["name"]: column for column in inspector.get_columns(table)}
        for name in names:
            column = columns[name]
            op.alter_column(
                table,
                name,
                type_=DATETIME(fsp=fsp),
                existing_type=column["type"],
                existing_nullable=column["nullable"],
                existing_server_default=sa.text(column["default"]) if column["default"] else None,
            )


def upgrade() -> None:
    _precision(6)


def downgrade() -> None:
    _precision(0)
