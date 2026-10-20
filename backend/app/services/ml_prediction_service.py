"""Bounded candidate scoring using verified native models and explicit fallback."""

from __future__ import annotations

import math
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ml import native, registry
from app.ml.dataset import audit_dataset
from app.ml.features import EXPLANATIONS, HistoryIndex, timestamp, vector
from app.models.business import ContentVariant, MediaAsset, PlatformAccount, PublishSchedule
from app.services.engagement_collection_service import (
    PLATFORMS,
    account_reference,
    business_to_utc,
)


def candidate_scores(
    db: Session,
    *,
    platform: str,
    account_id: int | None,
    variant: ContentVariant,
    now: datetime,
) -> tuple[dict[tuple[int, int], float], dict]:
    info = {
        "mode": "STATISTICAL_FALLBACK",
        "reason": "NO_VALIDATED_MODEL",
        "modelId": None,
        "target": "24小时点赞、回复、转发总数",
        "explanations": [],
    }
    if platform not in PLATFORMS:
        info["reason"] = "PLATFORM_UNSUPPORTED"
        return {}, info
    model_id = registry.active_id(db, platform)
    if not model_id:
        return {}, info
    info["modelId"] = model_id
    started = time.perf_counter()
    try:
        directory, manifest, schema, report = registry.read_model(model_id)
        reason = registry.activation_reason(manifest, report, platform)
        if reason:
            info["reason"] = reason
            return {}, info
        decision = business_to_utc(now).replace(tzinfo=UTC)
        if timestamp(manifest["trainedThrough"]) > decision:
            info["reason"] = "MODEL_NOT_AVAILABLE_ASOF_DECISION"
            return {}, info
        account = db.get(PlatformAccount, account_id) if account_id else None
        if account is None or account.platform != platform or account.status != "CONNECTED":
            info["reason"] = "ACCOUNT_NOT_CONNECTED"
            return {}, info
        account_ref = account_reference(
            PublishSchedule(platform=platform, account_id=account_id), account
        )
        if account_ref not in manifest.get("trainingAccounts", []):
            info["reason"] = "COLD_ACCOUNT"
            return {}, info
        rows, _ = audit_dataset(db, platform=platform)
        history = HistoryIndex(rows)
        row = {
            "account": account_ref,
            "decision_at": decision.isoformat(),
            "published_at": decision.isoformat(),
            "text": variant.content_text,
            "title": variant.title,
            "hashtags": variant.hashtags_json or [],
            "image_count": db.scalar(
                select(func.count())
                .select_from(MediaAsset)
                .where(MediaAsset.article_id == variant.article_id, MediaAsset.selected.is_(True))
            )
            or 0,
            "language": "zh"
            if any("\u4e00" <= c <= "\u9fff" for c in variant.content_text)
            else "other",
        }
        # Enumerate each business-time slot once, then encode its actual UTC time.
        base = now.replace(minute=0, second=0, microsecond=0)
        slots = [base + timedelta(hours=offset) for offset in range(168)]
        values = [
            vector(
                row,
                schema,
                history,
                candidate=business_to_utc(slot).replace(tzinfo=UTC),
                decision=decision,
            )
            for slot in slots
        ]
        model = native.load(manifest["algorithm"], directory / manifest["modelFile"])
        predictions = native.predict(model, values)
        if time.perf_counter() - started > 3:
            info["reason"] = "INFERENCE_BUDGET_EXCEEDED"
            return {}, info
        low, high = (manifest["scoreCalibration"][key] for key in ("low", "high"))
        scores = {
            (slot.weekday(), slot.hour): max(0.0, min(100.0, 100 * (float(p) - low) / (high - low)))
            for slot, p in zip(slots, predictions, strict=True)
        }
        best = int(predictions.argmax())
        contributions = native.contributions(model, manifest["algorithm"], values[best])
        explanations = sorted(
            zip(schema["names"], contributions, strict=True),
            key=lambda pair: abs(pair[1]),
            reverse=True,
        )[:5]
        info.update(
            mode="MACHINE_LEARNING",
            reason=None,
            expectedInteractions=round(math.expm1(float(predictions[best])), 2),
            explanationTime=slots[best].isoformat(),
            explanations=[
                {
                    "feature": EXPLANATIONS.get(name, "训练集文本特征"),
                    "contribution": round(value, 4),
                }
                for name, value in explanations
            ],
        )
        return scores, info
    except Exception:
        # Missing optional dependencies, corruption or model failure must not block scheduling.
        info["reason"] = "MODEL_UNAVAILABLE"
        return {}, info
