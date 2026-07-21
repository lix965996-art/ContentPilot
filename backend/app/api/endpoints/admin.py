from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.exceptions import AppException
from app.core.responses import success_response
from app.core.security import hash_password
from app.db.session import get_db
from app.models.business import AuditLog, SystemSetting
from app.models.user import Role, User
from app.schemas.business import LlmConfigUpdate, SettingUpdate, UserCreate
from app.schemas.user import UserData
from app.services.audit_service import record_audit
from app.services.llm_config_service import (
    llm_usage,
    read_llm_config,
    save_llm_config,
    test_llm_connection,
)
from app.services.serializers import model_dict
from app.services.setting_service import encrypt_secret

router = APIRouter(tags=["系统管理"])


@router.post("/admin/users")
def create_user(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> dict:
    if db.scalar(select(User).where(User.username == payload.username)):
        raise AppException(40921, "用户名已存在", 409)
    role = db.scalar(select(Role).where(Role.code == payload.role))
    row = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
        email=payload.email,
        status="ACTIVE",
        roles=[role] if role else [],
    )
    db.add(row)
    db.flush()
    record_audit(db, request, user, "CREATE", "SYSTEM", "USER", row.id, {"role": payload.role})
    db.commit()
    db.refresh(row)
    return success_response(
        request, UserData.model_validate(row).model_dump(mode="json"), "用户已创建"
    )


@router.put("/admin/users/{user_id}/status")
async def update_user_status(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles("ADMIN")),
) -> dict:
    row = db.get(User, user_id)
    if not row:
        raise AppException(40421, "用户不存在", 404)
    body = await request.json()
    status = body.get("status")
    if status not in {"ACTIVE", "DISABLED"}:
        raise AppException(40051, "用户状态无效")
    if row.id == actor.id and status == "DISABLED":
        raise AppException(40052, "不能禁用当前登录账号")
    row.status = status
    record_audit(db, request, actor, "UPDATE_STATUS", "SYSTEM", "USER", row.id, {"status": status})
    db.commit()
    return success_response(
        request, UserData.model_validate(row).model_dump(mode="json"), "用户状态已更新"
    )


@router.get("/admin/audit-logs")
def audit_logs(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    module: str = "",
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("ADMIN")),
) -> dict:
    query = select(AuditLog).order_by(AuditLog.created_at.desc())
    if module:
        query = query.where(AuditLog.module == module)
    items = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return success_response(request, [model_dict(row, camel=True) for row in items])


@router.get("/settings")
def settings_list(
    request: Request, db: Session = Depends(get_db), _: User = Depends(require_roles("ADMIN"))
) -> dict:
    items = []
    for row in db.scalars(select(SystemSetting).order_by(SystemSetting.setting_key)).all():
        data = model_dict(row, camel=True)
        if row.is_secret and row.setting_value:
            data["settingValue"] = "••••••••"
        items.append(data)
    return success_response(request, items)


@router.get("/settings/model-service")
def get_model_service(
    request: Request, db: Session = Depends(get_db), _: User = Depends(require_roles("ADMIN"))
) -> dict:
    return success_response(request, read_llm_config(db))


@router.put("/settings/model-service")
def update_model_service(
    payload: LlmConfigUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> dict:
    data = save_llm_config(db, payload)
    record_audit(
        db,
        request,
        user,
        "UPDATE",
        "SETTINGS",
        "MODEL_SERVICE",
        payload.provider,
        {"provider": payload.provider, "model": payload.model},
    )
    db.commit()
    return success_response(request, data, "模型服务配置已保存")


@router.post("/settings/model-service/test")
async def test_model_service(
    payload: LlmConfigUpdate,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("ADMIN")),
) -> dict:
    return success_response(request, await test_llm_connection(db, payload))


@router.get("/settings/model-service/usage")
def model_service_usage(
    request: Request,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("ADMIN")),
) -> dict:
    return success_response(request, llm_usage(db, days))


@router.put("/settings/{setting_key}")
def update_setting(
    setting_key: str,
    payload: SettingUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
) -> dict:
    row = db.scalar(select(SystemSetting).where(SystemSetting.setting_key == setting_key))
    if not row:
        raise AppException(40422, "系统配置项不存在", 404)
    if row.is_secret and payload.value == "••••••••":
        return success_response(request, {"settingKey": setting_key}, "密钥未变更")
    row.setting_value = encrypt_secret(payload.value) if row.is_secret else payload.value
    record_audit(
        db,
        request,
        user,
        "UPDATE",
        "SETTINGS",
        "SYSTEM_SETTING",
        setting_key,
        {"secret": row.is_secret},
    )
    db.commit()
    return success_response(
        request,
        {
            "settingKey": setting_key,
            "settingValue": "••••••••"
            if row.is_secret and row.setting_value
            else row.setting_value,
        },
        "配置已保存",
    )
