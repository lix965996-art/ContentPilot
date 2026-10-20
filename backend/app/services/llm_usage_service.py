"""Durable provider-call accounting and conservative local budget admission.

Prices are snapshots, not provider invoices. Unknown response usage stays unknown.
Reservations bound concurrent estimated spend; a provider can still bill more
than an estimate. No prompt, credentials or provider response bodies are stored.
"""

import uuid
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol
from weakref import WeakKeyDictionary

from sqlalchemy import case, create_engine, func, inspect, select, update
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool, StaticPool
from sqlalchemy.schema import CreateIndex, CreateTable

from app.core.config import settings
from app.core.exceptions import AppException
from app.models.business import ContentVariant, LlmBudgetMonth, LlmUsageEntry, SystemSetting
from app.services.setting_service import setting_value

BOOTSTRAP_KEY = "llm.usage_ledger_initialized"
SCHEMA_KEY = "llm.usage_ledger_schema_version"
SETTING_KEYS = (
    "llm.input_price_per_million",
    "llm.output_price_per_million",
    "llm.currency",
    "llm.monthly_budget",
    "llm.budget_warning_percent",
)
_memory_stores: WeakKeyDictionary[Engine, Engine] = WeakKeyDictionary()


class UsageRuntime(Protocol):
    @property
    def provider(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    @property
    def usage_bind(self) -> Engine | Connection | None: ...

    @property
    def usage_session(self) -> Session | None: ...


@dataclass(frozen=True)
class UsageTicket:
    bind: Engine | Connection
    id: str
    month_id: str


def initialize_legacy_usage(db: Session, source_db: Session | None = None) -> None:
    """Snapshot old variants once, before the first tracked provider request.

    The marker prevents new variants from being billed again after their calls
    have already entered the ledger. Migrations use the same marker.
    """
    if db.scalar(select(SystemSetting.id).where(SystemSetting.setting_key == BOOTSTRAP_KEY)):
        return
    input_price = float(setting_value(db, "llm.input_price_per_million", "0") or 0)
    output_price = float(setting_value(db, "llm.output_price_per_million", "0") or 0)
    currency = setting_value(db, "llm.currency", "CNY")
    rows = (
        (source_db or db)
        .scalars(select(ContentVariant).where(ContentVariant.token_usage > 0))
        .all()
    )
    for row in rows:
        known_tokens = row.prompt_tokens + row.completion_tokens > 0
        saved_cost = row.estimated_cost if row.estimated_cost > 0 else None
        cost = saved_cost
        if cost is None and known_tokens and input_price + output_price > 0:
            cost = (row.prompt_tokens * input_price + row.completion_tokens * output_price) / 1e6
        db.add(
            LlmUsageEntry(
                id=str(uuid.uuid4()),
                legacy_variant_id=row.id,
                provider="LEGACY",
                model=row.model_name or "未标记模型",
                operation="LEGACY_GENERATION",
                status="SUCCEEDED",
                prompt_tokens=row.prompt_tokens if known_tokens else row.token_usage,
                completion_tokens=row.completion_tokens if known_tokens else 0,
                input_price=input_price,
                output_price=output_price,
                currency=currency,
                estimated_cost=cost,
                reserved_cost=0,
                pricing_status="SAVED_ESTIMATE" if saved_cost else "LEGACY_ESTIMATE",
                created_at=row.created_at,
                completed_at=row.created_at,
            )
        )
    db.add(SystemSetting(setting_key=BOOTSTRAP_KEY, setting_value="1", is_secret=False))
    db.flush()


def _accounting_bind(bind: Engine | Connection) -> Engine | Connection:
    engine = bind.engine if isinstance(bind, Connection) else bind
    if engine.dialect.name != "sqlite":
        return bind
    database = engine.url.database
    if database and database != ":memory:":
        path = Path(database).resolve()
        ledger_engine = create_engine(
            f"sqlite:///{path.with_suffix(path.suffix + '.llm-usage.sqlite').as_posix()}",
            poolclass=NullPool,
            connect_args={"timeout": 30},
        )
    else:
        ledger_engine = _memory_stores.get(engine)
        if ledger_engine is None:
            ledger_engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
            _memory_stores[engine] = ledger_engine
    from app.db.base import Base

    tables = [
        Base.metadata.tables[name]
        for name in ("system_setting", "llm_usage_entry", "llm_budget_month")
    ]
    with ledger_engine.begin() as connection:
        for table in tables:
            connection.execute(CreateTable(table, if_not_exists=True))
            for index in table.indexes:
                connection.execute(CreateIndex(index, if_not_exists=True))
    inspector = inspect(ledger_engine)
    for table in tables:
        if {column["name"] for column in inspector.get_columns(table.name)} != set(
            table.columns.keys()
        ):
            raise AppException(50362, "模型调用账本结构版本不兼容，请先备份并升级账本", 503)
    with Session(ledger_engine) as db:
        version = db.scalar(select(SystemSetting).where(SystemSetting.setting_key == SCHEMA_KEY))
        if version is not None and version.setting_value != "1":
            raise AppException(50362, "模型调用账本版本不兼容，请先备份并升级账本", 503)
        if version is None:
            db.add(SystemSetting(setting_key=SCHEMA_KEY, setting_value="1", is_secret=False))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
    return ledger_engine


def ensure_legacy_usage(
    bind: Engine | Connection, source_db: Session | None = None
) -> Engine | Connection:
    accounting = _accounting_bind(bind)
    if accounting is bind:
        with Session(bind) as db:
            try:
                initialize_legacy_usage(db)
                _recover_interrupted_usage(db)
                db.commit()
            except IntegrityError:
                db.rollback()
        return accounting
    # Only non-secret accounting settings are mirrored. Business writes remain
    # in their original transaction; the companion ledger commits independently.
    with nullcontext(source_db) if source_db is not None else Session(bind) as source:
        assert source is not None
        values = {key: setting_value(source, key, "") for key in SETTING_KEYS}
        with Session(accounting) as db:
            try:
                for key, value in values.items():
                    row = db.scalar(select(SystemSetting).where(SystemSetting.setting_key == key))
                    if row is None:
                        db.add(SystemSetting(setting_key=key, setting_value=value, is_secret=False))
                    else:
                        row.setting_value = value
                initialize_legacy_usage(db, source)
                _recover_interrupted_usage(db)
                db.commit()
            except IntegrityError:
                db.rollback()
    return accounting


def _monthly_cost(db: Session, start: datetime, currency: str) -> float:
    return float(
        db.scalar(
            select(func.coalesce(func.sum(LlmUsageEntry.estimated_cost), 0)).where(
                LlmUsageEntry.created_at >= start, LlmUsageEntry.currency == currency
            )
        )
        or 0
    )


def _recover_interrupted_usage(db: Session) -> None:
    cutoff = datetime.now() - timedelta(seconds=max(900, settings.llm_timeout_seconds + 60))
    stale = db.scalars(
        select(LlmUsageEntry).where(
            LlmUsageEntry.status == "RUNNING", LlmUsageEntry.created_at < cutoff
        )
    ).all()
    for row in stale:
        month_id = f"{row.created_at:%Y-%m}:{row.currency}"
        db.execute(
            update(LlmBudgetMonth)
            .where(LlmBudgetMonth.id == month_id)
            .values(reserved_cost=LlmBudgetMonth.reserved_cost)
        )
        db.refresh(row)
        if row.status != "RUNNING":
            continue
        # A killed process cannot tell whether the provider billed its request.
        # Preserve the unresolved cost and stop admitting budget-limited calls.
        row.status = "UNCERTAIN"
        row.pricing_status = "UNKNOWN_USAGE"
        row.error_code = "CALL_INTERRUPTED"
        row.completed_at = datetime.now()
        db.execute(
            update(LlmBudgetMonth)
            .where(LlmBudgetMonth.id == month_id)
            .values(
                reserved_cost=case(
                    (LlmBudgetMonth.reserved_cost <= row.reserved_cost, 0),
                    else_=LlmBudgetMonth.reserved_cost - row.reserved_cost,
                )
            )
        )
        row.reserved_cost = 0


def begin_usage(
    runtime: UsageRuntime,
    operation: str,
    *,
    prompt_text: str = "",
    model: str | None = None,
    token_priced: bool = True,
) -> UsageTicket | None:
    bind = getattr(runtime, "usage_bind", None)
    if bind is None:
        return None
    bind = ensure_legacy_usage(bind, getattr(runtime, "usage_session", None))
    now = datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    with Session(bind) as db:
        currency = setting_value(db, "llm.currency", "CNY")
        budget = float(setting_value(db, "llm.monthly_budget", "0") or 0)
        input_price = float(setting_value(db, "llm.input_price_per_million", "0") or 0)
        output_price = float(setting_value(db, "llm.output_price_per_million", "0") or 0)
        month_id = f"{now:%Y-%m}:{currency}"
        if db.get(LlmBudgetMonth, month_id) is None:
            try:
                with db.begin_nested():
                    db.add(LlmBudgetMonth(id=month_id, reserved_cost=0))
                    db.flush()
            except IntegrityError:
                pass
        # Serialize admissions and settlements for this month. SQL UPDATE is
        # atomic on SQLite too, unlike SELECT FOR UPDATE which SQLite ignores.
        db.execute(
            update(LlmBudgetMonth)
            .where(LlmBudgetMonth.id == month_id)
            .values(reserved_cost=LlmBudgetMonth.reserved_cost)
        )
        reserved = 0.0
        if budget > 0:
            if not token_priced or input_price + output_price <= 0:
                raise AppException(
                    40961,
                    "月度预算已启用，但该调用缺少可用计价规则；请配置文本单价，"
                    "图片调用需关闭本地预算限制后使用",
                    409,
                )
            spent = _monthly_cost(db, month_start, currency)
            if spent >= budget:
                raise AppException(40963, "本月模型预算已用尽", 409)
            unknown = db.scalar(
                select(LlmUsageEntry.id)
                .where(
                    LlmUsageEntry.created_at >= month_start,
                    LlmUsageEntry.currency == currency,
                    LlmUsageEntry.estimated_cost.is_(None),
                    LlmUsageEntry.status != "RUNNING",
                )
                .limit(1)
            )
            if unknown:
                raise AppException(
                    40962,
                    "本月存在费用未知的模型调用，无法保证预算；请核对账单或关闭本地预算限制",
                    409,
                )
            # UTF-8 bytes bound input tokens conservatively; output is an
            # estimate, explicitly not a hard provider billing guarantee.
            reserved = (len(prompt_text.encode("utf-8")) * input_price + 1024 * output_price) / 1e6
            reserved = max(reserved, 0.00000001)
            result = db.execute(
                update(LlmBudgetMonth)
                .where(
                    LlmBudgetMonth.id == month_id,
                    LlmBudgetMonth.reserved_cost + spent + reserved <= budget,
                )
                .values(reserved_cost=LlmBudgetMonth.reserved_cost + reserved)
            )
            if result.rowcount != 1:
                raise AppException(40963, "本月模型预算已用尽，或剩余额度不足以预留本次调用", 409)
        entry = LlmUsageEntry(
            id=str(uuid.uuid4()),
            provider=runtime.provider,
            model=model or runtime.model_name,
            operation=operation,
            status="RUNNING",
            prompt_tokens=None,
            completion_tokens=None,
            input_price=input_price if token_priced else 0,
            output_price=output_price if token_priced else 0,
            currency=currency,
            estimated_cost=None,
            reserved_cost=reserved,
            pricing_status="PENDING",
            created_at=now,
        )
        db.add(entry)
        db.commit()
        return UsageTicket(bind, entry.id, month_id)


def finish_usage(
    ticket: UsageTicket | None,
    *,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    status: str = "SUCCEEDED",
    error_code: str | None = None,
) -> None:
    if ticket is None:
        return
    with Session(ticket.bind) as db:
        db.execute(
            update(LlmBudgetMonth)
            .where(LlmBudgetMonth.id == ticket.month_id)
            .values(reserved_cost=LlmBudgetMonth.reserved_cost)
        )
        row = db.get(LlmUsageEntry, ticket.id)
        if row is None or row.status not in {"RUNNING", "UNCERTAIN"}:
            return
        row.status = status
        row.error_code = error_code[:100] if error_code else None
        prompt = max(0, prompt_tokens) if prompt_tokens is not None else None
        completion = max(0, completion_tokens) if completion_tokens is not None else None
        row.prompt_tokens = prompt
        row.completion_tokens = completion
        if prompt is not None and completion is not None:
            if row.input_price + row.output_price > 0:
                row.estimated_cost = (
                    prompt * row.input_price + completion * row.output_price
                ) / 1e6
                row.pricing_status = "PRICE_SNAPSHOT"
            elif prompt + completion == 0:
                row.estimated_cost = 0
                row.pricing_status = "NO_USAGE"
            else:
                row.pricing_status = "UNPRICED"
        else:
            row.pricing_status = "UNKNOWN_USAGE"
        db.execute(
            update(LlmBudgetMonth)
            .where(LlmBudgetMonth.id == ticket.month_id)
            .values(
                reserved_cost=case(
                    (LlmBudgetMonth.reserved_cost <= row.reserved_cost, 0),
                    else_=LlmBudgetMonth.reserved_cost - row.reserved_cost,
                )
            )
        )
        row.reserved_cost = 0
        row.completed_at = datetime.now()
        db.commit()
