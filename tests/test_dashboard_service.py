import os
from types import SimpleNamespace

os.environ["LOG_FORMAT"] = "%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s"

import json

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from apps.dashboard.crud import dashboard_service
import pytest
from fastapi import HTTPException

from apps.dashboard.models.dashboard_model import CoreDashboard, CreateDashboard, QueryDashboard, DashboardSqlPreview

def _engine_with_dashboard_table():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine, tables=[CoreDashboard.__table__])
    return engine


def _engine_with_dashboard_permission_tables():
    engine = _engine_with_dashboard_table()
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE core_datasource (
                id INTEGER PRIMARY KEY,
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


def _create_simple_datasource_table(session: Session):
    session.execute(text(
        """
        CREATE TABLE core_datasource (
            id INTEGER PRIMARY KEY,
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
            (id, enable, name, description, permission_list, user_list, white_list_user)
        VALUES
            (2000, 1, 'user 2 orders columns', '', '[1000]', '[2]', '[]')
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
            (id, enable, name, description, permission_list, user_list, white_list_user)
        VALUES
            (2001, 1, 'user 2 orders rows', '', '[1001]', '[2]', '[]')
        """
    ))


def test_list_resource_returns_dashboard_tree_nodes_for_admin():
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=1, isAdmin=True)

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


def test_list_resource_marks_project_editor_can_edit(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False)
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

    assert len(tree) == 1
    assert tree[0].can_edit is True


def test_list_resource_marks_project_viewer_cannot_edit(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False)
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

    assert len(tree) == 1
    assert tree[0].can_edit is False


def test_list_resource_marks_creator_can_edit_with_project_viewer_role(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False)
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


def test_list_resource_includes_legacy_dashboard_when_canvas_uses_selected_datasource(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=1, isAdmin=True)
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
                create_by="1",
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
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=1, isAdmin=True)
    chart_calls = []
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 1)
    monkeypatch.setattr(dashboard_service, "has_datasource_access", lambda *args, **kwargs: True)
    monkeypatch.setattr(dashboard_service, "has_datasource_role", lambda *args, **kwargs: False)
    monkeypatch.setattr(dashboard_service, "_user_name", lambda *args, **kwargs: "Administrator")
    monkeypatch.setattr(
        dashboard_service,
        "_extract_physical_tables",
        lambda statements: {"chart_source"},
    )
    monkeypatch.setattr(
        dashboard_service,
        "_build_dashboard_permission_scope",
        lambda *args, **kwargs: {"chart_source": {"fields": {"value"}}},
    )
    monkeypatch.setattr(
        dashboard_service,
        "exec_sql",
        lambda ds, sql, origin_column=False: chart_calls.append((ds.id, sql))
        or {"data": [{"value": 1}], "fields": ["value"]},
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


def test_load_resource_infers_legacy_dashboard_datasource_from_canvas_items(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=True)
    chart_calls = []
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 1)
    monkeypatch.setattr(dashboard_service, "has_datasource_access", lambda *args, **kwargs: True)
    monkeypatch.setattr(dashboard_service, "has_datasource_role", lambda *args, **kwargs: False)
    monkeypatch.setattr(dashboard_service, "_user_name", lambda *args, **kwargs: "Administrator")
    monkeypatch.setattr(
        dashboard_service,
        "_extract_physical_tables",
        lambda statements: {"chart_source"},
    )
    monkeypatch.setattr(
        dashboard_service,
        "_build_dashboard_permission_scope",
        lambda *args, **kwargs: {"chart_source": {"fields": {"value"}}},
    )
    monkeypatch.setattr(
        dashboard_service,
        "exec_sql",
        lambda ds, sql, origin_column=False: chart_calls.append((ds.id, sql))
        or {"data": [{"value": 1}], "fields": ["value"]},
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
                create_by="1",
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
    current_user = SimpleNamespace(id=2, isAdmin=False)
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


def test_project_viewer_can_create_own_dashboard(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False)
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


def test_project_editor_can_rename_dashboard(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False)
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

        record = dashboard_service.update_resource(
            session=session,
            user=current_user,
            dashboard=QueryDashboard(id="dashboard-1", name="新名称"),
        )

        assert record.name == "新名称"
        assert record.update_by == "2"


def test_project_viewer_cannot_rename_dashboard(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False)
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
    current_user = SimpleNamespace(id=2, isAdmin=False)
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


def test_project_viewer_cannot_create_under_folder_they_cannot_edit(monkeypatch):
    engine = _engine_with_dashboard_table()
    current_user = SimpleNamespace(id=2, isAdmin=False)
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
    engine = _engine_with_dashboard_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False)
    exec_calls = []
    monkeypatch.setattr(
        dashboard_service,
        "exec_sql",
        lambda ds, sql, origin_column=False: exec_calls.append(sql)
        or {"data": [{"payment_id": 1}], "fields": ["payment_id"]},
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
    assert "无权限表" in chart["message"]
    assert "payments" in chart["message"]


def test_dashboard_preview_denies_chart_sql_with_unauthorized_field(monkeypatch):
    engine = _engine_with_dashboard_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False)
    exec_calls = []
    monkeypatch.setattr(
        dashboard_service,
        "exec_sql",
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
    assert "无权限字段" in result["message"]
    assert "amount" in result["message"]


def test_dashboard_preview_applies_row_permission_before_execution(monkeypatch):
    engine = _engine_with_dashboard_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False)
    exec_calls = []
    monkeypatch.setattr(
        dashboard_service,
        "exec_sql",
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

    assert result["status"] == "success"
    assert len(exec_calls) == 1
    assert "FROM (SELECT * FROM orders WHERE" in exec_calls[0]
    assert "region" in exec_calls[0]
    assert "'US'" in exec_calls[0]


def test_dashboard_preview_denies_select_star_for_normal_user(monkeypatch):
    engine = _engine_with_dashboard_permission_tables()
    current_user = SimpleNamespace(id=2, isAdmin=False)
    exec_calls = []
    monkeypatch.setattr(
        dashboard_service,
        "exec_sql",
        lambda ds, sql, origin_column=False: exec_calls.append(sql)
        or {"data": [{"order_id": 1}], "fields": ["order_id"]},
    )

    with Session(engine) as session:
        _insert_dashboard_permission_fixture(session)
        session.commit()

        result = dashboard_service.preview_sql(
            session=session,
            current_user=current_user,
            request=DashboardSqlPreview(datasource=1, sql="select * from orders"),
        )

    assert exec_calls == []
    assert result["status"] == "failed"
    assert "SELECT *" in result["message"]


def test_user_name_unwraps_row_result():
    class Result:
        def first(self):
            return ("Administrator",)

    class Session:
        def exec(self, statement):
            return Result()

    assert dashboard_service._user_name(Session(), "1") == "Administrator"
