"""
脚本说明：这个脚本封装数据源的增删改查和保存逻辑，让接口层不直接处理太多细节。
"""
from dataclasses import dataclass
import inspect
import re
import time
from typing import Any

from sqlglot import exp

from apps.datasource.crud.permission import (
    get_row_permission_filters,
    has_datasource_access,
    is_normal_user,
)
from apps.datasource.crud.permission_errors import (
    PERMISSION_DENIED_DISPLAY_MESSAGE,
    PERMISSION_DENIED_ERROR_TYPE,
    audit_permission_denied,
    looks_like_permission_scope_error,
)
from apps.datasource.crud.sql_permission import (
    apply_row_permission_filters,
    extract_physical_tables,
    normalize_identifier,
    parse_condition_expression,
    parse_sql_statements,
    validate_sql_columns,
    validate_sql_scope,
    validate_sql_table_scope,
)
from apps.datasource.models.datasource import CoreDatasource
from apps.db.db import check_sql_read, _unsafe_exec_sql_after_validation, get_sqlglot_dialect
from apps.system.schemas.system_schema import AssistantOutDsSchema
from common.core.deps import CurrentUser, SessionDep
from common.error import DataUnavailableError
from common.user_facing_errors import (
    DATA_UNAVAILABLE_ERROR_TYPE,
    classify_error,
    data_unavailable_data_result,
    failed_data_result,
    looks_like_data_unavailable_error as common_looks_like_data_unavailable_error,
)
from common.utils.data_format import DataFormat
from common.utils.utils import AppLogUtil


USER_QUERY_PERMISSION_DENIED_MESSAGE = PERMISSION_DENIED_DISPLAY_MESSAGE


def looks_like_data_unavailable_error(message: str) -> bool:
    """
    是什么：判断 SQL 执行错误是否是缺表、缺字段或数据结构不可用。
    谁调用：查询执行器和 Smart Q&A 错误处理。
    做了什么：把底层数据库错误归类为用户可理解的数据不可用反馈。
    """
    return common_looks_like_data_unavailable_error(message)


def user_data_unavailable_message(message: str) -> str:
    """
    是什么：把数据库缺表/缺字段错误转成面向用户的业务提示。
    谁调用：执行 SQL 时捕获结构缺失错误。
    做了什么：避免把 traceback 暴露给用户。
    """
    text = str(message or "")
    identifiers = []
    for pattern in [
        r'relation\s+"([^"]+)"\."([^"]+)"\s+does not exist',
        r'relation\s+"([^"]+)"\s+does not exist',
        r'column\s+"([^"]+)"\s+does not exist',
        r'table\s+"([^"]+)"\s+does not exist',
        r'表[“"]?([^”"\s]+)[”"]?不存在',
        r'列[“"]?([^”"\s]+)[”"]?不存在',
        r'字段[“"]?([^”"\s]+)[”"]?不存在',
    ]:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            identifiers.append(".".join(part for part in match.groups() if part))
            break

    suffix = f"：{identifiers[0]}" if identifiers else ""
    return (
        f"当前数据源缺少本次问题所需的表、字段或埋点数据{suffix}。"
        "我不能编造不存在的数据；如果问题里还有当前数据源能支持的部分，我会只生成可支持的结果。"
        "请换一个当前数据源已包含的指标，或让管理员补充对应表/字段/埋点配置后再试。"
    )


@dataclass
class QueryExecutionResult:
    """
    类说明：QueryExecutionResult 把数据源相关的数据和行为放在一起，便于其他代码直接复用。
    """
    result: dict[str, Any]
    datasource: CoreDatasource | AssistantOutDsSchema
    requested_sql: str
    executed_sql: str
    tables: set[str]
    execution_time_ms: int


