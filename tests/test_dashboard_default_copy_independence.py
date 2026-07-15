import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select

from apps.dashboard.crud import dashboard_service
from apps.dashboard.models.dashboard_model import (
    CoreDashboard,
    CoreDashboardShare,
    CoreDashboardTree,
    DashboardDefaultCopyRequest,
    DashboardDefaultRequest,
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


def test_copy_default_resource_does_not_inherit_source_tracking_metadata(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="owner")
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)
    monkeypatch.setattr(dashboard_service, "datasource_bound_to_tenant", lambda *args, **kwargs: True)
    monkeypatch.setattr(dashboard_service, "_require_create_permission", lambda *args, **kwargs: None)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="default-with-metadata",
                name=" 推荐看板 ",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                create_by="1",
                create_time=100,
                delete_flag=0,
                is_default=1,
                remark="source_dashboard_id=legacy-source",
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info="{}",
            )
        )
        session.commit()

        copied = dashboard_service.copy_default_resource(
            session=session,
            user=current_user,
            request=DashboardDefaultCopyRequest(dashboard_id="default-with-metadata"),
        )

        assert copied.name == " 推荐看板 "
        assert copied.remark is None
        assert copied.source is None
        assert copied.external_mcp_server_id is None


def test_set_default_resource_creates_independent_recommended_dashboard(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="owner")
    original_session_get = Session.get

    def session_get(current_session, entity, ident, *args, **kwargs):
        if entity is dashboard_service.CoreDatasource:
            return SimpleNamespace(id=ident)
        return original_session_get(current_session, entity, ident, *args, **kwargs)

    monkeypatch.setattr(Session, "get", session_get)
    monkeypatch.setattr(dashboard_service, "_require_set_default_permission", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 2)
    monkeypatch.setattr(dashboard_service, "datasource_bound_to_tenant", lambda *_args, **_kwargs: True)

    with Session(engine) as session:
        source = CoreDashboard(
            id="my-dashboard",
            tenant_id=1,
            name="付费",
            pid="root",
            datasource=2,
            node_type="leaf",
            type="dashboard",
            create_by="2",
            create_time=100,
            update_time=101,
            delete_flag=0,
            is_default=0,
            mobile_layout=1,
            component_data='[{"id":"chart-1","_dragId":"chart-1","component":"SQView"}]',
            canvas_style_data='{"width":1920}',
            canvas_view_info='{"chart-1":{"id":"chart-1","chart":{"id":"chart-1"},"datasource":2,"sql":"select 1"}}',
        )
        session.add(source)
        session.add(
            CoreDashboardTree(
                id="tree-my",
                tenant_id=1,
                scope="my",
                dashboard_id=source.id,
                parent_id="root",
                sort=1,
            )
        )
        session.commit()

        response = dashboard_service.set_default_resource(
            session,
            current_user,
            DashboardDefaultRequest(dashboard_id=source.id, is_default=True),
        )
        source_after = session.get(CoreDashboard, source.id)
        copied = session.get(CoreDashboard, response.id)
        copied_positions = session.exec(
            select(CoreDashboardTree).where(CoreDashboardTree.dashboard_id == response.id)
        ).all()

        assert response.id != source.id
        assert source_after is not None
        assert source_after.is_default == 0
        assert source_after.update_time == 101
        assert copied is not None
        assert copied.is_default == 1
        assert copied.name == "付费"
        assert copied.datasource == 2
        assert copied.mobile_layout == 1
        assert json.loads(copied.canvas_style_data) == {"width": 1920}
        assert "chart-1" not in copied.component_data
        assert "chart-1" not in copied.canvas_view_info
        assert [(row.scope, row.parent_id) for row in copied_positions] == [("default", "root")]


