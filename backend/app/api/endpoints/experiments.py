from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.exceptions import AppException
from app.core.responses import success_response
from app.db.session import get_db
from app.models.business import Experiment
from app.models.user import User
from app.schemas.business import ExperimentCreate, ExperimentUpdate
from app.services.audit_service import record_audit
from app.services.serializers import model_dict

router = APIRouter(tags=["实验管理"])


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
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
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
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
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
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
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
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
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
    user: User = Depends(require_roles("ADMIN", "OPERATOR")),
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
