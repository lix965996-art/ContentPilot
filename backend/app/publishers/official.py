from app.publishers.base import PublishResult


class OfficialPublisherStub:
    """Extension point for an official platform API; never uses browser automation."""

    platform = "UNCONFIGURED"

    async def validate_account(self, account: object | None) -> bool:
        return False

    async def publish(self, request: dict) -> PublishResult:
        return PublishResult(
            False,
            "FAILED",
            message=f"{self.platform} 官方 API 尚未配置，请使用 MOCK 或 MANUAL 模式",
        )

    async def query_status(self, task_id: str) -> dict:
        return {"taskId": task_id, "status": "UNCONFIGURED"}


class WeiboPublisher(OfficialPublisherStub):
    platform = "WEIBO"


class WechatOfficialPublisher(OfficialPublisherStub):
    platform = "WECHAT_OFFICIAL"


class XiaohongshuPublisher(OfficialPublisherStub):
    platform = "XIAOHONGSHU"
