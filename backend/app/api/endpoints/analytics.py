import csv
import io
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.exceptions import AppException
from app.core.responses import success_response
from app.db.session import get_db
from app.models.business import (
    ContentArticle,
    ContentVariant,
    EngagementMetric,
    PublishSchedule,
)
from app.models.user import User
from app.schemas.business import MetricCreate
from app.services.activity_service import classify_content_type, content_type_name
from app.services.analytics_service import (
    article_engagement,
    articles_engagement_batch,
    grouped,
    summarize,
)
from app.services.audit_service import record_audit
from app.services.recommendation_service import explain_slot

router = APIRouter(tags=["数据复盘"])
HEADERS = [
    "schedule_id",
    "platform",
    "metric_date",
    "group_type",
    "impressions",
    "likes",
    "comments",
    "collects",
    "shares",
    "followers",
    "metric_basis",
    "data_source",
]
OPTIONAL_HEADERS = {"metric_basis", "followers", "data_source"}
DEFAULT_METRIC_BASIS = "IMPRESSIONS"
DEFAULT_DATA_SOURCE = "IMPORTED"


def _save_metric(db: Session, payload: MetricCreate) -> EngagementMetric:
    if not db.get(PublishSchedule, payload.schedule_id):
        raise AppException(40407, f"排期任务 {payload.schedule_id} 不存在", 404)
    total = payload.likes + payload.comments + payload.collects + payload.shares
    # Resolve the denominator from the caller's explicit choice. Previously the
    # code silently fell back to followers when impressions was zero, which
    # inflated engagement rates whenever a platform did not expose impressions.
    # The denominator is now selected explicitly; zero denominator means the
    # caller did not provide a valid basis, and we record the rate as 0.
    denominator = (
        payload.impressions if payload.metric_basis == "IMPRESSIONS" else payload.followers
    )
    return EngagementMetric(
        **payload.model_dump(exclude={"metric_basis"}),
        engagement_total=total,
        engagement_rate=round(total / denominator, 6) if denominator else 0,
    )


@router.get("/analytics/template")
def template(_: User = Depends(get_current_user)) -> StreamingResponse:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "互动数据导入"
    sheet.append(HEADERS)
    stream = io.BytesIO()
    workbook.save(stream)
    stream.seek(0)
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=contentpilot-analytics-template.xlsx"
        },
    )


