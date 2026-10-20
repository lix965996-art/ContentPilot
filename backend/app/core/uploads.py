"""Bounded upload reading so oversized files cannot exhaust memory first."""

from __future__ import annotations

from fastapi import UploadFile

from app.core.exceptions import AppException

CHUNK_SIZE = 1024 * 1024


async def read_upload_limited(
    file: UploadFile,
    max_bytes: int,
    *,
    code: int = 40042,
    label: str = "文件",
) -> bytes:
    """Read an upload in chunks and stop as soon as it exceeds ``max_bytes``.

    ``UploadFile.size`` is used when the ASGI server exposes it; chunking is the
    backstop for chunked transfers that do not declare a length.
    """
    declared = getattr(file, "size", None)
    if declared is not None and declared > max_bytes:
        raise AppException(code, f"{label}不能超过 {max_bytes // 1024 // 1024}MB")
    buffer = bytearray()
    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            return bytes(buffer)
        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            raise AppException(code, f"{label}不能超过 {max_bytes // 1024 // 1024}MB")
