import os
from types import SimpleNamespace

os.environ["LOG_FORMAT"] = "%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s"

import json

from sqlmodel import Session, SQLModel, create_engine

from apps.dashboard.crud import dashboard_service
from apps.dashboard.models.dashboard_model import CoreDashboard, QueryDashboard

def _engine_with_dashboard_table():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine, tables=[CoreDashboard.__table__])
    return engine


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
    monkeypatch.setattr(dashboard_service, "_user_name", lambda *args, **kwargs: "Administrator")
    monkeypatch.setattr(
        dashboard_service,
        "get_chart_data_ds",
        lambda session, datasource, sql: chart_calls.append((datasource, sql))
        or {"status": "success", "data": [{"value": 1}], "fields": ["value"], "message": ""},
    )

    with Session(engine) as session:
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
    current_user = SimpleNamespace(id=2, isAdmin=False)
    chart_calls = []
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *args, **kwargs: 1)
    monkeypatch.setattr(dashboard_service, "has_datasource_access", lambda *args, **kwargs: True)
    monkeypatch.setattr(dashboard_service, "_user_name", lambda *args, **kwargs: "Administrator")
    monkeypatch.setattr(
        dashboard_service,
        "get_chart_data_ds",
        lambda session, datasource, sql: chart_calls.append((datasource, sql))
        or {"status": "success", "data": [{"value": 1}], "fields": ["value"], "message": ""},
    )

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


def test_user_name_unwraps_row_result():
    class Result:
        def first(self):
            return ("Administrator",)

    class Session:
        def exec(self, statement):
            return Result()

    assert dashboard_service._user_name(Session(), "1") == "Administrator"
