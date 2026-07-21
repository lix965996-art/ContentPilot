from dataclasses import dataclass
from typing import Protocol


@dataclass
class PublishResult:
    success: bool
    status: str
    url: str | None = None
    message: str = ""


class PlatformPublisher(Protocol):
    platform: str

    async def validate_account(self, account: object | None) -> bool: ...
    async def publish(self, request: dict) -> PublishResult: ...
    async def query_status(self, task_id: str) -> dict: ...
