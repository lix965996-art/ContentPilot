"""clean legacy simulated connection labels

Revision ID: 20260722_0008
Revises: 20260722_0007
Create Date: 2026-07-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260722_0008"
down_revision: str | None = "20260722_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE platform_account SET account_name = '微博账号（待真实授权）' "
        "WHERE platform = 'WEIBO' AND account_name LIKE '%本地演示%'"
    )
    op.execute(
        "UPDATE platform_account SET account_name = '公众号（待真实配置）' "
        "WHERE platform = 'WECHAT_OFFICIAL' AND account_name LIKE '%草稿演示%'"
    )
    op.execute(
        "UPDATE platform_account SET capabilities_json = "
        '\'["TEXT_PUBLISH","IMAGE_PUBLISH","STATUS_READ"]\' '
        "WHERE platform = 'WEIBO'"
    )
    op.execute(
        "UPDATE platform_account SET capabilities_json = "
        '\'["MATERIAL_UPLOAD","DRAFT_CREATE"]\', access_token_encrypted = NULL, '
        "token_expires_at = NULL WHERE platform = 'WECHAT_OFFICIAL' "
        "AND status = 'NOT_CONFIGURED'"
    )
    op.execute(
        "UPDATE platform_account SET capabilities_json = "
        '\'["COPYWRITING","IMAGE_PACKAGE","MANUAL_CONFIRM"]\' '
        "WHERE platform = 'XIAOHONGSHU'"
    )
    op.execute("DELETE FROM platform_auth_log WHERE action = 'DEMO_SETUP'")
    op.execute(
        "DELETE FROM platform_auth_log WHERE action = 'TEST_CONNECTION' AND status = 'SUCCESS' "
        "AND platform_account_id IN (SELECT id FROM platform_account "
        "WHERE status IN ('NOT_CONFIGURED', 'MANUAL_ONLY'))"
    )


def downgrade() -> None:
    pass
