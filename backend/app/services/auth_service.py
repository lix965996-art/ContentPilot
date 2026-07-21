from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppException
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User


def authenticate_user(db: Session, username: str, password: str) -> User:
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not verify_password(password, user.password_hash):
        raise AppException(40103, "用户名或密码错误", 401)
    if user.status != "ACTIVE":
        raise AppException(40302, "账号已停用，请联系管理员", 403)

    user.last_login_at = datetime.now()
    db.commit()
    db.refresh(user)
    return user


def build_tokens(user: User) -> dict[str, str | int]:
    return {
        "access_token": create_access_token(str(user.id)),
        "refresh_token": create_refresh_token(str(user.id)),
        "token_type": "bearer",
        "expires_in": settings.jwt_expire_minutes * 60,
    }


def refresh_tokens(db: Session, refresh_token: str) -> tuple[User, dict[str, str | int]]:
    payload = decode_token(refresh_token, "refresh")
    user = db.get(User, int(payload["sub"]))
    if user is None or user.status != "ACTIVE":
        raise AppException(40101, "用户不存在或账号不可用", 401)
    return user, build_tokens(user)


def update_password(
    db: Session,
    user: User,
    current_password: str,
    new_password: str,
) -> None:
    if not verify_password(current_password, user.password_hash):
        raise AppException(40003, "当前密码不正确")
    if current_password == new_password:
        raise AppException(40004, "新密码不能与当前密码相同")
    user.password_hash = hash_password(new_password)
    db.commit()
