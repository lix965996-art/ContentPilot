"""Independent provider usage ledger and monthly budget reservations.

Revision ID: 20261020_0023
Revises: 20261020_0022
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261020_0023"
down_revision: str | None = "20261020_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    ledger = op.create_table(
        "llm_usage_entry",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("legacy_variant_id", sa.Integer(), nullable=True, unique=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("operation", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("input_price", sa.Float(), nullable=False),
        sa.Column("output_price", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("estimated_cost", sa.Float(), nullable=True),
        sa.Column("reserved_cost", sa.Float(), nullable=False),
        sa.Column("pricing_status", sa.String(30), nullable=False),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_llm_usage_entry_created_at", "llm_usage_entry", ["created_at"])
    op.create_table(
        "llm_budget_month",
        sa.Column("id", sa.String(20), primary_key=True),
        sa.Column("reserved_cost", sa.Float(), nullable=False),
    )
    bind = op.get_bind()
    metadata = sa.MetaData()
    variants = sa.Table("content_variant", metadata, autoload_with=bind)
    settings = sa.Table("system_setting", metadata, autoload_with=bind)
    values = dict(bind.execute(sa.select(settings.c.setting_key, settings.c.setting_value)).all())
    input_price = float(values.get("llm.input_price_per_million", "0") or 0)
    output_price = float(values.get("llm.output_price_per_million", "0") or 0)
    for row in bind.execute(sa.select(variants).where(variants.c.token_usage > 0)).mappings():
        split_known = row["prompt_tokens"] + row["completion_tokens"] > 0
        cost = row["estimated_cost"] if row["estimated_cost"] > 0 else None
        saved_cost = cost is not None
        if cost is None and split_known and input_price + output_price > 0:
            cost = (
                row["prompt_tokens"] * input_price + row["completion_tokens"] * output_price
            ) / 1e6
        bind.execute(
            ledger.insert().values(
                id=str(uuid.uuid4()),
                legacy_variant_id=row["id"],
                provider="LEGACY",
                model=row["model_name"] or "未标记模型",
                operation="LEGACY_GENERATION",
                status="SUCCEEDED",
                prompt_tokens=row["prompt_tokens"] if split_known else row["token_usage"],
                completion_tokens=row["completion_tokens"] if split_known else 0,
                input_price=input_price,
                output_price=output_price,
                currency=values.get("llm.currency", "CNY"),
                estimated_cost=cost,
                reserved_cost=0,
                pricing_status="SAVED_ESTIMATE" if saved_cost else "LEGACY_ESTIMATE",
                created_at=row["created_at"],
                completed_at=row["created_at"],
            )
        )
    bind.execute(
        settings.insert().values(
            setting_key="llm.usage_ledger_initialized", setting_value="1", is_secret=False
        )
    )


def downgrade() -> None:
    op.execute("DELETE FROM system_setting WHERE setting_key='llm.usage_ledger_initialized'")
    op.drop_table("llm_budget_month")
    op.drop_index("ix_llm_usage_entry_created_at", table_name="llm_usage_entry")
    op.drop_table("llm_usage_entry")
