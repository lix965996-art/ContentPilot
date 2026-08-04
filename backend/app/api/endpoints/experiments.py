from datetime import date, datetime, time

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.exceptions import AppException
from app.core.responses import success_response
from app.db.session import get_db
from app.models.business import (
    ContentArticle,
    EngagementMetric,
    Experiment,
    ExperimentSample,
    PublishRecommendation,
    PublishSchedule,
)
from app.models.user import User
from app.schemas.business import ExperimentCreate, ExperimentSampleGroupUpdate, ExperimentUpdate
from app.services.audit_service import record_audit
from app.services.recommendation_service import classify_schedule_group
from app.services.serializers import model_dict

router = APIRouter(tags=["实验管理"])
# Schedules in these terminal states have a settled outcome and are safe to
# fold into an experiment comparison.
MEASURED_SCHEDULE_STATUSES = ("SUCCESS", "MANUAL_PUBLISHED")


def _data(row: Experiment, include_samples: bool = False) -> dict:
    data = model_dict(row, camel=True)
    data["metrics"] = data.pop("metricsJson", {})
    data["result"] = data.pop("resultJson", {})
    if include_samples:
        data["samples"] = [model_dict(x, camel=True) for x in row.samples]
    data["sampleCount"] = len(row.samples)
    data["statistics"] = _results(row)
    data["hasSimulatedData"] = any(
        str(sample.metric_value_json.get("dataSource", "")).upper() == "SIMULATED"
        or str(sample.metric_value_json.get("dataNotice", "")).upper() == "SIMULATED"
        for sample in row.samples
    )
    return data


def _results(row: Experiment) -> dict:
    groups: dict[str, list[dict]] = {}
    for sample in row.samples:
        groups.setdefault(sample.group_type, []).append(sample.metric_value_json)
    output = {}
    for name, samples in groups.items():
        keys = {
            key for item in samples for key, value in item.items() if isinstance(value, int | float)
        }
        output[name] = {
            key: round(sum(float(item.get(key, 0)) for item in samples) / len(samples), 4)
            for key in keys
        }
        output[name]["sampleCount"] = len(samples)
    return output