def _failed_query_result(message: str, error_type: str | None = None) -> dict[str, Any]:
    """
    是什么：_failed_query_result 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if error_type:
        return failed_data_result(error_type=error_type, message=message)
    return {
        "status": "failed",
        "fields": [],
        "data": [],
        "message": message,
    }


def safe_query_error_message(current_user: CurrentUser, message: str) -> str:
    """
    是什么：safe_query_error_message 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if is_normal_user(current_user) and looks_like_permission_scope_error(message):
        return USER_QUERY_PERMISSION_DENIED_MESSAGE
    return message


def safe_query_error_type(current_user: CurrentUser, message: str) -> str | None:
    """
    是什么：safe_query_error_type 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if is_normal_user(current_user) and looks_like_permission_scope_error(message):
        return PERMISSION_DENIED_ERROR_TYPE
    return None


def _validate_allowed_tables(actual_tables: set[str], allowed_tables: list[str] | set[str] | None) -> None:
    """
    是什么：_validate_allowed_tables 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查数据源里的数据、权限或配置是否合法，不对就及时拦住。
    """
    if allowed_tables is None:
        return
    allowed_table_set = {str(table).lower() for table in allowed_tables}
    unauthorized_tables = {table for table in actual_tables if table.lower() not in allowed_table_set}
    if unauthorized_tables:
        raise ValueError(f"SQL 包含无权限表：{', '.join(sorted(unauthorized_tables))}")


def _external_table_scope(datasource: AssistantOutDsSchema) -> dict[str, dict[str, Any]]:
    """
    是什么：把 assistant 外部数据源配置转换成可复用的表/字段权限范围。
    谁调用：外部 assistant SQL 执行前的确定性权限校验。
    做了什么：逻辑表和动态临时表都只允许配置中暴露的字段，SELECT * 默认失败关闭。
    """
    scope: dict[str, dict[str, Any]] = {}
    for table in getattr(datasource, "tables", None) or []:
        table_name = normalize_identifier(getattr(table, "name", None))
        if not table_name:
            continue
        fields = {
            normalize_identifier(getattr(field, "name", None))
            for field in (getattr(table, "fields", None) or [])
            if normalize_identifier(getattr(field, "name", None))
        }
        entry = {
            "table": table,
            "fields": fields,
            # 外部数据源没有系统库里的完整字段全集。只要配置了表，就禁止 SELECT *，
            # 防止底层真实表新增或隐藏字段被顺带带出。
            "denied_fields": {"*"},
        }
        scope[table_name] = entry
        scope[normalize_identifier(f"app_dynamic_temp_table_{getattr(table, 'name', '')}")] = entry
    return scope


def _validate_external_sql_scope(
        datasource: AssistantOutDsSchema,
        statements: list[Any],
        actual_tables: set[str],
) -> None:
    """
    是什么：校验 assistant 外部数据源 SQL 只访问已配置的逻辑表和字段。
    谁调用：execute_external_user_query_or_raise。
    做了什么：基于 AssistantOutDsSchema.tables 做确定性白名单，而不是依赖 LLM 自觉。
    """
    scope = _external_table_scope(datasource)
    if not scope:
        raise ValueError("外部数据源缺少表权限配置，无法安全执行 SQL")
    unauthorized_tables = actual_tables - set(scope.keys())
    if unauthorized_tables:
        raise ValueError(f"SQL 包含无权限表：{', '.join(sorted(unauthorized_tables))}")
    validate_sql_columns(statements, scope, current_user=None, enforce=True)


def _external_row_filters(datasource: AssistantOutDsSchema, actual_tables: set[str]) -> list[dict[str, str]]:
    """
    是什么：从 assistant 外部数据源表配置中提取需要强制应用的行过滤条件。
    谁调用：外部 assistant SQL 执行和动态子查询生成。
    做了什么：同时支持逻辑表名和 app_dynamic_temp_table_* 临时表名。
    """
    filters: list[dict[str, str]] = []
    actual_table_set = {normalize_identifier(table) for table in actual_tables}
    for table in getattr(datasource, "tables", None) or []:
        table_name = normalize_identifier(getattr(table, "name", None))
        if not table_name:
            continue
        temp_table_name = normalize_identifier(f"app_dynamic_temp_table_{getattr(table, 'name', '')}")
        rule = str(getattr(table, "rule", None) or "").strip()
        if not rule:
            continue
        if table_name in actual_table_set:
            filters.append({"table": table_name, "filter": rule})
        if temp_table_name in actual_table_set:
            filters.append({"table": temp_table_name, "filter": rule})
    return filters


def external_table_rule(datasource: AssistantOutDsSchema, table_name: str) -> str | None:
    """
    是什么：读取 assistant 外部数据源某个逻辑表的行过滤规则。
    谁调用：动态 assistant 子查询替换前的确定性过滤。
    做了什么：兼容原始逻辑表名和 app_dynamic_temp_table_* 名称。
    """
    requested = normalize_identifier(table_name)
    for table in getattr(datasource, "tables", None) or []:
        raw_name = str(getattr(table, "name", None) or "")
        logical_name = normalize_identifier(raw_name)
        temp_name = normalize_identifier(f"app_dynamic_temp_table_{raw_name}")
        if requested in {logical_name, temp_name}:
            rule = str(getattr(table, "rule", None) or "").strip()
            return rule or None
    return None


def wrap_external_subquery_with_table_rule(
        datasource: AssistantOutDsSchema,
        table_name: str,
        sql: str,
) -> str:
    """
    是什么：给动态 assistant 的真实子查询包上配置的行过滤规则。
    谁调用：Smart Q&A 动态外部数据源替换 app_dynamic_temp_table_* 前。
    做了什么：把 table.rule 作为外层 WHERE 强制应用，避免只校验占位 SQL 却执行未过滤 SQL。
    """
    rule = external_table_rule(datasource, table_name)
    if not rule:
        return sql
    parse_condition_expression(rule, getattr(datasource, "type", None))
    logic_alias = table_name
    temp_alias = f"app_dynamic_temp_table_{table_name}"
    return f"SELECT * FROM (SELECT * FROM ({sql}) {logic_alias} WHERE {rule}) {temp_alias}"


def _ensure_external_row_filters_enforced(
        datasource: AssistantOutDsSchema,
        sql: str,
        row_filters: list[dict[str, str]],
) -> None:
    """
    是什么：确认外部 assistant 的行权限过滤已经落到实际执行 SQL。
    谁调用：execute_external_user_query_or_raise。
    做了什么：普通逻辑表可由 AST 重写保障；动态子查询必须已经显式包含对应规则，否则失败关闭。
    """
    if not row_filters:
        return
    statements = parse_sql_statements(sql, datasource.type)
    sqlglot_dialect = get_sqlglot_dialect(getattr(datasource, "type", None))
    where_fragments = {
        fragment.sql()
        for statement in statements
        for where in statement.find_all(exp.Where)
        for fragment in where.this.walk()
    }
    where_fragments.update(
        fragment.sql(dialect=sqlglot_dialect)
        for statement in statements
        for where in statement.find_all(exp.Where)
        for fragment in where.this.walk()
    )
    missing: list[str] = []
    for item in row_filters:
        table_name = normalize_identifier(item.get("table"))
        filter_sql = str(item.get("filter") or "").strip()
        if not table_name or not filter_sql:
            continue
        condition = parse_condition_expression(filter_sql, getattr(datasource, "type", None))
        condition_sqls = {
            condition.sql(),
            condition.sql(dialect=sqlglot_dialect),
        }
        if condition_sqls & where_fragments:
            continue
        missing.append(table_name)
    if missing:
        raise ValueError(f"外部数据源行权限过滤条件未应用：{', '.join(sorted(set(missing)))}")


def _normalize_query_result(result: dict[str, Any], origin_column: bool) -> dict[str, Any]:
    """
    是什么：_normalize_query_result 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    data = DataFormat.convert_large_numbers_in_object_array(result.get("data"))
    data = DataFormat.normalize_qualified_sql_column_keys_in_object_array(data)
    result["data"] = data
    if data:
        result["fields"] = list(data[0].keys())
    return result


