import time
from collections import defaultdict
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.models.business import SystemSetting
from app.schemas.business import LlmConfigUpdate
from app.services.setting_service import decrypt_secret, encrypt_secret, setting_value

MASKED_SECRET = "••••••••"

SETTING_DEFINITIONS = {
    "llm.provider": (False, "大模型提供方"),
    "llm.base_url": (False, "OpenAI 兼容接口地址"),
    "llm.api_key": (True, "大模型 API Key"),
    "llm.model": (False, "模型名称"),
    "llm.input_price_per_million": (False, "每百万输入 Token 价格"),
    "llm.output_price_per_million": (False, "每百万输出 Token 价格"),
    "llm.currency": (False, "计费币种"),
    "llm.monthly_budget": (False, "模型月度预算"),
    "llm.budget_warning_percent": (False, "预算预警比例"),
}


def _stored_api_key(db: Session) -> str:
    row = db.scalar(select(SystemSetting).where(SystemSetting.setting_key == "llm.api_key"))
    return decrypt_secret(row.setting_value) if row and row.setting_value else ""


def read_llm_config(db: Session) -> dict:
    api_key = _stored_api_key(db)
    return {
        "provider": setting_value(db, "llm.provider", "openai-compatible"),
        "baseUrl": setting_value(db, "llm.base_url"),
        "apiKey": MASKED_SECRET if api_key else "",
        "apiKeyConfigured": bool(api_key),
        "model": setting_value(db, "llm.model"),
        "inputPricePerMillion": float(setting_value(db, "llm.input_price_per_million", "0")),
        "outputPricePerMillion": float(setting_value(db, "llm.output_price_per_million", "0")),
        "currency": setting_value(db, "llm.currency", "CNY"),
        "monthlyBudget": float(setting_value(db, "llm.monthly_budget", "0")),
        "budgetWarningPercent": int(setting_value(db, "llm.budget_warning_percent", "80")),
    }


def save_llm_config(db: Session, payload: LlmConfigUpdate) -> dict:
    values = {
        "llm.provider": payload.provider,
        "llm.base_url": payload.base_url,
        "llm.api_key": payload.api_key,
        "llm.model": payload.model,
        "llm.input_price_per_million": str(payload.input_price_per_million),
        "llm.output_price_per_million": str(payload.output_price_per_million),
        "llm.currency": payload.currency,
        "llm.monthly_budget": str(payload.monthly_budget),
        "llm.budget_warning_percent": str(payload.budget_warning_percent),
    }
    for key, value in values.items():
        is_secret, description = SETTING_DEFINITIONS[key]
        row = db.scalar(select(SystemSetting).where(SystemSetting.setting_key == key))
        if row is None:
            row = SystemSetting(
                setting_key=key,
                setting_value="",
                is_secret=is_secret,
                description=description,
            )
            db.add(row)
        if is_secret and value == MASKED_SECRET:
            continue
        row.setting_value = encrypt_secret(value) if is_secret else value
    db.flush()
    return read_llm_config(db)


async def test_llm_connection(db: Session, payload: LlmConfigUpdate) -> dict:
    api_key = _stored_api_key(db) if payload.api_key == MASKED_SECRET else payload.api_key
    if not api_key:
        raise AppException(40061, "请填写 API Key")
    if not payload.base_url:
        raise AppException(40062, "请填写 API Base URL")
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"{payload.base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {api_key}"},
                params=_model_query_params(payload.provider),
            )
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPStatusError as exc:
        raise AppException(50203, _connection_error_message(exc.response), 502) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise AppException(50203, f"连接失败：{type(exc).__name__}", 502) from exc
    models = sorted(
        {
            str(item.get("id"))
            for item in body.get("data", [])
            if isinstance(item, dict) and item.get("id")
        }
    )
    return {
        "connected": True,
        "latencyMs": int((time.perf_counter() - started) * 1000),
        "models": models,
        "message": f"连接成功，发现 {len(models)} 个模型",
    }


def _model_query_params(provider: str) -> dict[str, str] | None:
    if provider.lower() == "siliconflow":
        return {"type": "text", "sub_type": "chat"}
    return None


def _connection_error_message(response: httpx.Response) -> str:
    """Return an actionable error without ever reflecting an API key."""
    status = response.status_code
    error_code = ""
    try:
        body = response.json()
        error = body.get("error", {}) if isinstance(body, dict) else {}
        if isinstance(error, dict):
            error_code = str(error.get("code") or "").lower()
    except ValueError:
        pass

    if status == 401:
        return (
            "连接失败：API Key 无效、已失效，或与当前 API Base URL 不匹配。"
            "请在服务商控制台重新创建密钥后再试。"
        )
    if status == 403:
        return "连接失败：API Key 没有访问模型列表的权限，请检查项目和密钥权限。"
    if status == 404:
        return "连接失败：未找到模型接口，请检查 API Base URL 是否包含正确的 /v1 路径。"
    if status == 429:
        if error_code == "insufficient_quota":
            return "连接失败：API 额度不足或尚未启用计费，请检查服务商账户余额。"
        return "连接失败：请求过于频繁，请稍后再试。"
    if status >= 500:
        return f"连接失败：模型服务暂时不可用（HTTP {status}），请稍后再试。"
    return f"连接失败：模型服务返回 HTTP {status}，请检查服务地址和账号权限。"


