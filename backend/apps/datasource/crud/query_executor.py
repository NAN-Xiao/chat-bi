"""
脚本说明：这个脚本封装数据源的增删改查和保存逻辑，让接口层不直接处理太多细节。
"""
from dataclasses import dataclass
import inspect
import re
import time
from typing import Any

from apps.datasource.crud.permission import (
    get_row_permission_filters,
    has_datasource_access,
    is_normal_user,
)
from apps.datasource.crud.permission_errors import (
    PERMISSION_DENIED_DISPLAY_MESSAGE,
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
from common.error import DataUnavailableError
from common.user_facing_errors import (
    DATA_UNAVAILABLE_ERROR_TYPE,
    data_unavailable_data_result,
    failed_data_result,
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
    text = str(message or "")
    lowered = text.lower()
    patterns = [
        r"\bundefinedtable\b",
        r"\bundefinedcolumn\b",
        r"\bno such table\b",
        r"\bno such column\b",
        r"\bunknown column\b",
        r"\binvalid column name\b",
        r"\binvalid object name\b",
        r"\brelation\s+.+\s+does not exist\b",
        r"\bcolumn\s+.+\s+does not exist\b",
        r"\btable\s+.+\s+does not exist\b",
        r"\bdoesn't exist\b",
        r"表[“\"]?[^”\"\s]+[”\"]?不存在",
        r"列[“\"]?[^”\"\s]+[”\"]?不存在",
        r"字段[“\"]?[^”\"\s]+[”\"]?不存在",
        r"无效的列名",
        r"对象名.+无效",
    ]
    return any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in patterns)


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
        if looks_like_data_unavailable_error(str(exc)):
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

    statements = parse_sql_statements(scope_sql or sql, datasource.type)
    actual_tables = extract_physical_tables(statements)
    if not actual_tables:
        raise ValueError("SQL 解析失败，无法确认查询表范围")
    _validate_allowed_tables(actual_tables, allowed_tables)

    started_at = time.perf_counter()
    result = _execute_after_validation(ds=datasource, sql=sql, origin_column=origin_column)
    execution_time_ms = int((time.perf_counter() - started_at) * 1000)
    result = _normalize_query_result(result, origin_column)
    return QueryExecutionResult(
        result=result,
        datasource=datasource,
        requested_sql=scope_sql or sql,
        executed_sql=sql,
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
        if error_type is None and looks_like_data_unavailable_error(str(exc)):
            message = user_data_unavailable_message(str(exc))
            error_type = DATA_UNAVAILABLE_ERROR_TYPE
        return _failed_query_result(message, error_type)
