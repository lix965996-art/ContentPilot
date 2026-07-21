import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.exceptions import AppException
from app.core.responses import success_response
from app.db.session import get_db
from app.models.business import ContentArticle, ContentVariant, GenerationTask
from app.models.user import User
from app.schemas.business import GenerateRequest, KeywordRequest
from app.services.audit_service import record_audit
from app.services.generation_service import extract_keywords, generate_variant_data, save_variant
from app.services.serializers import model_dict

router = APIRouter(tags=["AI 内容生成"])


@router.post("/generation/content")
async def generate(
    payload: GenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    article = db.get(ContentArticle, payload.article_id)
    if not article:
        raise AppException(40401, "文章不存在", 404)
    task = GenerationTask(
        id=str(uuid.uuid4()),
        article_id=article.id,
        status="RUNNING",
        progress=5,
        platforms_json=payload.platforms,
        result_variant_ids_json=[],
    )
    db.add(task)
    db.commit()
    try:
        ids = []
        options = payload.model_dump()
        for index, platform in enumerate(payload.platforms):
            data, model, duration, prompt_tokens, completion_tokens = await generate_variant_data(
                db, article, platform, options
            )
            variant = save_variant(
                db,
                article,
                platform,
                data,
                model,
                duration,
                prompt_tokens,
                completion_tokens,
            )
            ids.append(variant.id)
            task.progress = int((index + 1) / len(payload.platforms) * 90)
        task.result_variant_ids_json = ids
        task.progress = 100
        task.status = "SUCCESS"
        article.status = "GENERATED"
        record_audit(
            db,
            request,
            user,
            "GENERATE",
            "AI",
            "ARTICLE",
            article.id,
            {"platforms": payload.platforms, "taskId": task.id},
        )
        db.commit()
    except Exception as exc:
        task.status = "FAILED"
        task.error_message = str(exc)
        db.commit()
        raise
    return success_response(request, {"taskId": task.id, "status": task.status}, "生成完成")


@router.get("/generation/tasks/{task_id}")
def task_status(
    task_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    task = db.get(GenerationTask, task_id)
    if not task:
        raise AppException(40403, "生成任务不存在", 404)
    data = model_dict(task, camel=True)
    if task.result_variant_ids_json:
        data["variants"] = [
            model_dict(item, camel=True)
            for item in db.query(ContentVariant)
            .filter(ContentVariant.id.in_(task.result_variant_ids_json))
            .all()
        ]
    return success_response(request, data)


@router.post("/generation/content/{variant_id}/regenerate")
async def regenerate(
    variant_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    old = db.get(ContentVariant, variant_id)
    if not old:
        raise AppException(40402, "内容版本不存在", 404)
    payload = GenerateRequest(article_id=old.article_id, platforms=[old.platform])
    return await generate(payload, request, db, user)


@router.post("/generation/keywords")
def keywords(
    payload: KeywordRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    article = db.get(ContentArticle, payload.article_id)
    if not article:
        raise AppException(40401, "文章不存在", 404)
    return success_response(
        request,
        {
            "keywords": extract_keywords(article.title + "\n" + article.source_text),
            "provider": "MOCK",
        },
    )


@router.post("/generation/review")
def review(
    payload: KeywordRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    variant = db.get(ContentVariant, payload.article_id)
    if not variant:
        raise AppException(40402, "内容版本不存在", 404)
    score = variant.quality_score or 80
    return success_response(
        request,
        {
            "overallScore": score,
            "informationCompleteness": max(0, score - 3),
            "factualConsistency": min(100, score + 5),
            "platformFit": score,
            "readability": min(100, score + 2),
            "tagRelevance": score,
            "issues": [],
            "suggestions": ["发布前建议由运营人员完成最终事实核验"],
            "needHumanReview": True,
            "provider": "MOCK",
        },
    )
