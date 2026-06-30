"""
脚本说明：这个脚本封装数据源的增删改查和保存逻辑，让接口层不直接处理太多细节。
"""
from dataclasses import dataclass
from typing import Any

from apps.datasource.crud.permission import (
    get_row_permission_filters,
    has_datasource_access,
    is_normal_user,
)
from apps.datasource.crud.permission_errors import (
    PERMISSION_DENIED_ERROR_TYPE,
    looks_like_permission_scope_error,
)
from apps.datasource.crud.sql_permission import (
    apply_row_permission_filters,
    extract_physical_tables,
    parse_sql_statements,
    validate_sql_scope,
    validate_sql_table_scope,
)
from apps.datasource.models.datasource import CoreDatasource
from apps.db.db import check_sql_read, _unsafe_exec_sql_after_validation
from apps.system.schemas.system_schema import AssistantOutDsSchema
from common.core.deps import CurrentUser, SessionDep
from common.utils.data_format import DataFormat
from common.utils.utils import AppLogUtil


USER_QUERY_PERMISSION_DENIED_MESSAGE = "SQL 超出当前数据权限范围"


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


def _failed_query_result(message: str, error_type: str | None = None) -> dict[str, Any]:
    """
    是什么：_failed_query_result 是一个可以复用的小步骤，负责数据源相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把数据源里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    result: dict[str, Any] = {
        "status": "failed",
        "fields": [],
        "data": [],
        "message": message,
    }
    if error_type:
        result["error_type"] = error_type
        result["reason"] = message
    return result


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
    result = _unsafe_exec_sql_after_validation(ds=datasource, sql=executed_sql, origin_column=origin_column)
    result = _normalize_query_result(result, origin_column)
    return QueryExecutionResult(
        result=result,
        datasource=datasource,
        requested_sql=sql,
        executed_sql=executed_sql,
        tables=tables,
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

    statements = parse_sql_statements(scope_sql or sql, datasource.type)
    actual_tables = extract_physical_tables(statements)
    if not actual_tables:
        raise ValueError("SQL 解析失败，无法确认查询表范围")
    _validate_allowed_tables(actual_tables, allowed_tables)

    result = _unsafe_exec_sql_after_validation(ds=datasource, sql=sql, origin_column=origin_column)
    result = _normalize_query_result(result, origin_column)
    return QueryExecutionResult(
        result=result,
        datasource=datasource,
        requested_sql=scope_sql or sql,
        executed_sql=sql,
        tables=actual_tables,
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
        )
        return {
            "status": "success",
            "fields": query_result.result.get("fields", []),
            "data": query_result.result.get("data", []),
            "message": "",
            "sql": query_result.result.get("sql"),
        }
    except Exception as exc:
        AppLogUtil.error(f"User query execution failed: {exc}")
        message = safe_query_error_message(current_user, f"{exc}")
        return _failed_query_result(message, safe_query_error_type(current_user, f"{exc}"))
