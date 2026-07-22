from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


@dataclass
class PublishResult:
    success: bool
    platform: str
    mode: str
    status: str
    external_id: str = ""
    published_url: str = ""
    retryable: bool = False
    error_code: str = ""
    error_message: str = ""
    suggested_action: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def url(self) -> str | None:
        return self.published_url or None

    @property
    def message(self) -> str:
        return self.error_message or self.status

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class PlatformPublisher(Protocol):
    platform: str
    mode: str

    async def validate_credentials(self) -> PublishResult: ...
    async def get_capabilities(self) -> list[str]: ...
    async def publish(self, request: dict[str, Any]) -> PublishResult: ...
    async def query_status(self, task_id: str) -> dict[str, Any]: ...
    async def disconnect(self) -> PublishResult: ...
