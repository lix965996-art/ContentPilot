"""add platform account integration and publishing result fields

Revision ID: 20260721_0004
Revises: 20260721_0003
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260721_0004"
down_revision: str | None = "20260721_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    def add_column(table: str, column: sa.Column) -> None:
        existing = {item["name"] for item in sa.inspect(bind).get_columns(table)}
        if column.name not in existing:
            op.add_column(table, column)

    add_column(
        "platform_account",
        sa.Column("auth_type", sa.String(length=30), nullable=False, server_default="NONE"),
    )
    add_column("platform_account", sa.Column("app_id", sa.String(length=255), nullable=True))
    add_column("platform_account", sa.Column("client_id", sa.String(length=255), nullable=True))
    add_column("platform_account", sa.Column("credentials_encrypted", sa.Text(), nullable=True))
    add_column("platform_account", sa.Column("access_token_encrypted", sa.Text(), nullable=True))
    add_column("platform_account", sa.Column("refresh_token_encrypted", sa.Text(), nullable=True))
    add_column("platform_account", sa.Column("token_expires_at", sa.DateTime(), nullable=True))
    add_column("platform_account", sa.Column("capabilities_json", sa.JSON(), nullable=True))
    add_column("platform_account", sa.Column("last_test_at", sa.DateTime(), nullable=True))
    add_column("platform_account", sa.Column("last_error", sa.Text(), nullable=True))
    empty_json = "JSON_ARRAY()" if bind.dialect.name == "mysql" else "'[]'"
    op.execute(
        f"UPDATE platform_account SET capabilities_json = {empty_json} "
        "WHERE capabilities_json IS NULL"
    )
    op.execute(
        "UPDATE platform_account SET credentials_encrypted = credential_encrypted "
        "WHERE credentials_encrypted IS NULL AND credential_encrypted IS NOT NULL"
    )
    op.execute("UPDATE platform_account SET status = 'CONNECTED' WHERE status = 'ACTIVE'")
    unique_names = {
        item.get("name") for item in sa.inspect(bind).get_unique_constraints("platform_account")
    }
    with op.batch_alter_table("platform_account") as batch_op:
        batch_op.alter_column("capabilities_json", existing_type=sa.JSON(), nullable=False)
        if "uq_platform_account_user" not in unique_names:
            batch_op.create_unique_constraint("uq_platform_account_user", ["user_id", "platform"])
    if not sa.inspect(bind).has_table("platform_auth_log"):
        op.create_table(
            "platform_auth_log",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("platform_account_id", sa.Integer(), nullable=False),
            sa.Column("action", sa.String(length=50), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("message", sa.String(length=500), nullable=False, server_default=""),
            sa.Column("detail_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(
                ["platform_account_id"], ["platform_account.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_platform_auth_log_account", "platform_auth_log", ["platform_account_id"]
        )
        op.create_index("ix_platform_auth_log_action", "platform_auth_log", ["action"])
        op.create_index("ix_platform_auth_log_created", "platform_auth_log", ["created_at"])
    add_column("publish_schedule", sa.Column("external_id", sa.String(255), nullable=True))
    add_column("publish_schedule", sa.Column("result_mode", sa.String(30), nullable=True))
    add_column("publish_schedule", sa.Column("publish_package_json", sa.JSON(), nullable=True))
    empty_object = "JSON_OBJECT()" if bind.dialect.name == "mysql" else "'{}'"
    op.execute(
        f"UPDATE publish_schedule SET publish_package_json = {empty_object} "
        "WHERE publish_package_json IS NULL"
    )
    op.alter_column(
        "publish_schedule", "publish_package_json", existing_type=sa.JSON(), nullable=False
    )


def downgrade() -> None:
    op.drop_column("publish_schedule", "publish_package_json")
    op.drop_column("publish_schedule", "result_mode")
    op.drop_column("publish_schedule", "external_id")
    # Dropping the table removes its indexes; dropping the FK-backed index
    # first is rejected by MySQL while the constraint still exists.
    op.drop_table("platform_auth_log")
    with op.batch_alter_table("platform_account") as batch_op:
        batch_op.drop_constraint("uq_platform_account_user", type_="unique")
        batch_op.drop_column("last_error")
        batch_op.drop_column("last_test_at")
        batch_op.drop_column("capabilities_json")
        batch_op.drop_column("token_expires_at")
        batch_op.drop_column("refresh_token_encrypted")
        batch_op.drop_column("access_token_encrypted")
        batch_op.drop_column("credentials_encrypted")
        batch_op.drop_column("client_id")
        batch_op.drop_column("app_id")
        batch_op.drop_column("auth_type")
