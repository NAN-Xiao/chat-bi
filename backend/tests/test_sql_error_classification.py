"""SQL 执行异常不能因查询文本或字段名称被误报为权限不足。"""
from types import SimpleNamespace

import pytest
from pymysql.err import OperationalError as MysqlError
from sqlalchemy.exc import OperationalError

from common.user_facing_errors import (
    DATA_UNAVAILABLE_ERROR_TYPE,
    PERMISSION_DENIED_ERROR_TYPE,
    classify_error,
)


def _semantic_error(sql="SELECT * FROM touch_results"):
    return OperationalError(sql, {}, MysqlError(1815, "[9001] SemanticError\x00"))


@pytest.mark.parametrize("sql", [
    "SELECT * FROM touch_results UNION ALL SELECT * FROM direct_conversions",
    "SELECT permission, permission_scope FROM allowed_tables",
    "SELECT '没有查看权限', 'access denied', 'unknown column', '42501', '[1142]'",
])
@pytest.mark.parametrize("as_text", [False, True])
def test_sqlalchemy_query_echo_is_not_a_permission_or_schema_diagnostic(sql, as_text):
    error = _semantic_error(sql)
    if as_text:
        error = str(error)
    result = classify_error(error)
    assert result.error_type is None
    assert result.source == "unknown"
    assert "SemanticError" in result.message


@pytest.mark.parametrize("message", [
    "SemanticError: SELECT * is not supported",
    "SQL 解析失败，无法确认查询表范围",
    "字段权限配置格式无效",
    "timeout while loading permission_scope from allowed tables",
    "syntax error\nLINE 1: SELECT 'permission denied', '42P01', '[1142]'",
    "syntax error\nQUERY: SELECT '没有查看权限'",
    "syntax error\nSTATEMENT: SELECT 'unknown column'",
    "syntax error\n[parameters: {'value': 'access denied'}]",
])
def test_non_denial_diagnostics_are_not_permission_errors(message):
    assert classify_error(ValueError(message)).error_type is None


@pytest.mark.parametrize("message", [
    "SQL 包含无权限表：orders",
    "SQL 包含无权限字段：amount",
    "SQL 使用了 SELECT *，无法安全应用字段权限；请显式选择授权字段",
    "SQL 可能读取行权限禁止的数据",
    "没有访问该数据源的权限",
    "当前用户的权限不足",
    "permission denied for table orders",
    "SELECT command denied to user 'reader' for table 'orders'",
    "Access denied for user 'reader'",
    "insufficient privileges",
    "unauthorized table orders",
])
def test_explicit_denial_text_remains_a_permission_error(message):
    assert classify_error(message).error_type == PERMISSION_DENIED_ERROR_TYPE


@pytest.mark.parametrize("message", [
    "Unknown column 'permission' in 'field list'",
    "no such table: permission_scope",
    "relation \"allowed tables\" does not exist",
])
def test_permission_named_missing_resources_are_schema_errors(message):
    assert classify_error(message).error_type == DATA_UNAVAILABLE_ERROR_TYPE


@pytest.mark.parametrize("errno,expected", [
    (1142, PERMISSION_DENIED_ERROR_TYPE),
    (1054, DATA_UNAVAILABLE_ERROR_TYPE),
    (1146, DATA_UNAVAILABLE_ERROR_TYPE),
])
def test_wrapped_driver_codes_take_priority_over_sql_payload(errno, expected):
    error = OperationalError("SELECT * FROM permission_scope", {}, MysqlError(errno, "localized"))
    wrapper = ValueError(str(error))
    wrapper.__cause__ = error
    result = classify_error(wrapper)
    assert result.error_type == expected
    assert result.source == "errno"


def test_typed_permission_denial_does_not_depend_on_wording():
    from apps.datasource.crud.permission_errors import SqlPermissionScopeError

    error = SqlPermissionScopeError("禁止读取所选列", fields=["amount"])
    result = classify_error(error)
    assert result.error_type == PERMISSION_DENIED_ERROR_TYPE
    assert result.source == "explicit"


