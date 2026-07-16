"""ROI 独立只读查询执行边界测试。"""

import ast
import inspect
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
