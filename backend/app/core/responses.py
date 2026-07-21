from typing import Any

from fastapi import Request


def _trace_id(request: Request) -> str:
    return getattr(request.state, "trace_id", "")


def success_response(
    request: Request,
    data: Any = None,
    message: str = "success",
) -> dict[str, Any]:
    return {
        "code": 0,
        "message": message,
        "data": data,
        "traceId": _trace_id(request),
    }


def error_response(
    request: Request,
    code: int,
    message: str,
    data: Any = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "data": data,
        "traceId": _trace_id(request),
    }
