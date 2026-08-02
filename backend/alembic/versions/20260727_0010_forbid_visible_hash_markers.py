"""forbid visible hash markers in saved variants

Revision ID: 20260727_0010
Revises: 20260727_0009
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260727_0010"
down_revision: str | None = "20260727_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE content_variant "
            "SET title = REPLACE(title, '#', ''), "
            "content_text = REPLACE(content_text, '#', ''), "
            "original_generated_text = CASE "
            "WHEN original_generated_text IS NULL THEN NULL "
            "ELSE REPLACE(original_generated_text, '#', '') END"
        )
    )


def downgrade() -> None:
    # Removed presentation markers cannot be reconstructed reliably.
    pass
