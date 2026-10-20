"""mark legacy reviews without a content fingerprint as needing confirmation

Reviews created before review_fingerprint existed cannot be proven to describe
the current content. They are moved back to PENDING with an explicit stale
marker instead of backfilling the current fingerprint and pretending the old
approval is still valid.

Revision ID: 20261020_0021
Revises: 20261020_0020
Create Date: 2026-10-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261020_0021"
down_revision: str | None = "20261020_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE content_variant "
        "SET review_status = 'PENDING', quality_score = 0, "
        "review_detail_json = "
        '\'{"stale": true, "staleReason": "旧审核缺少内容指纹，需重新审核"}\' '
        "WHERE review_status IN ('APPROVED', 'REJECTED') "
        "AND review_fingerprint IS NULL"
    )
    op.execute(
        "UPDATE content_article SET status = 'GENERATED' "
        "WHERE status = 'APPROVED' AND NOT EXISTS ("
        "SELECT 1 FROM content_variant "
        "WHERE content_variant.article_id = content_article.id "
        "AND content_variant.review_status = 'APPROVED')"
    )


def downgrade() -> None:
    # The previous review state cannot be reconstructed safely; keep the
    # explicit "needs confirmation" marker rather than pretending it was valid.
    pass