def test_set_default_resource_rejects_trimmed_case_insensitive_duplicate_name(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="owner")
    original_session_get = Session.get

    def session_get(current_session, entity, ident, *args, **kwargs):
        if entity is dashboard_service.CoreDatasource:
            return SimpleNamespace(id=ident)
        return original_session_get(current_session, entity, ident, *args, **kwargs)

    monkeypatch.setattr(Session, "get", session_get)
    monkeypatch.setattr(dashboard_service, "_require_set_default_permission", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 2)
    monkeypatch.setattr(dashboard_service, "datasource_bound_to_tenant", lambda *_args, **_kwargs: True)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="existing-default",
                tenant_id=1,
                name="Pay Dashboard",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                is_default=1,
                status=1,
                delete_flag=0,
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info="{}",
            )
        )
        session.add(
            CoreDashboard(
                id="source",
                tenant_id=1,
                name="  pay dashboard  ",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                is_default=0,
                status=1,
                delete_flag=0,
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info="{}",
            )
        )
        session.commit()

        with pytest.raises(HTTPException) as exc:
            dashboard_service.set_default_resource(
                session,
                current_user,
                DashboardDefaultRequest(dashboard_id="source", is_default=True),
            )
        records = session.exec(select(CoreDashboard)).all()

        assert exc.value.status_code == 409
        assert exc.value.detail == dashboard_service.RECOMMENDED_DASHBOARD_NAME_CONFLICT_MESSAGE
        assert {record.id for record in records} == {"existing-default", "source"}


def test_set_default_resource_allows_same_name_in_another_workspace(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="owner")
    original_session_get = Session.get

    def session_get(current_session, entity, ident, *args, **kwargs):
        if entity is dashboard_service.CoreDatasource:
            return SimpleNamespace(id=ident)
        return original_session_get(current_session, entity, ident, *args, **kwargs)

    monkeypatch.setattr(Session, "get", session_get)
    monkeypatch.setattr(dashboard_service, "_require_set_default_permission", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 2)
    monkeypatch.setattr(dashboard_service, "datasource_bound_to_tenant", lambda *_args, **_kwargs: True)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="tenant-2-default",
                tenant_id=2,
                name="Pay Dashboard",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                is_default=1,
                status=1,
                delete_flag=0,
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info="{}",
            )
        )
        session.add(
            CoreDashboard(
                id="tenant-1-source",
                tenant_id=1,
                name="pay dashboard",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                is_default=0,
                status=1,
                delete_flag=0,
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info="{}",
            )
        )
        session.commit()

        response = dashboard_service.set_default_resource(
            session,
            current_user,
            DashboardDefaultRequest(dashboard_id="tenant-1-source", is_default=True),
        )
        copied = session.get(CoreDashboard, response.id)

        assert copied is not None
        assert copied.tenant_id == 1
        assert copied.name == "pay dashboard"


def test_remove_independent_recommended_dashboard_soft_deletes_only_copy(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="owner")
    original_session_get = Session.get

    def session_get(current_session, entity, ident, *args, **kwargs):
        if entity is dashboard_service.CoreDatasource:
            return SimpleNamespace(id=ident)
        return original_session_get(current_session, entity, ident, *args, **kwargs)

    monkeypatch.setattr(Session, "get", session_get)
    monkeypatch.setattr(dashboard_service, "_require_set_default_permission", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 2)
    monkeypatch.setattr(dashboard_service, "datasource_bound_to_tenant", lambda *_args, **_kwargs: True)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="source",
                tenant_id=1,
                name="付费",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                is_default=0,
                status=1,
                delete_flag=0,
            )
        )
        session.add(
            CoreDashboard(
                id="recommended-copy",
                tenant_id=1,
                name="付费",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                is_default=1,
                status=1,
                delete_flag=0,
            )
        )
        session.add(
            CoreDashboardTree(
                id="tree-my",
                tenant_id=1,
                scope="my",
                dashboard_id="source",
                parent_id="root",
                sort=1,
            )
        )
        session.add(
            CoreDashboardTree(
                id="tree-default",
                tenant_id=1,
                scope="default",
                dashboard_id="recommended-copy",
                parent_id="root",
                sort=1,
            )
        )
        session.commit()

        dashboard_service.set_default_resource(
            session,
            current_user,
            DashboardDefaultRequest(dashboard_id="recommended-copy", is_default=False),
        )
        source = session.get(CoreDashboard, "source")
        copied = session.get(CoreDashboard, "recommended-copy")
        positions = session.exec(select(CoreDashboardTree)).all()

        assert source is not None and source.delete_flag == 0
        assert copied is not None and copied.delete_flag == 1 and copied.is_default == 0
        assert [(row.scope, row.dashboard_id) for row in positions] == [("my", "source")]


