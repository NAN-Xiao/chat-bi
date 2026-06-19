import hashlib
import inspect
import time
from collections.abc import Callable
from typing import Any

import sqlglot
from sqlglot import exp

from apps.datasource.crud.permission import (
    get_row_permission_filters,
    has_datasource_access,
    is_normal_user,
)
from apps.datasource.crud.sql_permission import (
    apply_row_permission_filters,
    validate_sql_scope,
)
from apps.datasource.models.datasource import CoreDatasource
from apps.db.db import check_sql_read, exec_sql as default_exec_sql, get_sqlglot_dialect
from common.core.config import settings
from common.core.deps import CurrentUser, SessionDep
from common.utils.data_format import DataFormat
from common.utils.utils import AppLogUtil

QueryExecutor = Callable[..., dict[str, Any]]

USER_PERMISSION_DENIED_MESSAGE = "SQL 超出当前数据权限范围"

_PERMISSION_ERROR_MARKERS = (
    "无权限",
    "权限",
    "permission",
    "unauthorized",
    "not authorized",
    "SELECT *",
    "字段权限",
    "表范围",
)


def _sql_hash(sql: str) -> str:
    return hashlib.sha256(str(sql or "").encode("utf-8")).hexdigest()[:16]


def _looks_like_permission_scope_error(message: str) -> bool:
    lowered = message.lower()
    return any(marker.lower() in lowered for marker in _PERMISSION_ERROR_MARKERS)


def _public_error_message(current_user: CurrentUser, message: str) -> str:
    if is_normal_user(current_user) and _looks_like_permission_scope_error(message):
        return USER_PERMISSION_DENIED_MESSAGE
    if is_normal_user(current_user) and settings.APP_ENV == "production":
        return "数据查询失败，请联系管理员查看后台日志"
    return message


def failed_query_result(
    message: str,
    *,
    executed_sql: str = "",
    row_count: int = 0,
) -> dict[str, Any]:
    return {
        "status": "failed",
        "fields": [],
        "data": [],
        "message": message,
        "executed_sql": executed_sql,
        "row_count": row_count,
    }


def _success_query_result(
    data: list[Any],
    fields: list[Any],
    *,
    executed_sql: str,
    truncated: bool = False,
) -> dict[str, Any]:
    return {
        "status": "success",
        "fields": fields,
        "data": data,
        "message": "",
        "executed_sql": executed_sql,
        "row_count": len(data),
        "truncated": truncated,
        "formatted": True,
    }


def _default_executor(
        datasource: CoreDatasource,
        sql: str,
        origin_column: bool = False,
        execution_timeout_seconds: int | None = None,
        fetch_limit: int | None = None,
) -> dict[str, Any]:
    return default_exec_sql(
        ds=datasource,
        sql=sql,
        origin_column=origin_column,
        execution_timeout_seconds=execution_timeout_seconds,
        fetch_limit=fetch_limit,
    )


def _limit_literal(limit_expr: exp.Expression | None) -> exp.Literal | None:
    if limit_expr is None:
        return None
    value = limit_expr.args.get("expression") or limit_expr.args.get("count")
    return value if isinstance(value, exp.Literal) else None


def _sqlglot_limit_dialect(datasource: CoreDatasource) -> str | None:
    dialect = get_sqlglot_dialect(str(getattr(datasource, "type", "") or ""))
    if dialect:
        return dialect
    ds_type = str(getattr(datasource, "type", "") or "").casefold()
    if ds_type in {"pg", "excel", "redshift", "kingbase"}:
        return "postgres"
    if ds_type == "oracle":
        return "oracle"
    if ds_type == "ck":
        return "clickhouse"
    return None


def _with_outer_row_limit(sql: str, datasource: CoreDatasource, row_limit: int | None) -> str:
    if not row_limit or row_limit <= 0:
        return sql
    dialect = _sqlglot_limit_dialect(datasource)
    try:
        statements = [stmt for stmt in sqlglot.parse(sql, dialect=dialect) if stmt is not None]
        if len(statements) != 1:
            return sql
        statement = statements[0]
        if not isinstance(statement, exp.Query):
            return sql

        current_limit = statement.args.get("limit")
        literal = _limit_literal(current_limit)
        if literal is not None:
            try:
                current_value = int(str(literal.this))
                if current_value <= row_limit:
                    return statement.sql(dialect=dialect)
            except (TypeError, ValueError):
                return statement.sql(dialect=dialect)
            if "count" in current_limit.args:
                current_limit.set("count", exp.Literal.number(row_limit))
            else:
                current_limit.set("expression", exp.Literal.number(row_limit))
        else:
            statement.set("limit", exp.Limit(expression=exp.Literal.number(row_limit)))
        return statement.sql(dialect=dialect)
    except Exception:
        AppLogUtil.exception("Failed to rewrite SQL row limit through sqlglot")
        return sql