@router.get("/experiments")
def list_experiments(
    request: Request, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> dict:
    return success_response(
        request,
        [
            _data(row)
            for row in db.scalars(select(Experiment).order_by(Experiment.updated_at.desc())).all()
        ],
    )


@router.post("/experiments")
def create_experiment(
    payload: ExperimentCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    values = payload.model_dump(exclude={"metrics"})
    row = Experiment(**values, metrics_json=payload.metrics, status="DRAFT", created_by=user.id)
    db.add(row)
    db.flush()
    record_audit(db, request, user, "CREATE", "EXPERIMENT", "EXPERIMENT", row.id)
    db.commit()
    db.refresh(row)
    return success_response(request, _data(row), "实验已创建")


@router.get("/experiments/{experiment_id}")
def get_experiment(
    experiment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    row = db.get(Experiment, experiment_id)
    if not row:
        raise AppException(40411, "实验不存在", 404)
    return success_response(request, _data(row, True))


@router.put("/experiments/{experiment_id}")
def update_experiment(
    experiment_id: int,
    payload: ExperimentUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    row = db.get(Experiment, experiment_id)
    if not row:
        raise AppException(40411, "实验不存在", 404)
    values = payload.model_dump(exclude_unset=True, exclude={"metrics"})
    for key, value in values.items():
        setattr(row, key, value)
    if payload.metrics is not None:
        row.metrics_json = payload.metrics
    record_audit(db, request, user, "UPDATE", "EXPERIMENT", "EXPERIMENT", row.id)
    db.commit()
    return success_response(request, _data(row), "实验已保存")


@router.delete("/experiments/{experiment_id}")
def delete_experiment(
    experiment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    row = db.get(Experiment, experiment_id)
    if not row:
        raise AppException(40411, "实验不存在", 404)
    record_audit(db, request, user, "DELETE", "EXPERIMENT", "EXPERIMENT", row.id)
    db.delete(row)
    db.commit()
    return success_response(request, {"id": experiment_id}, "实验已删除")


@router.post("/experiments/{experiment_id}/start")
def start(
    experiment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    row = db.get(Experiment, experiment_id)
    if not row:
        raise AppException(40411, "实验不存在", 404)
    row.status = "RUNNING"
    row.start_date = row.start_date or date.today()
    record_audit(db, request, user, "START", "EXPERIMENT", "EXPERIMENT", row.id)
    db.commit()
    return success_response(request, _data(row), "实验已开始")


@router.post("/experiments/{experiment_id}/finish")
def finish(
    experiment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    row = db.get(Experiment, experiment_id)
    if not row:
        raise AppException(40411, "实验不存在", 404)
    row.result_json = _results(row)
    row.status = "FINISHED"
    row.end_date = row.end_date or date.today()
    row.conclusion = (
        row.conclusion or "结果已按实验分组自动汇总；若包含 SIMULATED 样本，仅可用于系统功能演示。"
    )
    record_audit(db, request, user, "FINISH", "EXPERIMENT", "EXPERIMENT", row.id)
    db.commit()
    return success_response(request, _data(row, True), "实验已完成")


@router.post("/experiments/{experiment_id}/sync-schedules")
def sync_schedules(
    experiment_id: int,
    request: Request,
    platform: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    """Auto-assign settled schedules into this PUBLISH_TIME experiment's groups.

    The default group is entirely data-driven (see ``classify_schedule_group``):
    RECOMMENDED/ALTERNATIVE schedules land in the treatment group, CUSTOM
    schedules outside the recommendation's candidate-time tolerance land in
    the control group. Existing manual assignments are never touched.
    """
    row = db.get(Experiment, experiment_id)
    if not row:
        raise AppException(40411, "实验不存在", 404)
    if row.type != "PUBLISH_TIME":
        raise AppException(40023, "仅“发布时间”类型的实验支持按排期自动分组", 400)

    already_linked = {s.schedule_id for s in row.samples if s.schedule_id is not None}
    query = select(PublishSchedule).where(PublishSchedule.status.in_(MEASURED_SCHEDULE_STATUSES))
    if platform:
        query = query.where(PublishSchedule.platform == platform)
    if row.start_date:
        query = query.where(
            PublishSchedule.scheduled_at >= datetime.combine(row.start_date, time.min)
        )
    if row.end_date:
        query = query.where(
            PublishSchedule.scheduled_at <= datetime.combine(row.end_date, time.max)
        )
    candidates = db.scalars(query.order_by(PublishSchedule.scheduled_at)).all()

    created = 0
    skipped_no_metric = 0
    for schedule in candidates:
        if schedule.id in already_linked:
            continue
        metrics = db.scalars(
            select(EngagementMetric).where(EngagementMetric.schedule_id == schedule.id)
        ).all()
        if not metrics:
            # No measured engagement yet: never fabricate a sample value.
            skipped_no_metric += 1
            continue
        recommendation = (
            db.get(PublishRecommendation, schedule.recommendation_id)
            if schedule.recommendation_id
            else None
        )
        group_type, reason = classify_schedule_group(schedule, recommendation)
        avg_rate = sum(m.engagement_rate for m in metrics) / len(metrics)
        article = db.get(ContentArticle, schedule.article_id)
        data_sources = sorted({m.data_source for m in metrics})
        db.add(
            ExperimentSample(
                experiment_id=row.id,
                schedule_id=schedule.id,
                group_type=group_type,
                sample_label=f"{article.title if article else '未知文章'} · 排期#{schedule.id}",
                metric_value_json={
                    "engagementRate": round(avg_rate * 100, 3),
                    "dataSource": "/".join(data_sources),
                    "metricCount": len(metrics),
                },
                assignment_source="AUTO",
                assignment_reason=reason,
            )
        )
        created += 1
    record_audit(
        db,
        request,
        user,
        "SYNC_SCHEDULES",
        "EXPERIMENT",
        "EXPERIMENT",
        row.id,
        {"created": created, "skippedNoMetric": skipped_no_metric},
    )
    db.commit()
    db.refresh(row)
    return success_response(
        request,
        {"experiment": _data(row, True), "created": created, "skippedNoMetric": skipped_no_metric},
        f"已自动同步 {created} 条排期样本" if created else "没有新的可同步排期样本",
    )


@router.put("/experiments/{experiment_id}/samples/{sample_id}/group")
def override_sample_group(
    experiment_id: int,
    sample_id: int,
    payload: ExperimentSampleGroupUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OPERATOR")),
) -> dict:
    """Manually move a sample between control/treatment, always with a reason."""
    row = db.get(Experiment, experiment_id)
    if not row:
        raise AppException(40411, "实验不存在", 404)
    sample = db.get(ExperimentSample, sample_id)
    if not sample or sample.experiment_id != experiment_id:
        raise AppException(40412, "实验样本不存在", 404)

    previous_group = sample.group_type
    sample.group_type = payload.group_type
    sample.assignment_source = "MANUAL"
    sample.assignment_reason = payload.reason
    record_audit(
        db,
        request,
        user,
        "OVERRIDE_GROUP",
        "EXPERIMENT",
        "EXPERIMENT_SAMPLE",
        sample.id,
        {
            "experimentId": experiment_id,
            "previousGroup": previous_group,
            "newGroup": payload.group_type,
            "reason": payload.reason,
        },
    )
    db.commit()
    db.refresh(row)
    return success_response(request, _data(row, True), "分组已手动调整")


@router.get("/experiments/{experiment_id}/report")
def experiment_report(
    experiment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    row = db.get(Experiment, experiment_id)
    if not row:
        raise AppException(40411, "实验不存在", 404)
    return success_response(
        request,
        {
            "experiment": _data(row, True),
            "statistics": _results(row),
            "disclaimer": "SIMULATED 样本仅用于功能演示，不代表真实研究结论。",
        },
    )
