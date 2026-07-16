"""ROI 独立只读查询执行边界测试。"""

import ast
import inspect
import logging
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import Session, create_engine

from apps.roi_dashboard import query_executor
from apps.roi_dashboard.models import CoreRoiWorkspaceConfig
from apps.roi_dashboard.query_executor import execute_roi_read_query


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
            id=1001,
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


def test_roi_query_skips_platform_table_field_and_row_permissions(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    _prepare_authorized_query(monkeypatch, session)

    monkeypatch.setattr(
        query_executor,
        "_run_validated_read",
        lambda **_kwargs: {"columns": ["secret"], "data": [[1]]},
    )

    result = execute_roi_read_query(
        session,
        make_user(),
        "select secret from private_table",
    )

    assert result.status == "success"
    assert result.data == [{"secret": 1}]


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
        "SELECT custom_side_effect(amount) FROM orders",
        "SELECT * FROM",
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
def test_roi_query_rejects_qualified_allowlisted_anonymous_functions(
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
        lambda **_kwargs: pytest.fail("限定调用不应到达执行层"),
    )

    with pytest.raises(HTTPException) as exc:
        execute_roi_read_query(session, make_user(), sql)

    assert exc.value.status_code == 400


def test_roi_query_still_rejects_unknown_anonymous_udf(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    _prepare_authorized_query(monkeypatch, session, datasource_type="pg")
    monkeypatch.setattr(
        query_executor,
        "_run_validated_read",
        lambda **_kwargs: pytest.fail("未知 UDF 不应到达执行层"),
    )

    with pytest.raises(HTTPException) as exc:
        execute_roi_read_query(
            session,
            make_user(),
            "SELECT my_side_effecting_function(amount) FROM orders",
        )

    assert exc.value.status_code == 400


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
