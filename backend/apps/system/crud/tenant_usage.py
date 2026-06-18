from datetime import datetime, timezone
from dataclasses import dataclass
import calendar
import json
from typing import Any

from sqlalchemy import func, inspect
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Session, select

from apps.system.models.tenant_usage import TenantUsageDailyModel
from common.core.config import settings
from common.utils.time import get_timestamp
from common.utils.utils import AppLogUtil


DEFAULT_USAGE_TENANT_ID = 1
USAGE_QUOTA_WINDOWS = {"daily", "monthly"}
ACTION_METRICS = {
    "chat": ("chat.generate_sql",),
    "analysis": ("analysis_assistant.request", "chat.analysis"),
    "recommend": ("chat.recommend",),
    "task": ("task.enqueued",),
}


@dataclass
class TenantUsageQuotaState:
    allowed: bool
    tenant_id: int
    plan: str
    action: str
    window: str | None
    limit: int
    used: int
    remaining: int
    reset_at: str | None = None
    reason: str | None = None
    subscription_status: str | None = None


def usage_metric_date(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).date().isoformat()


def _month_last_day(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def usage_window_dates(window: str, now: datetime | None = None) -> tuple[str, str, str]:
    current = now or datetime.now(timezone.utc)
    if window == "monthly":
        start = current.replace(day=1).date().isoformat()
        end = current.replace(day=_month_last_day(current.year, current.month)).date().isoformat()
        reset_at = end
    else:
        start = current.date().isoformat()
        end = start
        reset_at = start
    return start, end, reset_at


def token_total(token_usage: Any) -> int:
    if isinstance(token_usage, dict):
        value = token_usage.get("total_tokens")
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0
    if isinstance(token_usage, (int, float)):
        return int(token_usage)
    return 0


def _table_exists(session: Session) -> bool:
    try:
        return inspect(session.connection()).has_table(TenantUsageDailyModel.__tablename__)
    except Exception:
        return False


def _normalize_delta(value: int | None) -> int:
    return max(0, int(value or 0))


def _tenant_id(value: int | str | None) -> int:
    try:
        return int(value or DEFAULT_USAGE_TENANT_ID)
    except (TypeError, ValueError):
        return DEFAULT_USAGE_TENANT_ID


def _parse_quota_limits() -> dict[str, Any]:
    raw = (settings.TENANT_USAGE_QUOTA_PLAN_LIMITS or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        AppLogUtil.error("TENANT_USAGE_QUOTA_PLAN_LIMITS is not valid JSON")
        return {}
    return data if isinstance(data, dict) else {}


def _quota_limit_for_plan(plan: str | None, action: str, window: str) -> int | None:
    limits = _parse_quota_limits()
    plan_key = (plan or "default").strip().lower() or "default"
    action_key = (action or "").strip().lower()
    plan_config = limits.get(plan_key) or limits.get("default")
    if not isinstance(plan_config, dict):
        return None

    window_config = plan_config.get(window)
    value = None
    if isinstance(window_config, dict):
        value = window_config.get(action_key)
    if value is None:
        value = plan_config.get(f"{action_key}_{window}")
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return None
    return limit if limit > 0 else None


def _insert_for_dialect(session: Session):
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        return pg_insert(TenantUsageDailyModel.__table__)
    if dialect == "sqlite":
        return sqlite_insert(TenantUsageDailyModel.__table__)
    return None


def record_tenant_usage(
    session: Session,
    *,
    tenant_id: int | str | None,
    metric: str,
    usage_date: str | None = None,
    request_count: int = 0,
    success_count: int = 0,
    failure_count: int = 0,
    total_tokens: int = 0,
    task_count: int = 0,
) -> bool:
    if not settings.TENANT_USAGE_METERING_ENABLED:
        return False
    if not metric or not metric.strip():
        return False
    if not _table_exists(session):
        return False

    resolved_tenant_id = _tenant_id(tenant_id)
    now = get_timestamp()
    values = {
        "tenant_id": resolved_tenant_id,
        "usage_date": usage_date or usage_metric_date(),
        "metric": metric.strip()[:128],
        "request_count": _normalize_delta(request_count),
        "success_count": _normalize_delta(success_count),
        "failure_count": _normalize_delta(failure_count),
        "total_tokens": _normalize_delta(total_tokens),
        "task_count": _normalize_delta(task_count),
        "create_time": now,
        "update_time": now,
    }

    insert_stmt = _insert_for_dialect(session)
    if insert_stmt is not None:
        table = TenantUsageDailyModel.__table__
        statement = insert_stmt.values(**values).on_conflict_do_update(
            index_elements=["tenant_id", "usage_date", "metric"],
            set_={
                "request_count": table.c.request_count + values["request_count"],
                "success_count": table.c.success_count + values["success_count"],
                "failure_count": table.c.failure_count + values["failure_count"],
                "total_tokens": table.c.total_tokens + values["total_tokens"],
                "task_count": table.c.task_count + values["task_count"],
                "update_time": now,
            },
        )
        session.execute(statement)
        return True

    row = session.exec(
        select(TenantUsageDailyModel)
        .where(
            TenantUsageDailyModel.tenant_id == resolved_tenant_id,
            TenantUsageDailyModel.usage_date == values["usage_date"],
            TenantUsageDailyModel.metric == values["metric"],
        )
        .with_for_update()
    ).first()
    if row is None:
        session.add(TenantUsageDailyModel(**values))
    else:
        row.request_count += values["request_count"]
        row.success_count += values["success_count"]
        row.failure_count += values["failure_count"]
        row.total_tokens += values["total_tokens"]
        row.task_count += values["task_count"]
        row.update_time = now
        session.add(row)
    return True


def record_tenant_usage_detached(**kwargs) -> bool:
    if not settings.TENANT_USAGE_METERING_ENABLED:
        return False
    try:
        from common.core.db import engine

        with Session(engine) as session:
            recorded = record_tenant_usage(session, **kwargs)
            if recorded:
                session.commit()
            return recorded
    except Exception:
        AppLogUtil.exception("Failed to record tenant usage")
        return False


def list_tenant_usage_daily(
    session: Session,
    *,
    tenant_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    metric: str | None = None,
    limit: int = 500,
) -> list[TenantUsageDailyModel]:
    if not _table_exists(session):
        return []
    statement = select(TenantUsageDailyModel).order_by(
        TenantUsageDailyModel.usage_date.desc(),
        TenantUsageDailyModel.metric,
    )
    if tenant_id is not None:
        statement = statement.where(TenantUsageDailyModel.tenant_id == int(tenant_id))
    if start_date:
        statement = statement.where(TenantUsageDailyModel.usage_date >= start_date)
    if end_date:
        statement = statement.where(TenantUsageDailyModel.usage_date <= end_date)
    if metric:
        statement = statement.where(TenantUsageDailyModel.metric == metric)
    return list(session.exec(statement.limit(max(1, min(int(limit or 500), 5000)))).all())


def sum_tenant_usage(
    session: Session,
    *,
    tenant_id: int | str | None,
    metrics: tuple[str, ...],
    start_date: str,
    end_date: str,
    field: str = "request_count",
) -> int:
    if not metrics or not _table_exists(session):
        return 0
    column = getattr(TenantUsageDailyModel, field, TenantUsageDailyModel.request_count)
    value = session.exec(
        select(func.coalesce(func.sum(column), 0)).where(
            TenantUsageDailyModel.tenant_id == _tenant_id(tenant_id),
            TenantUsageDailyModel.metric.in_(metrics),
            TenantUsageDailyModel.usage_date >= start_date,
            TenantUsageDailyModel.usage_date <= end_date,
        )
    ).one()
    return int(value or 0)


def resolve_tenant_plan(session: Session | None, tenant_id: int | str | None) -> str:
    resolved_tenant_id = _tenant_id(tenant_id)
    try:
        from apps.system.models.tenant import TenantModel

        tenant = session.get(TenantModel, resolved_tenant_id) if session is not None else None
        if tenant and getattr(tenant, "plan", None):
            return str(tenant.plan)
    except Exception:
        AppLogUtil.exception("Could not resolve tenant plan for usage quota")
    return "default"


def resolve_tenant_subscription_status(session: Session | None, tenant_id: int | str | None) -> str:
    resolved_tenant_id = _tenant_id(tenant_id)
    try:
        from apps.system.crud.tenant import TENANT_SUBSCRIPTION_ACTIVE, normalize_subscription_status
        from apps.system.models.tenant import TenantModel

        tenant = session.get(TenantModel, resolved_tenant_id) if session is not None else None
        if tenant and getattr(tenant, "subscription_status", None):
            return normalize_subscription_status(str(tenant.subscription_status))
        return TENANT_SUBSCRIPTION_ACTIVE
    except Exception:
        AppLogUtil.exception("Could not resolve tenant subscription status")
        return "active"


def check_tenant_usage_quota(
    session: Session,
    *,
    tenant_id: int | str | None,
    action: str,
    now: datetime | None = None,
) -> TenantUsageQuotaState:
    resolved_tenant_id = _tenant_id(tenant_id)
    action_key = (action or "").strip().lower()
    plan = resolve_tenant_plan(session, resolved_tenant_id)
    subscription_status = resolve_tenant_subscription_status(session, resolved_tenant_id)
    try:
        from apps.system.crud.tenant import subscription_blocks_high_cost_features

        if subscription_blocks_high_cost_features(subscription_status):
            return TenantUsageQuotaState(
                allowed=False,
                tenant_id=resolved_tenant_id,
                plan=plan,
                action=action_key,
                window="subscription",
                limit=0,
                used=0,
                remaining=0,
                reason="subscription_suspended",
                subscription_status=subscription_status,
            )
    except Exception:
        AppLogUtil.exception("Could not evaluate tenant subscription status")
        if settings.APP_ENV == "production":
            raise RuntimeError("Tenant subscription status unavailable")
    if not settings.TENANT_USAGE_QUOTA_ENABLED:
        return TenantUsageQuotaState(
            True,
            resolved_tenant_id,
            plan,
            action_key,
            None,
            0,
            0,
            0,
            subscription_status=subscription_status,
        )
    metrics = ACTION_METRICS.get(action_key)
    if not metrics:
        return TenantUsageQuotaState(
            True,
            resolved_tenant_id,
            plan,
            action_key,
            None,
            0,
            0,
            0,
            subscription_status=subscription_status,
        )

    for window in ("daily", "monthly"):
        limit = _quota_limit_for_plan(plan, action_key, window)
        if not limit:
            continue
        start_date, end_date, reset_at = usage_window_dates(window, now)
        used = sum_tenant_usage(
            session,
            tenant_id=resolved_tenant_id,
            metrics=metrics,
            start_date=start_date,
            end_date=end_date,
        )
        if used >= limit:
            return TenantUsageQuotaState(
                allowed=False,
                tenant_id=resolved_tenant_id,
                plan=plan,
                action=action_key,
                window=window,
                limit=limit,
                used=used,
                remaining=0,
                reset_at=reset_at,
                reason="quota_exceeded",
                subscription_status=subscription_status,
            )
    return TenantUsageQuotaState(
        True,
        resolved_tenant_id,
        plan,
        action_key,
        None,
        0,
        0,
        0,
        subscription_status=subscription_status,
    )


def check_tenant_usage_quota_detached(*, tenant_id: int | str | None, action: str) -> TenantUsageQuotaState:
    resolved_tenant_id = _tenant_id(tenant_id)
    try:
        from common.core.db import engine

        with Session(engine) as session:
            return check_tenant_usage_quota(session, tenant_id=resolved_tenant_id, action=action)
    except Exception:
        AppLogUtil.exception("Failed to check tenant usage quota")
        if settings.APP_ENV == "production":
            raise RuntimeError("Tenant usage quota unavailable")
        return TenantUsageQuotaState(True, resolved_tenant_id, "default", action, None, 0, 0, 0)