def _execute_with_limits(
        executor: QueryExecutor,
        datasource: CoreDatasource,
        sql: str,
        origin_column: bool,
        *,
        execution_timeout_seconds: int,
        fetch_limit: int | None,
) -> dict[str, Any]:
    try:
        signature = inspect.signature(executor)
        accepts_kwargs = any(
            param.kind == inspect.Parameter.VAR_KEYWORD
            for param in signature.parameters.values()
        )
        supports_timeout = "execution_timeout_seconds" in signature.parameters
        supports_fetch_limit = "fetch_limit" in signature.parameters
    except (TypeError, ValueError):
        accepts_kwargs = supports_timeout = supports_fetch_limit = True

    if accepts_kwargs or supports_timeout or supports_fetch_limit:
        kwargs: dict[str, Any] = {}
        if accepts_kwargs or supports_timeout:
            kwargs["execution_timeout_seconds"] = execution_timeout_seconds
        if accepts_kwargs or supports_fetch_limit:
            kwargs["fetch_limit"] = fetch_limit
        return executor(datasource, sql, origin_column, **kwargs)
    return executor(datasource, sql, origin_column)


def call_exec_sql_compat(
        exec_func: Callable[..., dict[str, Any]],
        *,
        ds: CoreDatasource,
        sql: str,
        origin_column: bool = False,
        execution_timeout_seconds: int | None = None,
        fetch_limit: int | None = None,
) -> dict[str, Any]:
    """Call an exec_sql-like function while remaining compatible with old test doubles/extensions."""
    try:
        signature = inspect.signature(exec_func)
        parameters = signature.parameters
        accepts_kwargs = any(
            param.kind == inspect.Parameter.VAR_KEYWORD
            for param in parameters.values()
        )
        supports_ds_keyword = "ds" in parameters
        supports_origin_column = "origin_column" in parameters
        supports_timeout = "execution_timeout_seconds" in parameters
        supports_fetch_limit = "fetch_limit" in parameters
    except (TypeError, ValueError):
        accepts_kwargs = supports_ds_keyword = supports_origin_column = True
        supports_timeout = supports_fetch_limit = True

    optional_kwargs: dict[str, Any] = {}
    if accepts_kwargs or supports_origin_column:
        optional_kwargs["origin_column"] = origin_column
    if accepts_kwargs or supports_timeout:
        optional_kwargs["execution_timeout_seconds"] = execution_timeout_seconds
    if accepts_kwargs or supports_fetch_limit:
        optional_kwargs["fetch_limit"] = fetch_limit

    if accepts_kwargs or supports_ds_keyword:
        return exec_func(ds=ds, sql=sql, **optional_kwargs)
    return exec_func(ds, sql, **optional_kwargs)


def _audit_query_execution(
    *,
    current_user: CurrentUser,
    datasource_id: int,
    purpose: str,
    sql: str,
    executed_sql: str,
    elapsed_ms: int,
    row_count: int,
    status: str,
    failure_reason: str = "",
    record_id: int | str | None = None,
    task_id: str | None = None,
    model_id: int | str | None = None,
    custom_agent_id: int | str | None = None,
) -> None:
    message = (
        "sql_query_execution "
        f"status={status} purpose={purpose} user_id={getattr(current_user, 'id', None)} "
        f"datasource_id={datasource_id} record_id={record_id} task_id={task_id} "
        f"model_id={model_id} custom_agent_id={custom_agent_id} "
        f"sql_hash={_sql_hash(sql)} executed_sql_hash={_sql_hash(executed_sql)} "
        f"elapsed_ms={elapsed_ms} row_count={row_count}"
    )
    if failure_reason:
        message += f" failure_reason={failure_reason}"
    if status == "success":
        AppLogUtil.info(message)
    else:
        AppLogUtil.error(message)