def test_remove_legacy_dual_tree_dashboard_keeps_my_dashboard(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="owner")
    original_session_get = Session.get

    def session_get(current_session, entity, ident, *args, **kwargs):
        if entity is dashboard_service.CoreDatasource:
            return SimpleNamespace(id=ident)
        return original_session_get(current_session, entity, ident, *args, **kwargs)

    monkeypatch.setattr(Session, "get", session_get)
    monkeypatch.setattr(dashboard_service, "_require_set_default_permission", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 2)
    monkeypatch.setattr(dashboard_service, "datasource_bound_to_tenant", lambda *_args, **_kwargs: True)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="legacy",
                tenant_id=1,
                name="历史看板",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                is_default=1,
                status=1,
                delete_flag=0,
            )
        )
        session.add(
            CoreDashboardTree(
                id="legacy-my",
                tenant_id=1,
                scope="my",
                dashboard_id="legacy",
                parent_id="root",
                sort=1,
            )
        )
        session.add(
            CoreDashboardTree(
                id="legacy-default",
                tenant_id=1,
                scope="default",
                dashboard_id="legacy",
                parent_id="root",
                sort=1,
            )
        )
        session.commit()

        dashboard_service.set_default_resource(
            session,
            current_user,
            DashboardDefaultRequest(dashboard_id="legacy", is_default=False),
        )
        record = session.get(CoreDashboard, "legacy")
        positions = session.exec(
            select(CoreDashboardTree).where(CoreDashboardTree.dashboard_id == "legacy")
        ).all()

        assert record is not None and record.delete_flag == 0 and record.is_default == 0
        assert [(row.scope, row.dashboard_id) for row in positions] == [("my", "legacy")]


def test_recommended_name_integrity_error_is_converted_to_conflict(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="owner")
    original_session_get = Session.get

    def session_get(current_session, entity, ident, *args, **kwargs):
        if entity is dashboard_service.CoreDatasource:
            return SimpleNamespace(id=ident)
        return original_session_get(current_session, entity, ident, *args, **kwargs)

    monkeypatch.setattr(Session, "get", session_get)
    monkeypatch.setattr(dashboard_service, "_require_set_default_permission", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 2)
    monkeypatch.setattr(dashboard_service, "datasource_bound_to_tenant", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        dashboard_service,
        "_recommended_dashboard_name_exists",
        lambda *_args, **_kwargs: False,
    )

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="source",
                tenant_id=1,
                name="付费",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                is_default=0,
                status=1,
                delete_flag=0,
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info="{}",
            )
        )
        session.commit()
        original_rollback = session.rollback
        rollback_called = False

        def conflicting_commit():
            raise IntegrityError(
                "insert",
                {},
                RuntimeError(
                    'duplicate key violates unique constraint "uq_core_dashboard_recommended_name"'
                ),
            )

        def tracked_rollback():
            nonlocal rollback_called
            rollback_called = True
            return original_rollback()

        monkeypatch.setattr(session, "commit", conflicting_commit)
        monkeypatch.setattr(session, "rollback", tracked_rollback)

        with pytest.raises(HTTPException) as exc:
            dashboard_service.set_default_resource(
                session,
                current_user,
                DashboardDefaultRequest(dashboard_id="source", is_default=True),
            )

        assert rollback_called is True
        assert exc.value.status_code == 409
        assert exc.value.detail == dashboard_service.RECOMMENDED_DASHBOARD_NAME_CONFLICT_MESSAGE


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