def _copy_datasource_for_query(datasource: CoreDatasource) -> CoreDatasource:
    """
    是什么：_copy_datasource_for_query 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：复制数据源对象，避免关闭系统库事务后继续依赖会话绑定对象。
    """
    if hasattr(datasource, "model_dump"):
        try:
            return CoreDatasource(**datasource.model_dump())
        except Exception:
            pass
    return datasource


def _execute_after_validation(
        ds: CoreDatasource | AssistantOutDsSchema,
        sql: str,
        *,
        origin_column: bool,
        query_timeout: int | None = None,
) -> dict[str, Any]:
    """
    是什么：_execute_after_validation 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：调用底层 SQL 执行器，并在执行器支持时传递查询超时时间。
    """
    try:
        if query_timeout and query_timeout > 0:
            try:
                signature = inspect.signature(_unsafe_exec_sql_after_validation)
                params = signature.parameters
                accepts_timeout = "query_timeout" in params or any(
                    param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values()
                )
            except (TypeError, ValueError):
                accepts_timeout = True
            if accepts_timeout:
                return _unsafe_exec_sql_after_validation(
                    ds=ds,
                    sql=sql,
                    origin_column=origin_column,
                    query_timeout=query_timeout,
                )
        return _unsafe_exec_sql_after_validation(ds=ds, sql=sql, origin_column=origin_column)
    except Exception as exc:
        if classify_error(exc).error_type == DATA_UNAVAILABLE_ERROR_TYPE:
            raise DataUnavailableError(user_data_unavailable_message(str(exc))) from exc
        raise