def execute_scoped_query(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    datasource_id: int,
    sql: str,
    purpose: str,
    row_limit: int | None = None,
    executor: QueryExecutor | None = None,
    apply_row_permissions: bool = True,
    allow_row_permission_filter_star: bool = False,
    origin_column: bool = False,
    record_id: int | str | None = None,
    task_id: str | None = None,
    model_id: int | str | None = None,
    custom_agent_id: int | str | None = None,
) -> dict[str, Any]:
    """Execute a datasource query through the shared production safety envelope.

    This service intentionally keeps the public result shape compatible with the
    older callers while adding executed_sql and row_count for audit/debug use.
    """
    started = time.monotonic()
    execute_sql_text = str(sql or "").strip()
    executor = executor or _default_executor
    limit = row_limit if row_limit is not None else settings.SQL_QUERY_DEFAULT_ROW_LIMIT
    row_permission_star_allowed = allow_row_permission_filter_star

    try:
        datasource = session.get(CoreDatasource, datasource_id)
        if datasource is None:
            return failed_query_result("项目不存在")
        if not has_datasource_access(session, current_user, datasource_id):
            return failed_query_result(_public_error_message(
                current_user,
                "You do not have permission to access this datasource",
            ))

        is_safe, error_reason = check_sql_read(execute_sql_text, datasource)
        if not is_safe:
            raise ValueError(f"SQL can only contain read operations: {error_reason}")

        statements, actual_tables, _permission_scope = validate_sql_scope(
            session,
            current_user,
            datasource,
            execute_sql_text,
            allow_row_permission_filter_star=allow_row_permission_filter_star,
        )
        if len(statements) != 1:
            raise ValueError("只允许执行一条只读 SQL")

        if apply_row_permissions and is_normal_user(current_user):
            row_filters = get_row_permission_filters(
                session=session,
                current_user=current_user,
                ds=datasource,
                tables=sorted(actual_tables),
            )
            if row_filters:
                execute_sql_text = apply_row_permission_filters(execute_sql_text, datasource, row_filters)
                row_permission_star_allowed = True
                is_safe, error_reason = check_sql_read(execute_sql_text, datasource)
                if not is_safe:
                    raise ValueError(f"SQL can only contain read operations: {error_reason}")
                validate_sql_scope(
                    session,
                    current_user,
                    datasource,
                    execute_sql_text,
                    allow_row_permission_filter_star=True,
                )

        execute_sql_text = _with_outer_row_limit(execute_sql_text, datasource, limit)
        is_safe, error_reason = check_sql_read(execute_sql_text, datasource)
        if not is_safe:
            raise ValueError(f"SQL can only contain read operations after limit rewrite: {error_reason}")
        validate_sql_scope(
            session,
            current_user,
            datasource,
            execute_sql_text,
            allow_row_permission_filter_star=row_permission_star_allowed,
        )

        fetch_limit = limit if limit and limit > 0 else None
        result = _execute_with_limits(
            executor,
            datasource,
            execute_sql_text,
            origin_column,
            execution_timeout_seconds=settings.SQL_QUERY_EXECUTION_TIMEOUT_SECONDS,
            fetch_limit=fetch_limit,
        )
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if elapsed_ms > settings.SQL_QUERY_EXECUTION_TIMEOUT_SECONDS * 1000:
            raise TimeoutError(
                f"SQL execution exceeded {settings.SQL_QUERY_EXECUTION_TIMEOUT_SECONDS}s"
            )

        raw_data = result.get("data") or []
        data = DataFormat.convert_large_numbers_in_object_array(raw_data)
        data = DataFormat.normalize_qualified_sql_column_keys_in_object_array(data)
        truncated = False
        if limit and limit > 0 and len(data) > limit:
            data = data[:limit]
            truncated = True
        fields = list(data[0].keys()) if data else list(result.get("fields") or [])

        _audit_query_execution(
            current_user=current_user,
            datasource_id=datasource_id,
            purpose=purpose,
            sql=sql,
            executed_sql=execute_sql_text,
            elapsed_ms=elapsed_ms,
            row_count=len(data),
            status="success",
            record_id=record_id,
            task_id=task_id,
            model_id=model_id,
            custom_agent_id=custom_agent_id,
        )
        return _success_query_result(
            data,
            fields,
            executed_sql=execute_sql_text,
            truncated=truncated,
        )
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        raw_message = str(exc)
        _audit_query_execution(
            current_user=current_user,
            datasource_id=datasource_id,
            purpose=purpose,
            sql=sql,
            executed_sql=execute_sql_text,
            elapsed_ms=elapsed_ms,
            row_count=0,
            status="failed",
            failure_reason=raw_message,
            record_id=record_id,
            task_id=task_id,
            model_id=model_id,
            custom_agent_id=custom_agent_id,
        )
        return failed_query_result(
            _public_error_message(current_user, raw_message),
            executed_sql=execute_sql_text,
        )
