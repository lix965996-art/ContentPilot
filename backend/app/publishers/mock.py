import asyncio

from app.publishers.base import PublishResult


class MockPublisher:
    platform = "ALL"

    async def validate_account(self, account: object | None) -> bool:
        return True

    async def publish(self, request: dict) -> PublishResult:
        await asyncio.sleep(0.05)
        return PublishResult(
            True,
            "MOCK_SUCCESS",
            f"mock://socialflow/published/{request['schedule_id']}",
            "MOCK：模拟发布成功，未向任何真实平台发送内容",
        )

    async def query_status(self, task_id: str) -> dict:
        return {"taskId": task_id, "status": "MOCK_SUCCESS"}


class ManualConfirmPublisher(MockPublisher):
    async def publish(self, request: dict) -> PublishResult:
        return PublishResult(
            False, "WAITING_MANUAL_CONFIRM", None, "等待运营人员在平台后台发布后手工确认"
        )
