import os
from types import SimpleNamespace

os.environ["LOG_FORMAT"] = "%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s"

import json

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine, select

from apps.dashboard.crud import dashboard_service
from apps.dashboard.crud.dashboard_date_filter import DashboardDateFilterPreparation
from apps.dashboard.models.dashboard_chart_config import DashboardDateFilterRequest
from apps.datasource.crud import sql_engine_executor as query_executor
import pytest
from fastapi import HTTPException

from apps.dashboard.models.dashboard_model import (
    CoreDashboard,
    CoreDashboardShare,
    CoreDashboardTree,
    CreateDashboard,
    QueryDashboard,
    DashboardDefaultCopyRequest,
    DashboardPivotRequest,
    DashboardSqlPreview,
    DashboardShareRequest,
    DashboardShareListQuery,
    SharedDashboardQuery,
    SharedDashboardUseRequest,
)


@pytest.fixture(autouse=True)
def _clear_dashboard_service_preview_cache(monkeypatch):
    monkeypatch.setattr(dashboard_service.settings, "DASHBOARD_SQL_PREVIEW_CACHE_TTL_SECONDS", 0)
    with dashboard_service._DASHBOARD_SQL_PREVIEW_CACHE_LOCK:
        dashboard_service._DASHBOARD_SQL_PREVIEW_CACHE.clear()
    with dashboard_service._DASHBOARD_SQL_PREVIEW_INFLIGHT_LOCKS_LOCK:
        dashboard_service._DASHBOARD_SQL_PREVIEW_INFLIGHT_LOCKS.clear()


def _engine_with_dashboard_table():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(
        engine,
        tables=[CoreDashboard.__table__, CoreDashboardTree.__table__, CoreDashboardShare.__table__],
    )
    with engine.begin() as conn:
        conn.execute(text(
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
        ))
        for tenant_id, user_id, role in (
            (1, 1, "owner"),
            (1, 2, "member"),
            (1, 5, "admin"),
            (1, 9, "member"),
            (2, 1, "owner"),
            (2, 9, "member"),
            (20, 1, "owner"),
            (20, 5, "member"),
        ):
            conn.execute(
                text(
                    """
                    INSERT INTO sys_tenant_user (tenant_id, user_id, role, status)
                    VALUES (:tenant_id, :user_id, :role, 1)
                    """
                ),
                {"tenant_id": tenant_id, "user_id": user_id, "role": role},
            )
        conn.execute(text(
            """
            CREATE TABLE core_roi_workspace_config (
                tenant_id INTEGER NOT NULL,
                datasource_id INTEGER NOT NULL,
                deleted BOOLEAN NOT NULL DEFAULT 0
            )
            """
        ))
    with Session(engine) as session:
        _create_simple_datasource_table(session)
        session.commit()
    return engine


