"""Historical engagement data import: template, preview, commit and batch history."""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.exceptions import AppException
from app.core.responses import success_response
from app.db.session import get_db
from app.models.business import EngagementHistory, HistoryImportBatch
from app.models.user import User
from app.services.activity_service import (
    SOURCE_TYPE_LABELS,
    content_type_name,
    summarize_import_window,
)
from app.services.audit_service import record_audit
from app.services.history_import_service import (
    CANONICAL_FIELDS,
    build_preview,
    build_template,
    commit_import,
    read_table,
    suggest_mapping,
)
from app.services.serializers import model_dict

router = APIRouter(tags=["历史数据导入"])


@router.get("/activity/history/template")
def history_template(_: User = Depends(get_current_user)) -> StreamingResponse:
    return StreamingResponse(
        iter([build_template()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=contentpilot-history-template.xlsx"},
    )


@router.get("/activity/history/fields")
def history_fields(request: Request, _: User = Depends(get_current_user)) -> dict:
    return success_response(
        request,
        {
            "fields": CANONICAL_FIELDS,
            "sourceTypes": [
                {"value": key, "label": value} for key, value in SOURCE_TYPE_LABELS.items()
            ],
        },
    )


def _parse_mapping(raw: str) -> dict[str, str]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AppException(40046, "字段映射不是合法的 JSON") from exc
    if not isinstance(value, dict):
        raise AppException(40046, "字段映射必须是对象")
    return {str(key): str(item or "") for key, item in value.items()}


@router.post("/activity/history/preview")
async def history_preview(
    request: Request,
    file: UploadFile = File(...),
    mapping: str = Form(default=""),
    default_platform: str = Form(default=""),
    default_source_type: str = Form(default="ACCOUNT_HISTORY"),
    default_content_type: str = Form(default=""),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("OPERATOR")),
) -> dict:
    raw = await file.read()
    headers, records = read_table(raw, file.filename or "")
    if not records:
        raise AppException(40047, "文件里没有数据行")
    resolved = suggest_mapping(headers)
    resolved.update({key: value for key, value in _parse_mapping(mapping).items() if value})
    data = build_preview(
        db,
        headers,
        records,
        resolved,
        default_platform=default_platform.strip().upper(),
        default_source_type=default_source_type,
        default_content_type=default_content_type,
    )
    data["filename"] = file.filename or ""
    return success_response(request, data, "文件解析完成")


@router.post("/activity/history/import")
async def history_import(
    request: Request,
    file: UploadFile = File(...),
    mapping: str = Form(default=""),
    default_platform: str = Form(default=""),
    default_source_type: str = Form(default="ACCOUNT_HISTORY"),
    default_content_type: str = Form(default=""),
    source_note: str = Form(default=""),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    raw = await file.read()
    headers, records = read_table(raw, file.filename or "")
    if not records:
        raise AppException(40047, "文件里没有数据行")
    resolved = suggest_mapping(headers)
    resolved.update({key: value for key, value in _parse_mapping(mapping).items() if value})
    batch = commit_import(
        db,
        filename=file.filename or "",
        headers=headers,
        records=records,
        mapping=resolved,
        user_id=user.id,
        default_platform=default_platform.strip().upper(),
        default_source_type=default_source_type,
        default_content_type=default_content_type,
        source_note=source_note,
    )
    record_audit(
        db,
        request,
        user,
        "IMPORT",
        "ANALYTICS",
        "HISTORY_BATCH",
        batch.id,
        {
            "filename": batch.filename,
            "success": batch.success_count,
            "duplicate": batch.duplicate_count,
            "errors": batch.error_count,
        },
    )
    db.commit()
    db.refresh(batch)
    rows = db.scalars(select(EngagementHistory).where(EngagementHistory.batch_id == batch.id)).all()
    data = model_dict(batch, camel=True)
    data["window"] = summarize_import_window(list(rows))
    data["sourceLabel"] = SOURCE_TYPE_LABELS.get(batch.source_type, batch.source_type)
    return success_response(request, data, "历史数据导入完成")


@router.get("/activity/history/batches")
def history_batches(
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    batches = db.scalars(
        select(HistoryImportBatch).order_by(HistoryImportBatch.id.desc()).limit(50)
    ).all()
    items = []
    for batch in batches:
        data = model_dict(batch, camel=True)
        data["sourceLabel"] = SOURCE_TYPE_LABELS.get(batch.source_type, batch.source_type)
        data["remainingRows"] = int(
            db.scalar(
                select(func.count())
                .select_from(EngagementHistory)
                .where(EngagementHistory.batch_id == batch.id)
            )
            or 0
        )
        items.append(data)
    total = int(db.scalar(select(func.count()).select_from(EngagementHistory)) or 0)
    by_source = db.execute(
        select(EngagementHistory.source_type, func.count(EngagementHistory.id)).group_by(
            EngagementHistory.source_type
        )
    ).all()
    return success_response(
        request,
        {
            "items": items,
            "totalRecords": total,
            "bySource": [
                {
                    "sourceType": item[0],
                    "label": SOURCE_TYPE_LABELS.get(item[0], item[0]),
                    "count": int(item[1]),
                }
                for item in by_source
            ],
        },
    )


@router.get("/activity/history/records")
def history_records(
    request: Request,
    platform: str = "",
    source_type: str = "",
    batch_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    filters = []
    if platform:
        filters.append(EngagementHistory.platform == platform)
    if source_type:
        filters.append(EngagementHistory.source_type == source_type)
    if batch_id:
        filters.append(EngagementHistory.batch_id == batch_id)
    total = int(db.scalar(select(func.count()).select_from(EngagementHistory).where(*filters)) or 0)
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    rows = db.scalars(
        select(EngagementHistory)
        .where(*filters)
        .order_by(EngagementHistory.publish_time.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = []
    for row in rows:
        data = model_dict(row, camel=True)
        data["contentTypeName"] = content_type_name(row.content_type)
        data["sourceLabel"] = SOURCE_TYPE_LABELS.get(row.source_type, row.source_type)
        items.append(data)
    return success_response(
        request, {"items": items, "total": total, "page": page, "pageSize": page_size}
    )


@router.delete("/activity/history/batches/{batch_id}")
def delete_batch(
    batch_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    batch = db.get(HistoryImportBatch, batch_id)
    if not batch:
        raise AppException(40408, "导入批次不存在", 404)
    removed = db.execute(
        delete(EngagementHistory).where(EngagementHistory.batch_id == batch_id)
    ).rowcount
    db.delete(batch)
    record_audit(
        db, request, user, "DELETE", "ANALYTICS", "HISTORY_BATCH", batch_id, {"rows": removed}
    )
    db.commit()
    return success_response(
        request, {"id": batch_id, "removed": int(removed or 0)}, "导入批次已删除"
    )


@router.get("/activity/history/summary")
def history_summary(
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    rows = db.execute(
        select(
            EngagementHistory.platform,
            EngagementHistory.source_type,
            func.count(EngagementHistory.id),
            func.min(EngagementHistory.publish_time),
            func.max(EngagementHistory.publish_time),
        ).group_by(EngagementHistory.platform, EngagementHistory.source_type)
    ).all()
    return success_response(
        request,
        {
            "items": [
                {
                    "platform": item[0],
                    "sourceType": item[1],
                    "sourceLabel": SOURCE_TYPE_LABELS.get(item[1], item[1]),
                    "count": int(item[2]),
                    "start": item[3].isoformat() if isinstance(item[3], datetime) else item[3],
                    "end": item[4].isoformat() if isinstance(item[4], datetime) else item[4],
                }
                for item in rows
            ],
            "notice": (
                "公开样本（含 YouTube 公开数据集）只作为冷启动基线，"
                "系统不会将其展示为微博 / 小红书 / 微信公众号的真实平台数据。"
            ),
        },
    )
