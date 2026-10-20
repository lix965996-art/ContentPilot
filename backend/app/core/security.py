from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

import jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.exceptions import AppException

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return password_context.verify(plain_password, password_hash)


def hash_password(password: str) -> str:
    return password_context.hash(password)


def create_token(
    subject: str,
    token_type: Literal["access", "refresh"],
    expires_delta: timedelta,
    token_version: int = 0,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
        "ver": token_version,
        "jti": uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(subject: str, token_version: int = 0) -> str:
    return create_token(
        subject,
        "access",
        timedelta(minutes=settings.jwt_expire_minutes),
        token_version,
    )


def create_refresh_token(subject: str, token_version: int = 0) -> str:
    return create_token(
        subject,
        "refresh",
        timedelta(days=settings.jwt_refresh_expire_days),
        token_version,
    )


def decode_token(token: str, expected_type: Literal["access", "refresh"]) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "type", "iat", "exp", "ver"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AppException(40102, "登录凭证已过期", 401) from exc
    except jwt.InvalidTokenError as exc:
        raise AppException(40101, "登录凭证无效", 401) from exc

    if payload.get("type") != expected_type or not payload.get("sub"):
        raise AppException(40101, "登录凭证类型无效", 401)
    if type(payload.get("ver")) is not int or payload["ver"] < 0:
        raise AppException(40101, "登录凭证无效", 401)
    return payload
