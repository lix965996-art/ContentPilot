from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.responses import success_response
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, PasswordUpdateRequest, RefreshRequest
from app.schemas.user import UserData
from app.services.auth_service import (
    authenticate_user,
    build_tokens,
    refresh_tokens,
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
