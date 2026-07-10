from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine, select

from apps.dashboard.crud import dashboard_service
from apps.dashboard.models.dashboard_model import (
    CoreDashboard,
    CoreDashboardShare,
    CoreDashboardTree,
    DashboardDefaultCopyRequest,
)


def _engine_with_dashboard_table():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(
        engine,
        tables=[CoreDashboard.__table__, CoreDashboardTree.__table__, CoreDashboardShare.__table__],
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE sys_tenant_user (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    role VARCHAR(32),
                    is_primary BOOLEAN,
                    status INTEGER NOT NULL DEFAULT 1,
                    create_time DATETIME
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO sys_tenant_user (tenant_id, user_id, role, status)
                VALUES (1, 2, 'owner', 1)
                """
            )
        )
    return engine


def test_delete_resource_rejects_default_dashboard_shared_with_my_tree(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="owner")
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="default-dashboard",
                name="推荐看板",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                create_by="2",
                create_time=100,
                delete_flag=0,
                is_default=1,
            )
        )
        session.add(
            CoreDashboardTree(
                id="tree-default",
                tenant_id=1,
                scope="default",
                dashboard_id="default-dashboard",
                parent_id="root",
                sort=1,
            )
        )
        session.add(
            CoreDashboardTree(
                id="tree-my",
                tenant_id=1,
                scope="my",
                dashboard_id="default-dashboard",
                parent_id="root",
                sort=1,
            )
        )
        session.commit()

        with pytest.raises(HTTPException) as exc:
            dashboard_service.delete_resource(session, current_user, "default-dashboard")
        source = session.get(CoreDashboard, "default-dashboard")
        tree_rows = session.exec(
            select(CoreDashboardTree).where(CoreDashboardTree.dashboard_id == "default-dashboard")
        ).all()

    assert exc.value.status_code == 400
    assert source is not None
    assert {row.scope for row in tree_rows} == {"default", "my"}


def test_copy_default_resource_creates_independent_my_dashboard(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="owner")
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)
    monkeypatch.setattr(dashboard_service, "datasource_bound_to_tenant", lambda *args, **kwargs: True)
    monkeypatch.setattr(dashboard_service, "_require_create_permission", lambda *args, **kwargs: None)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="default-dashboard",
                name="推荐看板",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                create_by="1",
                create_time=100,
                delete_flag=0,
                is_default=1,
                component_data='[{"id":"chart-1","_dragId":"chart-1","component":"SQView"}]',
                canvas_style_data="{}",
                canvas_view_info='{"chart-1":{"id":"chart-1","chart":{"id":"chart-1"},"datasource":2,"sql":"select 1"}}',
            )
        )
        session.commit()

        copied = dashboard_service.copy_default_resource(
            session=session,
            user=current_user,
            request=DashboardDefaultCopyRequest(dashboard_id="default-dashboard"),
        )
        source = session.get(CoreDashboard, "default-dashboard")
        my_tree_row = session.exec(
            select(CoreDashboardTree).where(
                CoreDashboardTree.scope == "my",
                CoreDashboardTree.dashboard_id == copied.id,
            )
        ).one()

    assert copied.id != "default-dashboard"
    assert copied.is_default == 0
    assert source is not None
    assert source.is_default == 1
    assert my_tree_row.parent_id == "root"
    assert "chart-1" not in copied.component_data
    assert "chart-1" not in copied.canvas_view_info


def test_repair_my_tree_default_dashboard_copies_repoints_my_tree(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="owner")
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)
    monkeypatch.setattr(dashboard_service, "datasource_bound_to_tenant", lambda *args, **kwargs: True)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="default-dashboard",
                name="推荐看板",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                create_by="1",
                create_time=100,
                delete_flag=0,
                is_default=1,
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info="{}",
            )
        )
        session.add(
            CoreDashboardTree(
                id="tree-default",
                tenant_id=1,
                scope="default",
                dashboard_id="default-dashboard",
                parent_id="root",
                sort=1,
            )
        )
        session.add(
            CoreDashboardTree(
                id="tree-my",
                tenant_id=1,
                scope="my",
                dashboard_id="default-dashboard",
                parent_id="root",
                sort=2,
            )
        )
        session.commit()

        repaired = dashboard_service.repair_my_tree_default_dashboard_copies(session, current_user)
        source = session.get(CoreDashboard, "default-dashboard")
        my_row = session.exec(select(CoreDashboardTree).where(CoreDashboardTree.id == "tree-my")).one()
        default_row = session.exec(select(CoreDashboardTree).where(CoreDashboardTree.id == "tree-default")).one()
        copied = session.get(CoreDashboard, my_row.dashboard_id)

    assert len(repaired) == 1
    assert source is not None
    assert default_row.dashboard_id == "default-dashboard"
    assert my_row.dashboard_id != "default-dashboard"
    assert my_row.parent_id == "root"
    assert my_row.sort == 2
    assert copied is not None
    assert copied.is_default == 0
    assert copied.name == "推荐看板"
    assert copied.create_by == "2"


def test_repair_my_tree_default_dashboard_copies_supports_legacy_no_datasource(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="owner")

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="legacy-default-dashboard",
                name="历史推荐看板",
                pid="root",
                datasource=None,
                node_type="leaf",
                type="dashboard",
                create_by="1",
                create_time=100,
                delete_flag=0,
                is_default=1,
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info="{}",
            )
        )
        session.add(
            CoreDashboardTree(
                id="tree-default-legacy",
                tenant_id=1,
                scope="default",
                dashboard_id="legacy-default-dashboard",
                parent_id="root",
                sort=1,
            )
        )
        session.add(
            CoreDashboardTree(
                id="tree-my-legacy",
                tenant_id=1,
                scope="my",
                dashboard_id="legacy-default-dashboard",
                parent_id="root",
                sort=3,
            )
        )
        session.commit()

        repaired = dashboard_service.repair_my_tree_default_dashboard_copies(session, current_user)
        my_row = session.exec(select(CoreDashboardTree).where(CoreDashboardTree.id == "tree-my-legacy")).one()
        copied = session.get(CoreDashboard, my_row.dashboard_id)

    assert len(repaired) == 1
    assert my_row.dashboard_id != "legacy-default-dashboard"
    assert copied is not None
    assert copied.datasource is None
    assert copied.is_default == 0
    assert copied.name == "历史推荐看板"