def prepare_query_sql(
        session: SessionDep,
        current_user: CurrentUser,
        datasource: CoreDatasource,
        sql: str,
        *,
        allowed_tables: list[str] | set[str] | None = None,
        apply_row_permissions: bool = True,
        validate_columns: bool = True,
) -> tuple[str, set[str]]:
    """
    是什么：prepare_query_sql 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    is_safe, error_reason = check_sql_read(sql, datasource)
    if not is_safe:
        raise ValueError(f"SQL can only contain read operations: {error_reason}")

    if validate_columns:
        _statements, actual_tables, _permission_scope = validate_sql_scope(
            session,
            current_user,
            datasource,
            sql,
        )
    else:
        actual_tables = validate_sql_table_scope(session, current_user, datasource, sql)

    _validate_allowed_tables(actual_tables, allowed_tables)

    executed_sql = sql
    if apply_row_permissions and is_normal_user(current_user):
        row_filters = get_row_permission_filters(
            session=session,
            current_user=current_user,
            ds=datasource,
            tables=sorted(actual_tables),
        )
        if row_filters:
            executed_sql = apply_row_permission_filters(sql, datasource, row_filters)
            is_safe, error_reason = check_sql_read(executed_sql, datasource)
            if not is_safe:
                raise ValueError(f"SQL can only contain read operations: {error_reason}")
            rewritten_tables = validate_sql_table_scope(session, current_user, datasource, executed_sql)
            _validate_allowed_tables(rewritten_tables, allowed_tables)

    return executed_sql, actual_tables


def validate_user_query_sql_or_raise(
        session: SessionDep,
        current_user: CurrentUser,
        datasource: CoreDatasource,
        sql: str,
        *,
        allowed_tables: list[str] | set[str] | None = None,
) -> tuple[str, set[str]]:
    """
    是什么：validate_user_query_sql_or_raise 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查数据源里的数据、权限或配置是否合法，不对就及时拦住。
    """
    if datasource is None:
        raise ValueError("项目不存在")
    if getattr(datasource, "id", None) is not None and not has_datasource_access(session, current_user, datasource.id):
        raise ValueError("You do not have permission to access this datasource")
    return prepare_query_sql(
        session=session,
        current_user=current_user,
        datasource=datasource,
        sql=sql,
        allowed_tables=allowed_tables,
        apply_row_permissions=False,
        validate_columns=True,
    )


def execute_user_query_or_raise(
        session: SessionDep,
        current_user: CurrentUser,
        datasource: CoreDatasource,
        sql: str,
        *,
        allowed_tables: list[str] | set[str] | None = None,
        origin_column: bool = False,
        apply_row_permissions: bool = True,
        validate_columns: bool = True,
        query_timeout: int | None = None,
        close_system_transaction_before_query: bool = False,
) -> QueryExecutionResult:
    """
    是什么：execute_user_query_or_raise 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源的主要流程跑起来，一步步调用需要的处理。
    """
    if datasource is None:
        raise ValueError("项目不存在")
    if getattr(datasource, "id", None) is not None and not has_datasource_access(session, current_user, datasource.id):
        raise ValueError("You do not have permission to access this datasource")

    executed_sql, tables = prepare_query_sql(
        session=session,
        current_user=current_user,
        datasource=datasource,
        sql=sql,
        allowed_tables=allowed_tables,
        apply_row_permissions=apply_row_permissions,
        validate_columns=validate_columns,
    )
    datasource_for_query = _copy_datasource_for_query(datasource)
    if close_system_transaction_before_query:
        try:
            session.rollback()
        except Exception as exc:
            AppLogUtil.warning(f"Failed to close system DB read transaction before datasource query: {exc}")
    started_at = time.perf_counter()
    result = _execute_after_validation(
        ds=datasource_for_query,
        sql=executed_sql,
        origin_column=origin_column,
        query_timeout=query_timeout,
    )
    execution_time_ms = int((time.perf_counter() - started_at) * 1000)
    result = _normalize_query_result(result, origin_column)
    return QueryExecutionResult(
        result=result,
        datasource=datasource_for_query,
        requested_sql=sql,
        executed_sql=executed_sql,
        tables=tables,
        execution_time_ms=execution_time_ms,
    )


def execute_user_analysis_query_or_raise(
        session: SessionDep,
        current_user: CurrentUser,
        datasource: CoreDatasource,
        sql: str,
        *,
        allowed_tables: list[str] | set[str] | None = None,
        origin_column: bool = False,
) -> QueryExecutionResult:
    """
    是什么：execute_user_analysis_query_or_raise 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源的主要流程跑起来，一步步调用需要的处理。
    """
    return execute_user_query_or_raise(
        session=session,
        current_user=current_user,
        datasource=datasource,
        sql=sql,
        allowed_tables=allowed_tables,
        origin_column=origin_column,
    )


def execute_external_user_query_or_raise(
        datasource: AssistantOutDsSchema,
        sql: str,
        *,
        allowed_tables: list[str] | set[str] | None = None,
        origin_column: bool = False,
        scope_sql: str | None = None,
) -> QueryExecutionResult:
    """
    是什么：execute_external_user_query_or_raise 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源的主要流程跑起来，一步步调用需要的处理。
    """
    if datasource is None:
        raise ValueError("项目不存在")

    is_safe, error_reason = check_sql_read(sql, datasource)
    if not is_safe:
        raise ValueError(f"SQL can only contain read operations: {error_reason}")

    scope_statements = parse_sql_statements(scope_sql or sql, datasource.type)
    actual_tables = extract_physical_tables(scope_statements)
    if not actual_tables:
        raise ValueError("SQL 解析失败，无法确认查询表范围")
    _validate_external_sql_scope(datasource, scope_statements, actual_tables)
    _validate_allowed_tables(actual_tables, allowed_tables)

    executed_sql = sql
    row_filters = _external_row_filters(datasource, actual_tables)
    if row_filters:
        executed_sql = apply_row_permission_filters(sql, datasource, row_filters)
        is_safe, error_reason = check_sql_read(executed_sql, datasource)
        if not is_safe:
            raise ValueError(f"SQL can only contain read operations: {error_reason}")
        _ensure_external_row_filters_enforced(datasource, executed_sql, row_filters)

    parse_sql_statements(executed_sql, datasource.type)

    started_at = time.perf_counter()
    result = _execute_after_validation(ds=datasource, sql=executed_sql, origin_column=origin_column)
    execution_time_ms = int((time.perf_counter() - started_at) * 1000)
    result = _normalize_query_result(result, origin_column)
    return QueryExecutionResult(
        result=result,
        datasource=datasource,
        requested_sql=scope_sql or sql,
        executed_sql=executed_sql,
        tables=actual_tables,
        execution_time_ms=execution_time_ms,
    )


def execute_user_query(
        session: SessionDep,
        current_user: CurrentUser,
        datasource_id: int,
        sql: str,
        *,
        allowed_tables: list[str] | set[str] | None = None,
        origin_column: bool = False,
        apply_row_permissions: bool = True,
        validate_columns: bool = True,
        query_timeout: int | None = None,
        close_system_transaction_before_query: bool = False,
        include_execution_meta: bool = False,
) -> dict[str, Any]:
    """
    是什么：execute_user_query 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源的主要流程跑起来，一步步调用需要的处理。
    """
    try:
        datasource = session.get(CoreDatasource, datasource_id)
        if datasource is None:
            return _failed_query_result("项目不存在")
        if not has_datasource_access(session, current_user, datasource_id):
            message = "You do not have permission to access this datasource"
            audit_permission_denied(
                current_user=current_user,
                datasource_id=datasource_id,
                operation="execute_user_query.datasource_access",
                reason=message,
            )
            return _failed_query_result(
                safe_query_error_message(current_user, message),
                safe_query_error_type(current_user, message),
            )
        query_result = execute_user_query_or_raise(
            session=session,
            current_user=current_user,
            datasource=datasource,
            sql=sql,
            allowed_tables=allowed_tables,
            origin_column=origin_column,
            apply_row_permissions=apply_row_permissions,
            validate_columns=validate_columns,
            query_timeout=query_timeout,
            close_system_transaction_before_query=close_system_transaction_before_query,
        )
        result = {
            "status": "success",
            "fields": query_result.result.get("fields", []),
            "data": query_result.result.get("data", []),
            "message": "",
            "sql": query_result.result.get("sql"),
        }
        if include_execution_meta:
            result["_execution_meta"] = {
                "requested_sql": query_result.requested_sql,
                "executed_sql": query_result.executed_sql,
                "execution_time_ms": query_result.execution_time_ms,
                "tables": sorted(query_result.tables),
            }
        return result
    except DataUnavailableError as exc:
        AppLogUtil.error(f"User query data unavailable: {exc}")
        return data_unavailable_data_result(str(exc))
    except Exception as exc:
        AppLogUtil.error(f"User query execution failed: {exc}")
        message = safe_query_error_message(current_user, f"{exc}")
        error_type = safe_query_error_type(current_user, f"{exc}")
        classification = classify_error(exc)
        if error_type is None and classification.error_type == PERMISSION_DENIED_ERROR_TYPE:
            message = USER_QUERY_PERMISSION_DENIED_MESSAGE if is_normal_user(current_user) else str(exc)
            error_type = PERMISSION_DENIED_ERROR_TYPE
        if error_type == PERMISSION_DENIED_ERROR_TYPE:
            audit_permission_denied(
                current_user=current_user,
                datasource_id=datasource_id,
                operation="execute_user_query.permission_scope",
                reason=str(exc),
            )
        if error_type is None and classification.error_type == DATA_UNAVAILABLE_ERROR_TYPE:
            message = user_data_unavailable_message(str(exc))
            error_type = DATA_UNAVAILABLE_ERROR_TYPE
        return _failed_query_result(message, error_type)
