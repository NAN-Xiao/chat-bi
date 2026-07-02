from types import SimpleNamespace

import pytest

from apps.datasource.crud import query_executor


def _user():
    return SimpleNamespace(id=2, system_role="viewer", tenant_id=1, tenant_role="member")


def _datasource():
    return SimpleNamespace(id=1, type="pg")


class _SessionWithDatasource:
    def get(self, _model, _obj_id):
        return _datasource()


def _external_datasource(*, rule=None):
    return SimpleNamespace(
        id=99,
        type="pg",
        tables=[
            SimpleNamespace(
                name="orders",
                rule=rule,
                fields=[
                    SimpleNamespace(name="id"),
                    SimpleNamespace(name="region"),
                    SimpleNamespace(name="amount"),
                ],
            )
        ],
    )


def test_prepare_query_sql_applies_row_permissions(monkeypatch):
    monkeypatch.setattr(query_executor, "has_datasource_access", lambda *args, **kwargs: True)
    monkeypatch.setattr(query_executor, "check_sql_read", lambda sql, ds: (True, ""))
    monkeypatch.setattr(query_executor, "is_normal_user", lambda current_user: True)
    monkeypatch.setattr(
        query_executor,
        "validate_sql_scope",
        lambda *args, **kwargs: ([], {"orders"}, {}),
    )
    monkeypatch.setattr(
        query_executor,
        "get_row_permission_filters",
        lambda *args, **kwargs: [{"table": "orders", "filter": "region = 'US'"}],
    )
    monkeypatch.setattr(
        query_executor,
        "apply_row_permission_filters",
        lambda sql, ds, filters: "select * from (select * from orders where region = 'US') orders",
    )
    monkeypatch.setattr(
        query_executor,
        "validate_sql_table_scope",
        lambda *args, **kwargs: {"orders"},
    )

    sql, tables = query_executor.prepare_query_sql(
        session=object(),
        current_user=_user(),
        datasource=_datasource(),
        sql="select id from orders",
        allowed_tables=["orders"],
    )

    assert "region = 'US'" in sql
    assert tables == {"orders"}


def test_execute_user_query_audits_datasource_permission_denied(monkeypatch):
    captured = {}
    monkeypatch.setattr(query_executor, "has_datasource_access", lambda *args, **kwargs: False)
    monkeypatch.setattr(query_executor, "is_normal_user", lambda current_user: True)
    monkeypatch.setattr(
        query_executor,
        "audit_permission_denied",
        lambda **kwargs: captured.update(kwargs),
    )

    result = query_executor.execute_user_query(
        session=_SessionWithDatasource(),
        current_user=_user(),
        datasource_id=1,
        sql="select id from orders",
    )

    assert captured["operation"] == "execute_user_query.datasource_access"
    assert captured["current_user"].id == 2
    assert captured["datasource_id"] == 1
    assert result["status"] == "failed"
    assert result["error_type"] == "permission_denied"


def test_prepare_query_sql_rejects_write_sql(monkeypatch):
    monkeypatch.setattr(
        query_executor,
        "check_sql_read",
        lambda sql, ds: (False, "Write operation 'DELETE' is not allowed"),
    )

    with pytest.raises(ValueError, match="SQL can only contain read operations"):
        query_executor.prepare_query_sql(
            session=object(),
            current_user=_user(),
            datasource=_datasource(),
            sql="delete from orders",
        )


def test_execute_prepared_query_skips_second_row_rewrite(monkeypatch):
    calls = {"row_filters": 0}
    monkeypatch.setattr(query_executor, "has_datasource_access", lambda *args, **kwargs: True)
    monkeypatch.setattr(query_executor, "check_sql_read", lambda sql, ds: (True, ""))
    monkeypatch.setattr(query_executor, "validate_sql_table_scope", lambda *args, **kwargs: {"orders"})

    def row_filters(*args, **kwargs):
        calls["row_filters"] += 1
        return [{"table": "orders", "filter": "region = 'US'"}]

    monkeypatch.setattr(query_executor, "get_row_permission_filters", row_filters)
    monkeypatch.setattr(
        query_executor,
        "_unsafe_exec_sql_after_validation",
        lambda ds, sql, origin_column=False: {"fields": ["id"], "data": [{"id": 1}], "sql": "encoded"},
    )

    result = query_executor.execute_user_query_or_raise(
        session=object(),
        current_user=_user(),
        datasource=_datasource(),
        sql="select * from (select * from orders where region = 'US') orders",
        apply_row_permissions=False,
        validate_columns=False,
    )

    assert calls["row_filters"] == 0
    assert result.result["data"] == [{"id": 1}]


