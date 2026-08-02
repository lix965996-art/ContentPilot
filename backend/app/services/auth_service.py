from datetime import datetime

from sqlalchemy import func, select
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
from app.models.user import Role, User


def authenticate_user(db: Session, username: str, password: str) -> User:
    normalized_username = username.strip().lower()
    user = db.scalar(select(User).where(func.lower(User.username) == normalized_username))
    if user is None or not verify_password(password, user.password_hash):
        raise AppException(40103, "用户名或密码错误", 401)
    if user.status != "ACTIVE":
        raise AppException(40302, "账号已停用，请联系管理员", 403)

    user.last_login_at = datetime.now()
    db.commit()
    db.refresh(user)
    return user


def register_user(
    db: Session,
    *,
    username: str,
    password: str,
    display_name: str,
    email: str,
) -> User:
    normalized_username = username.strip().lower()
    if db.scalar(select(User.id).where(func.lower(User.username) == normalized_username)):
        raise AppException(40921, "用户名已被使用", 409)
    if db.scalar(select(User.id).where(func.lower(User.email) == email.lower())):
        raise AppException(40922, "邮箱已被使用", 409)
    role = db.scalar(select(Role).where(Role.code == "OPERATOR"))
    if role is None:
        raise AppException(50302, "系统尚未初始化运营者角色，请联系管理员", 503)
    user = User(
        username=normalized_username,
        password_hash=hash_password(password),
        display_name=display_name.strip(),
        email=email.lower(),
        status="ACTIVE",
        last_login_at=datetime.now(),
        roles=[role],
    )
    db.add(user)
    db.flush()
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
