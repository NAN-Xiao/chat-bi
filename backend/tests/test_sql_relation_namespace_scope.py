"""验证 SQL 限定库名不能越过当前数据源连接边界。"""

from __future__ import annotations

import json

import pytest

from apps.datasource.crud.permission_errors import SqlSchemaScopeError
from apps.datasource.crud.sql_permission import (
    parse_sql_statements,
    validate_sql_relation_namespaces,
    validate_sql_scope,
)
from apps.datasource.models.datasource import CoreDatasource


def _datasource(ds_type: str, **configuration) -> CoreDatasource:
    return CoreDatasource(
        id=10,
        tenant_id=20,
        name="test",
        type=ds_type,
        configuration=json.dumps(configuration),
        create_by=1,
        recommended_config=1,
    )


def _validate(sql: str, datasource: CoreDatasource) -> None:
    statements = parse_sql_statements(sql, datasource.type)
    validate_sql_relation_namespaces(statements, datasource)


def test_mysql_allows_unqualified_and_current_database_tables() -> None:
    datasource = _datasource("mysql", database="lds")

    _validate("SELECT * FROM event", datasource)
    _validate("SELECT * FROM lds.event", datasource)


def test_mysql_rejects_table_from_another_database() -> None:
    datasource = _datasource("mysql", database="lds")

    with pytest.raises(SqlSchemaScopeError, match="first_zombie.event") as exc_info:
        _validate("SELECT * FROM first_zombie.event", datasource)

    assert exc_info.value.tables == ("first_zombie.event",)


def test_postgres_allows_current_schema_and_rejects_other_schema() -> None:
    datasource = _datasource("postgresql", database="analytics", dbSchema="public")

    _validate("SELECT * FROM public.orders", datasource)
    with pytest.raises(SqlSchemaScopeError, match="private.orders"):
        _validate("SELECT * FROM private.orders", datasource)


def test_sqlserver_validates_catalog_and_schema() -> None:
    datasource = _datasource("sqlserver", database="analytics", dbSchema="dbo")

    _validate("SELECT * FROM analytics.dbo.orders", datasource)
    with pytest.raises(SqlSchemaScopeError, match="legacy.dbo.orders"):
        _validate("SELECT * FROM legacy.dbo.orders", datasource)


def test_qualified_cte_name_does_not_hide_physical_table_reference() -> None:
    datasource = _datasource("mysql", database="gig")

    with pytest.raises(SqlSchemaScopeError, match="xtxdj.orders"):
        _validate(
            "WITH daily AS (SELECT id FROM xtxdj.orders) SELECT * FROM daily",
            datasource,
        )


def test_qualified_table_fails_closed_when_connection_database_is_missing() -> None:
    datasource = _datasource("mysql")

    with pytest.raises(SqlSchemaScopeError, match="gig.orders"):
        _validate("SELECT * FROM gig.orders", datasource)


def test_validate_sql_scope_rejects_foreign_database_before_permission_queries() -> None:
    class UnexpectedSession:
        def query(self, *_args, **_kwargs):
            raise AssertionError("跨库 SQL 不应进入权限查询")

    datasource = _datasource("mysql", database="lds")

    with pytest.raises(SqlSchemaScopeError, match="first_zombie.orders"):
        validate_sql_scope(
            UnexpectedSession(),
            object(),
            datasource,
            "SELECT * FROM first_zombie.orders",
        )
