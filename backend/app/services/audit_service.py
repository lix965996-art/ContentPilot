from fastapi import Request
from sqlalchemy.orm import Session

from app.models.business import AuditLog
from app.models.user import User


def record_audit(
    db: Session,
    request: Request,
    user: User | None,
    action: str,
    module: str,
    target_type: str | None = None,
    target_id: object | None = None,
    detail: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user.id if user else None,
            action=action,
            module=module,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            request_path=str(request.url.path),
            request_method=request.method,
            ip_address=request.client.host if request.client else None,
            success=True,
            detail_json=detail or {},
        )
    )
