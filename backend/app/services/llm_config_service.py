import time
from collections import defaultdict
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.models.business import ContentVariant, SystemSetting
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
}


def _stored_api_key(db: Session) -> str:
    row = db.scalar(select(SystemSetting).where(SystemSetting.setting_key == "llm.api_key"))
    return decrypt_secret(row.setting_value) if row and row.setting_value else ""


def read_llm_config(db: Session) -> dict:
    api_key = _stored_api_key(db)
    return {
        "provider": setting_value(db, "llm.provider", "mock"),
        "baseUrl": setting_value(db, "llm.base_url"),
        "apiKey": MASKED_SECRET if api_key else "",
        "apiKeyConfigured": bool(api_key),
        "model": setting_value(db, "llm.model"),
        "inputPricePerMillion": float(setting_value(db, "llm.input_price_per_million", "0")),
        "outputPricePerMillion": float(setting_value(db, "llm.output_price_per_million", "0")),
        "currency": setting_value(db, "llm.currency", "CNY"),
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
    if payload.provider.lower() == "mock":
        return {
            "connected": True,
            "latencyMs": 0,
            "models": ["contentpilot-local"],
            "message": "本地规则模型可用",
        }
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
            )
            response.raise_for_status()
            body = response.json()
    except httpx.HTTPStatusError as exc:
        raise AppException(
            50203, f"连接失败：服务返回 HTTP {exc.response.status_code}", 502
        ) from exc
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


def llm_usage(db: Session, days: int) -> dict:
    since = datetime.now() - timedelta(days=days)
    rows = db.scalars(
        select(ContentVariant)
        .where(ContentVariant.created_at >= since)
        .order_by(ContentVariant.created_at.desc())
    ).all()
    model_groups: dict[str, dict[str, float | int | str]] = {}
    daily_groups: dict[str, dict[str, float | int | str]] = defaultdict(
        lambda: {"tokens": 0, "cost": 0.0}
    )
    for row in rows:
        model = row.model_name or "未标记模型"
        group = model_groups.setdefault(
            model,
            {"model": model, "generations": 0, "tokens": 0, "cost": 0.0},
        )
        group["generations"] = int(group["generations"]) + 1
        group["tokens"] = int(group["tokens"]) + row.token_usage
        group["cost"] = float(group["cost"]) + row.estimated_cost
        day = row.created_at.date().isoformat()
        daily_groups[day]["tokens"] = int(daily_groups[day]["tokens"]) + row.token_usage
        daily_groups[day]["cost"] = float(daily_groups[day]["cost"]) + row.estimated_cost
    total_tokens = sum(row.token_usage for row in rows)
    return {
        "days": days,
        "generations": len(rows),
        "promptTokens": sum(row.prompt_tokens for row in rows),
        "completionTokens": sum(row.completion_tokens for row in rows),
        "totalTokens": total_tokens,
        "estimatedCost": round(sum(row.estimated_cost for row in rows), 6),
        "averageTokens": round(total_tokens / len(rows)) if rows else 0,
        "currency": setting_value(db, "llm.currency", "CNY"),
        "byModel": [
            {**item, "cost": round(float(item["cost"]), 6)}
            for item in sorted(
                model_groups.values(), key=lambda item: int(item["tokens"]), reverse=True
            )
        ],
        "daily": [
            {"date": day, "tokens": values["tokens"], "cost": round(float(values["cost"]), 6)}
            for day, values in sorted(daily_groups.items())
        ],
    }
