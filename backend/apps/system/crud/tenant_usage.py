"""
脚本说明：这个脚本封装系统管理的增删改查和保存逻辑，让接口层不直接处理太多细节。
"""
from datetime import date, datetime, timezone
from dataclasses import dataclass
import calendar
import json
from typing import Any

from sqlalchemy import BigInteger, Text, case, cast, func, inspect
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Session, select

from apps.chat.models.chat_model import ChatLog, ChatRecord
from apps.system.models.tenant_usage import TenantUsageDailyModel
from apps.system.models.user import UserModel
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
    """
    类说明：TenantUsageQuotaState 把系统管理相关的数据和行为放在一起，便于其他代码直接复用。
    """
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
    """
    是什么：usage_metric_date 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return (now or datetime.now(timezone.utc)).date().isoformat()


def _month_last_day(year: int, month: int) -> int:
    """
    是什么：_month_last_day 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return calendar.monthrange(year, month)[1]


def usage_window_dates(window: str, now: datetime | None = None) -> tuple[str, str, str]:
    """
    是什么：usage_window_dates 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
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
    """
    是什么：token_total 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if isinstance(token_usage, dict):
        value = token_usage.get("total_tokens")
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0
    if isinstance(token_usage, (int, float)):
        return int(token_usage)
    return 0


def _chat_log_total_tokens_expr(session: Session):
    """
    是什么：_chat_log_total_tokens_expr 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        token_usage_type = func.jsonb_typeof(ChatLog.token_usage)
        object_total_tokens = cast(
            func.coalesce(func.nullif(ChatLog.token_usage.op("->>")("total_tokens"), ""), "0"),
            BigInteger,
        )
        number_total_tokens = cast(cast(ChatLog.token_usage, Text), BigInteger)
        return case(
            (token_usage_type == "object", object_total_tokens),
            (token_usage_type == "number", number_total_tokens),
            else_=0,
        )
    if dialect == "sqlite":
        token_usage_type = func.json_type(ChatLog.token_usage)
        object_total_tokens = cast(
            func.coalesce(func.nullif(func.json_extract(ChatLog.token_usage, "$.total_tokens"), ""), 0),
            BigInteger,
        )
        number_total_tokens = cast(ChatLog.token_usage, BigInteger)
        return case(
            (token_usage_type == "object", object_total_tokens),
            (token_usage_type.in_(("integer", "real")), number_total_tokens),
            else_=0,
        )
    return 0


def _chat_log_token_key_expr(session: Session, key: str):
    """
    是什么：_chat_log_token_key_expr 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        token_usage_type = func.jsonb_typeof(ChatLog.token_usage)
        object_tokens = cast(
            func.coalesce(func.nullif(ChatLog.token_usage.op("->>")(key), ""), "0"),
            BigInteger,
        )
        return case((token_usage_type == "object", object_tokens), else_=0)
    if dialect == "sqlite":
        token_usage_type = func.json_type(ChatLog.token_usage)
        object_tokens = cast(
            func.coalesce(func.nullif(func.json_extract(ChatLog.token_usage, f"$.{key}"), ""), 0),
            BigInteger,
        )
        return case((token_usage_type == "object", object_tokens), else_=0)
    return 0


def _datetime_to_millis(value) -> int:
    """
    是什么：_datetime_to_millis 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if value is None:
        return 0
    if isinstance(value, datetime):
        return int(value.timestamp() * 1000)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _parse_iso_date(value: str | date | None) -> date | None:
    """
    是什么：_parse_iso_date 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _table_exists(session: Session) -> bool:
    """
    是什么：_table_exists 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    try:
        return inspect(session.connection()).has_table(TenantUsageDailyModel.__tablename__)
    except Exception:
        return False


def _normalize_delta(value: int | None) -> int:
    """
    是什么：_normalize_delta 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    return max(0, int(value or 0))


