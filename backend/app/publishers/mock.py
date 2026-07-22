import asyncio
from typing import Any

from app.publishers.base import PublishResult


class MockPublisher:
    platform = "ALL"
    mode = "MOCK"

    def __init__(self, platform: str = "ALL") -> None:
        self.platform = platform

    async def validate_credentials(self) -> PublishResult:
        return PublishResult(True, self.platform, self.mode, "CONNECTED")

    async def get_capabilities(self) -> list[str]:
        return ["SIMULATED_PUBLISH"]

    async def publish(self, request: dict[str, Any]) -> PublishResult:
        await asyncio.sleep(0.01)
        schedule_id = request["schedule_id"]
        return PublishResult(
            True,
            self.platform,
            self.mode,
            "MOCK_SUCCESS",
            external_id=f"mock-{schedule_id}",
            published_url=f"mock://contentpilot/published/{schedule_id}",
            detail={"simulated": True},
        )

    async def query_status(self, task_id: str) -> dict[str, Any]:
        return {"taskId": task_id, "status": "MOCK_SUCCESS", "simulated": True}

    async def disconnect(self) -> PublishResult:
        return PublishResult(True, self.platform, self.mode, "DISCONNECTED")


class ManualConfirmPublisher(MockPublisher):
    mode = "MANUAL_CONFIRM"

    async def get_capabilities(self) -> list[str]:
        return ["CONTENT_HANDOFF", "MANUAL_CONFIRM"]

    async def publish(self, request: dict[str, Any]) -> PublishResult:
        return PublishResult(
            False,
            self.platform,
            self.mode,
            "WAITING_MANUAL_CONFIRM",
            retryable=False,
            suggested_action="请在平台后台发布后填写公开链接并确认。",
        )
