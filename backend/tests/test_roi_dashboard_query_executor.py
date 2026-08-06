"""ROI 独立只读查询执行边界测试。"""

import ast
import inspect
import json
import logging
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import Session, create_engine

from apps.datasource.crud.sql_engine_executor import validate_user_query_sql_or_raise
from apps.roi_dashboard import query_executor
from apps.roi_dashboard.models import CoreRoiWorkspaceConfig
from apps.roi_dashboard.query_executor import execute_roi_read_query, render_roi_sql_date_range


def make_user(
    *,
    id: int = 7,
    tenant_id: int = 11,
    tenant_role: str = "admin",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id,
        tenant_id=tenant_id,
        tenant_role=tenant_role,
        system_role="viewer",
        isAdmin=False,
        workspace_status="active",
    )


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE core_roi_workspace_config ("
                "id BIGINT PRIMARY KEY, tenant_id BIGINT NOT NULL, datasource_id BIGINT NOT NULL, "
                "version INTEGER NOT NULL, create_by BIGINT, update_by BIGINT, "
                "create_time BIGINT NOT NULL, update_time BIGINT NOT NULL, deleted BOOLEAN NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE core_table ("
                "id BIGINT PRIMARY KEY, ds_id BIGINT, checked BOOLEAN, "
                "table_name TEXT, table_comment TEXT, custom_comment TEXT, embedding TEXT, "
                "catalog_name TEXT, schema_name TEXT, catalog_key TEXT, schema_key TEXT, table_key TEXT)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE core_field ("
                "id BIGINT PRIMARY KEY, ds_id BIGINT, table_id BIGINT, checked BOOLEAN, "
                "field_name TEXT, field_type TEXT, field_comment TEXT, custom_comment TEXT, "
                "field_index BIGINT, field_key TEXT)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE ds_permission ("
                "id BIGINT PRIMARY KEY, name TEXT, enable BOOLEAN, auth_target_type TEXT, "
                "auth_target_id BIGINT, type TEXT, ds_id BIGINT, table_id BIGINT, "
                "expression_tree TEXT, permissions TEXT, white_list_user TEXT, create_time DATETIME)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE ds_rules ("
                "id INTEGER PRIMARY KEY, enable BOOLEAN, name TEXT, description TEXT, "
                "tenant_id BIGINT, scope TEXT, permission_list TEXT, user_list TEXT, "
                "white_list_user TEXT, create_time DATETIME)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO core_table "
                "(id, ds_id, checked, table_name, table_comment, custom_comment) VALUES "
                "(2001, 202, 1, 'private_table', '', ''), "
                "(2002, 202, 1, 'orders', '', ''), "
                "(2003, 202, 1, 'archived_orders', '', ''), "
                "(2004, 202, 1, 'payments', '', ''), "
                "(2005, 202, 1, 'large_table', '', '')"
            )
        )
    with Session(engine) as db_session:
        yield db_session


def seed_roi_config(
    session: Session,
    *,
    tenant_id: int = 11,
    datasource_id: int = 202,
) -> None:
    session.add(
        CoreRoiWorkspaceConfig(
            id=1000 + tenant_id,
            tenant_id=tenant_id,
            datasource_id=datasource_id,
            version=1,
            create_by=1,
            update_by=1,
            create_time=100,
            update_time=100,
            deleted=False,
        )
    )
    session.commit()


def _prepare_authorized_query(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    *,
    datasource_type: str = "pg",
) -> SimpleNamespace:
    datasource = SimpleNamespace(id=202, type=datasource_type, configuration="{}")
    seed_roi_config(session)
    monkeypatch.setattr(query_executor, "has_roi_datasource_access", lambda *_args: True)
    monkeypatch.setattr(session, "get", lambda _model, datasource_id: datasource if datasource_id == 202 else None)
    return datasource