def _tenant_id(value: int | str | None) -> int:
    """
    是什么：_tenant_id 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    try:
        return int(value or DEFAULT_USAGE_TENANT_ID)
    except (TypeError, ValueError):
        return DEFAULT_USAGE_TENANT_ID


def _parse_quota_limits() -> dict[str, Any]:
    """
    是什么：_parse_quota_limits 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
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
    """
    是什么：_quota_limit_for_plan 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
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
    """
    是什么：_insert_for_dialect 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存系统管理需要的东西，让后续流程能继续往下走。
    """
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
    """
    是什么：record_tenant_usage 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
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
    """
    是什么：record_tenant_usage_detached 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
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
    """
    是什么：list_tenant_usage_daily 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
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


def list_tenant_usage_by_user(
    session: Session,
    *,
    tenant_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """
    是什么：list_tenant_usage_by_user 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    try:
        inspector = inspect(session.connection())
        if not inspector.has_table(ChatLog.__tablename__) or not inspector.has_table(ChatRecord.__tablename__):
            return []
    except Exception:
        return []

    filters = [
        ChatLog.tenant_id == int(tenant_id),
        ChatRecord.tenant_id == int(tenant_id),
        ChatLog.pid == ChatRecord.id,
        ChatLog.local_operation == False,  # noqa: E712
        ChatLog.token_usage.is_not(None),
    ]
    # 即使用户离开工作区，历史用量仍保留在原租户和原用户名下。
    parsed_start_date = _parse_iso_date(start_date)
    parsed_end_date = _parse_iso_date(end_date)
    if parsed_start_date:
        filters.append(func.date(ChatLog.finish_time) >= parsed_start_date)
    if parsed_end_date:
        filters.append(func.date(ChatLog.finish_time) <= parsed_end_date)

    token_expr = _chat_log_total_tokens_expr(session)
    has_user_table = False
    try:
        has_user_table = inspect(session.connection()).has_table(UserModel.__tablename__)
    except Exception:
        has_user_table = False

    statement = (
        select(
            ChatRecord.create_by.label("user_id"),
            func.coalesce(func.sum(token_expr), 0).label("total_tokens"),
            func.count(ChatLog.id).label("request_count"),
            func.coalesce(func.sum(case((ChatLog.error == True, 0), else_=1)), 0).label("success_count"),  # noqa: E712
            func.coalesce(func.sum(case((ChatLog.error == True, 1), else_=0)), 0).label("failure_count"),  # noqa: E712
            func.max(ChatLog.finish_time).label("last_used_time"),
        )
        .select_from(ChatLog)
        .join(ChatRecord, ChatLog.pid == ChatRecord.id)
        .where(*filters)
        .where(ChatRecord.create_by.is_not(None))
        .group_by(ChatRecord.create_by)
        .having(func.coalesce(func.sum(token_expr), 0) > 0)
        .order_by(func.coalesce(func.sum(token_expr), 0).desc(), func.count(ChatLog.id).desc())
        .limit(max(1, min(int(limit or 100), 500)))
    )
    rows = session.exec(statement).all()
    user_ids = [int(row.user_id) for row in rows if row.user_id is not None]
    user_map: dict[int, dict[str, str | None]] = {}
    if has_user_table and user_ids:
        user_rows = session.exec(
            select(UserModel.id, UserModel.account, UserModel.name).where(UserModel.id.in_(user_ids))
        ).all()
        user_map = {
            int(user_id): {
                "account": account,
                "name": name,
            }
            for user_id, account, name in user_rows
        }

    return [
        {
            "tenant_id": int(tenant_id),
            "user_id": int(row.user_id),
            "user_account": user_map.get(int(row.user_id), {}).get("account"),
            "user_name": user_map.get(int(row.user_id), {}).get("name"),
            "request_count": int(row.request_count or 0),
            "success_count": int(row.success_count or 0),
            "failure_count": int(row.failure_count or 0),
            "total_tokens": int(row.total_tokens or 0),
            "last_used_time": _datetime_to_millis(row.last_used_time),
        }
        for row in rows
        if row.user_id is not None
    ]


def list_tenant_usage_by_model(
    session: Session,
    *,
    tenant_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """
    是什么：list_tenant_usage_by_model 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理需要的数据找出来，整理成后面好用的样子。
    """
    try:
        inspector = inspect(session.connection())
        if not inspector.has_table(ChatLog.__tablename__):
            return []
    except Exception:
        return []

    filters = [
        ChatLog.tenant_id == int(tenant_id),
        ChatLog.local_operation == False,  # noqa: E712
        ChatLog.token_usage.is_not(None),
    ]
    parsed_start_date = _parse_iso_date(start_date)
    parsed_end_date = _parse_iso_date(end_date)
    if parsed_start_date:
        filters.append(func.date(ChatLog.finish_time) >= parsed_start_date)
    if parsed_end_date:
        filters.append(func.date(ChatLog.finish_time) <= parsed_end_date)

    total_expr = _chat_log_total_tokens_expr(session)
    input_expr = _chat_log_token_key_expr(session, "input_tokens")
    output_expr = _chat_log_token_key_expr(session, "output_tokens")
    statement = (
        select(
            ChatLog.ai_modal_id.label("model_id"),
            ChatLog.base_modal.label("model_code"),
            func.count(ChatLog.id).label("request_count"),
            func.coalesce(func.sum(case((ChatLog.error == True, 0), else_=1)), 0).label("success_count"),  # noqa: E712
            func.coalesce(func.sum(case((ChatLog.error == True, 1), else_=0)), 0).label("failure_count"),  # noqa: E712
            func.coalesce(func.sum(input_expr), 0).label("input_tokens"),
            func.coalesce(func.sum(output_expr), 0).label("output_tokens"),
            func.coalesce(func.sum(total_expr), 0).label("total_tokens"),
            func.max(ChatLog.finish_time).label("last_used_time"),
        )
        .where(*filters)
        .group_by(ChatLog.ai_modal_id, ChatLog.base_modal)
        .having(func.coalesce(func.sum(total_expr), 0) > 0)
        .order_by(func.coalesce(func.sum(total_expr), 0).desc(), func.count(ChatLog.id).desc())
        .limit(max(1, min(int(limit or 100), 500)))
    )
    rows = session.exec(statement).all()

    model_ids = [int(row.model_id) for row in rows if row.model_id is not None]
    model_map: dict[int, dict[str, str | None]] = {}
    if model_ids:
        try:
            from apps.system.models.system_model import AiModelDetail

            if inspect(session.connection()).has_table(AiModelDetail.__tablename__):
                model_rows = session.exec(
                    select(AiModelDetail.id, AiModelDetail.name, AiModelDetail.base_model).where(
                        AiModelDetail.id.in_(model_ids)
                    )
                ).all()
                model_map = {
                    int(model_id): {
                        "name": name,
                        "base_model": base_model,
                    }
                    for model_id, name, base_model in model_rows
                }
        except Exception:
            AppLogUtil.exception("Could not resolve AI model names for tenant usage")

    result: list[dict[str, Any]] = []
    for row in rows:
        model_id = int(row.model_id) if row.model_id is not None else None
        configured_model = model_map.get(model_id or -1, {})
        fallback_code = str(row.model_code or "").strip() or "default"
        model_code = str(configured_model.get("base_model") or fallback_code)
        model_name = str(configured_model.get("name") or fallback_code)
        result.append(
            {
                "tenant_id": int(tenant_id),
                "model_id": model_id,
                "model_name": model_name,
                "model_code": model_code,
                "request_count": int(row.request_count or 0),
                "success_count": int(row.success_count or 0),
                "failure_count": int(row.failure_count or 0),
                "input_tokens": int(row.input_tokens or 0),
                "output_tokens": int(row.output_tokens or 0),
                "total_tokens": int(row.total_tokens or 0),
                "last_used_time": _datetime_to_millis(row.last_used_time),
            }
        )
    return result


def sum_tenant_usage(
    session: Session,
    *,
    tenant_id: int | str | None,
    metrics: tuple[str, ...],
    start_date: str,
    end_date: str,
    field: str = "request_count",
) -> int:
    """
    是什么：sum_tenant_usage 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
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
    """
    是什么：resolve_tenant_plan 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
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
    """
    是什么：resolve_tenant_subscription_status 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把系统管理里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
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
    """
    是什么：check_tenant_usage_quota 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查系统管理里的数据、权限或配置是否合法，不对就及时拦住。
    """
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
    """
    是什么：check_tenant_usage_quota_detached 是一个可以复用的小步骤，负责系统管理相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查系统管理里的数据、权限或配置是否合法，不对就及时拦住。
    """
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