def llm_usage(db: Session, days: int) -> dict:
    from app.services.llm_usage_service import ensure_legacy_usage

    accounting = ensure_legacy_usage(db.get_bind(), db)
    with Session(accounting) as ledger_db:
        return _ledger_usage(ledger_db, days)


def _ledger_usage(db: Session, days: int) -> dict:
    from app.models.business import LlmBudgetMonth, LlmUsageEntry

    since = datetime.now() - timedelta(days=days)
    currency = setting_value(db, "llm.currency", "CNY")
    rows = db.scalars(
        select(LlmUsageEntry)
        .where(LlmUsageEntry.created_at >= since)
        .order_by(LlmUsageEntry.created_at.desc())
    ).all()
    current_rows = [row for row in rows if row.currency == currency]
    input_price = float(setting_value(db, "llm.input_price_per_million", "0") or 0)
    output_price = float(setting_value(db, "llm.output_price_per_million", "0") or 0)
    groups: dict[str, dict] = {}
    daily: dict[str, dict] = defaultdict(lambda: {"tokens": 0, "cost": 0.0, "unpriced": 0})
    for row in rows:
        tokens = (row.prompt_tokens or 0) + (row.completion_tokens or 0)
        group = groups.setdefault(
            row.model,
            {
                "model": row.model,
                "generations": 0,
                "tokens": 0,
                "cost": 0.0,
                "unpricedGenerations": 0,
                "currencies": set(),
            },
        )
        group["generations"] += 1
        group["tokens"] += tokens
        group["currencies"].add(row.currency)
        if row.currency == currency:
            group["cost"] += row.estimated_cost or 0
        if row.estimated_cost is None:
            group["unpricedGenerations"] += 1
        day = row.created_at.date().isoformat()
        daily[day]["tokens"] += tokens
        if row.currency == currency:
            daily[day]["cost"] += row.estimated_cost or 0
        daily[day]["unpriced"] += int(row.estimated_cost is None)
    now = datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_rows = db.scalars(
        select(LlmUsageEntry).where(
            LlmUsageEntry.created_at >= month_start, LlmUsageEntry.currency == currency
        )
    ).all()
    month_cost = sum(row.estimated_cost or 0 for row in month_rows)
    monthly_budget = float(setting_value(db, "llm.monthly_budget", "0") or 0)
    warning = int(setting_value(db, "llm.budget_warning_percent", "80") or 80)
    used_percent = round(month_cost / monthly_budget * 100, 2) if monthly_budget else 0
    month = db.get(LlmBudgetMonth, f"{now:%Y-%m}:{currency}")
    unknown = sum(row.estimated_cost is None and row.status != "RUNNING" for row in month_rows)
    return {
        "days": days,
        # Retained API names count provider attempts, including failures/retries.
        "generations": len(rows),
        "pricedGenerations": sum(row.estimated_cost is not None for row in rows),
        "unpricedGenerations": sum(row.estimated_cost is None for row in rows),
        "promptTokens": sum(row.prompt_tokens or 0 for row in rows),
        "completionTokens": sum(row.completion_tokens or 0 for row in rows),
        "totalTokens": sum((row.prompt_tokens or 0) + (row.completion_tokens or 0) for row in rows),
        "estimatedCost": round(sum(row.estimated_cost or 0 for row in current_rows), 8),
        "averageTokens": round(
            sum((row.prompt_tokens or 0) + (row.completion_tokens or 0) for row in rows) / len(rows)
        )
        if rows
        else 0,
        "currency": currency,
        "priceConfigured": input_price + output_price > 0,
        "inputPricePerMillion": input_price,
        "outputPricePerMillion": output_price,
        "monthlyBudget": monthly_budget,
        "monthlyCost": round(month_cost, 8),
        "monthlyReservedCost": round(month.reserved_cost, 8) if month else 0,
        "monthlyUnknownCalls": unknown,
        "budgetWarningPercent": warning,
        "budgetUsedPercent": used_percent,
        "budgetAlert": monthly_budget > 0 and (used_percent >= warning or unknown > 0),
        "scope": "PROVIDER_CALL_LEDGER",
        "otherCurrencyCalls": sum(row.currency != currency for row in rows),
        "byModel": [
            {
                **{key: value for key, value in group.items() if key != "currencies"},
                "cost": round(group["cost"], 8),
            }
            for group in sorted(groups.values(), key=lambda item: item["tokens"], reverse=True)
        ],
        "daily": [
            {
                "date": day,
                "tokens": values["tokens"],
                "cost": round(values["cost"], 8),
                "unpricedGenerations": values["unpriced"],
            }
            for day, values in sorted(daily.items())
        ],
        "recent": [
            {
                "id": row.id,
                "articleTitle": row.operation,
                "platform": "",
                "model": row.model,
                "provider": row.provider,
                "operation": row.operation,
                "status": row.status,
                "promptTokens": row.prompt_tokens,
                "completionTokens": row.completion_tokens,
                "totalTokens": (row.prompt_tokens or 0) + (row.completion_tokens or 0),
                "cost": row.estimated_cost,
                "currency": row.currency,
                "pricingStatus": row.pricing_status,
                "createdAt": row.created_at.isoformat(),
            }
            for row in rows[:20]
        ],
    }