def seed_permission_rule(
    session: Session,
    *,
    permission_id: int,
    permission_type: str,
    table_id: int,
    user_id: int,
    white_list_user: list[str] | None = None,
) -> None:
    session.exec(
        text(
            "INSERT INTO ds_permission "
            "(id, name, enable, type, ds_id, table_id, permissions, white_list_user) "
            "VALUES (:id, '测试规则', 1, :type, 202, :table_id, '[]', :white_list_user)"
        ),
        params={
            "id": permission_id,
            "type": permission_type,
            "table_id": table_id,
            "white_list_user": json.dumps(white_list_user or []),
        },
    )
    session.exec(
        text(
            "INSERT INTO ds_rules "
            "(id, enable, name, tenant_id, scope, permission_list, user_list, white_list_user) "
            "VALUES (:id, 1, 'ROI 规则组', 11, 'TENANT', :permissions, :users, '[]')"
        ),
        params={
            "id": permission_id,
            "permissions": json.dumps([permission_id]),
            "users": json.dumps([str(user_id)]),
        },
    )
    session.commit()


def test_query_executor_uses_current_workspace_roi_datasource(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    seed_roi_config(session, tenant_id=11, datasource_id=202)
    seed_roi_config(session, tenant_id=22, datasource_id=303)
    datasources = {
        202: SimpleNamespace(id=202, type="pg", configuration="{}"),
        303: SimpleNamespace(id=303, type="pg", configuration="{}"),
    }
    selected: list[int] = []
    monkeypatch.setattr(query_executor, "has_roi_datasource_access", lambda *_args: True)
    monkeypatch.setattr(
        session,
        "get",
        lambda _model, datasource_id: datasources[datasource_id],
    )

    def run_validated_read(*, datasource, **_kwargs):
        selected.append(int(datasource.id))
        return {"columns": ["value"], "data": [[datasource.id]]}

    monkeypatch.setattr(query_executor, "_run_validated_read", run_validated_read)

    result_a = execute_roi_read_query(session, make_user(tenant_id=11), "SELECT 1")
    result_b = execute_roi_read_query(session, make_user(tenant_id=22), "SELECT 1")

    assert selected == [202, 303]
    assert result_a.data == [{"value": 202}]
    assert result_b.data == [{"value": 303}]


def test_roi_query_applies_table_rules_to_selected_workspace_admin(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    seed_permission_rule(
        session,
        permission_id=9001,
        permission_type="table",
        table_id=2001,
        user_id=7,
    )
    _prepare_authorized_query(monkeypatch, session)
    monkeypatch.setattr(
        query_executor,
        "_run_validated_read",
        lambda **_kwargs: pytest.fail("禁止表 SQL 不应到达数据库"),
    )

    with pytest.raises(HTTPException) as exc:
        execute_roi_read_query(
            session,
            make_user(id=7, tenant_role="admin"),
            "SELECT secret FROM private_table",
        )

    assert exc.value.status_code == 403
    assert "ROI SQL 包含禁止访问的数据表" in exc.value.detail


def test_prevalidated_dashboard_roi_datasource_still_enforces_table_rule(
    session: Session,
) -> None:
    """普通看板预授权 ROI 数据源后，仍必须执行当前用户的表禁止规则。"""
    seed_permission_rule(
        session,
        permission_id=9004,
        permission_type="table",
        table_id=2001,
        user_id=7,
    )
    datasource = SimpleNamespace(id=202, type="pg", configuration="{}")

    with pytest.raises(ValueError, match="private_table"):
        validate_user_query_sql_or_raise(
            session,
            make_user(id=7, tenant_role="member"),
            datasource,
            "SELECT secret FROM private_table",
            datasource_access_checked=True,
            row_permission_policy="deny_on_overlap",
        )


def test_roi_query_ignores_column_and_row_rules(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    seed_permission_rule(
        session,
        permission_id=9002,
        permission_type="column",
        table_id=2002,
        user_id=7,
    )
    seed_permission_rule(
        session,
        permission_id=9003,
        permission_type="row",
        table_id=2002,
        user_id=7,
    )
    _prepare_authorized_query(monkeypatch, session)
    calls = []
    monkeypatch.setattr(
        query_executor,
        "_run_validated_read",
        lambda **kwargs: calls.append(kwargs)
        or {"fields": ["secret"], "data": [{"secret": 1}]},
    )

    result = execute_roi_read_query(session, make_user(), "SELECT secret FROM orders")

    assert result.status == "success"
    assert result.data == [{"secret": 1}]
    assert calls[0]["sql"] == "SELECT secret FROM orders"


def test_roi_query_allows_user_not_selected_by_table_rule(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    seed_permission_rule(
        session,
        permission_id=9004,
        permission_type="table",
        table_id=2001,
        user_id=8,
    )
    _prepare_authorized_query(monkeypatch, session)
    monkeypatch.setattr(
        query_executor,
        "_run_validated_read",
        lambda **_kwargs: {"fields": ["secret"], "data": [{"secret": 1}]},
    )

    result = execute_roi_read_query(session, make_user(id=7), "SELECT secret FROM private_table")

    assert result.status == "success"


def test_roi_query_allows_permission_white_listed_user(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    seed_permission_rule(
        session,
        permission_id=9005,
        permission_type="table",
        table_id=2001,
        user_id=7,
        white_list_user=["7"],
    )
    _prepare_authorized_query(monkeypatch, session)
    monkeypatch.setattr(
        query_executor,
        "_run_validated_read",
        lambda **_kwargs: {"fields": ["secret"], "data": [{"secret": 1}]},
    )

    result = execute_roi_read_query(session, make_user(id=7), "SELECT secret FROM private_table")

    assert result.status == "success"


def test_roi_query_rejects_when_any_joined_table_is_denied(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    seed_permission_rule(
        session,
        permission_id=9006,
        permission_type="table",
        table_id=2001,
        user_id=7,
    )
    _prepare_authorized_query(monkeypatch, session)
    monkeypatch.setattr(
        query_executor,
        "_run_validated_read",
        lambda **_kwargs: pytest.fail("多表命中禁止表时不应执行数据库"),
    )

    with pytest.raises(HTTPException) as exc:
        execute_roi_read_query(
            session,
            make_user(id=7),
            "SELECT orders.id FROM orders JOIN private_table ON private_table.id = orders.id",
        )

    assert exc.value.status_code == 403


def test_roi_query_does_not_treat_cte_name_as_denied_physical_table(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    seed_permission_rule(
        session,
        permission_id=9007,
        permission_type="table",
        table_id=2001,
        user_id=7,
    )
    _prepare_authorized_query(monkeypatch, session)
    monkeypatch.setattr(
        query_executor,
        "_run_validated_read",
        lambda **_kwargs: {"fields": ["id"], "data": [{"id": 1}]},
    )

    result = execute_roi_read_query(
        session,
        make_user(id=7),
        "WITH private_table AS (SELECT id FROM orders) SELECT id FROM private_table",
    )

    assert result.status == "success"


def test_roi_query_fails_closed_for_unregistered_physical_table(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    _prepare_authorized_query(monkeypatch, session)
    monkeypatch.setattr(
        query_executor,
        "_run_validated_read",
        lambda **_kwargs: pytest.fail("未登记表不应到达数据库"),
    )

    with pytest.raises(HTTPException) as exc:
        execute_roi_read_query(session, make_user(id=7), "SELECT * FROM missing_table")

    assert exc.value.status_code == 403
    assert "missing_table" in exc.value.detail


def test_roi_query_rejects_write_sql(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    _prepare_authorized_query(monkeypatch, session)

    with pytest.raises(HTTPException) as exc:
        execute_roi_read_query(session, make_user(), "delete from orders")

    assert exc.value.status_code == 400
    assert "仅允许单条只读查询" in exc.value.detail


def test_roi_query_passes_timeout_and_original_sql_without_limit(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    _prepare_authorized_query(monkeypatch, session)
    captured: dict[str, object] = {}
    rows = [[index] for index in range(1005)]

    def run_validated_read(**kwargs):
        captured.update(kwargs)
        return {"columns": ["value"], "data": rows}

    monkeypatch.setattr(query_executor, "_run_validated_read", run_validated_read)
    sql = "SELECT value FROM large_table"

    result = execute_roi_read_query(session, make_user(), sql)

    assert captured["sql"] == sql
    assert captured["query_timeout"] == query_executor.settings.DASHBOARD_SQL_PREVIEW_QUERY_TIMEOUT_SECONDS
    assert captured["max_result_rows"] is None
    assert len(result.data) == 1005
    assert result.data[-1] == {"value": 1004}


def test_roi_query_does_not_call_normal_user_query_entrypoints(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    _prepare_authorized_query(monkeypatch, session)

    monkeypatch.setattr(
        query_executor,
        "_run_validated_read",
        lambda **_kwargs: {"status": "success", "data": [{"value": 1}]},
    )

    result = execute_roi_read_query(session, make_user(), "SELECT 1 AS value")

    assert result.status == "success"
    assert result.data == [{"value": 1}]


def test_query_executor_contains_no_ordinary_permission_calls() -> None:
    forbidden = {
        "execute_user_query",
        "validate_user_query_sql_or_raise",
        "validate_sql_scope",
        "get_row_permission_filters",
    }
    tree = ast.parse(inspect.getsource(query_executor))
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert called_names.isdisjoint(forbidden)


@pytest.mark.parametrize(
    "sql",
    [
        "WITH changed AS (DELETE FROM orders RETURNING id) SELECT * FROM changed",
        "WITH changed AS (UPDATE orders SET amount = 0 RETURNING id) SELECT * FROM changed",
        "SELECT * INTO orders_backup FROM orders",
        "CALL refresh_orders()",
        "SELECT 1; SELECT 2",
        "SELECT * FROM",
        (
            "WITH source AS ("
            "SELECT DATE_ADD(dt, period) AS cohort_day FROM orders"
            ") DELETE FROM archived_orders"
        ),
    ],
)
def test_roi_query_fail_closed_for_unsafe_or_malformed_sql(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    sql: str,
) -> None:
    _prepare_authorized_query(monkeypatch, session)
    monkeypatch.setattr(
        query_executor,
        "_run_validated_read",
        lambda **_kwargs: pytest.fail("不安全 SQL 不应到达执行层"),
    )

    with pytest.raises(HTTPException) as exc:
        execute_roi_read_query(session, make_user(), sql)

    assert exc.value.status_code == 400


def test_roi_query_allows_cte_union_aggregate_and_known_builtin(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    _prepare_authorized_query(monkeypatch, session)
    monkeypatch.setattr(
        query_executor,
        "_run_validated_read",
        lambda **_kwargs: {
            "fields": ["category", "total"],
            "data": [{"category": "all", "total": 3}],
        },
    )
    sql = """
        WITH source AS (
            SELECT category, amount FROM orders
            UNION ALL
            SELECT category, amount FROM archived_orders
        )
        SELECT COALESCE(category, 'all') AS category, SUM(amount) AS total
        FROM source
        GROUP BY category
    """

    result = execute_roi_read_query(session, make_user(), sql)

    assert result.status == "success"
    assert result.data == [{"category": "all", "total": 3}]


def test_roi_query_executes_mysql_native_date_add_without_interval(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    _prepare_authorized_query(monkeypatch, session, datasource_type="mysql")
    captured: dict[str, object] = {}

    def run_validated_read(**kwargs):
        captured.update(kwargs)
        return {
            "fields": ["cohort_day"],
            "data": [{"cohort_day": "2026-07-18"}],
        }

    monkeypatch.setattr(query_executor, "_run_validated_read", run_validated_read)
    sql = "SELECT DATE_ADD(dt, period) AS cohort_day FROM payments"

    result = execute_roi_read_query(session, make_user(), sql)

    assert captured["sql"] == sql
    assert result.status == "success"
    assert result.data == [{"cohort_day": "2026-07-18"}]


def test_roi_query_keeps_original_sql_after_table_extraction(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    _prepare_authorized_query(monkeypatch, session, datasource_type="mysql")
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        query_executor,
        "_run_validated_read",
        lambda **kwargs: captured.update(kwargs)
        or {"fields": ["value"], "data": [{"value": 1}]},
    )
    sql = "SELECT DATE_ADD(dt, period) AS value FROM payments"

    result = execute_roi_read_query(session, make_user(), sql)

    assert captured["sql"] == sql
    assert result.data == [{"value": 1}]


def test_roi_validated_read_marks_sql_as_prevalidated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def execute_after_validation(**kwargs):
        captured.update(kwargs)
        return {"status": "success"}

    monkeypatch.setattr(
        query_executor,
        "_execute_after_validation",
        execute_after_validation,
    )
    datasource = SimpleNamespace(type="mysql")

    query_executor._run_validated_read(
        datasource=datasource,
        sql="SELECT DATE_ADD(dt, period) FROM payments",
        query_timeout=10,
        max_result_rows=None,
    )

    assert captured["skip_read_validation"] is True
    assert captured["require_controlled_timeout"] is True
    assert captured["max_result_rows"] is None


def test_roi_query_rejects_datasource_without_controlled_timeout(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    _prepare_authorized_query(monkeypatch, session, datasource_type="oracle")
    monkeypatch.setattr(
        query_executor,
        "_run_validated_read",
        lambda **_kwargs: pytest.fail("不支持受控超时的数据源不应执行"),
    )

    with pytest.raises(HTTPException) as exc:
        execute_roi_read_query(session, make_user(), "SELECT 1 FROM dual")

    assert exc.value.status_code == 400
    assert exc.value.detail == "当前数据源类型不支持受控查询超时"


def test_roi_failed_result_logs_safe_context_at_warning_level(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _prepare_authorized_query(monkeypatch, session)
    monkeypatch.setattr(
        query_executor,
        "_run_validated_read",
        lambda **_kwargs: {
            "status": "failed",
            "message": "driver password=do-not-log",
        },
    )

    with caplog.at_level(logging.WARNING):
        result = execute_roi_read_query(session, make_user(), "SELECT 1")

    assert result.status == "failed"
    assert "tenant_id=11" in caplog.text
    assert "user_id=7" in caplog.text
    assert "datasource_id=202" in caplog.text
    assert "elapsed_ms=" in caplog.text
    assert "status=failed" in caplog.text
    assert "do-not-log" not in caplog.text


@pytest.mark.parametrize(
    ("datasource_type", "sql"),
    [
        ("pg", "SELECT nextval('order_seq')"),
        ("sqlServer", "SELECT NEXT VALUE FOR order_seq"),
        ("dm", "SELECT order_seq.NEXTVAL FROM orders"),
    ],
)
def test_roi_query_rejects_sequence_side_effects_structurally(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    datasource_type: str,
    sql: str,
) -> None:
    _prepare_authorized_query(
        monkeypatch,
        session,
        datasource_type=datasource_type,
    )
    monkeypatch.setattr(
        query_executor,
        "_run_validated_read",
        lambda **_kwargs: pytest.fail("序列副作用 SQL 不应到达执行层"),
    )

    with pytest.raises(HTTPException) as exc:
        execute_roi_read_query(session, make_user(), sql)

    assert exc.value.status_code == 400


@pytest.mark.parametrize(
    ("datasource_type", "sql"),
    [
        ("pg", "SELECT jsonb_build_object('amount', 1) AS payload"),
        ("mysql", "SELECT FIND_IN_SET('a', 'a,b') AS position"),
        ("mysql", "SELECT JSON_UNQUOTE('\"value\"') AS value"),
    ],
)
def test_roi_query_allows_dialect_safe_anonymous_builtins(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    datasource_type: str,
    sql: str,
) -> None:
    _prepare_authorized_query(
        monkeypatch,
        session,
        datasource_type=datasource_type,
    )
    monkeypatch.setattr(
        query_executor,
        "_run_validated_read",
        lambda **_kwargs: {"fields": ["value"], "data": [{"value": 1}]},
    )

    result = execute_roi_read_query(session, make_user(), sql)

    assert result.status == "success"


@pytest.mark.parametrize(
    ("datasource_type", "sql"),
    [
        ("pg", "SELECT evil.jsonb_build_object('amount', 1)"),
        ("mysql", "SELECT evil.FIND_IN_SET('a', 'a,b')"),
        ("mysql", "SELECT evil.JSON_UNQUOTE('\"value\"')"),
    ],
)
def test_roi_query_allows_qualified_database_native_functions(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    datasource_type: str,
    sql: str,
) -> None:
    _prepare_authorized_query(
        monkeypatch,
        session,
        datasource_type=datasource_type,
    )
    monkeypatch.setattr(
        query_executor,
        "_run_validated_read",
        lambda **_kwargs: {"fields": ["value"], "data": [{"value": 1}]},
    )

    result = execute_roi_read_query(session, make_user(), sql)

    assert result.data == [{"value": 1}]


def test_roi_query_allows_database_native_function_without_sqlglot_allowlist(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    _prepare_authorized_query(monkeypatch, session, datasource_type="pg")
    monkeypatch.setattr(
        query_executor,
        "_run_validated_read",
        lambda **_kwargs: {"fields": ["value"], "data": [{"value": 1}]},
    )

    result = execute_roi_read_query(
        session,
        make_user(),
        "SELECT customer_defined_metric(amount) AS value FROM orders",
    )

    assert result.data == [{"value": 1}]


@pytest.mark.parametrize(
    "datasource_type",
    ["pg", "mysql", "sqlServer", "dm", "doris", "starrocks", "kingbase"],
)
def test_roi_query_supported_timeout_matrix_executes(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    datasource_type: str,
) -> None:
    _prepare_authorized_query(
        monkeypatch,
        session,
        datasource_type=datasource_type,
    )
    calls: list[dict] = []
    monkeypatch.setattr(
        query_executor,
        "_run_validated_read",
        lambda **kwargs: calls.append(kwargs) or {"status": "success"},
    )

    result = execute_roi_read_query(session, make_user(), "SELECT 1")

    assert result.status == "success"
    assert calls[0]["query_timeout"] > 0
    assert calls[0]["max_result_rows"] is None


@pytest.mark.parametrize(
    "datasource_type",
    ["oracle", "ck", "redshift", "hive", "es"],
)
def test_roi_query_unsupported_timeout_or_unbounded_matrix_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    datasource_type: str,
) -> None:
    _prepare_authorized_query(
        monkeypatch,
        session,
        datasource_type=datasource_type,
    )
    monkeypatch.setattr(
        query_executor,
        "_run_validated_read",
        lambda **_kwargs: pytest.fail("不支持类型不应到达执行层"),
    )

    with pytest.raises(HTTPException) as exc:
        execute_roi_read_query(session, make_user(), "SELECT 1")

    assert exc.value.status_code == 400
    if datasource_type == "es":
        assert exc.value.detail == "当前数据源类型不支持受控且无截断 ROI 查询"


def test_render_roi_sql_date_range_supports_numeric_and_iso_placeholders() -> None:
    sql = (
        "SELECT * FROM t WHERE dt >= {{start_date_yyyymmdd}} "
        "AND dt <= {{end_date_yyyymmdd}} "
        "AND created_at >= {{start_date}} AND created_at < {{end_date}}"
    )

    rendered = render_roi_sql_date_range(
        sql,
        start_date=date(2026, 7, 10),
        end_date=date(2026, 7, 16),
    )

    assert "dt >= 20260710" in rendered
    assert "dt <= 20260716" in rendered
    assert "created_at >= '2026-07-10'" in rendered
    assert "created_at < '2026-07-16'" in rendered


def test_render_roi_sql_date_range_defaults_to_seven_complete_days() -> None:
    rendered = render_roi_sql_date_range(
        "SELECT * FROM t WHERE dt BETWEEN {{start_date_yyyymmdd}} AND {{end_date_yyyymmdd}}",
        today=date(2026, 7, 17),
    )

    assert "BETWEEN 20260710 AND 20260716" in rendered


def test_render_roi_sql_date_range_rejects_partial_or_missing_configuration() -> None:
    with pytest.raises(HTTPException, match="必须同时配置开始和结束日期占位符"):
        render_roi_sql_date_range(
            "SELECT * FROM t WHERE dt >= {{start_date_yyyymmdd}}",
            today=date(2026, 7, 17),
        )

    with pytest.raises(HTTPException, match="未配置时间范围占位符"):
        render_roi_sql_date_range(
            "SELECT * FROM t",
            start_date=date(2026, 7, 10),
            end_date=date(2026, 7, 16),
        )
