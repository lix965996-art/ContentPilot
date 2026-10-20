"""Conservative normalization of public post counters; never manufacture reach."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.astimezone(UTC).replace(tzinfo=None) if result.tzinfo else None
    except (ValueError, OverflowError):
        return None


def counter(value: Any) -> int | None:
    return value if type(value) is int and 0 <= value <= 2_147_483_647 else None


@dataclass
class MetricReadResult:
    status: str
    counts: dict[str, int | None] = field(default_factory=dict)
    published_at: datetime | None = None
    http_status: int | None = None
    error_code: str = ""
    retryable: bool = False
    retry_after: int = 0


def response_failure(response: httpx.Response) -> MetricReadResult:
    status = response.status_code
    code = {
        401: "AUTH_REQUIRED",
        403: "PERMISSION_DENIED",
        404: "POST_UNAVAILABLE",
        429: "RATE_LIMITED",
    }.get(status, "UPSTREAM_UNAVAILABLE" if status >= 500 else "INVALID_RESPONSE")
    delay = 0
    try:
        value = response.headers.get("Retry-After", "0")
        delay = int(value)
    except ValueError:
        try:
            delay = int(
                (
                    parsedate_to_datetime(value).astimezone(UTC).replace(tzinfo=None) - utc_now()
                ).total_seconds()
            )
        except (ValueError, TypeError, OverflowError):
            delay = 0
    return MetricReadResult(
        "FAILED",
        http_status=status,
        error_code=code,
        retryable=status == 429 or status >= 500,
        retry_after=max(0, min(delay, 86400)),
    )
