from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.exceptions import AppException
from app.core.responses import success_response
from app.db.session import get_db
from app.models.business import ResearchItem
from app.models.user import User
from app.schemas.business import ResearchItemCreate, ResearchItemUpdate
from app.services.audit_service import record_audit
from app.services.serializers import model_dict

router = APIRouter(tags=["研究与灵感"])


def _data(row: ResearchItem) -> dict:
    data = model_dict(row, camel=True)
    data["tags"] = data.pop("tagsJson", [])
    return data


@router.get("/research-items")
def list_research_items(
    request: Request,
    query: str = Query(default="", max_length=100),
    status: str = Query(default="", max_length=30),
    archived: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    filters = [ResearchItem.created_by == user.id, ResearchItem.archived == archived]
    if query:
        pattern = f"%{query.strip()}%"
        filters.append(
            or_(
                ResearchItem.title.ilike(pattern),
                ResearchItem.summary.ilike(pattern),
                ResearchItem.notes.ilike(pattern),
                ResearchItem.topic_cluster.ilike(pattern),
            )
        )
    if status:
        filters.append(ResearchItem.status == status)
    rows = db.scalars(
        select(ResearchItem)
        .where(*filters)
        .order_by(ResearchItem.updated_at.desc(), ResearchItem.id.desc())
    ).all()
    return success_response(request, [_data(row) for row in rows])


@router.post("/research-items")
def create_research_item(
    payload: ResearchItemCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    duplicate = None
    if payload.source_id:
        duplicate = db.scalar(
            select(ResearchItem).where(
                ResearchItem.created_by == user.id,
                ResearchItem.source == payload.source,
                ResearchItem.source_id == payload.source_id,
            )
        )
    if duplicate:
        return success_response(request, _data(duplicate), "该来源已在灵感库中")
    values = payload.model_dump(exclude={"tags"})
    row = ResearchItem(**values, tags_json=payload.tags, created_by=user.id)
    db.add(row)
    db.flush()
    record_audit(db, request, user, "CREATE", "RESEARCH", "RESEARCH_ITEM", row.id)
    db.commit()
    db.refresh(row)
    return success_response(request, _data(row), "已保存到灵感库")


@router.put("/research-items/{item_id}")
def update_research_item(
    item_id: int,
    payload: ResearchItemUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    row = db.scalar(
        select(ResearchItem).where(ResearchItem.id == item_id, ResearchItem.created_by == user.id)
    )
    if not row:
        raise AppException(40412, "研究条目不存在", 404)
    values = payload.model_dump(exclude_unset=True, exclude={"tags"})
    for key, value in values.items():
        setattr(row, key, value)
    if payload.tags is not None:
        row.tags_json = list(dict.fromkeys(tag.strip() for tag in payload.tags if tag.strip()))
    record_audit(db, request, user, "UPDATE", "RESEARCH", "RESEARCH_ITEM", row.id)
    db.commit()
    db.refresh(row)
    return success_response(request, _data(row), "灵感条目已更新")


@router.delete("/research-items/{item_id}")
def archive_research_item(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    row = db.scalar(
        select(ResearchItem).where(ResearchItem.id == item_id, ResearchItem.created_by == user.id)
    )
    if not row:
        raise AppException(40412, "研究条目不存在", 404)
    row.archived = True
    record_audit(db, request, user, "ARCHIVE", "RESEARCH", "RESEARCH_ITEM", row.id)
    db.commit()
    return success_response(request, {"id": item_id}, "已移入归档")
