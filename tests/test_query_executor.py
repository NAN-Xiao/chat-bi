from types import SimpleNamespace

import pytest

from apps.datasource.crud import query_executor


def _user():
    return SimpleNamespace(id=2, system_role="viewer", tenant_id=1, tenant_role="member")


def _datasource():
    return SimpleNamespace(id=1, type="pg")


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
        "exec_sql",
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
