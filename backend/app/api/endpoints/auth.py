from fastapi import APIRouter, Depends, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.exceptions import AppException
from app.core.responses import success_response
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    PasswordUpdateRequest,
    RefreshRequest,
    RegistrationRequest,
)
from app.schemas.user import UserData
from app.services.audit_service import record_audit
from app.services.auth_service import (
    authenticate_user,
    build_tokens,
    refresh_tokens,
    register_user,
    update_password,
)

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/login", summary="账号密码登录")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    user = authenticate_user(db, payload.username, payload.password)
    data = {
        **build_tokens(user),
        "user": UserData.model_validate(user).model_dump(mode="json"),
    }
    return success_response(request, data, "登录成功")


@router.post("/register", summary="注册运营者账号")
def register(
    payload: RegistrationRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    user = register_user(
        db,
        username=payload.username,
        password=payload.password,
        display_name=payload.display_name,
        email=payload.email,
    )
    record_audit(
        db,
        request,
        user,
        "REGISTER",
        "AUTH",
        "USER",
        user.id,
        {"role": "OPERATOR"},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppException(40921, "用户名或邮箱已被使用", 409) from exc
    db.refresh(user)
    data = {
        **build_tokens(user),
        "user": UserData.model_validate(user).model_dump(mode="json"),
    }
    return success_response(request, data, "注册成功")


@router.post("/logout", summary="退出登录")
def logout(
    request: Request,
    _: User = Depends(get_current_user),
) -> dict:
    return success_response(request, None, "已安全退出")


@router.get("/me", summary="获取当前用户")
def me(request: Request, user: User = Depends(get_current_user)) -> dict:
    return success_response(
        request,
        UserData.model_validate(user).model_dump(mode="json"),
    )


@router.post("/refresh", summary="刷新登录凭证")
def refresh(
    payload: RefreshRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    user, tokens = refresh_tokens(db, payload.refresh_token)
    return success_response(
        request,
        {
            **tokens,
            "user": UserData.model_validate(user).model_dump(mode="json"),
        },
        "凭证刷新成功",
    )


@router.put("/password", summary="修改当前用户密码")
def change_password(
    payload: PasswordUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    update_password(db, user, payload.current_password, payload.new_password)
    return success_response(request, None, "密码修改成功，请重新登录")