@router.post("/analytics/manual")
def manual(
    payload: MetricCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    row = _save_metric(db, payload)
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise AppException(40911, "同一排期、日期和来源的数据已存在", 409) from exc
    record_audit(
        db, request, user, "CREATE", "ANALYTICS", "METRIC", row.id, {"source": row.data_source}
    )
    db.commit()
    return success_response(
        request,
        {
            "id": row.id,
            "engagementTotal": row.engagement_total,
            "engagementRate": row.engagement_rate,
        },
        "互动数据已保存",
    )


@router.post("/analytics/import")
async def import_metrics(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    if not file.filename or not file.filename.lower().endswith((".csv", ".xlsx")):
        raise AppException(40041, "只支持 CSV 或 XLSX 文件")
    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:
        raise AppException(40042, "文件不能超过 5MB")
    records: list[dict] = []
    if file.filename.lower().endswith(".csv"):
        try:
            records = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
        except UnicodeDecodeError as exc:
            raise AppException(40043, "CSV 必须使用 UTF-8 编码") from exc
    else:
        workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        sheet = workbook.active
        rows = list(sheet.iter_rows(values_only=True))
        headers = [str(x or "") for x in rows[0]] if rows else []
        records = [dict(zip(headers, values, strict=False)) for values in rows[1:]]
    missing = [name for name in HEADERS if name not in (records[0].keys() if records else [])]
    if missing:
        raise AppException(40044, "导入字段不完整", 422, {"missingFields": missing})
    success, errors = 0, []
    for index, item in enumerate(records, start=2):
        try:
            basis = str(item.get("metric_basis") or DEFAULT_METRIC_BASIS).upper()
            if basis not in {"IMPRESSIONS", "FOLLOWERS"}:
                basis = DEFAULT_METRIC_BASIS
            payload = MetricCreate(
                schedule_id=int(item["schedule_id"]),
                platform=str(item["platform"]),
                metric_date=date.fromisoformat(str(item["metric_date"])[:10]),
                group_type=str(item["group_type"]),
                impressions=int(item["impressions"] or 0),
                likes=int(item["likes"] or 0),
                comments=int(item["comments"] or 0),
                collects=int(item["collects"] or 0),
                shares=int(item["shares"] or 0),
                followers=int(item["followers"] or 0),
                metric_basis=basis,
                data_source=str(item["data_source"] or DEFAULT_DATA_SOURCE),
            )
            with db.begin_nested():
                db.add(_save_metric(db, payload))
                db.flush()
            success += 1
        except Exception as exc:
            errors.append({"row": index, "message": str(exc)[:200]})
    record_audit(
        db,
        request,
        user,
        "IMPORT",
        "ANALYTICS",
        detail={"filename": file.filename, "success": success, "errors": len(errors)},
    )
    db.commit()
    return success_response(
        request,
        {"successCount": success, "errorCount": len(errors), "errors": errors},
        "数据导入完成",
    )


@router.get("/analytics/overview")
def overview(
    request: Request, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> dict:
    return success_response(request, summarize(db))


@router.get("/analytics/platform-comparison")
def platform_comparison(
    request: Request, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> dict:
    return success_response(request, grouped(db, "platform"))


@router.get("/analytics/time-comparison")
def time_comparison(
    request: Request, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> dict:
    return success_response(request, grouped(db, "group_type"))


@router.get("/analytics/content-ranking")
def content_ranking(
    request: Request, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> dict:
    metrics = db.scalars(
        select(EngagementMetric).order_by(EngagementMetric.engagement_rate.desc()).limit(50)
    ).all()
    items = []
    for metric in metrics:
        schedule = db.get(PublishSchedule, metric.schedule_id)
        article = db.get(ContentArticle, schedule.article_id) if schedule else None
        items.append(
            {
                "scheduleId": metric.schedule_id,
                "title": article.title if article else "未知内容",
                "platform": metric.platform,
                "impressions": metric.impressions,
                "likes": metric.likes,
                "comments": metric.comments,
                "collects": metric.collects,
                "shares": metric.shares,
                "followers": metric.followers,
                "engagementRate": round(metric.engagement_rate * 100, 2),
                "engagementTotal": metric.engagement_total,
                "dataSource": metric.data_source,
                "groupType": metric.group_type,
                "metricDate": metric.metric_date.isoformat(),
            }
        )
    return success_response(request, items)


@router.get("/analytics/articles/engagement")
def articles_engagement_summary(
    request: Request,
    ids: str = Query("", description="Comma-separated article ids"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    article_ids: list[int] = []
    for value in ids.split(","):
        value = value.strip()
        if value.isdigit():
            article_ids.append(int(value))
    article_ids = article_ids[:100]
    summaries = articles_engagement_batch(db, article_ids)
    return success_response(
        request,
        {"items": [summaries[article_id] for article_id in article_ids if article_id in summaries]},
    )


@router.get("/analytics/articles/{article_id}/engagement")
def article_engagement_detail(
    article_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    if not db.get(ContentArticle, article_id):
        raise AppException(40401, "文章不存在", 404)
    return success_response(request, article_engagement(db, article_id))


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


TIME_SOURCE_LABELS = {
    "RECOMMENDED": "采用系统推荐时间",
    "ALTERNATIVE": "采用系统备选时间",
    "CUSTOM": "运营自选时间",
}


@router.get("/analytics/publish-decision/{schedule_id}")
def publish_decision(
    schedule_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    """Full "why this time" chain for one schedule: content → analysis → decision → result."""
    schedule = db.get(PublishSchedule, schedule_id)
    if not schedule:
        raise AppException(40407, "排期任务不存在", 404)

    article = db.get(ContentArticle, schedule.article_id)
    variant = db.get(ContentVariant, schedule.variant_id)
    snapshot = schedule.recommendation_snapshot_json or {}

    content_type = (
        schedule.content_type
        or snapshot.get("contentType")
        or (classify_content_type(variant.title, variant.content_text) if variant else "UNKNOWN")
    )
    if schedule.content_type or snapshot.get("contentType"):
        type_provider = "STORED"
    else:
        type_provider = "RULE"

    # Explain the slot the post actually went out in, so a CUSTOM time can be
    # compared against what the model would have picked.
    reference = schedule.scheduled_at
    snapshot_window = snapshot.get("window") or {}
    analysis = explain_slot(
        db,
        platform=schedule.platform,
        moment=reference,
        content_type=content_type,
        account_id=schedule.account_id,
        window=snapshot_window.get("window") or "90D",
        start_date=_parse_date(snapshot_window.get("startDate")),
        end_date=_parse_date(snapshot_window.get("endDate")),
    )

    metrics = db.scalars(
        select(EngagementMetric).where(EngagementMetric.schedule_id == schedule.id)
    ).all()
    impressions = sum(item.impressions for item in metrics)
    engagement = sum(item.engagement_total for item in metrics)

    return success_response(
        request,
        {
            "scheduleId": schedule.id,
            "title": article.title if article else "未知内容",
            "platform": schedule.platform,
            "status": schedule.status,
            "explainSource": "SNAPSHOT" if snapshot else "RECOMPUTED",
            "explainNotice": (
                "以下依据来自排期时保存的推荐快照。"
                if snapshot
                else (
                    "该排期未保存推荐快照，以下依据由当前模型按同一时段复算得到，"
                    "仅用于解释打分构成。"
                )
            ),
            "content": {
                "articleTitle": article.title if article else None,
                "variantTitle": variant.title if variant else None,
                "contentType": content_type,
                "contentTypeName": content_type_name(content_type),
                "contentTypeProvider": type_provider,
                "modelName": variant.model_name if variant else None,
                "promptVersion": variant.prompt_version if variant else None,
                "wordCount": variant.word_count if variant else None,
                "emojiCount": variant.emoji_count if variant else None,
                "hashtags": (variant.hashtags_json or []) if variant else [],
                "generationDurationMs": variant.generation_duration_ms if variant else None,
                "tokenUsage": variant.token_usage if variant else None,
            },
            "analysis": analysis,
            "decision": {
                "recommendedAt": (
                    schedule.recommended_at.isoformat() if schedule.recommended_at else None
                ),
                "scheduledAt": schedule.scheduled_at.isoformat(),
                "actualPublishAt": (
                    schedule.actual_publish_at.isoformat() if schedule.actual_publish_at else None
                ),
                "timeSource": schedule.time_source,
                "timeSourceLabel": TIME_SOURCE_LABELS.get(
                    schedule.time_source, schedule.time_source
                ),
                "deviationMinutes": (
                    int((schedule.scheduled_at - schedule.recommended_at).total_seconds() // 60)
                    if schedule.recommended_at
                    else None
                ),
                "snapshotScore": snapshot.get("score"),
                "snapshotConfidence": snapshot.get("confidence"),
                "narrative": snapshot.get("narrative"),
                "alternatives": snapshot.get("alternatives") or [],
            },
            "result": {
                "sampleCount": len(metrics),
                "impressions": impressions,
                "engagementTotal": engagement,
                "engagementRate": (
                    round(engagement / impressions * 100, 2) if impressions else None
                ),
                "dataSources": sorted({item.data_source for item in metrics if item.data_source}),
            },
        },
    )


def _metric_index(db: Session) -> dict[int, list[EngagementMetric]]:
    index: dict[int, list[EngagementMetric]] = {}
    for metric in db.scalars(select(EngagementMetric)).all():
        index.setdefault(metric.schedule_id, []).append(metric)
    return index


def _effect_bucket(name: str, rows: list[dict]) -> dict:
    measured = [item for item in rows if item["sampleCount"]]
    impressions = sum(item["impressions"] for item in measured)
    engagement = sum(item["engagementTotal"] for item in measured)
    return {
        "name": name,
        "scheduleCount": len(rows),
        "measuredCount": len(measured),
        "impressions": impressions,
        "engagementTotal": engagement,
        "engagementRate": round(engagement / impressions * 100, 2) if impressions else 0,
        "avgEngagementRate": (
            round(sum(item["engagementRate"] for item in measured) / len(measured), 2)
            if measured
            else 0
        ),
    }


@router.get("/analytics/recommendation-effect")
def recommendation_effect(
    request: Request, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> dict:
    """Compare recommended slots with operator-chosen slots on real measured data."""
    schedules = db.scalars(select(PublishSchedule).order_by(PublishSchedule.scheduled_at)).all()
    metrics = _metric_index(db)
    rows = []
    for schedule in schedules:
        items = metrics.get(schedule.id, [])
        impressions = sum(item.impressions for item in items)
        engagement = sum(item.engagement_total for item in items)
        article = db.get(ContentArticle, schedule.article_id)
        rows.append(
            {
                "scheduleId": schedule.id,
                "title": article.title if article else "未知内容",
                "platform": schedule.platform,
                "status": schedule.status,
                "timeSource": schedule.time_source,
                "contentType": schedule.content_type,
                "scheduledAt": schedule.scheduled_at.isoformat(),
                "recommendedAt": (
                    schedule.recommended_at.isoformat() if schedule.recommended_at else None
                ),
                "actualPublishAt": (
                    schedule.actual_publish_at.isoformat() if schedule.actual_publish_at else None
                ),
                "deviationMinutes": (
                    int((schedule.scheduled_at - schedule.recommended_at).total_seconds() // 60)
                    if schedule.recommended_at
                    else None
                ),
                "executionDelayMinutes": (
                    int((schedule.actual_publish_at - schedule.scheduled_at).total_seconds() // 60)
                    if schedule.actual_publish_at
                    else None
                ),
                "sampleCount": len(items),
                "impressions": impressions,
                "engagementTotal": engagement,
                # 百分比口径，与平台/时间对比接口保持一致
                "engagementRate": round(engagement / impressions * 100, 2) if impressions else 0,
            }
        )

    with_recommendation = [item for item in rows if item["recommendedAt"]]
    adopted = [item for item in rows if item["timeSource"] in {"RECOMMENDED", "ALTERNATIVE"}]
    deviations = [
        abs(item["deviationMinutes"]) for item in with_recommendation if item["deviationMinutes"]
    ]
    buckets = {"准时采用": 0, "偏差 30 分钟内": 0, "偏差 2 小时内": 0, "偏差超过 2 小时": 0}
    for item in with_recommendation:
        value = abs(item["deviationMinutes"] or 0)
        if value == 0:
            buckets["准时采用"] += 1
        elif value <= 30:
            buckets["偏差 30 分钟内"] += 1
        elif value <= 120:
            buckets["偏差 2 小时内"] += 1
        else:
            buckets["偏差超过 2 小时"] += 1

    group_rows: dict[str, list[dict]] = {"RECOMMENDED_TIME": [], "FIXED_TIME": []}
    for item in rows:
        for metric in metrics.get(item["scheduleId"], []):
            group_rows.setdefault(metric.group_type, []).append(item)
            break

    return success_response(
        request,
        {
            "adoption": {
                "totalSchedules": len(rows),
                "withRecommendation": len(with_recommendation),
                "adoptedCount": len(adopted),
                "adoptionRate": (
                    round(len(adopted) / len(with_recommendation) * 100, 2)
                    if with_recommendation
                    else 0
                ),
                "averageDeviationMinutes": (
                    round(sum(deviations) / len(deviations), 1) if deviations else 0
                ),
                "deviationBuckets": [
                    {"name": key, "count": value} for key, value in buckets.items()
                ],
            },
            "comparison": [
                _effect_bucket(
                    "推荐时段", [item for item in rows if item["timeSource"] != "CUSTOM"]
                ),
                _effect_bucket(
                    "非推荐时段", [item for item in rows if item["timeSource"] == "CUSTOM"]
                ),
            ],
            "experimentGroups": [
                _effect_bucket("实验组（推荐时间）", group_rows.get("RECOMMENDED_TIME", [])),
                _effect_bucket("对照组（固定时间）", group_rows.get("FIXED_TIME", [])),
            ],
            "items": rows[-60:],
            "notice": (
                "对比仅使用已录入的真实或已标注来源的互动数据；"
                "标记为 SIMULATED 的样本不能作为效果结论。"
            ),
        },
    )


@router.get("/analytics/report")
def report(_: User = Depends(get_current_user), db: Session = Depends(get_db)) -> StreamingResponse:
    summary = summarize(db)
    platforms = grouped(db, "platform")
    times = grouped(db, "group_type")
    platform_rows = "".join(
        f"<tr><td>{item['name']}</td><td>{item['sampleCount']}</td>"
        f"<td>{item['engagementRate']}%</td></tr>"
        for item in platforms
    )
    html = (
        "<!doctype html><html lang='zh-CN'><meta charset='utf-8'>"
        "<title>ContentPilot 数据复盘</title><style>body{font:16px/1.7 sans-serif;"
        "max-width:900px;margin:40px auto;color:#172033}table{border-collapse:collapse;"
        "width:100%}td,th{border:1px solid #ddd;padding:8px}</style>"
        f"<h1>ContentPilot 数据复盘报告</h1><p>生成时间：{datetime.now():%Y-%m-%d %H:%M}</p>"
        f"<p>样本数：{summary['sampleCount']}；互动率：{summary['engagementRate']}%；"
        f"其中 SIMULATED：{summary['simulatedCount']} 条。</p>"
        "<h2>平台对比</h2><table><tr><th>平台</th><th>样本</th><th>互动率</th></tr>"
        f"{platform_rows}</table><h2>时间组对比</h2><pre>{times}</pre>"
    )
    return StreamingResponse(
        iter([html.encode("utf-8")]),
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=contentpilot-report.html"},
    )


@router.post("/analytics/ai-summary")
def ai_summary(
    request: Request, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> dict:
    summary = summarize(db)
    platforms = grouped(db, "platform")
    times = grouped(db, "group_type")
    if not summary["sampleCount"]:
        return success_response(
            request,
            {
                "summary": "暂无可分析数据",
                "keyFindings": [],
                "recommendations": ["先导入经过核验的平台互动数据"],
                "limitations": ["样本量为 0"],
                "provider": "RULE_BASED",
            },
        )
    best = platforms[0] if platforms else None
    return success_response(
        request,
        {
            "summary": (
                f"当前共 {summary['sampleCount']} 条样本，总互动率为 {summary['engagementRate']}%。"
            ),
            "keyFindings": [f"{best['name']} 当前样本互动率最高，为 {best['engagementRate']}%"]
            if best
            else [],
            "timeInsights": [f"{x['name']}：{x['engagementRate']}%" for x in times],
            "recommendations": [
                "持续补充真实数据后再判断时间推荐效果",
                "对高表现内容主题进行小规模复现",
            ],
            "limitations": (
                [f"包含 {summary['simulatedCount']} 条演示数据，不能作为真实效果结论"]
                if summary["simulatedCount"]
                else ["结论仅适用于当前已导入样本和统计口径"]
            ),
            "provider": "RULE_BASED",
        },
    )