def test_execute_user_analysis_query_always_applies_row_permissions(monkeypatch):
    calls = {"row_filters": 0}
    monkeypatch.setattr(query_executor, "has_datasource_access", lambda *args, **kwargs: True)
    monkeypatch.setattr(query_executor, "check_sql_read", lambda sql, ds: (True, ""))
    monkeypatch.setattr(query_executor, "is_normal_user", lambda current_user: True)
    monkeypatch.setattr(
        query_executor,
        "validate_sql_scope",
        lambda *args, **kwargs: ([], {"orders"}, {}),
    )
    monkeypatch.setattr(query_executor, "validate_sql_table_scope", lambda *args, **kwargs: {"orders"})

    def row_filters(*args, **kwargs):
        calls["row_filters"] += 1
        return [{"table": "orders", "filter": "region = 'US'"}]

    monkeypatch.setattr(query_executor, "get_row_permission_filters", row_filters)
    monkeypatch.setattr(
        query_executor,
        "apply_row_permission_filters",
        lambda sql, ds, filters: "select id from orders where region = 'US'",
    )
    monkeypatch.setattr(
        query_executor,
        "_unsafe_exec_sql_after_validation",
        lambda ds, sql, origin_column=False: {"fields": ["id"], "data": [{"id": 1, "sql": sql}], "sql": "encoded"},
    )

    result = query_executor.execute_user_analysis_query_or_raise(
        session=object(),
        current_user=_user(),
        datasource=_datasource(),
        sql="select id from orders",
        allowed_tables=["orders"],
    )

    assert calls["row_filters"] == 1
    assert "region = 'US'" in result.executed_sql
    assert result.result["data"][0]["sql"] == "select id from orders where region = 'US'"


def test_validate_user_query_sql_does_not_apply_row_permissions(monkeypatch):
    calls = {"row_filters": 0}
    monkeypatch.setattr(query_executor, "has_datasource_access", lambda *args, **kwargs: True)
    monkeypatch.setattr(query_executor, "check_sql_read", lambda sql, ds: (True, ""))
    monkeypatch.setattr(
        query_executor,
        "validate_sql_scope",
        lambda *args, **kwargs: ([], {"orders"}, {}),
    )

    def row_filters(*args, **kwargs):
        calls["row_filters"] += 1
        return [{"table": "orders", "filter": "region = 'US'"}]

    monkeypatch.setattr(query_executor, "get_row_permission_filters", row_filters)

    sql, tables = query_executor.validate_user_query_sql_or_raise(
        session=object(),
        current_user=_user(),
        datasource=_datasource(),
        sql="select id from orders",
        allowed_tables=["orders"],
    )

    assert calls["row_filters"] == 0
    assert sql == "select id from orders"
    assert tables == {"orders"}


def test_external_user_query_uses_scope_sql_for_allowed_table_checks(monkeypatch):
    datasource = _external_datasource(rule="region = 'US'")
    captured = {}
    monkeypatch.setattr(query_executor, "check_sql_read", lambda sql, ds: (True, ""))

    def fake_low_level_exec(ds, sql, origin_column=False):
        captured["sql"] = sql
        return {"fields": ["id"], "data": [{"id": 1}], "sql": "encoded"}

    monkeypatch.setattr(
        query_executor,
        "_unsafe_exec_sql_after_validation",
        fake_low_level_exec,
    )

    execution_sql = query_executor.wrap_external_subquery_with_table_rule(
        datasource,
        "orders",
        "select id, region from private_orders",
    )

    result = query_executor.execute_external_user_query_or_raise(
        datasource=datasource,
        sql=f"select id from ({execution_sql}) app_dynamic_temp_table_orders",
        scope_sql="select id from app_dynamic_temp_table_orders",
        allowed_tables=["app_dynamic_temp_table_orders"],
    )

    assert "region = 'US'" in captured["sql"]
    assert result.tables == {"app_dynamic_temp_table_orders"}