@pytest.mark.parametrize("permission_error", [True, False])
def test_dashboard_preflight_retains_structured_error(monkeypatch, permission_error):
    from apps.dashboard.crud import dashboard_service as dashboard
    from apps.datasource.crud import sql_engine_executor as executor
    from apps.datasource.crud.permission_errors import SqlPermissionScopeError

    error = SqlPermissionScopeError("禁止读取所选列") if permission_error else _semantic_error()

    def fail(**kwargs):
        raise error

    monkeypatch.setattr(dashboard, "_configured_chart_execution_datasources", lambda *args: [(1, "bound")])
    monkeypatch.setattr(dashboard, "validate_user_query_sql_or_raise", fail)
    monkeypatch.setattr(executor, "is_normal_user", lambda *args: True)
    session = SimpleNamespace(get=lambda *args: SimpleNamespace(id=1))
    result, cacheable = dashboard._dashboard_chart_permission_audit(
        session, SimpleNamespace(id=1), 1, "SELECT * FROM orders"
    )
    assert result["status"] == "failed"
    assert result.get("error_type") == (PERMISSION_DENIED_ERROR_TYPE if permission_error else None)
    assert (result["message"] == "没有查看权限") == permission_error
    assert cacheable is False


@pytest.mark.parametrize("is_normal", [True, False])
@pytest.mark.parametrize("case,expected", [
    ("semantic", None),
    ("permission", PERMISSION_DENIED_ERROR_TYPE),
    ("missing_column", DATA_UNAVAILABLE_ERROR_TYPE),
    ("typed_permission", PERMISSION_DENIED_ERROR_TYPE),
])
def test_shared_executor_preserves_error_category_and_audits_only_denials(monkeypatch, is_normal, case, expected):
    from apps.datasource.crud import sql_engine_executor as executor
    from apps.datasource.crud.permission_errors import SqlPermissionScopeError

    errors = {
        "semantic": _semantic_error(),
        "permission": OperationalError("SELECT * FROM orders", {}, MysqlError(1142, "localized")),
        # The misleading text must not override a structured missing-column code.
        "missing_column": OperationalError("SELECT * FROM orders", {}, MysqlError(1054, "permission denied")),
        "typed_permission": SqlPermissionScopeError("禁止读取所选列", fields=["amount"]),
    }
    def fail(*args, **kwargs):
        raise errors[case]

    audits = []
    monkeypatch.setattr(executor, "execute_user_query_or_raise", fail)
    monkeypatch.setattr(executor, "has_datasource_access", lambda *args: True)
    monkeypatch.setattr(executor, "is_normal_user", lambda *args: is_normal)
    monkeypatch.setattr(executor, "audit_permission_denied", lambda **kwargs: audits.append(kwargs))
    session = SimpleNamespace(get=lambda *args: SimpleNamespace(id=1))
    result = executor.execute_user_query(session, SimpleNamespace(id=1), 1, "SELECT * FROM orders")

    assert result["status"] == "failed"
    assert result.get("error_type") == expected
    assert result["data"] == []
    assert len(audits) == (1 if expected == PERMISSION_DENIED_ERROR_TYPE else 0)
    if case == "semantic":
        assert "SemanticError" in result["message"]
        assert result["message"] != "没有查看权限"
    if expected == PERMISSION_DENIED_ERROR_TYPE and is_normal:
        assert result["message"] == "没有查看权限"

    # 看板预览使用同一个结果契约，不得在展示阶段再次误报权限。
    from apps.dashboard.crud.dashboard_service import _normalize_dashboard_chart_result

    displayed = _normalize_dashboard_chart_result(result)
    assert (displayed["message"] == "没有查看权限") == (expected == PERMISSION_DENIED_ERROR_TYPE)
