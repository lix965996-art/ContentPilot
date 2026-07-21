from collections.abc import Callable

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppException(40101, "请先登录", 401)
    payload = decode_token(credentials.credentials, "access")
    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError) as exc:
        raise AppException(40101, "登录凭证无效", 401) from exc
    user = db.get(User, user_id)
    if user is None or user.status != "ACTIVE":
        raise AppException(40101, "用户不存在或账号不可用", 401)
    return user


def require_roles(*allowed_roles: str) -> Callable[..., User]:
    allowed = set(allowed_roles)

    def role_dependency(user: User = Depends(get_current_user)) -> User:
        user_roles = {role.code for role in user.roles}
        if not user_roles.intersection(allowed):
            raise AppException(40301, "当前账号无权执行此操作", 403)
        return user

    return role_dependency