def test_external_user_query_rejects_unscoped_logic_table(monkeypatch):
    datasource = _external_datasource()
    monkeypatch.setattr(query_executor, "check_sql_read", lambda sql, ds: (True, ""))

    with pytest.raises(ValueError, match="SQL 包含无权限表"):
        query_executor.execute_external_user_query_or_raise(
            datasource=datasource,
            sql="select id from (select id from private_orders) app_dynamic_temp_table_orders",
            scope_sql="select id from app_dynamic_temp_table_orders join hidden_table on 1=1",
            allowed_tables=["app_dynamic_temp_table_orders"],
        )


def test_external_user_query_wraps_dynamic_subquery_with_row_rule(monkeypatch):
    captured = {}
    monkeypatch.setattr(query_executor, "check_sql_read", lambda sql, ds: (True, ""))

    def fake_low_level_exec(ds, sql, origin_column=False):
        captured["sql"] = sql
        return {"fields": ["id"], "data": [{"id": 1}], "sql": "encoded"}

    monkeypatch.setattr(query_executor, "_unsafe_exec_sql_after_validation", fake_low_level_exec)

    query_executor.execute_external_user_query_or_raise(
        datasource=_external_datasource(rule="region = 'US'"),
        sql="select id from (select id, region from private_orders) app_dynamic_temp_table_orders",
        scope_sql="select id from app_dynamic_temp_table_orders",
        allowed_tables=["app_dynamic_temp_table_orders"],
    )

    assert "region = 'US'" in captured["sql"]
    assert "private_orders" in captured["sql"]


def test_external_user_query_rejects_denied_column(monkeypatch):
    monkeypatch.setattr(query_executor, "check_sql_read", lambda sql, ds: (True, ""))

    with pytest.raises(ValueError, match="SQL 包含无权限字段"):
        query_executor.execute_external_user_query_or_raise(
            datasource=_external_datasource(),
            sql="select secret from orders",
            allowed_tables=["orders"],
        )


def test_external_user_query_rejects_star_when_fields_are_scoped(monkeypatch):
    monkeypatch.setattr(query_executor, "check_sql_read", lambda sql, ds: (True, ""))

    with pytest.raises(ValueError, match=r"SELECT \*"):
        query_executor.execute_external_user_query_or_raise(
            datasource=_external_datasource(),
            sql="select * from orders",
            allowed_tables=["orders"],
        )


def test_external_user_query_applies_configured_row_rule(monkeypatch):
    captured = {}
    monkeypatch.setattr(query_executor, "check_sql_read", lambda sql, ds: (True, ""))

    def fake_low_level_exec(ds, sql, origin_column=False):
        captured["sql"] = sql
        return {"fields": ["id"], "data": [{"id": 1}], "sql": "encoded"}

    monkeypatch.setattr(query_executor, "_unsafe_exec_sql_after_validation", fake_low_level_exec)

    result = query_executor.execute_external_user_query_or_raise(
        datasource=_external_datasource(rule="region = 'US'"),
        sql="select id from orders",
        allowed_tables=["orders"],
    )

    assert "region = 'US'" in captured["sql"]
    assert "region = 'US'" in result.executed_sql


def test_external_dynamic_subquery_is_wrapped_with_table_rule():
    wrapped = query_executor.wrap_external_subquery_with_table_rule(
        _external_datasource(rule="orders.region = 'US'"),
        "orders",
        "select id, region from private_orders",
    )

    assert wrapped == (
        "SELECT * FROM (SELECT * FROM (select id, region from private_orders) "
        "orders WHERE orders.region = 'US') app_dynamic_temp_table_orders"
    )
