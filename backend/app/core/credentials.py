import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _fernet() -> Fernet:
    source = settings.platform_credential_key or settings.jwt_secret
    key = base64.urlsafe_b64encode(hashlib.sha256(source.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


def encrypt_json(value: dict[str, Any]) -> str | None:
    if not value:
        return None
    return encrypt_secret(json.dumps(value, ensure_ascii=False))


def decrypt_json(value: str | None) -> dict[str, Any]:
    raw = decrypt_secret(value)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def secret_hint(value: str | None) -> str:
    plain = decrypt_secret(value)
    if not plain:
        return ""
    return f"••••{plain[-4:]}" if len(plain) >= 4 else "••••"
