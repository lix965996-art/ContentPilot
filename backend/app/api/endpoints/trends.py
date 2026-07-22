from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.responses import success_response
from app.db.session import get_db
from app.models.user import User
from app.schemas.trends import TrendAnalysisOutput, TrendAnalyzeRequest
from app.services.generation_service import _validated_completion, load_llm_runtime
from app.services.trend_service import aggregate_trends

router = APIRouter(tags=["热点选题"])


@router.get("/trends")
async def trends(
    request: Request,
    source: str = Query(default="ALL", pattern="^(ALL|BAIDU|HACKER_NEWS)$"),
    limit: int = Query(default=20, ge=1, le=50),
    query: str = Query(default="", max_length=100),
    refresh: bool = False,
    _: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    return success_response(request, await aggregate_trends(source, limit, query, refresh))


@router.post("/trends/analyze")
async def analyze_trend(
    payload: TrendAnalyzeRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict:
    runtime = load_llm_runtime(db)
    system_prompt = """你是中文内容策划编辑。
基于热点标题和榜单摘要提出 2～3 个可执行的原创选题角度。
榜单摘要不是已核验事实，不得补造背景、数字或因果。明确列出发布前需要核验的问题和风险。
只返回符合指定结构的 JSON。"""
    user_prompt = (
        f"来源：{payload.source}\n标题：{payload.title}\n摘要：{payload.summary or '未提供'}\n"
        f"原始链接：{payload.url}\n请给出适合 ContentPilot 三平台创作的选题方案。"
    )
    result, prompt_tokens, completion_tokens, _ = await _validated_completion(
        runtime, system_prompt, user_prompt, TrendAnalysisOutput
    )
    data = result.model_dump(mode="json")
    data["provider"] = runtime.provider
    data["modelName"] = runtime.model_name
    data["tokenUsage"] = prompt_tokens + completion_tokens
    return success_response(request, data)
