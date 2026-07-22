"""remove user-facing mock modes

Revision ID: 20260722_0007
Revises: 20260722_0006
Create Date: 2026-07-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260722_0007"
down_revision: str | None = "20260722_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Legacy demo accounts must never remain visually connected after MOCK is removed.
    op.execute(
        "UPDATE platform_account SET publish_mode = 'REAL_API', status = 'NOT_CONFIGURED', "
        "last_error = '请配置真实微博开放平台凭证并完成 OAuth 授权' "
        "WHERE platform = 'WEIBO' AND publish_mode = 'MOCK'"
    )
    op.execute(
        "UPDATE platform_account SET publish_mode = 'DRAFT_ONLY', status = 'NOT_CONFIGURED', "
        "last_error = '请配置真实微信公众号 AppID/AppSecret' "
        "WHERE platform = 'WECHAT_OFFICIAL' AND publish_mode = 'MOCK'"
    )
    op.execute(
        "UPDATE platform_account SET publish_mode = 'MANUAL_CONFIRM', status = 'MANUAL_ONLY', "
        "last_error = NULL WHERE platform = 'XIAOHONGSHU'"
    )
    op.execute(
        "UPDATE publish_schedule SET publish_mode = 'REAL_API', status = 'CANCELLED', "
        "result_mode = NULL, published_url = NULL, external_id = NULL, actual_publish_at = NULL, "
        "error_message = '旧版模拟任务已停用，内容没有发布到真实微博' "
        "WHERE platform = 'WEIBO' AND publish_mode = 'MOCK'"
    )
    op.execute(
        "UPDATE publish_schedule SET publish_mode = 'DRAFT_ONLY', status = 'CANCELLED', "
        "result_mode = NULL, published_url = NULL, external_id = NULL, actual_publish_at = NULL, "
        "error_message = '旧版模拟任务已停用，内容没有进入真实公众号草稿箱' "
        "WHERE platform = 'WECHAT_OFFICIAL' AND publish_mode = 'MOCK'"
    )
    op.execute(
        "UPDATE publish_schedule SET publish_mode = 'MANUAL_CONFIRM', status = 'CANCELLED', "
        "result_mode = NULL, published_url = NULL, external_id = NULL, actual_publish_at = NULL, "
        "error_message = '旧版模拟任务已停用，请重新创建人工发布任务' "
        "WHERE platform = 'XIAOHONGSHU' AND publish_mode = 'MOCK'"
    )
    op.execute(
        "UPDATE publish_log SET status = 'CANCELLED', response_summary = "
        "'旧版模拟结果已作废，没有调用真实平台接口' "
        "WHERE status IN ('MOCK_SUCCESS', 'MOCK_DRAFT_CREATED')"
    )
    op.execute(
        "UPDATE content_variant SET model_name = 'demo-baseline-v1' "
        "WHERE model_name = 'mock-socialflow-v1'"
    )
    op.execute(
        "UPDATE system_setting SET setting_value = 'openai-compatible' "
        "WHERE setting_key = 'llm.provider' AND LOWER(setting_value) = 'mock'"
    )
    op.execute(
        "UPDATE system_setting SET setting_value = '' "
        "WHERE setting_key = 'llm.model' AND setting_value = 'contentpilot-local'"
    )


def downgrade() -> None:
    # Reviving simulated success records would misrepresent external side effects.
    pass