def _engine_with_dashboard_permission_tables():
    engine = _engine_with_dashboard_table()
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS core_datasource (
                id INTEGER PRIMARY KEY,
                tenant_id INTEGER NOT NULL DEFAULT 1,
                name VARCHAR(128) NOT NULL,
                description VARCHAR(512),
                type VARCHAR(64),
                type_name VARCHAR(64),
                configuration TEXT,
                create_time DATETIME,
                create_by INTEGER,
                status VARCHAR(64),
                num VARCHAR(256),
                table_relation TEXT,
                embedding TEXT,
                recommended_config INTEGER
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE core_datasource_user (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ds_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role VARCHAR(32) NOT NULL DEFAULT 'viewer',
                create_by INTEGER,
                create_time DATETIME
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE core_table (
                id INTEGER PRIMARY KEY,
                ds_id INTEGER NOT NULL,
                checked BOOLEAN,
                table_name TEXT,
                table_comment TEXT,
                custom_comment TEXT,
                embedding TEXT
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE core_field (
                id INTEGER PRIMARY KEY,
                ds_id INTEGER NOT NULL,
                table_id INTEGER NOT NULL,
                checked BOOLEAN,
                field_name TEXT,
                field_type VARCHAR(128),
                field_comment TEXT,
                custom_comment TEXT,
                field_index INTEGER
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE ds_rules (
                id INTEGER PRIMARY KEY,
                enable BOOLEAN NOT NULL,
                name VARCHAR NOT NULL,
                description VARCHAR,
                tenant_id INTEGER NOT NULL DEFAULT 1,
                scope VARCHAR(32) NOT NULL DEFAULT 'TENANT',
                permission_list TEXT,
                user_list TEXT,
                white_list_user TEXT,
                create_time DATETIME
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE ds_permission (
                id INTEGER PRIMARY KEY,
                name VARCHAR,
                enable BOOLEAN NOT NULL,
                auth_target_type VARCHAR,
                auth_target_id INTEGER,
                type VARCHAR NOT NULL,
                ds_id INTEGER,
                table_id INTEGER,
                expression_tree TEXT,
                permissions TEXT,
                white_list_user TEXT,
                create_time DATETIME
            )
            """
        ))
    return engine


def test_validate_dashboard_report_target_accepts_visible_dashboard_component(monkeypatch):
    """实时解读目标属于当前可见看板和数据源时应通过校验。"""
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="member")
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 2)
    _allow_requested_chart_execution_datasource(monkeypatch)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="dashboard-report-target",
                tenant_id=1,
                name="可解读看板",
                pid="root",
                datasource=2,
                node_type="leaf",
                is_default=1,
                create_by="1",
                delete_flag=0,
                component_data=json.dumps(
                    [{"id": "chart-1", "component": "SQView"}],
                    ensure_ascii=False,
                ),
                canvas_view_info=json.dumps(
                    {"chart-1": {"id": "chart-1", "datasource": 2, "sql": "select 1"}}
                ),
            )
        )
        session.commit()

        dashboard_service.validate_dashboard_report_target(
            session,
            current_user,
            "dashboard-report-target",
            2,
            ["chart-1"],
        )


@pytest.mark.parametrize(
    ("datasource_id", "component_ids"),
    [
        (3, ["chart-1"]),
        (2, ["forged-chart"]),
        (2, []),
    ],
)
def test_validate_dashboard_report_target_rejects_mismatched_target(
        monkeypatch,
        datasource_id,
        component_ids,
):
    """数据源不匹配、组件伪造或空目标都不能进入报表解读。"""
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="member")
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 2)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="dashboard-report-target",
                tenant_id=1,
                name="可解读看板",
                pid="root",
                datasource=2,
                node_type="leaf",
                is_default=1,
                create_by="1",
                delete_flag=0,
                component_data=json.dumps([{"id": "chart-1", "component": "SQView"}]),
            )
        )
        session.commit()

        with pytest.raises(HTTPException) as exc_info:
            dashboard_service.validate_dashboard_report_target(
                session,
                current_user,
                "dashboard-report-target",
                datasource_id,
                component_ids,
            )

    assert exc_info.value.status_code == 403


def _create_simple_datasource_table(session: Session):
    session.execute(text(
        """
        CREATE TABLE IF NOT EXISTS core_datasource (
            id INTEGER PRIMARY KEY,
            tenant_id INTEGER NOT NULL DEFAULT 1,
            name VARCHAR(128) NOT NULL,
            description VARCHAR(512),
            type VARCHAR(64),
            type_name VARCHAR(64),
            configuration TEXT,
            create_time DATETIME,
            create_by INTEGER,
            status VARCHAR(64),
            num VARCHAR(256),
            table_relation TEXT,
            embedding TEXT,
            recommended_config INTEGER
        )
        """
    ))


def _insert_simple_datasource_fixture(session: Session, datasource_id: int = 1):
    _create_simple_datasource_table(session)
    session.execute(text(
        """
        INSERT INTO core_datasource
            (id, name, type, type_name, configuration, create_by, recommended_config)
        VALUES
            (:datasource_id, 'Project 1', 'pg', 'PostgreSQL', '{}', 1, 1)
        """
    ), {"datasource_id": datasource_id})


def _insert_active_tenant_member(session: Session, user_id: int, tenant_id: int = 1):
    session.execute(text(
        """
        INSERT INTO sys_tenant_user (tenant_id, user_id, role, status)
        VALUES (:tenant_id, :user_id, 'member', 1)
        """
    ), {"tenant_id": tenant_id, "user_id": user_id})


def _insert_dashboard_permission_fixture(session: Session):
    session.execute(text(
        """
        INSERT INTO core_datasource
            (id, name, type, type_name, configuration, create_by, recommended_config)
        VALUES
            (1, 'Project 1', 'pg', 'PostgreSQL', '{}', 9, 1)
        """
    ))
    session.execute(text(
        """
        INSERT INTO core_roi_workspace_config (tenant_id, datasource_id, deleted)
        VALUES (1, 1, 0)
        """
    ))
    session.execute(text(
        """
        INSERT INTO core_datasource_user (ds_id, user_id, role, create_by)
        VALUES (1, 2, 'viewer', 9)
        """
    ))
    session.execute(text(
        """
        INSERT INTO core_table (id, ds_id, checked, table_name, table_comment, custom_comment)
        VALUES
            (10, 1, 1, 'orders', 'orders', 'orders'),
            (11, 1, 1, 'payments', 'payments', 'payments')
        """
    ))
    session.execute(text(
        """
        INSERT INTO core_field
            (id, ds_id, table_id, checked, field_name, field_type, field_comment, custom_comment, field_index)
        VALUES
            (100, 1, 10, 1, 'order_id', 'int', 'order_id', 'order_id', 1),
            (101, 1, 10, 1, 'amount', 'numeric', 'amount', 'amount', 2),
            (102, 1, 10, 1, 'region', 'varchar', 'region', 'region', 3),
            (110, 1, 11, 1, 'payment_id', 'int', 'payment_id', 'payment_id', 1)
        """
    ))


def _force_bound_chart_execution_datasource(monkeypatch):
    monkeypatch.setattr(
        dashboard_service,
        "_configured_chart_execution_datasources",
        lambda *_args, **_kwargs: [(1, "bound")],
    )


def _allow_requested_chart_execution_datasource(monkeypatch):
    monkeypatch.setattr(
        dashboard_service,
        "resolve_chart_execution_datasource",
        lambda _session, _user, datasource_id: int(datasource_id),
    )


def _insert_orders_column_rule(session: Session):
    permissions = json.dumps([
        {"field_id": 100, "field_name": "order_id", "enable": True},
        {"field_id": 101, "field_name": "amount", "enable": False},
        {"field_id": 102, "field_name": "region", "enable": True},
    ])
    session.execute(text(
        """
        INSERT INTO ds_permission
            (id, name, enable, auth_target_type, type, ds_id, table_id, expression_tree, permissions, white_list_user)
        VALUES
            (1000, 'orders columns', 1, 'user', 'column', 1, 10, '{}', :permissions, '[]')
        """
    ), {"permissions": permissions})
    session.execute(text(
        """
        INSERT INTO ds_rules
            (id, enable, name, description, tenant_id, scope, permission_list, user_list, white_list_user)
        VALUES
            (2000, 1, 'user 2 orders columns', '', 1, 'TENANT', '[1000]', '[2]', '[]')
        """
    ))


def _insert_payments_table_deny_rule(session: Session):
    session.execute(text(
        """
        INSERT INTO ds_permission
            (id, name, enable, auth_target_type, type, ds_id, table_id, expression_tree, permissions, white_list_user)
        VALUES
            (1002, 'payments denied', 1, 'user', 'table', 1, 11, '{}', '[]', '[]')
        """
    ))
    session.execute(text(
        """
        INSERT INTO ds_rules
            (id, enable, name, description, tenant_id, scope, permission_list, user_list, white_list_user)
        VALUES
            (2002, 1, 'user 2 payments denied', '', 1, 'TENANT', '[1002]', '[2]', '[]')
        """
    ))


def _insert_orders_row_rule(session: Session):
    tree = {
        "logic": "AND",
        "items": [
            {
                "type": "item",
                "field_id": 102,
                "filter_type": "text",
                "term": "eq",
                "value": "US",
            }
        ],
    }
    session.execute(text(
        """
        INSERT INTO ds_permission
            (id, name, enable, auth_target_type, type, ds_id, table_id, expression_tree, permissions, white_list_user)
        VALUES
            (1001, 'orders rows', 1, 'user', 'row', 1, 10, :tree, '[]', '[]')
        """
    ), {"tree": json.dumps(tree)})
    session.execute(text(
        """
        INSERT INTO ds_rules
            (id, enable, name, description, tenant_id, scope, permission_list, user_list, white_list_user)
        VALUES
            (2001, 1, 'user 2 orders rows', '', 1, 'TENANT', '[1001]', '[2]', '[]')
        """
    ))


def test_list_resource_returns_dashboard_tree_nodes_for_admin():
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=1, isAdmin=True, tenant_id=1)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="dashboard-1",
                name="运营看板",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                create_by="1",
                create_time=100,
                delete_flag=0,
            )
        )
        session.commit()

        tree = dashboard_service.list_resource(
            session=session,
            dashboard=QueryDashboard(),
            current_user=current_user,
        )

    assert len(tree) == 1
    assert tree[0].id == "dashboard-1"
    assert tree[0].name == "运营看板"
    assert tree[0].datasource == 2
    assert tree[0].leaf is True
    assert tree[0].can_edit is True


def test_list_resource_excludes_dashboards_from_other_tenants_for_admin():
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=1, isAdmin=True, tenant_id=2)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="tenant-1-dashboard",
                tenant_id=1,
                name="租户一看板",
                pid="root",
                datasource=None,
                node_type="leaf",
                type="dashboard",
                create_by="2",
                create_time=100,
                delete_flag=0,
            )
        )
        session.add(
            CoreDashboard(
                id="tenant-2-dashboard",
                tenant_id=2,
                name="租户二看板",
                pid="root",
                datasource=None,
                node_type="leaf",
                type="dashboard",
                create_by="1",
                create_time=101,
                delete_flag=0,
            )
        )
        session.commit()

        tree = dashboard_service.list_resource(
            session=session,
            dashboard=QueryDashboard(),
            current_user=current_user,
        )

    assert [node.id for node in tree] == ["tenant-2-dashboard"]


def test_load_resource_denies_cross_tenant_dashboard():
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=1, isAdmin=True, tenant_id=2)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="tenant-1-dashboard",
                tenant_id=1,
                name="租户一看板",
                pid="root",
                datasource=None,
                node_type="leaf",
                type="dashboard",
                create_by="1",
                create_time=100,
                delete_flag=0,
            )
        )
        session.commit()

        with pytest.raises(HTTPException) as exc_info:
            dashboard_service.load_resource(
                session=session,
                dashboard=QueryDashboard(id="tenant-1-dashboard"),
                current_user=current_user,
            )

    assert exc_info.value.status_code == 404


def test_list_resource_is_scoped_to_current_workspace_even_for_same_creator(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=20)
    monkeypatch.setattr(dashboard_service, "get_accessible_datasource_ids", lambda *args, **kwargs: None)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="tenant-10-dashboard",
                tenant_id=10,
                name="租户十看板",
                pid="root",
                datasource=None,
                node_type="leaf",
                type="dashboard",
                create_by="2",
                create_time=100,
                delete_flag=0,
            )
        )
        session.add(
            CoreDashboard(
                id="tenant-20-dashboard",
                tenant_id=20,
                name="租户二十看板",
                pid="root",
                datasource=None,
                node_type="leaf",
                type="dashboard",
                create_by="2",
                create_time=101,
                delete_flag=0,
            )
        )
        session.commit()

        tree = dashboard_service.list_resource(
            session=session,
            dashboard=QueryDashboard(),
            current_user=current_user,
        )

    assert [node.id for node in tree] == ["tenant-20-dashboard"]


def test_list_resource_hides_other_users_dashboard_for_project_editor(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(dashboard_service, "_supports_datasource_editor_role_lookup", lambda *args, **kwargs: True)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)
    monkeypatch.setattr(dashboard_service, "has_datasource_role", lambda *args, **kwargs: True)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="dashboard-1",
                name="项目看板",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                create_by="1",
                create_time=100,
                delete_flag=0,
            )
        )
        session.commit()

        tree = dashboard_service.list_resource(
            session=session,
            dashboard=QueryDashboard(datasource=2),
            current_user=current_user,
        )

    assert tree == []


def test_list_resource_hides_other_users_dashboard_for_project_viewer(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(dashboard_service, "_supports_datasource_editor_role_lookup", lambda *args, **kwargs: True)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)
    monkeypatch.setattr(dashboard_service, "has_datasource_role", lambda *args, **kwargs: False)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="dashboard-1",
                name="项目看板",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                create_by="1",
                create_time=100,
                delete_flag=0,
            )
        )
        session.commit()

        tree = dashboard_service.list_resource(
            session=session,
            dashboard=QueryDashboard(datasource=2),
            current_user=current_user,
        )

    assert tree == []


def test_list_resource_marks_creator_can_edit_with_project_viewer_role(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(dashboard_service, "_supports_datasource_editor_role_lookup", lambda *args, **kwargs: True)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)
    monkeypatch.setattr(dashboard_service, "has_datasource_role", lambda *args, **kwargs: False)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="dashboard-1",
                name="我的看板",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                create_by="2",
                create_time=100,
                delete_flag=0,
            )
        )
        session.commit()

        tree = dashboard_service.list_resource(
            session=session,
            dashboard=QueryDashboard(datasource=2),
            current_user=current_user,
        )

    assert len(tree) == 1
    assert tree[0].can_edit is True
    assert tree[0].can_share is True


def test_project_editor_cannot_load_other_users_private_dashboard(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(dashboard_service, "_supports_datasource_editor_role_lookup", lambda *args, **kwargs: True)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)
    monkeypatch.setattr(dashboard_service, "has_datasource_role", lambda *args, **kwargs: True)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="dashboard-1",
                name="别人的私有看板",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                create_by="1",
                create_time=100,
                delete_flag=0,
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info="{}",
            )
        )
        session.commit()

        with pytest.raises(HTTPException) as exc_info:
            dashboard_service.load_resource(
                session=session,
                dashboard=QueryDashboard(id="dashboard-1"),
                current_user=current_user,
            )

    assert exc_info.value.status_code == 404


def test_workspace_admin_cannot_load_member_private_dashboard(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=1, isAdmin=False, tenant_id=1, tenant_role="owner")
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="member-private-dashboard",
                name="成员私有看板",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                create_by="2",
                create_time=100,
                delete_flag=0,
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info="{}",
            )
        )
        session.commit()

        tree = dashboard_service.list_resource(
            session=session,
            dashboard=QueryDashboard(datasource=2),
            current_user=current_user,
        )
        with pytest.raises(HTTPException) as exc_info:
            dashboard_service.load_resource(
                session=session,
                dashboard=QueryDashboard(id="member-private-dashboard"),
                current_user=current_user,
            )

    assert tree == []
    assert exc_info.value.status_code == 404


def test_platform_delegate_cannot_list_or_load_member_private_dashboard(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(
        id=9,
        isAdmin=True,
        system_role="system_admin",
        tenant_id=1,
        tenant_role="owner",
        workspace_status="platform_workspace_delegate",
    )
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)
    monkeypatch.setattr(dashboard_service, "get_accessible_datasource_ids", lambda *args, **kwargs: {2})

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="private-dashboard",
                name="成员私有看板",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                create_by="2",
                create_time=100,
                delete_flag=0,
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info="{}",
            )
        )
        session.commit()

        tree = dashboard_service.list_resource(
            session=session,
            dashboard=QueryDashboard(datasource=2),
            current_user=current_user,
        )

        with pytest.raises(HTTPException) as exc_info:
            dashboard_service.load_resource(
                session=session,
                dashboard=QueryDashboard(id="private-dashboard"),
                current_user=current_user,
            )

    assert tree == []
    assert exc_info.value.status_code == 404


def test_platform_delegate_create_canvas_is_workspace_asset(monkeypatch):
    engine = _engine_with_dashboard_table()
    delegate_user = SimpleNamespace(
        id=9,
        isAdmin=True,
        system_role="system_admin",
        tenant_id=1,
        tenant_role="owner",
        workspace_status="platform_workspace_delegate",
    )
    workspace_admin = SimpleNamespace(id=1, isAdmin=False, tenant_id=1, tenant_role="owner")
    member = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="member")
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)
    monkeypatch.setattr(dashboard_service, "has_datasource_access", lambda *args, **kwargs: True)
    monkeypatch.setattr(dashboard_service, "has_datasource_role", lambda *args, **kwargs: True)
    monkeypatch.setattr(dashboard_service, "datasource_bound_to_tenant", lambda *args, **kwargs: True)
    monkeypatch.setattr(dashboard_service, "_user_name", lambda *args, **kwargs: None)
    monkeypatch.setattr(dashboard_service, "_execute_dashboard_chart_sql", lambda *args, **kwargs: {
        "status": "success",
        "data": [],
        "fields": [],
        "message": "",
    })

    with Session(engine) as session:
        created = dashboard_service.create_canvas(
            session=session,
            user=delegate_user,
            dashboard=CreateDashboard(
                name="SaaS 创建看板",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info="{}",
            ),
        )
        dashboard_id = created.id

        admin_tree = dashboard_service.list_resource(
            session=session,
            dashboard=QueryDashboard(datasource=2),
            current_user=workspace_admin,
        )
        admin_loaded = dashboard_service.load_resource(
            session=session,
            dashboard=QueryDashboard(id=dashboard_id),
            current_user=workspace_admin,
        )
        delegate_loaded = dashboard_service.load_resource(
            session=session,
            dashboard=QueryDashboard(id=dashboard_id),
            current_user=delegate_user,
        )

    assert created.status == dashboard_service.DASHBOARD_STATUS_ACTIVE
    assert created.source is None
    assert created.create_by == "1"
    assert created.update_by == "1"
    assert [item.id for item in admin_tree] == [dashboard_id]
    assert admin_loaded["id"] == dashboard_id
    assert admin_loaded["can_edit"] is True
    assert delegate_loaded["id"] == dashboard_id
    assert delegate_loaded["can_edit"] is True


def test_platform_delegate_updates_workspace_asset_directly(monkeypatch):
    _allow_requested_chart_execution_datasource(monkeypatch)
    engine = _engine_with_dashboard_table()
    delegate_user = SimpleNamespace(
        id=9,
        isAdmin=True,
        system_role="system_admin",
        tenant_id=1,
        tenant_role="owner",
        workspace_status="platform_workspace_delegate",
    )
    workspace_admin = SimpleNamespace(id=1, isAdmin=False, tenant_id=1, tenant_role="owner")
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)
    monkeypatch.setattr(dashboard_service, "has_datasource_access", lambda *args, **kwargs: True)
    monkeypatch.setattr(dashboard_service, "has_datasource_role", lambda *args, **kwargs: True)
    monkeypatch.setattr(dashboard_service, "datasource_bound_to_tenant", lambda *args, **kwargs: True)
    monkeypatch.setattr(dashboard_service, "_user_name", lambda *args, **kwargs: None)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="published-delegate-dashboard",
                name="正式代运营看板",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                source=dashboard_service.DASHBOARD_SOURCE_PLATFORM_DELEGATE,
                status=dashboard_service.DASHBOARD_STATUS_ACTIVE,
                create_by="1",
                create_time=100,
                delete_flag=0,
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info=json.dumps({"chart-1": {"datasource": 2, "sql": "select 1"}}),
            )
        )
        session.commit()

        admin_loaded = dashboard_service.load_resource(
            session=session,
            dashboard=QueryDashboard(id="published-delegate-dashboard"),
            current_user=workspace_admin,
        )
        updated = dashboard_service.update_canvas(
            session=session,
            user=delegate_user,
            dashboard=CreateDashboard(
                id="published-delegate-dashboard",
                name="维护后代运营看板",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info=json.dumps({"chart-1": {"datasource": 2, "sql": "select 2"}}),
            ),
        )
        target_after_publish = session.get(CoreDashboard, "published-delegate-dashboard")

    assert admin_loaded["can_edit"] is True
    assert updated.id == "published-delegate-dashboard"
    assert target_after_publish.name == "维护后代运营看板"
    assert target_after_publish.update_by == "1"
    assert json.loads(target_after_publish.canvas_view_info)["chart-1"]["sql"] == "select 2"


def test_platform_delegate_can_copy_public_dashboard_to_template_but_not_private(monkeypatch):
    _allow_requested_chart_execution_datasource(monkeypatch)
    engine = _engine_with_dashboard_table()
    delegate_user = SimpleNamespace(
        id=9,
        isAdmin=True,
        system_role="system_admin",
        tenant_id=1,
        tenant_role="owner",
        workspace_status="platform_workspace_delegate",
    )
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)
    monkeypatch.setattr(
        dashboard_service,
        "_dashboard_chart_permission_audit",
        lambda *args, **kwargs: (None, False),
    )
    monkeypatch.setattr(
        dashboard_service,
        "execute_user_query",
        lambda *args, **kwargs: {
            "status": "success",
            "fields": ["v"],
            "data": [{"v": 1}],
            "message": "",
            "error_type": None,
        },
    )

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="private-dashboard",
                name="成员私有看板",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                create_by="2",
                create_time=100,
                delete_flag=0,
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info="{}",
            )
        )
        session.add(
            CoreDashboard(
                id="default-dashboard",
                name="推荐看板",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                create_by="1",
                create_time=101,
                delete_flag=0,
                is_default=1,
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info=json.dumps(
                    {
                        "chart-1": {
                            "datasource": 2,
                            "sql": "select 1",
                            "status": "success",
                            "data": {"fields": ["v"], "data": [{"v": 1}]},
                            "fields": ["v"],
                        }
                    }
                ),
            )
        )
        session.commit()

        with pytest.raises(HTTPException) as exc_info:
            dashboard_service.copy_dashboard_to_platform_template(
                session=session,
                user=delegate_user,
                dashboard_id="private-dashboard",
            )
        template = dashboard_service.copy_dashboard_to_platform_template(
            session=session,
            user=delegate_user,
            dashboard_id="default-dashboard",
        )
        with pytest.raises(HTTPException) as duplicate_exc_info:
            dashboard_service.copy_dashboard_to_platform_template(
                session=session,
                user=delegate_user,
                dashboard_id="default-dashboard",
                name="重复模板",
            )
        templates = session.exec(
            select(CoreDashboard).where(
                CoreDashboard.source == dashboard_service.DASHBOARD_SOURCE_PLATFORM_TEMPLATE
            )
        ).all()
        template_record = session.get(CoreDashboard, template.id)

    assert exc_info.value.status_code == 404
    assert duplicate_exc_info.value.status_code == 400
    assert duplicate_exc_info.value.detail == "该看板已复制为平台模板"
    assert len(templates) == 1
    assert template.tenant_id == dashboard_service.DEFAULT_TENANT_ID
    assert template.source == dashboard_service.DASHBOARD_SOURCE_PLATFORM_TEMPLATE
    assert template.content_id == "0"
    assert template.datasource is None
    chart = json.loads(template_record.canvas_view_info)["chart-1"]
    assert chart["sql"] == "select 1"
    assert chart["datasource"] is None
    assert chart["status"] == "success"
    assert chart["data"]["data"] == [{"v": 1}]
    assert chart["data"]["fields"] == ["v"]


def test_platform_admin_can_list_dashboard_templates_without_workspace_context():
    engine = _engine_with_dashboard_table()
    platform_admin = SimpleNamespace(
        id=9,
        isAdmin=True,
        system_role="system_admin",
        tenant_id=None,
        tenant_role=None,
        workspace_status="platform_admin",
    )

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="template-dashboard",
                tenant_id=dashboard_service.DEFAULT_TENANT_ID,
                name="平台模板",
                pid="root",
                datasource=None,
                node_type="leaf",
                type="dashboard",
                source=dashboard_service.DASHBOARD_SOURCE_PLATFORM_TEMPLATE,
                status=dashboard_service.DASHBOARD_STATUS_ACTIVE,
                remark="source_dashboard_id=source-1;source_tenant_id=2",
                create_by="9",
                create_time=100,
                delete_flag=0,
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info=json.dumps({"chart-1": {"datasource": 2, "sql": "select 1"}}),
            )
        )
        session.commit()

        templates = dashboard_service.list_platform_dashboard_templates(session=session, user=platform_admin)

    assert len(templates) == 1
    assert templates[0].id == "template-dashboard"
    assert templates[0].source == dashboard_service.DASHBOARD_SOURCE_PLATFORM_TEMPLATE
    assert templates[0].remark == "source_dashboard_id=source-1;source_tenant_id=2"
    assert templates[0].can_edit is True
    assert templates[0].can_share is False
    assert templates[0].can_set_default is False


def test_platform_admin_updates_template_without_touching_source_dashboard():
    engine = _engine_with_dashboard_table()
    platform_admin = SimpleNamespace(
        id=9,
        isAdmin=True,
        system_role="system_admin",
        tenant_id=None,
        tenant_role=None,
        workspace_status="platform_admin",
    )

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="source-dashboard",
                tenant_id=2,
                name="来源看板",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                status=dashboard_service.DASHBOARD_STATUS_ACTIVE,
                create_by="1",
                create_time=90,
                update_time=90,
                delete_flag=0,
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info=json.dumps({"chart-1": {"datasource": 2, "sql": "select 1"}}),
            )
        )
        session.add(
            CoreDashboard(
                id="template-dashboard",
                tenant_id=dashboard_service.DEFAULT_TENANT_ID,
                name="平台模板",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                source=dashboard_service.DASHBOARD_SOURCE_PLATFORM_TEMPLATE,
                status=dashboard_service.DASHBOARD_STATUS_ACTIVE,
                remark="source_dashboard_id=source-dashboard;source_tenant_id=2",
                content_id="0",
                create_by="9",
                create_time=100,
                update_time=100,
                delete_flag=0,
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info=json.dumps({"chart-1": {"datasource": 2, "sql": "select 2"}}),
            )
        )
        session.commit()

        updated = dashboard_service.update_platform_dashboard_template(
            session=session,
            user=platform_admin,
            dashboard=CreateDashboard(
                id="template-dashboard",
                name="平台模板新版",
                node_type="leaf",
                type="dashboard",
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info=json.dumps({"chart-1": {"datasource": 2, "sql": "select 3"}}),
            ),
        )
        source = session.get(CoreDashboard, "source-dashboard")
        template = session.get(CoreDashboard, "template-dashboard")

    assert updated.id == "template-dashboard"
    assert updated.name == "平台模板新版"
    assert template.name == "平台模板新版"
    assert template.content_id == "0"
    assert json.loads(template.canvas_view_info)["chart-1"]["sql"] == "select 3"
    assert json.loads(template.canvas_view_info)["chart-1"]["datasource"] is None
    assert source.name == "来源看板"
    assert json.loads(source.canvas_view_info)["chart-1"]["sql"] == "select 1"


def test_platform_admin_deletes_template_without_touching_source_dashboard():
    engine = _engine_with_dashboard_table()
    platform_admin = SimpleNamespace(
        id=9,
        isAdmin=True,
        system_role="system_admin",
        tenant_id=None,
        tenant_role=None,
        workspace_status="platform_admin",
    )

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="source-dashboard",
                tenant_id=2,
                name="来源看板",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                status=dashboard_service.DASHBOARD_STATUS_ACTIVE,
                create_by="1",
                create_time=90,
                update_time=90,
                delete_flag=0,
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info=json.dumps({"chart-1": {"datasource": 2, "sql": "select 1"}}),
            )
        )
        session.add(
            CoreDashboard(
                id="template-dashboard",
                tenant_id=dashboard_service.DEFAULT_TENANT_ID,
                name="平台模板",
                pid="root",
                datasource=None,
                node_type="leaf",
                type="dashboard",
                source=dashboard_service.DASHBOARD_SOURCE_PLATFORM_TEMPLATE,
                status=dashboard_service.DASHBOARD_STATUS_ACTIVE,
                remark="source_dashboard_id=source-dashboard;source_tenant_id=2",
                content_id="0",
                create_by="9",
                create_time=100,
                update_time=100,
                delete_flag=0,
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info=json.dumps({"chart-1": {"datasource": None, "sql": "select 2"}}),
            )
        )
        session.commit()

        deleted = dashboard_service.delete_platform_dashboard_template(
            session=session,
            user=platform_admin,
            template_id="template-dashboard",
        )
        source = session.get(CoreDashboard, "source-dashboard")
        template = session.get(CoreDashboard, "template-dashboard")
        templates = dashboard_service.list_platform_dashboard_templates(session=session, user=platform_admin)

    assert deleted is True
    assert template.delete_flag == 1
    assert template.delete_by == "9"
    assert source.delete_flag == 0
    assert json.loads(source.canvas_view_info)["chart-1"]["sql"] == "select 1"
    assert templates == []


def test_platform_delegate_cannot_delete_platform_template():
    engine = _engine_with_dashboard_table()
    delegate_user = SimpleNamespace(
        id=9,
        isAdmin=True,
        system_role="system_admin",
        tenant_id=1,
        tenant_role="owner",
        workspace_status="platform_workspace_delegate",
    )

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="template-dashboard",
                tenant_id=dashboard_service.DEFAULT_TENANT_ID,
                name="平台模板",
                pid="root",
                datasource=None,
                node_type="leaf",
                type="dashboard",
                source=dashboard_service.DASHBOARD_SOURCE_PLATFORM_TEMPLATE,
                status=dashboard_service.DASHBOARD_STATUS_ACTIVE,
                create_by="9",
                create_time=100,
                delete_flag=0,
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info="{}",
            )
        )
        session.commit()

        with pytest.raises(HTTPException) as exc_info:
            dashboard_service.delete_platform_dashboard_template(
                session=session,
                user=delegate_user,
                template_id="template-dashboard",
            )
        template = session.get(CoreDashboard, "template-dashboard")

    assert exc_info.value.status_code == 403
    assert template.delete_flag == 0


def test_platform_template_load_repairs_legacy_loading_template_snapshot(monkeypatch):
    engine = _engine_with_dashboard_table()
    platform_admin = SimpleNamespace(
        id=9,
        isAdmin=True,
        system_role="system_admin",
        tenant_id=None,
        tenant_role=None,
        workspace_status="platform_admin",
    )
    monkeypatch.setattr(dashboard_service, "_user_name", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        dashboard_service,
        "_platform_template_source_user_context",
        lambda *args, **kwargs: platform_admin,
    )
    monkeypatch.setattr(
        dashboard_service,
        "_materialize_dashboard_template_canvas_view_info",
        lambda _session, _user, _dashboard, canvas_view_info: (
            dashboard_service._prepare_dashboard_template_canvas_view_info(canvas_view_info)
        ),
    )

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="source-dashboard",
                tenant_id=2,
                name="来源看板",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                status=dashboard_service.DASHBOARD_STATUS_ACTIVE,
                create_by="1",
                create_time=90,
                update_time=90,
                delete_flag=0,
                component_data=json.dumps([{"id": "source-chart", "component": "SQView"}]),
                canvas_style_data="{}",
                canvas_view_info=json.dumps(
                    {
                        "source-chart": {
                            "id": "source-chart",
                            "datasource": 2,
                            "sql": "select 1",
                            "status": "success",
                            "data": {"fields": ["v"], "data": [{"v": 7}]},
                            "fields": ["v"],
                            "chart": {"id": "source-chart", "title": "来源图表"},
                        }
                    }
                ),
            )
        )
        session.add(
            CoreDashboard(
                id="template-dashboard",
                tenant_id=dashboard_service.DEFAULT_TENANT_ID,
                name="平台模板",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                source=dashboard_service.DASHBOARD_SOURCE_PLATFORM_TEMPLATE,
                status=dashboard_service.DASHBOARD_STATUS_ACTIVE,
                remark="source_dashboard_id=source-dashboard;source_tenant_id=2",
                content_id="source-dashboard",
                create_by="9",
                create_time=100,
                update_time=100,
                delete_flag=0,
                component_data=json.dumps([{"id": "legacy-chart", "component": "SQView"}]),
                canvas_style_data="{}",
                canvas_view_info=json.dumps(
                    {
                        "legacy-chart": {
                            "id": "legacy-chart",
                            "datasource": 2,
                            "sql": "select 1",
                            "status": "loading",
                            "data": {"fields": [], "data": []},
                            "fields": [],
                        }
                    }
                ),
            )
        )
        session.commit()

        loaded = dashboard_service.load_platform_dashboard_template(
            session=session,
            user=platform_admin,
            template_id="template-dashboard",
        )
        template = session.get(CoreDashboard, "template-dashboard")

    assert template.datasource is None
    assert template.content_id == "0"
    loaded_views = json.loads(loaded["canvas_view_info"])
    assert len(loaded_views) == 1
    repaired_chart = next(iter(loaded_views.values()))
    assert repaired_chart["datasource"] is None
    assert repaired_chart["status"] == "success"
    assert repaired_chart["data"]["data"] == [{"v": 7}]


def test_platform_template_copy_to_workspace_creates_independent_workspace_dashboard(monkeypatch):
    engine = _engine_with_dashboard_table()
    delegate_user = SimpleNamespace(
        id=9,
        isAdmin=True,
        system_role="system_admin",
        tenant_id=1,
        tenant_role="owner",
        workspace_status="platform_workspace_delegate",
    )
    monkeypatch.setattr(dashboard_service, "get_bound_datasource_id_for_tenant", lambda *args, **kwargs: 3)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 3)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="template-dashboard",
                tenant_id=dashboard_service.DEFAULT_TENANT_ID,
                name="平台模板",
                pid="root",
                datasource=None,
                node_type="leaf",
                type="dashboard",
                source=dashboard_service.DASHBOARD_SOURCE_PLATFORM_TEMPLATE,
                status=dashboard_service.DASHBOARD_STATUS_ACTIVE,
                create_by="9",
                create_time=100,
                delete_flag=0,
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info=json.dumps({"chart-1": {"datasource": None, "sql": "select 1"}}),
            )
        )
        session.commit()

        copied = dashboard_service.copy_platform_template_to_workspace_dashboard(
            session=session,
            user=delegate_user,
            template_id="template-dashboard",
        )
        duplicate_copy = dashboard_service.copy_platform_template_to_workspace_dashboard(
            session=session,
            user=delegate_user,
            template_id="template-dashboard",
            name="重复看板",
        )
        workspace_dashboards = [
            item
            for item in session.exec(select(CoreDashboard)).all()
            if item.source != dashboard_service.DASHBOARD_SOURCE_PLATFORM_TEMPLATE
        ]
        copied_record = session.get(CoreDashboard, copied.id)
        template_record = session.get(CoreDashboard, "template-dashboard")

    assert copied.id != "template-dashboard"
    assert duplicate_copy.id == copied.id
    assert len(workspace_dashboards) == 1
    assert copied.tenant_id == 1
    assert copied.datasource == 3
    assert copied.status == dashboard_service.DASHBOARD_STATUS_ACTIVE
    assert copied.source is None
    assert copied.remark == "source_template_id=template-dashboard"
    assert copied.create_by == "1"
    assert copied.update_by == "1"
    assert json.loads(copied_record.canvas_view_info)["chart-1"]["datasource"] == 3
    assert json.loads(template_record.canvas_view_info)["chart-1"]["datasource"] is None


def test_platform_template_copy_to_workspace_deduplicates_templates_with_same_source(monkeypatch):
    engine = _engine_with_dashboard_table()
    delegate_user = SimpleNamespace(
        id=9,
        isAdmin=True,
        system_role="system_admin",
        tenant_id=1,
        tenant_role="owner",
        workspace_status="platform_workspace_delegate",
    )
    monkeypatch.setattr(dashboard_service, "get_bound_datasource_id_for_tenant", lambda *args, **kwargs: 3)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 3)

    with Session(engine) as session:
        session.add_all(
            [
                CoreDashboard(
                    id="template-dashboard-a",
                    tenant_id=dashboard_service.DEFAULT_TENANT_ID,
                    name="平台模板 A",
                    pid="root",
                    datasource=None,
                    node_type="leaf",
                    type="dashboard",
                    source=dashboard_service.DASHBOARD_SOURCE_PLATFORM_TEMPLATE,
                    status=dashboard_service.DASHBOARD_STATUS_ACTIVE,
                    remark="source_dashboard_id=source-dashboard;source_tenant_id=2;source_datasource_id=8",
                    create_by="9",
                    create_time=100,
                    delete_flag=0,
                    component_data="[]",
                    canvas_style_data="{}",
                    canvas_view_info=json.dumps({"chart-1": {"datasource": None, "sql": "select 1"}}),
                ),
                CoreDashboard(
                    id="template-dashboard-b",
                    tenant_id=dashboard_service.DEFAULT_TENANT_ID,
                    name="平台模板 B",
                    pid="root",
                    datasource=None,
                    node_type="leaf",
                    type="dashboard",
                    source=dashboard_service.DASHBOARD_SOURCE_PLATFORM_TEMPLATE,
                    status=dashboard_service.DASHBOARD_STATUS_ACTIVE,
                    remark="source_dashboard_id=source-dashboard;source_tenant_id=2;source_datasource_id=8",
                    create_by="9",
                    create_time=101,
                    delete_flag=0,
                    component_data="[]",
                    canvas_style_data="{}",
                    canvas_view_info=json.dumps({"chart-1": {"datasource": None, "sql": "select 2"}}),
                ),
            ]
        )
        session.commit()

        copied = dashboard_service.copy_platform_template_to_workspace_dashboard(
            session=session,
            user=delegate_user,
            template_id="",
            template_ids=["template-dashboard-a", "template-dashboard-b"],
        )
        workspace_dashboards = [
            item
            for item in session.exec(select(CoreDashboard)).all()
            if item.source != dashboard_service.DASHBOARD_SOURCE_PLATFORM_TEMPLATE
        ]
        copied_record = workspace_dashboards[0]

    assert isinstance(copied, list)
    assert len(copied) == 1
    assert len(workspace_dashboards) == 1
    assert copied[0].id == copied_record.id
    assert copied_record.remark == (
        "source_template_id=template-dashboard-a;"
        "source_dashboard_id=source-dashboard;"
        "source_tenant_id=2;"
        "source_datasource_id=8"
    )


def test_project_viewer_sees_copied_default_dashboard_but_not_admin_default(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)
    monkeypatch.setattr(dashboard_service, "has_datasource_access", lambda *args, **kwargs: True)
    monkeypatch.setattr(dashboard_service, "datasource_bound_to_tenant", lambda *args, **kwargs: True)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="default-dashboard",
                name="默认看板",
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
        session.commit()

        copied = dashboard_service.copy_default_resource(
            session=session,
            user=current_user,
            request=DashboardDefaultCopyRequest(dashboard_id="default-dashboard"),
        )
        tree = dashboard_service.list_resource(
            session=session,
            dashboard=QueryDashboard(datasource=2),
            current_user=current_user,
        )

    assert copied.create_by == "2"
    assert copied.is_default == 0
    assert [node.id for node in tree] == [copied.id]
    assert tree[0].name == "默认看板"


def test_default_dashboard_load_is_readonly_for_non_owner_member(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="member")
    monkeypatch.setattr(dashboard_service, "has_datasource_access", lambda *args, **kwargs: True)
    monkeypatch.setattr(dashboard_service, "has_datasource_role", lambda *args, **kwargs: True)
    monkeypatch.setattr(dashboard_service, "_user_name", lambda *args, **kwargs: None)
    monkeypatch.setattr(dashboard_service, "_execute_dashboard_chart_sql", lambda *args, **kwargs: {
        "status": "success",
        "data": [],
        "fields": [],
        "message": "",
    })

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="default-dashboard",
                name="管理员推荐看板",
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
        session.commit()

        resource = dashboard_service.load_default_resource(
            session=session,
            dashboard=QueryDashboard(id="default-dashboard"),
            current_user=current_user,
        )

    assert resource["can_edit"] is False
    assert resource["can_share"] is False
    assert resource["can_set_default"] is False


def test_workspace_owner_can_edit_own_default_dashboard_with_workspace_role(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(
        id=2,
        isAdmin=False,
        tenant_id=1,
        tenant_role=None,
        workspace_role="owner",
    )
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)
    monkeypatch.setattr(dashboard_service, "has_datasource_access", lambda *args, **kwargs: True)
    monkeypatch.setattr(dashboard_service, "_user_name", lambda *args, **kwargs: None)
    monkeypatch.setattr(dashboard_service, "_execute_dashboard_chart_sql", lambda *args, **kwargs: {
        "status": "success",
        "data": [],
        "fields": [],
        "message": "",
    })

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="owner-default-dashboard",
                name="空间所有者默认看板",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                create_by="2",
                create_time=100,
                delete_flag=0,
                is_default=1,
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info="{}",
            )
        )
        session.commit()

        resource = dashboard_service.load_resource(
            session=session,
            dashboard=QueryDashboard(id="owner-default-dashboard"),
            current_user=current_user,
        )
        updated = dashboard_service.update_canvas(
            session=session,
            user=current_user,
            dashboard=CreateDashboard(
                id="owner-default-dashboard",
                name="已修改的默认看板",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info="{}",
            ),
        )

    assert resource["can_edit"] is True
    assert resource["can_set_default"] is True
    assert updated.name == "已修改的默认看板"
    assert updated.update_by == "2"


def test_my_dashboard_list_includes_default_folder_ancestor_for_visible_dashboard(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="owner")
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="admin-default-dashboard",
                name="管理员推荐看板",
                pid="admin-default-folder",
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
            CoreDashboard(
                id="admin-default-folder",
                name="管理员推荐目录",
                pid="root",
                datasource=2,
                node_type="folder",
                type="dashboard",
                create_by="2",
                create_time=101,
                delete_flag=0,
                is_default=1,
            )
        )
        session.commit()

        tree = dashboard_service.list_resource(
            session=session,
            dashboard=QueryDashboard(datasource=2),
            current_user=current_user,
        )

    assert [node.id for node in tree] == ["admin-default-folder"]
    assert tree[0].can_edit is True
    assert tree[0].can_set_default is True
    assert [node.id for node in tree[0].children] == ["admin-default-dashboard"]


def test_reorder_my_scope_can_move_recommended_dashboard_under_my_folder(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="owner")
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="my-folder",
                name="我的目录",
                pid="root",
                datasource=2,
                node_type="folder",
                type="dashboard",
                create_by="2",
                create_time=100,
                delete_flag=0,
                is_default=0,
            )
        )
        session.add(
            CoreDashboard(
                id="my-recommended-dashboard",
                name="已推荐的我的看板",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                create_by="2",
                create_time=101,
                delete_flag=0,
                is_default=1,
            )
        )
        session.commit()

        dashboard_service.reorder_resources(
            session=session,
            user=current_user,
            request=dashboard_service.DashboardReorderRequest(
                scope="my",
                items=[
                    {"id": "my-folder", "pid": "root", "sort": 1},
                    {"id": "my-recommended-dashboard", "pid": "my-folder", "sort": 1},
                ],
            ),
        )
        tree = dashboard_service.list_resource(
            session=session,
            dashboard=QueryDashboard(datasource=2),
            current_user=current_user,
        )
        moved = session.get(CoreDashboard, "my-recommended-dashboard")
        moved_position = session.exec(
            select(CoreDashboardTree).where(
                CoreDashboardTree.scope == "my",
                CoreDashboardTree.dashboard_id == "my-recommended-dashboard",
            )
        ).first()

    assert moved.pid == "root"
    assert moved_position.parent_id == "my-folder"
    assert [node.id for node in tree] == ["my-folder"]
    assert [node.id for node in tree[0].children] == ["my-recommended-dashboard"]


def test_default_list_includes_non_default_folder_ancestor():
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="owner")

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="my-folder",
                name="我的目录",
                pid="root",
                datasource=2,
                node_type="folder",
                type="dashboard",
                create_by="2",
                create_time=100,
                delete_flag=0,
                is_default=0,
            )
        )
        session.add(
            CoreDashboard(
                id="recommended-dashboard",
                name="已推荐的我的看板",
                pid="my-folder",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                create_by="2",
                create_time=101,
                delete_flag=0,
                is_default=1,
            )
        )
        session.commit()

        tree = dashboard_service.list_default_resources(
            session=session,
            current_user=current_user,
        )

    assert [node.id for node in tree] == ["my-folder"]
    assert tree[0].is_default is False
    assert [node.id for node in tree[0].children] == ["recommended-dashboard"]


def test_my_and_default_dashboard_trees_store_same_dashboard_independently(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="owner")
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)

    with Session(engine) as session:
        for record in [
            CoreDashboard(
                id="my-folder",
                name="我的目录",
                pid="root",
                datasource=2,
                node_type="folder",
                type="dashboard",
                create_by="2",
                create_time=100,
                delete_flag=0,
            ),
            CoreDashboard(
                id="default-folder",
                name="推荐目录",
                pid="root",
                datasource=2,
                node_type="folder",
                type="dashboard",
                create_by="2",
                create_time=101,
                delete_flag=0,
            ),
            CoreDashboard(
                id="dashboard-123",
                name="同一个看板",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                create_by="2",
                create_time=102,
                delete_flag=0,
                is_default=1,
            ),
        ]:
            session.add(record)
        session.commit()

        dashboard_service.reorder_resources(
            session=session,
            user=current_user,
            request=dashboard_service.DashboardReorderRequest(
                scope="my",
                items=[
                    {"id": "my-folder", "pid": "root", "sort": 1},
                    {"id": "dashboard-123", "pid": "my-folder", "sort": 1},
                ],
            ),
        )
        dashboard_service.reorder_resources(
            session=session,
            user=current_user,
            request=dashboard_service.DashboardReorderRequest(
                scope="default",
                items=[
                    {"id": "default-folder", "pid": "root", "sort": 1},
                    {"id": "dashboard-123", "pid": "default-folder", "sort": 1},
                ],
            ),
        )

        my_tree = dashboard_service.list_resource(
            session=session,
            dashboard=QueryDashboard(datasource=2),
            current_user=current_user,
        )
        default_tree = dashboard_service.list_default_resources(
            session=session,
            current_user=current_user,
        )
        positions = session.exec(
            select(CoreDashboardTree).where(CoreDashboardTree.dashboard_id == "dashboard-123")
        ).all()

    position_by_scope = {position.scope: position for position in positions}
    assert position_by_scope["my"].parent_id == "my-folder"
    assert position_by_scope["default"].parent_id == "default-folder"
    assert [node.id for node in my_tree] == ["my-folder"]
    assert [node.id for node in my_tree[0].children] == ["dashboard-123"]
    assert [node.id for node in default_tree] == ["default-folder"]
    assert default_tree[0].is_default is False
    assert default_tree[0].is_default_tree is True
    assert [node.id for node in default_tree[0].children] == ["dashboard-123"]


def test_reorder_default_scope_does_not_change_my_tree(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="owner")
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)

    with Session(engine) as session:
        for record in [
            CoreDashboard(
                id="my-folder",
                name="我的目录",
                pid="root",
                datasource=2,
                node_type="folder",
                type="dashboard",
                create_by="2",
                create_time=100,
                delete_flag=0,
            ),
            CoreDashboard(
                id="default-folder",
                name="推荐目录",
                pid="root",
                datasource=2,
                node_type="folder",
                type="dashboard",
                create_by="2",
                create_time=101,
                delete_flag=0,
            ),
            CoreDashboard(
                id="dashboard-123",
                name="同一个看板",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                create_by="2",
                create_time=102,
                delete_flag=0,
                is_default=1,
            ),
        ]:
            session.add(record)
        session.add(CoreDashboardTree(
            id="tree-my-folder",
            tenant_id=1,
            scope="my",
            dashboard_id="my-folder",
            parent_id="root",
            sort=1,
        ))
        session.add(CoreDashboardTree(
            id="tree-my-dashboard",
            tenant_id=1,
            scope="my",
            dashboard_id="dashboard-123",
            parent_id="my-folder",
            sort=1,
        ))
        session.commit()

        dashboard_service.reorder_resources(
            session=session,
            user=current_user,
            request=dashboard_service.DashboardReorderRequest(
                scope="default",
                items=[
                    {"id": "default-folder", "pid": "root", "sort": 1},
                    {"id": "dashboard-123", "pid": "default-folder", "sort": 1},
                ],
            ),
        )
        my_tree = dashboard_service.list_resource(
            session=session,
            dashboard=QueryDashboard(datasource=2),
            current_user=current_user,
        )
        default_tree = dashboard_service.list_default_resources(
            session=session,
            current_user=current_user,
        )

    assert [node.id for node in my_tree] == ["my-folder"]
    assert [node.id for node in my_tree[0].children] == ["dashboard-123"]
    assert [node.id for node in default_tree] == ["default-folder"]
    assert [node.id for node in default_tree[0].children] == ["dashboard-123"]


def test_non_owner_member_cannot_update_default_dashboard_even_with_project_editor_role(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="member")
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)
    monkeypatch.setattr(dashboard_service, "has_datasource_role", lambda *args, **kwargs: True)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="default-dashboard",
                name="管理员推荐看板",
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
        session.commit()

        with pytest.raises(HTTPException) as exc:
            dashboard_service.update_canvas(
                session=session,
                user=current_user,
                dashboard=CreateDashboard(
                    id="default-dashboard",
                    name="被成员修改",
                    pid="root",
                    datasource=2,
                    node_type="leaf",
                    type="dashboard",
                    component_data="[]",
                    canvas_style_data="{}",
                    canvas_view_info="{}",
                ),
            )

    assert exc.value.status_code == 403


def test_copy_default_dashboard_rekeys_canvas_components(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1, tenant_role="member")
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)
    monkeypatch.setattr(dashboard_service, "has_datasource_access", lambda *args, **kwargs: True)
    monkeypatch.setattr(dashboard_service, "datasource_bound_to_tenant", lambda *args, **kwargs: True)

    source_component_data = [
        {
            "id": "tab-1",
            "_dragId": "tab-1",
            "component": "SQTab",
            "activeTabName": "tab-pane-1",
            "propValue": [
                {
                    "name": "tab-pane-1",
                    "title": "趋势",
                    "componentData": [
                        {
                            "id": "chart-1",
                            "_dragId": "chart-1",
                            "component": "SQView",
                        }
                    ],
                }
            ],
        }
    ]
    source_canvas_view_info = {
        "chart-1": {
            "id": "chart-1",
            "sourceId": "",
            "datasource": 2,
            "sql": "select 1",
            "chart": {
                "id": "chart-1",
                "title": "趋势图",
                "type": "table",
            },
        }
    }

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="default-dashboard",
                name="管理员推荐看板",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                create_by="1",
                create_time=100,
                delete_flag=0,
                is_default=1,
                component_data=json.dumps(source_component_data),
                canvas_style_data="{}",
                canvas_view_info=json.dumps(source_canvas_view_info),
            )
        )
        session.commit()

        copied = dashboard_service.copy_default_resource(
            session=session,
            user=current_user,
            request=DashboardDefaultCopyRequest(dashboard_id="default-dashboard"),
        )
        source = session.get(CoreDashboard, "default-dashboard")

    copied_components = json.loads(copied.component_data)
    copied_tab = copied_components[0]
    copied_chart = copied_tab["propValue"][0]["componentData"][0]
    copied_view_info = json.loads(copied.canvas_view_info)
    copied_chart_id = copied_chart["id"]

    assert copied.id != "default-dashboard"
    assert copied.create_by == "2"
    assert copied.is_default == 0
    assert copied_tab["id"] != "tab-1"
    assert copied_tab["_dragId"] == copied_tab["id"]
    assert copied_tab["activeTabName"] != "tab-pane-1"
    assert copied_tab["activeTabName"] == copied_tab["propValue"][0]["name"]
    assert copied_chart_id != "chart-1"
    assert copied_chart["_dragId"] == copied_chart_id
    assert set(copied_view_info.keys()) == {copied_chart_id}
    assert copied_view_info[copied_chart_id]["id"] == copied_chart_id
    assert copied_view_info[copied_chart_id]["chart"]["id"] == copied_chart_id
    assert json.loads(source.component_data) == source_component_data
    assert json.loads(source.canvas_view_info) == source_canvas_view_info


def test_list_resource_marks_current_user_shared_dashboard(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="dashboard-1",
                name="我的看板",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                create_by="2",
                create_time=100,
                delete_flag=0,
            )
        )
        session.add(
            CoreDashboardShare(
                id="share-1",
                name="我的看板",
                datasource=2,
                share_type="dashboard",
                source_dashboard_id="dashboard-1",
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info="{}",
                create_by="2",
                update_by="2",
                create_time=101,
                update_time=101,
                delete_flag=0,
            )
        )
        session.commit()

        tree = dashboard_service.list_resource(
            session=session,
            dashboard=QueryDashboard(datasource=2),
            current_user=current_user,
        )

    assert len(tree) == 1
    assert tree[0].is_shared is True
    assert tree[0].share_id == "share-1"
    assert tree[0].can_share is True


def test_list_resource_includes_legacy_dashboard_when_canvas_uses_selected_datasource(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=1, isAdmin=True, tenant_id=1)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 1)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="legacy-dashboard",
                name="历史看板",
                pid="root",
                datasource=None,
                node_type="leaf",
                type="dashboard",
                create_by="2",
                create_time=100,
                delete_flag=0,
                canvas_view_info=json.dumps({"chart-1": {"datasource": 1, "sql": "select 1"}}),
            )
        )
        session.commit()

        tree = dashboard_service.list_resource(
            session=session,
            dashboard=QueryDashboard(datasource=1),
            current_user=current_user,
        )

    assert len(tree) == 1
    assert tree[0].id == "legacy-dashboard"
    assert tree[0].datasource == 1


def test_load_resource_runs_legacy_chart_with_dashboard_datasource(monkeypatch):
    _allow_requested_chart_execution_datasource(monkeypatch)
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=1, isAdmin=True, tenant_id=1)
    chart_calls = []
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 1)
    monkeypatch.setattr(dashboard_service, "has_datasource_access", lambda *args, **kwargs: True)
    monkeypatch.setattr(dashboard_service, "has_datasource_role", lambda *args, **kwargs: False)
    monkeypatch.setattr(dashboard_service, "_user_name", lambda *args, **kwargs: "Administrator")
    monkeypatch.setattr(
        dashboard_service,
        "_execute_dashboard_chart_sql",
        lambda session, current_user, datasource_id, sql: chart_calls.append((datasource_id, sql))
        or {"status": "success", "data": [{"value": 1}], "fields": ["value"], "message": ""},
    )

    with Session(engine) as session:
        _insert_simple_datasource_fixture(session, 1)
        session.add(
            CoreDashboard(
                id="dashboard-1",
                name="运营看板",
                pid="root",
                datasource=1,
                node_type="leaf",
                type="dashboard",
                create_by="1",
                create_time=100,
                delete_flag=0,
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info=json.dumps({"chart-1": {"datasource": None, "sql": "select 1"}}),
            )
        )
        session.commit()

        resource = dashboard_service.load_resource(
            session=session,
            dashboard=QueryDashboard(id="dashboard-1"),
            current_user=current_user,
        )

    canvas_view_info = json.loads(resource["canvas_view_info"])
    assert chart_calls == [(1, "select 1")]
    assert canvas_view_info["chart-1"]["datasource"] == 1
    assert canvas_view_info["chart-1"]["status"] == "success"
    assert canvas_view_info["chart-1"]["data"]["data"] == [{"value": 1}]


def test_load_resource_marks_refreshed_loading_chart_ready(monkeypatch):
    _allow_requested_chart_execution_datasource(monkeypatch)
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=1, isAdmin=True, tenant_id=1)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 1)
    monkeypatch.setattr(dashboard_service, "has_datasource_access", lambda *args, **kwargs: True)
    monkeypatch.setattr(dashboard_service, "has_datasource_role", lambda *args, **kwargs: False)
    monkeypatch.setattr(dashboard_service, "_user_name", lambda *args, **kwargs: "Administrator")
    monkeypatch.setattr(
        dashboard_service,
        "_execute_dashboard_chart_sql",
        lambda *args, **kwargs: {
            "status": "success",
            "data": [{"step": "首次战斗", "rate": 97.58}],
            "fields": ["step", "rate"],
            "message": "",
        },
    )

    with Session(engine) as session:
        _insert_simple_datasource_fixture(session, 1)
        session.add(
            CoreDashboard(
                id="dashboard-loading",
                name="旧加载状态看板",
                pid="root",
                datasource=1,
                node_type="leaf",
                type="dashboard",
                create_by="1",
                create_time=100,
                delete_flag=0,
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info=json.dumps(
                    {
                        "chart-1": {
                            "datasource": 1,
                            "sql": "select step, rate from funnel",
                            "data": {"data": [], "fields": []},
                            "fields": [],
                            "status": "loading",
                            "dataState": "loading",
                            "loadingProgress": 0,
                        }
                    }
                ),
            )
        )
        session.commit()

        resource = dashboard_service.load_resource(
            session=session,
            dashboard=QueryDashboard(id="dashboard-loading"),
            current_user=current_user,
        )

    chart = json.loads(resource["canvas_view_info"])["chart-1"]
    assert chart["status"] == "success"
    assert chart["dataState"] == "ready"
    assert chart["loadingProgress"] == 100
    assert chart["fields"] == ["step", "rate"]
    assert chart["data"]["fields"] == ["step", "rate"]
    assert chart["data"]["data"] == [{"step": "首次战斗", "rate": 97.58}]


def test_load_resource_infers_legacy_dashboard_datasource_from_canvas_items(monkeypatch):
    _allow_requested_chart_execution_datasource(monkeypatch)
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=True, tenant_id=1)
    chart_calls = []
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 1)
    monkeypatch.setattr(dashboard_service, "has_datasource_access", lambda *args, **kwargs: True)
    monkeypatch.setattr(dashboard_service, "has_datasource_role", lambda *args, **kwargs: False)
    monkeypatch.setattr(dashboard_service, "_user_name", lambda *args, **kwargs: "Administrator")
    monkeypatch.setattr(
        dashboard_service,
        "_execute_dashboard_chart_sql",
        lambda session, current_user, datasource_id, sql: chart_calls.append((datasource_id, sql))
        or {"status": "success", "data": [{"value": 1}], "fields": ["value"], "message": ""},
    )

    with Session(engine) as session:
        _insert_simple_datasource_fixture(session, 1)
        session.add(
            CoreDashboard(
                id="legacy-dashboard",
                name="历史看板",
                pid="root",
                datasource=None,
                node_type="leaf",
                type="dashboard",
                create_by="2",
                create_time=100,
                delete_flag=0,
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info=json.dumps(
                    {
                        "chart-1": {"datasource": 1, "sql": "select 1"},
                        "chart-2": {"datasource": None, "sql": "select 2"},
                    }
                ),
            )
        )
        session.commit()

        resource = dashboard_service.load_resource(
            session=session,
            dashboard=QueryDashboard(id="legacy-dashboard"),
            current_user=current_user,
        )

    canvas_view_info = json.loads(resource["canvas_view_info"])
    assert resource["datasource"] == 1
    assert chart_calls == [(1, "select 1"), (1, "select 2")]
    assert canvas_view_info["chart-2"]["datasource"] == 1


def test_project_editor_can_create_dashboard(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=3)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)
    monkeypatch.setattr(dashboard_service, "has_datasource_access", lambda *args, **kwargs: True)
    monkeypatch.setattr(dashboard_service, "has_datasource_role", lambda *args, **kwargs: True)

    with Session(engine) as session:
        record = dashboard_service.create_resource(
            session=session,
            user=current_user,
            dashboard=CreateDashboard(
                name="项目看板",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
            ),
        )

        assert record.datasource == 2
        assert record.create_by == "2"
        assert record.tenant_id == 3


def test_dashboard_create_base_info_normalizes_default_flag():
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=3)

    record = dashboard_service.get_create_base_info(
        current_user,
        CreateDashboard(
            name="项目看板",
            pid="root",
            datasource=2,
            node_type="leaf",
            type="dashboard",
            is_default=False,
        ),
    )

    assert record.is_default == 0
    assert not isinstance(record.is_default, bool)


def test_create_canvas_normalizes_materialized_loading_chart_state(monkeypatch):
    _allow_requested_chart_execution_datasource(monkeypatch)
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 1)
    monkeypatch.setattr(dashboard_service, "has_datasource_access", lambda *args, **kwargs: True)

    canvas_view_info = {
        "chart-1": {
            "id": "chart-1",
            "datasource": 1,
            "sql": "select step, rate from funnel",
            "data": {
                "data": [{"step": "首次战斗", "rate": 97.58}],
                "fields": [],
            },
            "fields": ["step", "rate"],
            "status": "success",
            "dataState": "loading",
            "loadingProgress": 0,
        }
    }

    with Session(engine) as session:
        record = dashboard_service.create_canvas(
            session=session,
            user=current_user,
            dashboard=CreateDashboard(
                name="项目看板",
                pid="root",
                datasource=1,
                node_type="leaf",
                type="dashboard",
                component_data=json.dumps([{"id": "chart-1", "component": "SQView"}]),
                canvas_style_data="{}",
                canvas_view_info=json.dumps(canvas_view_info),
            ),
        )

    chart = json.loads(record.canvas_view_info)["chart-1"]
    assert chart["status"] == "success"
    assert chart["dataState"] == "ready"
    assert chart["loadingProgress"] == 100
    assert chart["data"]["data"] == [{"step": "首次战斗", "rate": 97.58}]


def test_project_viewer_can_create_own_dashboard(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)
    monkeypatch.setattr(dashboard_service, "has_datasource_access", lambda *args, **kwargs: True)

    with Session(engine) as session:
        record = dashboard_service.create_resource(
            session=session,
            user=current_user,
            dashboard=CreateDashboard(
                name="项目看板",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
            ),
        )

        assert record.datasource == 2
        assert record.create_by == "2"


def test_create_dashboard_with_external_mcp_id_uses_external_mcp_source(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    sql_access_calls = []

    monkeypatch.setattr(
        dashboard_service,
        "external_mcp_bound_to_tenant",
        lambda session, external_mcp_server_id, tenant_id: int(external_mcp_server_id) == 88 and int(tenant_id) == 1,
    )
    monkeypatch.setattr(
        dashboard_service,
        "_ensure_datasource_access",
        lambda *args, **kwargs: sql_access_calls.append(args) or 2,
    )
    monkeypatch.setattr(dashboard_service, "has_datasource_access", lambda *args, **kwargs: True)

    with Session(engine) as session:
        record = dashboard_service.create_resource(
            session=session,
            user=current_user,
            dashboard=CreateDashboard(
                name="ChatMon 告警",
                pid="root",
                datasource=2,
                external_mcp_server_id=88,
                node_type="leaf",
                type="dashboard",
            ),
        )

        assert record.source == dashboard_service.DASHBOARD_SOURCE_EXTERNAL_MCP
        assert record.external_mcp_server_id == 88
        assert record.datasource is None
        assert sql_access_calls == []


def test_project_editor_cannot_rename_other_users_dashboard(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)
    monkeypatch.setattr(dashboard_service, "has_datasource_role", lambda *args, **kwargs: True)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="dashboard-1",
                name="旧名称",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                create_by="1",
                create_time=100,
                delete_flag=0,
            )
        )
        session.commit()

        with pytest.raises(HTTPException) as exc:
            dashboard_service.update_resource(
                session=session,
                user=current_user,
                dashboard=QueryDashboard(id="dashboard-1", name="新名称"),
            )

    assert exc.value.status_code == 403


def test_project_viewer_cannot_rename_dashboard(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)
    monkeypatch.setattr(dashboard_service, "has_datasource_role", lambda *args, **kwargs: False)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="dashboard-1",
                name="旧名称",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                create_by="1",
                create_time=100,
                delete_flag=0,
            )
        )
        session.commit()

        with pytest.raises(HTTPException) as exc:
            dashboard_service.update_resource(
                session=session,
                user=current_user,
                dashboard=QueryDashboard(id="dashboard-1", name="新名称"),
            )

    assert exc.value.status_code == 403


def test_project_viewer_can_rename_own_dashboard(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)
    monkeypatch.setattr(dashboard_service, "has_datasource_role", lambda *args, **kwargs: False)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="dashboard-1",
                name="旧名称",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                create_by="2",
                create_time=100,
                delete_flag=0,
            )
        )
        session.commit()

        record = dashboard_service.update_resource(
            session=session,
            user=current_user,
            dashboard=QueryDashboard(id="dashboard-1", name="新名称"),
        )

        assert record.name == "新名称"
        assert record.update_by == "2"


def test_validate_name_allows_update_when_name_unchanged(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)
    monkeypatch.setattr(dashboard_service, "has_datasource_role", lambda *args, **kwargs: False)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="dashboard-1",
                name="留存相关",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                create_by="2",
                create_time=100,
                delete_flag=0,
            )
        )
        session.commit()

        assert dashboard_service.validate_name(
            session=session,
            user=current_user,
            dashboard=QueryDashboard(id="dashboard-1", name="留存相关", opt="updateLeaf", datasource=2),
        ) is True


def test_validate_name_checks_external_mcp_dashboard_scope(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    sql_access_calls = []

    monkeypatch.setattr(
        dashboard_service,
        "external_mcp_bound_to_tenant",
        lambda session, external_mcp_server_id, tenant_id: int(external_mcp_server_id) == 88 and int(tenant_id) == 1,
    )
    monkeypatch.setattr(
        dashboard_service,
        "_ensure_datasource_access",
        lambda *args, **kwargs: sql_access_calls.append(args) or 2,
    )

    with Session(engine) as session:
        session.add_all([
            CoreDashboard(
                id="sql-dashboard",
                name="重复名称",
                pid="root",
                datasource=2,
                node_type="leaf",
                type="dashboard",
                create_by="2",
                create_time=100,
                delete_flag=0,
            ),
            CoreDashboard(
                id="other-external-dashboard",
                name="重复名称",
                pid="root",
                datasource=None,
                external_mcp_server_id=99,
                source=dashboard_service.DASHBOARD_SOURCE_EXTERNAL_MCP,
                node_type="leaf",
                type="dashboard",
                create_by="2",
                create_time=100,
                delete_flag=0,
            ),
        ])
        session.commit()

        assert dashboard_service.validate_name(
            session=session,
            user=current_user,
            dashboard=QueryDashboard(
                name="重复名称",
                opt="newLeaf",
                external_mcp_server_id=88,
                node_type="leaf",
                type="dashboard",
            ),
        ) is True

        session.add(
            CoreDashboard(
                id="same-external-dashboard",
                name="重复名称",
                pid="root",
                datasource=None,
                external_mcp_server_id=88,
                source=dashboard_service.DASHBOARD_SOURCE_EXTERNAL_MCP,
                node_type="leaf",
                type="dashboard",
                create_by="2",
                create_time=100,
                delete_flag=0,
            )
        )
        session.commit()

        assert dashboard_service.validate_name(
            session=session,
            user=current_user,
            dashboard=QueryDashboard(
                name="重复名称",
                opt="newLeaf",
                external_mcp_server_id=88,
                node_type="leaf",
                type="dashboard",
            ),
        ) is False
        assert sql_access_calls == []


def test_project_viewer_cannot_create_under_folder_they_cannot_edit(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 2)
    monkeypatch.setattr(dashboard_service, "has_datasource_access", lambda *args, **kwargs: True)
    monkeypatch.setattr(dashboard_service, "has_datasource_role", lambda *args, **kwargs: False)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="folder-1",
                name="公共目录",
                pid="root",
                datasource=2,
                node_type="folder",
                type="dashboard",
                create_by="1",
                create_time=100,
                delete_flag=0,
            )
        )
        session.commit()

        with pytest.raises(HTTPException) as exc:
            dashboard_service.create_resource(
                session=session,
                user=current_user,
                dashboard=CreateDashboard(
                    name="项目看板",
                    pid="folder-1",
                    datasource=2,
                    node_type="leaf",
                    type="dashboard",
                ),
            )

    assert exc.value.status_code == 403


def test_dashboard_load_denies_chart_sql_with_unauthorized_table(monkeypatch):
    _force_bound_chart_execution_datasource(monkeypatch)
    engine = _engine_with_dashboard_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    exec_calls = []
    monkeypatch.setattr(
        query_executor,
        "_unsafe_exec_sql_after_validation",
        lambda ds, sql, origin_column=False: exec_calls.append(sql)
        or {"data": [{"payment_id": 1}], "fields": ["payment_id"]},
    )
    monkeypatch.setattr(dashboard_service, "_user_name", lambda *args, **kwargs: "Viewer")

    with Session(engine) as session:
        _insert_dashboard_permission_fixture(session)
        _insert_orders_column_rule(session)
        _insert_payments_table_deny_rule(session)
        session.add(
            CoreDashboard(
                id="dashboard-1",
                name="项目看板",
                pid="root",
                datasource=1,
                node_type="leaf",
                type="dashboard",
                create_by="2",
                create_time=100,
                delete_flag=0,
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info=json.dumps(
                    {"chart-1": {"datasource": 1, "sql": "select payment_id from payments"}}
                ),
            )
        )
        session.commit()

        resource = dashboard_service.load_resource(
            session=session,
            dashboard=QueryDashboard(id="dashboard-1"),
            current_user=current_user,
        )

    chart = json.loads(resource["canvas_view_info"])["chart-1"]
    assert exec_calls == []
    assert chart["status"] == "failed"
    assert chart["message"] == "没有查看权限"
    assert "payments" not in chart["message"]


def test_dashboard_structure_load_clears_unauthorized_chart_snapshot(monkeypatch):
    _force_bound_chart_execution_datasource(monkeypatch)
    engine = _engine_with_dashboard_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    exec_calls = []
    monkeypatch.setattr(
        query_executor,
        "_unsafe_exec_sql_after_validation",
        lambda ds, sql, origin_column=False: exec_calls.append(sql)
        or {"data": [{"amount": 99}], "fields": ["amount"]},
    )
    monkeypatch.setattr(
        dashboard_service,
        "safe_query_error_type",
        lambda _current_user, _message: "permission_denied",
    )
    monkeypatch.setattr(dashboard_service, "_user_name", lambda *args, **kwargs: "Viewer")

    with Session(engine) as session:
        _insert_dashboard_permission_fixture(session)
        _insert_orders_column_rule(session)
        session.add(
            CoreDashboard(
                id="dashboard-1",
                name="项目看板",
                pid="root",
                datasource=1,
                node_type="leaf",
                type="dashboard",
                create_by="2",
                create_time=100,
                delete_flag=0,
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info=json.dumps(
                    {
                        "chart-1": {
                            "datasource": 1,
                            "sql": "select amount from orders",
                            "status": "success",
                            "dataState": "ready",
                            "fields": ["amount"],
                            "data": {"fields": ["amount"], "data": [{"amount": 99}]},
                        }
                    }
                ),
            )
        )
        session.commit()

        resource = dashboard_service.load_resource(
            session=session,
            dashboard=QueryDashboard(id="dashboard-1", include_data=False),
            current_user=current_user,
        )

    chart = json.loads(resource["canvas_view_info"])["chart-1"]
    assert exec_calls == []
    assert chart["status"] == "failed"
    assert chart["error_type"] == "permission_denied"
    assert chart["message"] == "没有查看权限"
    assert chart["fields"] == []
    assert chart["data"]["fields"] == []
    assert chart["data"]["data"] == []


def test_dashboard_preview_denies_chart_sql_with_unauthorized_field(monkeypatch):
    _force_bound_chart_execution_datasource(monkeypatch)
    engine = _engine_with_dashboard_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    exec_calls = []
    monkeypatch.setattr(
        query_executor,
        "_unsafe_exec_sql_after_validation",
        lambda ds, sql, origin_column=False: exec_calls.append(sql)
        or {"data": [{"amount": 99}], "fields": ["amount"]},
    )

    with Session(engine) as session:
        _insert_dashboard_permission_fixture(session)
        _insert_orders_column_rule(session)
        session.commit()

        result = dashboard_service.preview_sql(
            session=session,
            current_user=current_user,
            request=DashboardSqlPreview(datasource=1, sql="select amount from orders"),
        )

    assert exec_calls == []
    assert result["status"] == "failed"
    assert result["message"] == "没有查看权限"
    assert "amount" not in result["message"]


def test_dashboard_preview_hides_date_filter_when_permission_is_denied(monkeypatch):
    _force_bound_chart_execution_datasource(monkeypatch)
    engine = _engine_with_dashboard_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(
        query_executor,
        "_unsafe_exec_sql_after_validation",
        lambda *_args, **_kwargs: pytest.fail("无权限 SQL 不应执行"),
    )

    with Session(engine) as session:
        _insert_dashboard_permission_fixture(session)
        _insert_orders_column_rule(session)
        session.commit()
        result = dashboard_service.preview_sql(
            session=session,
            current_user=current_user,
            request=DashboardSqlPreview(
                datasource=1,
                sql=(
                    "select amount from orders where order_id between "
                    "{{dashboard_start_yyyymmdd}} and {{dashboard_end_yyyymmdd}}"
                ),
                    pivot=DashboardPivotRequest(
                        enabled=False,
                        time_field="order_id",
                    ),
                    date_filter=DashboardDateFilterRequest(parameter_type="yyyymmdd_number"),
            ),
        )

    assert result["status"] == "failed"
    assert result["date_filter_capability"] == {
        "status": "forbidden",
        "reason": "permission_denied",
    }


def test_dashboard_preview_denies_unbounded_query_when_row_permission_applies(monkeypatch):
    _force_bound_chart_execution_datasource(monkeypatch)
    engine = _engine_with_dashboard_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    exec_calls = []
    monkeypatch.setattr(
        query_executor,
        "_unsafe_exec_sql_after_validation",
        lambda ds, sql, origin_column=False: exec_calls.append(sql)
        or {"data": [{"order_id": 1}], "fields": ["order_id"]},
    )

    with Session(engine) as session:
        _insert_dashboard_permission_fixture(session)
        _insert_orders_row_rule(session)
        session.commit()

        result = dashboard_service.preview_sql(
            session=session,
            current_user=current_user,
            request=DashboardSqlPreview(datasource=1, sql="select order_id from orders"),
        )

    assert result["status"] == "failed"
    assert result["error_type"] == "permission_denied"
    assert result["message"] == "没有查看权限"
    assert result["executed_sql"] is None
    assert exec_calls == []


@pytest.mark.parametrize(
    "sql",
    [
        "select order_id from orders where region in ('EU', 'US')",
        "select o.order_id from orders o where o.region in ('EU', 'US')",
        "select order_id from orders where region like '%S'",
        "select order_id from orders where region not like 'EU%'",
        "select order_id from orders where region = 'EU' or region = 'US'",
        (
            "with scoped as ("
            "select order_id, region, max(case when region = 'US' then 1 else 0 end) as denied "
            "from orders where region in ('EU', 'US') group by order_id, region"
            ") select order_id from scoped"
        ),
    ],
)
def test_dashboard_preview_denies_query_that_can_read_forbidden_rows(monkeypatch, sql):
    _force_bound_chart_execution_datasource(monkeypatch)
    engine = _engine_with_dashboard_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    exec_calls = []
    monkeypatch.setattr(
        query_executor,
        "_unsafe_exec_sql_after_validation",
        lambda ds, sql, origin_column=False: exec_calls.append(sql)
        or {"data": [{"order_id": 1}], "fields": ["order_id"]},
    )

    with Session(engine) as session:
        _insert_dashboard_permission_fixture(session)
        _insert_orders_row_rule(session)
        session.commit()

        result = dashboard_service.preview_sql(
            session=session,
            current_user=current_user,
            request=DashboardSqlPreview(datasource=1, sql=sql),
        )

    assert result["status"] == "failed"
    assert result["error_type"] == "permission_denied"
    assert result["message"] == "没有查看权限"
    assert result["executed_sql"] is None
    assert exec_calls == []


@pytest.mark.parametrize(
    "sql",
    [
        "select order_id from orders where region = 'EU'",
        "select o.order_id from orders o where o.region = 'EU'",
        "select order_id from orders where region in ('EU', 'APAC')",
        "select order_id from orders where region <> 'US'",
        "select order_id from orders where region not like '%US%'",
    ],
)
def test_dashboard_preview_executes_original_sql_when_forbidden_rows_are_excluded(monkeypatch, sql):
    _force_bound_chart_execution_datasource(monkeypatch)
    engine = _engine_with_dashboard_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    exec_calls = []
    monkeypatch.setattr(
        query_executor,
        "_unsafe_exec_sql_after_validation",
        lambda ds, sql, origin_column=False: exec_calls.append(sql)
        or {"data": [{"order_id": 1}], "fields": ["order_id"]},
    )

    with Session(engine) as session:
        _insert_dashboard_permission_fixture(session)
        _insert_orders_row_rule(session)
        session.commit()

        result = dashboard_service.preview_sql(
            session=session,
            current_user=current_user,
            request=DashboardSqlPreview(datasource=1, sql=sql),
        )

    assert result["status"] == "success"
    assert result["requested_sql"] == sql
    assert result["executed_sql"] == sql
    assert exec_calls == [sql]


def test_dashboard_preview_denies_select_star_when_fields_are_denied(monkeypatch):
    _force_bound_chart_execution_datasource(monkeypatch)
    engine = _engine_with_dashboard_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    exec_calls = []
    monkeypatch.setattr(
        query_executor,
        "_unsafe_exec_sql_after_validation",
        lambda ds, sql, origin_column=False: exec_calls.append(sql)
        or {"data": [{"order_id": 1}], "fields": ["order_id"]},
    )

    with Session(engine) as session:
        _insert_dashboard_permission_fixture(session)
        _insert_orders_column_rule(session)
        session.commit()

        result = dashboard_service.preview_sql(
            session=session,
            current_user=current_user,
            request=DashboardSqlPreview(datasource=1, sql="select * from orders"),
        )

    assert exec_calls == []
    assert result["status"] == "failed"
    assert result["message"] == "没有查看权限"


def test_dashboard_preview_builds_pivot_sql(monkeypatch):
    engine = _engine_with_dashboard_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    exec_calls = []
    _force_bound_chart_execution_datasource(monkeypatch)
    monkeypatch.setattr(
        query_executor,
        "_unsafe_exec_sql_after_validation",
        lambda ds, sql, origin_column=False: exec_calls.append(sql)
        or {"data": [{"order_day": "2026-06-01", "region": "US", "amount": 99}], "fields": ["order_day", "region", "amount"]},
    )

    with Session(engine) as session:
        _insert_dashboard_permission_fixture(session)
        session.commit()

        result = dashboard_service.preview_sql(
            session=session,
            current_user=current_user,
            request=DashboardSqlPreview(
                datasource=1,
                sql='select order_id as "order_day", amount, region from orders',
                pivot=DashboardPivotRequest(
                    enabled=True,
                    time_field="order_day",
                    metric_field="amount",
                        group_field="region",
                        group_enabled=True,
                        granularity="day",
                        aggregation="sum",
                ),
            ),
        )

    assert result["status"] == "success"
    assert len(exec_calls) == 1
    executed_sql = exec_calls[0]
    normalized_sql = executed_sql.lower()
    assert "FROM (" in executed_sql
    assert 'select order_id as "order_day", amount, region from orders' in executed_sql
    assert ') AS "pivot_src"' in executed_sql
    assert 'order_id as "order_day"' in normalized_sql
    assert 'SUM("pivot_src"."amount") AS "amount"' in executed_sql
    assert '"pivot_src"."region" AS "region"' in executed_sql
    assert 'WITH "pivot_src" AS' not in executed_sql
    assert '"pivot_bounds" AS' not in executed_sql
    assert 'CURRENT_DATE' not in executed_sql
    assert "GROUP BY" in executed_sql
    assert "LIMIT 1000" in executed_sql


def test_dashboard_preview_pivot_source_range_keeps_generated_time_window(monkeypatch):
    engine = _engine_with_dashboard_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    exec_calls = []
    monkeypatch.setattr(
        query_executor,
        "_unsafe_exec_sql_after_validation",
        lambda ds, sql, origin_column=False: exec_calls.append(sql)
        or {"data": [{"order_day": "2026-06-01", "amount": 99}], "fields": ["order_day", "amount"]},
    )

    with Session(engine) as session:
        _insert_dashboard_permission_fixture(session)
        session.commit()

        result = dashboard_service.preview_sql(
            session=session,
            current_user=current_user,
            request=DashboardSqlPreview(
                datasource=1,
                sql="select order_id as order_day, amount from orders where order_id >= 10",
                pivot=DashboardPivotRequest(
                    enabled=True,
                    time_field="order_day",
                    metric_field="amount",
                    granularity="day",
                    range="source",
                    aggregation="sum",
                ),
            ),
        )

    assert result["status"] == "success"
    assert len(exec_calls) == 1
    executed_sql = exec_calls[0]
    assert 'WITH "pivot_src"' not in executed_sql
    assert '"pivot_bounds"' not in executed_sql
    assert "CURRENT_DATE" not in executed_sql
    assert "where order_id >= 10" in executed_sql.lower()
    assert '\nWHERE CAST("pivot_src"."order_day" AS DATE)' not in executed_sql


def test_dashboard_preview_pivot_keeps_multiple_chart_metrics(monkeypatch):
    engine = _engine_with_dashboard_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    exec_calls = []
    monkeypatch.setattr(
        query_executor,
        "_unsafe_exec_sql_after_validation",
        lambda ds, sql, origin_column=False: exec_calls.append(sql)
        or {"data": [{"order_day": "2026-06-01", "ARPU": 10, "ARPPU": 20}], "fields": ["order_day", "ARPU", "ARPPU"]},
    )

    with Session(engine) as session:
        _insert_dashboard_permission_fixture(session)
        session.commit()

        result = dashboard_service.preview_sql(
            session=session,
            current_user=current_user,
            request=DashboardSqlPreview(
                datasource=1,
                sql='select order_id as order_day, amount as "ARPU", amount * 2 as "ARPPU" from orders',
                pivot=DashboardPivotRequest(
                    enabled=True,
                    time_field="order_day",
                    metric_fields=["ARPU", "ARPPU"],
                    granularity="day",
                    range="source",
                    aggregation="sum",
                ),
            ),
        )

    assert result["status"] == "success"
    assert len(exec_calls) == 1
    executed_sql = exec_calls[0]
    assert 'SUM("pivot_src"."ARPU") AS "ARPU"' in executed_sql
    assert 'SUM("pivot_src"."ARPPU") AS "ARPPU"' in executed_sql
    assert 'GROUP BY CAST("pivot_src"."order_day" AS DATE)' in executed_sql


def test_dashboard_preview_pivot_supports_metric_level_aggregations(monkeypatch):
    engine = _engine_with_dashboard_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    exec_calls = []
    monkeypatch.setattr(
        query_executor,
        "_unsafe_exec_sql_after_validation",
        lambda ds, sql, origin_column=False: exec_calls.append(sql)
        or {"data": [{"order_day": "2026-06-01", "revenue": 100, "ARPU": 10}], "fields": ["order_day", "revenue", "ARPU"]},
    )

    with Session(engine) as session:
        _insert_dashboard_permission_fixture(session)
        session.commit()

        result = dashboard_service.preview_sql(
            session=session,
            current_user=current_user,
            request=DashboardSqlPreview(
                datasource=1,
                sql='select order_id as order_day, amount as revenue, amount / 10.0 as "ARPU" from orders',
                pivot=DashboardPivotRequest(
                    enabled=True,
                    time_field="order_day",
                    metric_fields=["revenue", "ARPU"],
                    metric_aggregations={"revenue": "sum", "ARPU": "avg"},
                    granularity="week",
                    range="source",
                    aggregation="sum",
                ),
            ),
        )

    assert result["status"] == "success"
    executed_sql = exec_calls[0]
    assert 'SUM("pivot_src"."revenue") AS "revenue"' in executed_sql
    assert 'AVG("pivot_src"."ARPU") AS "ARPU"' in executed_sql


def test_dashboard_preview_pivot_week_and_month_change_period_sql(monkeypatch):
    engine = _engine_with_dashboard_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    exec_calls = []
    monkeypatch.setattr(
        query_executor,
        "_unsafe_exec_sql_after_validation",
        lambda ds, sql, origin_column=False: exec_calls.append(sql)
        or {"data": [{"order_day": "2026-06-01", "amount": 99}], "fields": ["order_day", "amount"]},
    )

    with Session(engine) as session:
        _insert_dashboard_permission_fixture(session)
        session.commit()

        for granularity in ("week", "month"):
            result = dashboard_service.preview_sql(
                session=session,
                current_user=current_user,
                request=DashboardSqlPreview(
                    datasource=1,
                    sql="select order_id as order_day, amount from orders",
                    pivot=DashboardPivotRequest(
                        enabled=True,
                        time_field="order_day",
                        metric_field="amount",
                        granularity=granularity,
                        range="source",
                        aggregation="sum",
                    ),
                ),
            )
            assert result["status"] == "success"

    assert len(exec_calls) == 2
    assert "DATE_TRUNC('week', CAST(\"pivot_src\".\"order_day\" AS TIMESTAMP))" in exec_calls[0]
    assert "DATE_TRUNC('month', CAST(\"pivot_src\".\"order_day\" AS TIMESTAMP))" in exec_calls[1]
    assert exec_calls[0] != exec_calls[1]


def test_dashboard_preview_pivot_custom_range_filters_literal_dates(monkeypatch):
    engine = _engine_with_dashboard_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    exec_calls = []
    monkeypatch.setattr(
        query_executor,
        "_unsafe_exec_sql_after_validation",
        lambda ds, sql, origin_column=False: exec_calls.append(sql)
        or {"data": [{"order_day": "2026-06-01", "amount": 99}], "fields": ["order_day", "amount"]},
    )

    with Session(engine) as session:
        _insert_dashboard_permission_fixture(session)
        session.commit()

        result = dashboard_service.preview_sql(
            session=session,
            current_user=current_user,
            request=DashboardSqlPreview(
                datasource=1,
                sql=(
                    "select order_id as order_day, amount from orders where order_id between "
                    "{{dashboard_start_yyyymmdd}} and {{dashboard_end_yyyymmdd}}"
                ),
                pivot=DashboardPivotRequest(
                    enabled=True,
                    time_field="order_day",
                    metric_field="amount",
                    granularity="day",
                    aggregation="sum",
                ),
                date_filter=DashboardDateFilterRequest(
                    parameter_type="yyyymmdd_number",
                    custom_start="2026-05-01",
                    custom_end="2026-05-31",
                ),
            ),
        )

    assert result["status"] == "success"
    assert len(exec_calls) == 1
    executed_sql = exec_calls[0]
    assert 'WITH "pivot_src"' not in executed_sql
    assert '"pivot_bounds"' not in executed_sql
    assert "20260501" in executed_sql
    assert "20260531" in executed_sql


def test_dashboard_preview_pivot_rejects_same_time_and_metric_field(monkeypatch):
    engine = _engine_with_dashboard_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    exec_calls = []
    monkeypatch.setattr(
        query_executor,
        "_unsafe_exec_sql_after_validation",
        lambda ds, sql, origin_column=False: exec_calls.append(sql)
        or {"data": [{"amount": 99}], "fields": ["amount"]},
    )

    with Session(engine) as session:
        _insert_dashboard_permission_fixture(session)
        session.commit()

        result = dashboard_service.preview_sql(
            session=session,
            current_user=current_user,
            request=DashboardSqlPreview(
                datasource=1,
                sql="select amount from orders",
                pivot=DashboardPivotRequest(
                    enabled=True,
                    time_field="amount",
                    metric_field="amount",
                    granularity="day",
                    range="source",
                    aggregation="sum",
                ),
            ),
        )

    assert result["status"] == "failed"
    assert "不能相同" in result["message"]
    assert "图表指标" in result["message"]
    assert exec_calls == []


def test_dashboard_preview_pivot_date_cast_error_returns_friendly_message(monkeypatch):
    engine = _engine_with_dashboard_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)

    def raise_date_cast_error(ds, sql, origin_column=False):
        raise RuntimeError(
            'psycopg2.errors.CannotCoerce: 无法把类型 numeric 转换为 date LINE 2: CAST("pivot_src"."ARPU" AS DATE)'
        )

    monkeypatch.setattr(query_executor, "_unsafe_exec_sql_after_validation", raise_date_cast_error)

    with Session(engine) as session:
        _insert_dashboard_permission_fixture(session)
        session.commit()

        result = dashboard_service.preview_sql(
            session=session,
            current_user=current_user,
            request=DashboardSqlPreview(
                datasource=1,
                sql='select order_id as "日期", amount as "ARPU" from orders',
                pivot=DashboardPivotRequest(
                    enabled=True,
                    time_field="ARPU",
                    metric_field="amount",
                    granularity="day",
                    range="source",
                    aggregation="sum",
                ),
            ),
        )

    assert result["status"] == "failed"
    assert result["message"] == "透视时间字段「ARPU」无法转换为日期/时间，请改选日期或时间字段；图表指标应选择数值字段。"
    assert "SELECT" not in result["message"]


def test_dashboard_preview_ignores_disabled_pivot(monkeypatch):
    engine = _engine_with_dashboard_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    exec_calls = []
    monkeypatch.setattr(
        query_executor,
        "_unsafe_exec_sql_after_validation",
        lambda ds, sql, origin_column=False: exec_calls.append(sql)
        or {"data": [{"order_id": 1}], "fields": ["order_id"]},
    )

    with Session(engine) as session:
        _insert_dashboard_permission_fixture(session)
        session.commit()

        result = dashboard_service.preview_sql(
            session=session,
            current_user=current_user,
            request=DashboardSqlPreview(
                datasource=1,
                sql="select order_id from orders",
                pivot=DashboardPivotRequest(
                    enabled=False,
                    time_field="order_id",
                    metric_field="order_id",
                ),
            ),
        )

    assert result["status"] == "success"
    assert exec_calls == ["select order_id from orders"]


def test_dashboard_preview_missing_date_filter_does_not_execute(monkeypatch):
    monkeypatch.setattr(dashboard_service, "resolve_chart_execution_datasource", lambda *_args: 1)
    monkeypatch.setattr(
        dashboard_service,
        "_execute_dashboard_chart_sql",
        lambda *_args, **_kwargs: pytest.fail("缺少日期配置时不得执行 SQL"),
    )

    result = dashboard_service.preview_sql(
        session=SimpleNamespace(get=lambda *_args: SimpleNamespace(id=1, type="mysql")),
        current_user=SimpleNamespace(id=2, isAdmin=False, tenant_id=1),
        request=DashboardSqlPreview(
            datasource=1,
            sql=(
                "select dt from orders where dt between "
                "{{dashboard_start_yyyymmdd}} and {{dashboard_end_yyyymmdd}}"
            ),
            pivot=DashboardPivotRequest(enabled=False),
        ),
    )

    assert result["status"] == "failed"
    assert result["error_type"] == "dashboard_date_filter_unconfigured"


@pytest.mark.parametrize(
    ("date_filter", "expected_error_type"),
    [
        (None, "dashboard_date_filter_migration_required"),
        (
            {
                "parameterType": "yyyymmdd_number",
                "expression": {"version": 2, "mode": "preset", "preset": "today"},
            },
            "dashboard_date_filter_invalid_template",
        ),
    ],
)
def test_dashboard_payload_preserves_date_filter_resolution_error_type(
    monkeypatch,
    date_filter,
    expected_error_type,
):
    engine = _engine_with_dashboard_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(dashboard_service, "_dashboard_refresh_policy_from_skills", lambda *_args: {})
    monkeypatch.setattr(dashboard_service, "_user_name", lambda *_args: None)
    monkeypatch.setattr(
        dashboard_service,
        "_execute_dashboard_chart_sql",
        lambda *_args, **_kwargs: pytest.fail("日期配置错误时不得执行 SQL"),
    )
    chart = {
        "id": "chart-1",
        "datasource": 1,
        "sql": (
            "select dt from orders where dt between "
            "{{dashboard_start_yyyymmdd}} and {{dashboard_end_yyyymmdd}}"
        ),
        "configVersion": 2,
    }
    if date_filter is not None:
        chart["dateFilter"] = date_filter

    with Session(engine) as session:
        _insert_dashboard_permission_fixture(session)
        record = CoreDashboard(
            id=f"dashboard-date-error-{expected_error_type}",
            tenant_id=1,
            name="日期配置错误",
            pid="root",
            node_type="leaf",
            datasource=1,
            component_data="[]",
            canvas_style_data="{}",
            canvas_view_info=json.dumps({"chart-1": chart}),
        )
        session.add(record)
        session.commit()
        result = dashboard_service._dashboard_payload(
            session,
            current_user,
            record,
            default_context=True,
            include_data=True,
        )

    response_chart = json.loads(result["canvas_view_info"])["chart-1"]
    assert response_chart["status"] == "failed"
    assert response_chart["error_type"] == expected_error_type


def test_dashboard_preview_date_filter_renders_before_disabled_pivot_execution(monkeypatch):
    engine = _engine_with_dashboard_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    exec_calls = []
    monkeypatch.setattr(
        query_executor,
        "_unsafe_exec_sql_after_validation",
        lambda ds, sql, origin_column=False: exec_calls.append(sql)
        or {"data": [{"dt": 20260501}], "fields": ["dt"]},
    )
    with Session(engine) as session:
        _insert_dashboard_permission_fixture(session)
        session.commit()
        result = dashboard_service.preview_sql(
            session,
            current_user,
            DashboardSqlPreview(
                datasource=1,
                sql=(
                    "select order_id as dt from orders where order_id between "
                    "{{dashboard_start_yyyymmdd}} and {{dashboard_end_yyyymmdd}}"
                ),
                pivot=DashboardPivotRequest(enabled=False),
                date_filter=DashboardDateFilterRequest(
                    parameter_type="yyyymmdd_number",
                    custom_start="2026-05-01",
                    custom_end="2026-05-31",
                ),
            ),
        )

    assert result["status"] == "success"
    assert len(exec_calls) == 1
    assert "20260501" in exec_calls[0] and "20260531" in exec_calls[0]
    assert "pivot_src" not in exec_calls[0]


def test_dashboard_preview_renders_date_template_before_permission_and_execution(monkeypatch):
    engine = _engine_with_dashboard_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    exec_calls = []
    monkeypatch.setattr(
        query_executor,
        "_unsafe_exec_sql_after_validation",
        lambda ds, sql, origin_column=False: exec_calls.append(sql)
        or {"data": [{"order_day": "2026-05-01", "amount": 99}], "fields": ["order_day", "amount"]},
    )
    with Session(engine) as session:
        _insert_dashboard_permission_fixture(session)
        session.commit()
        result = dashboard_service.preview_sql(
            session,
            current_user,
            DashboardSqlPreview(
                datasource=1,
                sql=(
                    "select order_id as order_day, amount from orders "
                    "where order_id between {{dashboard_start_yyyymmdd}} and {{dashboard_end_yyyymmdd}}"
                ),
                    pivot=DashboardPivotRequest(
                        enabled=True,
                        time_field="order_day",
                        metric_field="amount",
                    ),
                    date_filter=DashboardDateFilterRequest(
                        parameter_type="yyyymmdd_number",
                        custom_start="2026-05-01",
                        custom_end="2026-05-31",
                    ),
            ),
        )
    assert result["date_filter_capability"]["status"] == "available"
    assert len(exec_calls) == 1
    assert "20260501" in exec_calls[0] and "20260531" in exec_calls[0]
    assert "{{dashboard_" not in exec_calls[0]


def test_dashboard_source_preview_renders_date_template_without_outer_pivot(monkeypatch):
    engine = _engine_with_dashboard_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    exec_calls = []
    monkeypatch.setattr(
        query_executor,
        "_unsafe_exec_sql_after_validation",
        lambda ds, sql, origin_column=False: exec_calls.append(sql)
        or {"data": [{"order_day": 20260713, "amount": 99}], "fields": ["order_day", "amount"]},
    )
    with Session(engine) as session:
        _insert_dashboard_permission_fixture(session)
        session.commit()
        result = dashboard_service.preview_sql(
            session,
            current_user,
            DashboardSqlPreview(
                datasource=1,
                sql=(
                    "select order_id as order_day, amount from orders "
                    "where order_id between {{dashboard_start_yyyymmdd}} and {{dashboard_end_yyyymmdd}}"
                ),
                    pivot=DashboardPivotRequest(
                        enabled=False,
                        time_field="order_day",
                        metric_field="amount",
                    ),
                    date_filter=DashboardDateFilterRequest(parameter_type="yyyymmdd_number"),
            ),
        )

    assert result["status"] == "success"
    assert result["date_filter_capability"]["status"] == "available"
    assert len(exec_calls) == 1
    assert "{{dashboard_" not in exec_calls[0]
    assert "pivot_src" not in exec_calls[0]
    assert "{{dashboard_" not in exec_calls[0]


def test_dashboard_preview_date_filter_allows_empty_results_after_permission_audit(monkeypatch):
    events = []
    monkeypatch.setattr(dashboard_service, "resolve_chart_execution_datasource", lambda *_args: 1)
    monkeypatch.setattr(
        dashboard_service,
        "_dashboard_chart_permission_audit",
        lambda *_args: (events.append("audit") or None, False),
    )
    monkeypatch.setattr(
        dashboard_service,
        "_dashboard_sql_preview_cache_get",
        lambda *_args, **_kwargs: events.append("cache_get") or None,
    )
    monkeypatch.setattr(dashboard_service, "_dashboard_sql_preview_cache_set", lambda *_args: None)
    monkeypatch.setattr(
        dashboard_service,
        "_execute_dashboard_chart_sql",
        lambda *_args: {
            "status": "success",
            "fields": ["dt"],
            "data": [],
            "message": "",
        },
    )

    result = dashboard_service.preview_sql(
        session=SimpleNamespace(get=lambda *_args: SimpleNamespace(id=1, type="mysql")),
        current_user=SimpleNamespace(id=2, isAdmin=False, tenant_id=1),
        request=DashboardSqlPreview(
            datasource=1,
            sql=(
                "select dt from orders where dt between "
                "{{dashboard_start_yyyymmdd}} and {{dashboard_end_yyyymmdd}}"
            ),
                pivot=DashboardPivotRequest(
                    enabled=False,
                    time_field="dt",
                ),
                    date_filter=DashboardDateFilterRequest(
                        parameter_type="yyyymmdd_number",
                        custom_start="2026-07-28",
                        custom_end="2026-07-28",
                    ),
        ),
    )

    assert result["status"] == "success"
    assert result["data"] == []
    assert result["date_filter_capability"]["resolvedStart"] == "2026-07-28"
    assert events.index("audit") < events.index("cache_get")


@pytest.mark.parametrize(
    ("pivot", "date_filter"),
    [
        (
            DashboardPivotRequest(time_field="dt"),
            DashboardDateFilterRequest(
                parameter_type="yyyymmdd_number",
                custom_start="2026-05-01",
                custom_end="2026-05-31",
            ),
        ),
        (
            DashboardPivotRequest(time_field="dt"),
            DashboardDateFilterRequest(
                parameter_type="yyyymmdd_number",
                expression={"version": 1, "mode": "preset", "preset": "today"},
            ),
        ),
    ],
)
def test_dashboard_preview_rejects_explicit_date_for_event_realtime(monkeypatch, pivot, date_filter):
    prepared = DashboardDateFilterPreparation(
        sql="select dt from event_realtime",
        start=None,
        end=None,
        physical_tables={"event_realtime"},
        capability={"status": "realtime", "reason": "realtime_table"},
    )
    monkeypatch.setattr(dashboard_service, "resolve_chart_execution_datasource", lambda *_args: 1)
    monkeypatch.setattr(dashboard_service, "prepare_dashboard_date_filter", lambda *args, **kwargs: prepared)
    monkeypatch.setattr(
        dashboard_service,
        "_execute_dashboard_chart_sql",
        lambda *args, **kwargs: pytest.fail("实时图表不得应用自定义日期"),
    )
    result = dashboard_service.preview_sql(
        session=SimpleNamespace(get=lambda *_: SimpleNamespace(id=1, type="mysql")),
        current_user=SimpleNamespace(id=2, isAdmin=False, tenant_id=1),
        request=DashboardSqlPreview(
            datasource=1,
            sql="select dt from event_realtime",
            pivot=pivot,
            date_filter=date_filter,
        ),
    )
    assert result["status"] == "failed"
    assert result["error_type"] == "dashboard_date_filter_realtime"
    assert result["date_filter_capability"]["status"] == "realtime"


def test_dashboard_preview_empty_sql_returns_date_capability():
    result = dashboard_service.preview_sql(
        object(),
        SimpleNamespace(id=2, isAdmin=False, tenant_id=1),
        DashboardSqlPreview(sql="   ", datasource=1),
    )

    assert result["status"] == "failed"
    assert result["date_filter_capability"] == {
        "status": "unconfigured",
        "reason": "missing_sql",
    }


@pytest.mark.parametrize(
    "date_filter",
    [
        {
            "parameterType": "yyyymmdd_number",
            "expression": {
                "version": 1,
                "mode": "range",
                "start": {"mode": "static", "date": "2026-07-13"},
                "end": {"mode": "static", "date": "2026-07-26"},
            },
        },
        {
            "parameterType": "yyyymmdd_number",
            "expression": {"version": 1, "mode": "preset", "preset": "today"},
        },
    ],
)
def test_dashboard_payload_rejects_explicit_date_for_event_realtime(monkeypatch, date_filter):
    engine = _engine_with_dashboard_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    executed = []
    monkeypatch.setattr(dashboard_service, "_dashboard_refresh_policy_from_skills", lambda *_args: {})
    monkeypatch.setattr(dashboard_service, "_user_name", lambda *_args: None)
    monkeypatch.setattr(
        dashboard_service,
        "_execute_dashboard_chart_sql",
        lambda *_args, **_kwargs: executed.append(True)
        or {"status": "success", "fields": [], "data": [], "message": ""},
    )
    with Session(engine) as session:
        _insert_dashboard_permission_fixture(session)
        record = CoreDashboard(
            id="dashboard-realtime-custom-date",
            tenant_id=1,
            name="实时日期拒绝测试",
            pid="root",
            node_type="leaf",
            datasource=1,
            component_data="[]",
            canvas_style_data="{}",
            canvas_view_info=json.dumps({
                "chart": {
                    "id": "chart",
                    "datasource": 1,
                    "sql": (
                        "select dt from event_realtime where dt between "
                        "{{dashboard_start_yyyymmdd}} and {{dashboard_end_yyyymmdd}}"
                    ),
                    "configVersion": 2,
                    "dateFilter": date_filter,
                }
            }),
        )
        session.add(record)
        session.commit()

        payload = dashboard_service._dashboard_payload(
            session,
            current_user,
            record,
            default_context=True,
            include_data=True,
        )

    chart = json.loads(payload["canvas_view_info"])["chart"]
    assert executed == []
    assert chart["dateFilterCapability"]["status"] == "realtime"
    assert chart["error_type"] == "dashboard_date_filter_realtime"


def test_dashboard_payload_adds_transient_date_capability_without_persisting(monkeypatch):
    engine = _engine_with_dashboard_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    original = {
        "available": {
            "id": "available",
            "sql": (
                "select order_id as dt from orders where order_id between "
                "{{dashboard_start_yyyymmdd}} and {{dashboard_end_yyyymmdd}}"
            ),
            "configVersion": 2,
            "dateFilter": {
                "parameterType": "yyyymmdd_number",
                "expression": {"version": 1, "mode": "preset", "preset": "past_30_days"},
            },
        },
        "realtime": {
            "id": "realtime",
            "sql": "select dt from event_realtime",
        },
        "plain": {"id": "plain", "sql": "select amount from orders", "pivot": {}},
    }
    prepare_calls = []
    original_prepare = dashboard_service._prepare_dashboard_chart_query

    def count_prepare(datasource, sql, pivot, **kwargs):
        prepare_calls.append(sql)
        return original_prepare(datasource, sql, pivot, **kwargs)

    monkeypatch.setattr(dashboard_service, "_dashboard_refresh_policy_from_skills", lambda *_args: {})
    monkeypatch.setattr(dashboard_service, "_user_name", lambda *_args: None)
    monkeypatch.setattr(dashboard_service, "_prepare_dashboard_chart_query", count_prepare)
    monkeypatch.setattr(dashboard_service, "_dashboard_chart_permission_audit", lambda *_args: (None, False))
    with Session(engine) as session:
        _insert_dashboard_permission_fixture(session)
        record = CoreDashboard(
            id="dashboard-date-capability",
            tenant_id=1,
            name="日期能力测试",
            pid="root",
            node_type="leaf",
            datasource=1,
            component_data="[]",
            canvas_style_data="{}",
            canvas_view_info=json.dumps(original),
        )
        session.add(record)
        session.commit()
        payload = dashboard_service._dashboard_payload(
            session,
            current_user,
            record,
            default_context=True,
            include_data=False,
        )
        response_views = json.loads(payload["canvas_view_info"])
        assert response_views["available"]["dateFilterCapability"]["status"] == "available"
        assert response_views["realtime"]["dateFilterCapability"]["status"] == "realtime"
        assert response_views["plain"]["dateFilterCapability"]["status"] == "unconfigured"
        assert len(prepare_calls) == len(original)
        session.expire_all()
        persisted = session.get(CoreDashboard, record.id)
        assert "dateFilterCapability" not in persisted.canvas_view_info


def test_canvas_save_strips_transient_date_filter_capability_recursively():
    canvas = {
        "chart-1": {
            "id": "chart-1",
            "dateFilterCapability": {
                "status": "available",
                "defaultStart": "2026-07-13",
                "defaultEnd": "2026-07-26",
            },
            "children": [
                {
                    "id": "nested-chart",
                    "dateFilterCapability": {"status": "realtime"},
                }
            ],
        }
    }

    sanitized = json.loads(dashboard_service._sanitize_canvas_view_info(json.dumps(canvas)))

    assert "dateFilterCapability" not in sanitized["chart-1"]
    assert "dateFilterCapability" not in sanitized["chart-1"]["children"][0]
    assert sanitized["chart-1"]["id"] == "chart-1"


def test_user_name_unwraps_row_result():
    class Result:
        def first(self):
            return ("Administrator",)

    class Session:
        def exec(self, statement):
            return Result()

    assert dashboard_service._user_name(Session(), "1") == "Administrator"


def test_share_dashboard_creates_share_record(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(dashboard_service, "has_datasource_role", lambda *args, **kwargs: False)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 1)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="dashboard-1",
                name="看板 A",
                pid="root",
                datasource=1,
                node_type="leaf",
                type="dashboard",
                create_by="2",
                create_time=100,
                delete_flag=0,
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info="{}",
            )
        )
        session.commit()

        share = dashboard_service.share_resource(
            session=session,
            user=current_user,
            request=DashboardShareRequest(
                dashboard_id="dashboard-1",
                share_type="dashboard",
                preview_image="data:image/jpeg;base64,preview",
            ),
        )

    assert share.source_dashboard_id == "dashboard-1"
    assert share.share_type == "dashboard"
    assert share.name == "看板 A"
    assert share.preview_image == "data:image/jpeg;base64,preview"


def test_share_chart_creates_chart_snapshot(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(dashboard_service, "has_datasource_role", lambda *args, **kwargs: False)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 1)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="dashboard-1",
                name="看板 A",
                pid="root",
                datasource=1,
                node_type="leaf",
                type="dashboard",
                create_by="2",
                create_time=100,
                delete_flag=0,
                component_data=json.dumps([{"id": "chart-1", "component": "SQView"}]),
                canvas_style_data="{}",
                canvas_view_info=json.dumps(
                    {
                        "chart-1": {
                            "datasource": 1,
                            "sql": "select 1",
                            "chart": {"title": "图表 A", "type": "table"},
                        }
                    }
                ),
            )
        )
        session.commit()

        share = dashboard_service.share_resource(
            session=session,
            user=current_user,
            request=DashboardShareRequest(
                dashboard_id="dashboard-1",
                share_type="chart",
                source_view_id="chart-1",
            ),
        )

    assert share.share_type == "chart"
    assert share.source_view_id == "chart-1"
    assert json.loads(share.component_data)[0]["id"] == "chart-1"
    assert json.loads(share.canvas_view_info)["chart-1"]["chart"]["title"] == "图表 A"


def test_project_viewer_cannot_share_other_users_dashboard(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(dashboard_service, "has_datasource_role", lambda *args, **kwargs: False)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 1)

    with Session(engine) as session:
        session.add(
            CoreDashboard(
                id="dashboard-1",
                name="别人的看板",
                pid="root",
                datasource=1,
                node_type="leaf",
                type="dashboard",
                create_by="1",
                create_time=100,
                delete_flag=0,
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info="{}",
            )
        )
        session.commit()

        with pytest.raises(HTTPException) as exc_info:
            dashboard_service.share_resource(
                session=session,
                user=current_user,
                request=DashboardShareRequest(
                    dashboard_id="dashboard-1",
                    share_type="dashboard",
                ),
            )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "You do not have permission to share this dashboard"


def test_list_shared_resources_marks_permission_status(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=9, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(
        dashboard_service,
        "has_datasource_access",
        lambda session, user, datasource_id: datasource_id == 1,
    )
    monkeypatch.setattr(dashboard_service, "_datasource_name", lambda *args, **kwargs: None)
    monkeypatch.setattr(dashboard_service, "_user_name", lambda *args, **kwargs: None)

    with Session(engine) as session:
        session.add(
            CoreDashboardShare(
                id="share-1",
                name="共享看板",
                datasource=1,
                share_type="dashboard",
                source_dashboard_id="dashboard-1",
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info="{}",
                preview_image="data:image/jpeg;base64,preview",
                create_by="1",
                update_by="1",
                create_time=100,
                update_time=100,
                delete_flag=0,
            )
        )
        session.add(
            CoreDashboardShare(
                id="share-2",
                name="无权限共享看板",
                datasource=2,
                share_type="dashboard",
                source_dashboard_id="dashboard-2",
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info="{}",
                create_by="1",
                update_by="1",
                create_time=101,
                update_time=101,
                delete_flag=0,
            )
        )
        session.commit()

        result = dashboard_service.list_shared_resources(
            session=session,
            current_user=current_user,
            query=DashboardShareListQuery(),
        )

    can_use_map = {item["id"]: item["can_use"] for item in result}
    preview_map = {item["id"]: item["preview_image"] for item in result}
    assert can_use_map["share-1"] is True
    assert can_use_map["share-2"] is False
    assert preview_map["share-1"] == "data:image/jpeg;base64,preview"


def test_list_shared_resources_excludes_other_tenant_shares(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=9, isAdmin=False, tenant_id=2)
    monkeypatch.setattr(dashboard_service, "has_datasource_access", lambda *args, **kwargs: True)
    monkeypatch.setattr(dashboard_service, "_datasource_name", lambda *args, **kwargs: None)
    monkeypatch.setattr(dashboard_service, "_user_name", lambda *args, **kwargs: None)

    with Session(engine) as session:
        session.add(
            CoreDashboardShare(
                id="tenant-1-share",
                tenant_id=1,
                name="租户一共享",
                datasource=1,
                share_type="dashboard",
                source_dashboard_id="dashboard-1",
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info="{}",
                create_by="1",
                update_by="1",
                create_time=100,
                update_time=100,
                delete_flag=0,
            )
        )
        session.add(
            CoreDashboardShare(
                id="tenant-2-share",
                tenant_id=2,
                name="租户二共享",
                datasource=1,
                share_type="dashboard",
                source_dashboard_id="dashboard-2",
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info="{}",
                create_by="1",
                update_by="1",
                create_time=101,
                update_time=101,
                delete_flag=0,
            )
        )
        session.commit()

        result = dashboard_service.list_shared_resources(
            session=session,
            current_user=current_user,
            query=DashboardShareListQuery(),
        )

    assert [item["id"] for item in result] == ["tenant-2-share"]


def test_load_shared_resource_denies_cross_tenant_share(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=9, isAdmin=True, tenant_id=2)
    monkeypatch.setattr(dashboard_service, "has_datasource_access", lambda *args, **kwargs: True)

    with Session(engine) as session:
        session.add(
            CoreDashboardShare(
                id="tenant-1-share",
                tenant_id=1,
                name="租户一共享",
                datasource=1,
                share_type="dashboard",
                source_dashboard_id="dashboard-1",
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info="{}",
                create_by="1",
                update_by="1",
                create_time=100,
                update_time=100,
                delete_flag=0,
            )
        )
        session.commit()

        with pytest.raises(HTTPException) as exc_info:
            dashboard_service.load_shared_resource(
                session=session,
                current_user=current_user,
                query=SharedDashboardQuery(id="tenant-1-share"),
            )

    assert exc_info.value.status_code == 404


def test_list_shared_resources_deduplicates_same_source(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=1, isAdmin=True, tenant_id=1)
    monkeypatch.setattr(dashboard_service, "has_datasource_access", lambda *args, **kwargs: True)
    monkeypatch.setattr(dashboard_service, "_datasource_name", lambda *args, **kwargs: None)
    monkeypatch.setattr(dashboard_service, "_user_name", lambda *args, **kwargs: None)

    with Session(engine) as session:
        session.add(
            CoreDashboardShare(
                id="share-new",
                name="共享看板新",
                datasource=1,
                share_type="dashboard",
                source_dashboard_id="dashboard-1",
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info="{}",
                create_by="2",
                update_by="2",
                create_time=200,
                update_time=200,
                delete_flag=0,
            )
        )
        session.add(
            CoreDashboardShare(
                id="share-old",
                name="共享看板旧",
                datasource=1,
                share_type="dashboard",
                source_dashboard_id="dashboard-1",
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info="{}",
                create_by="2",
                update_by="2",
                create_time=100,
                update_time=100,
                delete_flag=0,
            )
        )
        session.commit()

        result = dashboard_service.list_shared_resources(
            session=session,
            current_user=current_user,
            query=DashboardShareListQuery(),
        )

    assert [item["id"] for item in result] == ["share-new"]


def test_use_shared_resource_creates_dashboard_copy(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=5, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(dashboard_service, "has_datasource_access", lambda *args, **kwargs: True)

    with Session(engine) as session:
        session.add(
            CoreDashboardShare(
                id="share-1",
                name="共享图表包",
                datasource=1,
                share_type="dashboard",
                source_dashboard_id="dashboard-1",
                component_data=json.dumps([{"id": "chart-1", "component": "SQView"}]),
                canvas_style_data="{}",
                canvas_view_info=json.dumps({"chart-1": {"datasource": 1, "sql": "select 1"}}),
                preview_image="data:image/jpeg;base64,preview",
                create_by="1",
                update_by="1",
                create_time=100,
                update_time=100,
                delete_flag=0,
            )
        )
        session.commit()

        record = dashboard_service.use_shared_resource(
            session=session,
            user=current_user,
            request=SharedDashboardUseRequest(id="share-1"),
        )
        position = session.exec(
            select(CoreDashboardTree).where(
                CoreDashboardTree.scope == "my",
                CoreDashboardTree.dashboard_id == record.id,
            )
        ).first()

    assert record.name == "共享图表包"
    assert record.datasource == 1
    assert record.create_by == "5"
    assert position is not None
    assert position.parent_id == "root"


def test_use_shared_resource_binds_copy_to_current_workspace(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=5, isAdmin=False, tenant_id=20)
    monkeypatch.setattr(dashboard_service, "has_datasource_access", lambda *args, **kwargs: True)

    with Session(engine) as session:
        session.add(
            CoreDashboardShare(
                id="share-1",
                tenant_id=20,
                name="空间看板",
                datasource=1,
                share_type="dashboard",
                source_dashboard_id="dashboard-1",
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info="{}",
                create_by="1",
                update_by="1",
                create_time=100,
                update_time=100,
                delete_flag=0,
            )
        )
        session.commit()

        record = dashboard_service.use_shared_resource(
            session=session,
            user=current_user,
            request=SharedDashboardUseRequest(id="share-1"),
        )

    assert record.tenant_id == 20
    assert record.create_by == "5"


def test_load_shared_resource_returns_permission_denied_state_without_access(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=5, isAdmin=False, tenant_id=1)
    monkeypatch.setattr(dashboard_service, "has_datasource_access", lambda *args, **kwargs: False)
    monkeypatch.setattr(dashboard_service, "_user_name", lambda *args, **kwargs: None)

    with Session(engine) as session:
        session.add(
            CoreDashboardShare(
                id="share-1",
                name="共享图表",
                datasource=1,
                share_type="chart",
                source_dashboard_id="dashboard-1",
                source_view_id="chart-1",
                component_data=json.dumps([{"id": "chart-1", "component": "SQView"}]),
                canvas_style_data="{}",
                canvas_view_info=json.dumps({"chart-1": {"datasource": 1, "sql": "select 1"}}),
                preview_image="data:image/jpeg;base64,preview",
                create_by="1",
                update_by="1",
                create_time=100,
                update_time=100,
                delete_flag=0,
            )
        )
        session.commit()

        result = dashboard_service.load_shared_resource(
            session=session,
            current_user=current_user,
            query=SharedDashboardQuery(id="share-1"),
        )

    chart = json.loads(result["canvas_view_info"])["chart-1"]
    assert result["can_use"] is False
    assert result["preview_image"] == "data:image/jpeg;base64,preview"
    assert chart["status"] == "failed"
    assert chart["message"] == "没有查看权限"


def test_delete_shared_resource_soft_deletes_for_creator(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False, tenant_id=1)

    with Session(engine) as session:
        session.add(
            CoreDashboardShare(
                id="share-1",
                name="共享看板",
                datasource=1,
                share_type="dashboard",
                source_dashboard_id="dashboard-1",
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info="{}",
                create_by="2",
                update_by="2",
                create_time=100,
                update_time=100,
                delete_flag=0,
            )
        )
        session.commit()

        result = dashboard_service.delete_shared_resource(
            session=session,
            current_user=current_user,
            query=SharedDashboardQuery(id="share-1"),
        )
        updated = session.get(CoreDashboardShare, "share-1")

    assert result is True
    assert updated.delete_flag == 1
    assert updated.delete_by == "2"


def test_delete_shared_resource_allows_system_admin(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=1, isAdmin=True, tenant_id=1)

    with Session(engine) as session:
        session.add(
            CoreDashboardShare(
                id="share-1",
                name="共享看板",
                datasource=1,
                share_type="dashboard",
                source_dashboard_id="dashboard-1",
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info="{}",
                create_by="2",
                update_by="2",
                create_time=100,
                update_time=100,
                delete_flag=0,
            )
        )
        session.commit()

        result = dashboard_service.delete_shared_resource(
            session=session,
            current_user=current_user,
            query=SharedDashboardQuery(id="share-1"),
        )
        updated = session.get(CoreDashboardShare, "share-1")

    assert result is True
    assert updated.delete_flag == 1
    assert updated.delete_by == "1"


def test_delete_shared_resource_deletes_duplicate_same_source_shares(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=1, isAdmin=True, tenant_id=1)

    with Session(engine) as session:
        for share_id, update_time in (("share-new", 200), ("share-old", 100)):
            session.add(
                CoreDashboardShare(
                    id=share_id,
                    name="共享看板",
                    datasource=1,
                    share_type="dashboard",
                    source_dashboard_id="dashboard-1",
                    component_data="[]",
                    canvas_style_data="{}",
                    canvas_view_info="{}",
                    create_by="2",
                    update_by="2",
                    create_time=update_time,
                    update_time=update_time,
                    delete_flag=0,
                )
            )
        session.commit()

        result = dashboard_service.delete_shared_resource(
            session=session,
            current_user=current_user,
            query=SharedDashboardQuery(id="share-new"),
        )
        records = session.exec(select(CoreDashboardShare)).all()

    assert result is True
    assert {record.id: record.delete_flag for record in records} == {
        "share-new": 1,
        "share-old": 1,
    }


def test_delete_shared_resource_denied_for_non_creator(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=9, isAdmin=False, tenant_id=1)

    with Session(engine) as session:
        session.add(
            CoreDashboardShare(
                id="share-1",
                name="共享看板",
                datasource=1,
                share_type="dashboard",
                source_dashboard_id="dashboard-1",
                component_data="[]",
                canvas_style_data="{}",
                canvas_view_info="{}",
                create_by="2",
                update_by="2",
                create_time=100,
                update_time=100,
                delete_flag=0,
            )
        )
        session.commit()

        with pytest.raises(HTTPException) as exc_info:
            dashboard_service.delete_shared_resource(
                session=session,
                current_user=current_user,
                query=SharedDashboardQuery(id="share-1"),
            )

    assert exc_info.value.status_code == 403
