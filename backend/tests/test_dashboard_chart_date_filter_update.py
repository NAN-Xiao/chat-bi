"""Date changes persist on one owned chart without replacing the whole canvas."""
import copy
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from apps.dashboard.crud import dashboard_service as service
from apps.dashboard.models.dashboard_chart_config import DashboardDateFilterConfig
from apps.dashboard.models.dashboard_chart_config import DashboardDateFilterRequest
from apps.dashboard.models.dashboard_model import CoreDashboard
from apps.dashboard.models.dashboard_model import DashboardChartDateFilterUpdateRequest
from sqlmodel import Session as SqlSession, create_engine
from sqlalchemy import text

PREPARE_QUERY = service._prepare_dashboard_chart_item_query

WEEK = {"version": 1, "mode": "preset", "preset": "past_7_days"}
MONTH = {"version": 1, "mode": "preset", "preset": "past_30_days"}
SQL = "SELECT dt FROM facts WHERE dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}"


class Session:
    def __init__(self, record):
        self.record = record
        self.commits = 0
        self.locked = False
        self.concurrent_canvas = None

    def get(self, *_args):
        return SimpleNamespace(id=7, type="mysql")

    def refresh(self, record, *, with_for_update=None):
        self.locked = bool(with_for_update)
        if with_for_update and self.concurrent_canvas:
            record.canvas_view_info = self.concurrent_canvas

    def add(self, record):
        assert record is self.record

    def commit(self):
        self.commits += 1


@pytest.fixture
def setup(monkeypatch):
    chart = {
        "id": "a", "sql": SQL, "datasource": 7,
        "dateFilter": {"enabled": True, "parameterType": "yyyymmdd_number", "expression": WEEK},
        "sourceConfig": {"sql": {"sql": SQL, "builder": {"timeExpression": WEEK, "timeRange": "expression"},
                                  "lastResult": {"data": [{"dt": "2026-10-05"}]}}},
        "pivot": {"date_expression": WEEK, "range": "custom", "custom_start": "2026-10-05", "custom_end": "2026-10-11"},
        "data": {"fields": ["dt"], "data": [{"dt": "2026-10-05"}]},
        "fields": ["dt"], "snapshotRefreshedAt": 123,
        "chart": {"title": "Generic chart", "columns": [{"name": "dt"}]},
    }
    canvas = {"a": chart, "b": {"id": "b", "sql": "SELECT 2", "data": {"data": [{"value": 2}]}}}
    record = CoreDashboard(id="board", tenant_id=1, node_type="leaf", datasource=3,
                           component_data=json.dumps([{"id": "a", "component": "SQView"}, {"id": "b", "component": "SQView"}]),
                           canvas_view_info=json.dumps(canvas), canvas_style_data='{"width": 1000}')
    session = Session(record)
    user = SimpleNamespace(id=101, tenant_id=1)
    monkeypatch.setattr(service, "_load_dashboard_or_404", lambda *_args: record)
    monkeypatch.setattr(service, "_require_edit_permission", lambda *_args: None)
    monkeypatch.setattr(service, "resolve_chart_execution_datasource", lambda *_args: _args[-1])
    monkeypatch.setattr(service, "_dashboard_requires_pivot_time_field", lambda *_args: False)
    monkeypatch.setattr(service, "_dashboard_chart_permission_audit", lambda *_args: (None, False))
    monkeypatch.setattr(service, "_prepare_dashboard_chart_item_query", lambda _ds, item, **_kwargs: SimpleNamespace(
        date_filter_error_type="", source_sql=SQL, pivot=item.get("pivot"),
        date_filter_capability={"status": "available", "parameterType": "yyyymmdd_number",
                                "expression": item["dateFilter"]["expression"],
                                "resolvedStart": "2026-09-12", "resolvedEnd": "2026-10-11"}))
    monkeypatch.setattr(service, "_asset_operator_id", lambda *_args: "101")
    request = SimpleNamespace(dashboard_id="board", chart_id="a", expected_sql=SQL, expected_datasource=7,
                              date_filter=DashboardDateFilterConfig.model_validate({
                                  "enabled": True, "parameterType": "yyyymmdd_number", "expression": MONTH}))
    return session, user, request, canvas


def test_success_persists_expression_and_invalidates_old_date_snapshot(setup):
    session, user, request, before = setup
    result = service.update_chart_date_filter(session, user, request)
    after = json.loads(session.record.canvas_view_info)
    assert session.commits == 1 and session.locked
    assert after["a"]["dateFilter"]["expression"] == MONTH
    assert after["a"]["configVersion"] == 2
    assert after["a"]["sourceConfig"]["sql"]["builder"]["timeExpression"] == MONTH
    assert after["a"]["pivot"]["date_expression"] == MONTH
    assert after["a"]["pivot"]["range"] == "source"
    assert after["a"]["pivot"]["custom_start"] == ""
    assert after["a"]["data"]["data"] == []
    assert after["a"]["snapshotRefreshedAt"] == 0
    assert "lastResult" not in after["a"]["sourceConfig"]["sql"]
    assert after["a"]["chart"] == before["a"]["chart"]
    assert after["a"]["sql"] == SQL and after["a"]["datasource"] == 7
    assert after["b"] == before["b"]
    assert session.record.canvas_style_data == '{"width": 1000}'
    assert result["dateFilter"]["expression"] == MONTH


def test_saving_dates_merges_with_another_chart_changed_after_loading(setup):
    session, user, request, canvas = setup
    newer = copy.deepcopy(canvas)
    newer["b"]["sql"] = "SELECT 999"
    session.concurrent_canvas = json.dumps(newer)
    service.update_chart_date_filter(session, user, request)
    assert json.loads(session.record.canvas_view_info)["b"] == newer["b"]


def test_changed_sql_rejects_stale_date_save(setup):
    session, user, request, canvas = setup
    newer = copy.deepcopy(canvas)
    newer["a"]["sql"] = "SELECT dt FROM other_facts"
    session.concurrent_canvas = json.dumps(newer)
    with pytest.raises(HTTPException) as exc:
        service.update_chart_date_filter(session, user, request)
    assert exc.value.status_code == 409
    assert session.commits == 0
    assert json.loads(session.record.canvas_view_info)["a"]["dateFilter"]["expression"] == WEEK


def test_read_only_user_cannot_change_saved_dates(setup, monkeypatch):
    session, user, request, before = setup
    def denied(*_args):
        raise HTTPException(403, "没有编辑权限")
    monkeypatch.setattr(service, "_require_edit_permission", denied)
    with pytest.raises(HTTPException) as exc:
        service.update_chart_date_filter(session, user, request)
    assert exc.value.status_code == 403 and session.commits == 0
    assert json.loads(session.record.canvas_view_info) == before


def test_invalid_expression_never_changes_saved_dates(setup):
    session, user, request, before = setup
    request.date_filter.expression = {"version": 1, "mode": "preset", "preset": "invalid"}
    with pytest.raises(HTTPException) as exc:
        service.update_chart_date_filter(session, user, request)
    assert exc.value.status_code == 400 and session.commits == 0
    assert json.loads(session.record.canvas_view_info) == before


def test_unknown_chart_is_not_created_by_a_date_update(setup):
    session, user, request, before = setup
    request.chart_id = "unknown"
    with pytest.raises(HTTPException) as exc:
        service.update_chart_date_filter(session, user, request)
    assert exc.value.status_code == 404 and session.commits == 0
    assert json.loads(session.record.canvas_view_info) == before


def test_changed_datasource_rejects_results_from_the_previous_datasource(setup):
    session, user, request, canvas = setup
    newer = copy.deepcopy(canvas)
    newer["a"]["datasource"] = 8
    session.concurrent_canvas = json.dumps(newer)
    with pytest.raises(HTTPException) as exc:
        service.update_chart_date_filter(session, user, request)
    assert exc.value.status_code == 409 and session.commits == 0


@pytest.mark.parametrize("expression", [MONTH, {
    "version": 1, "mode": "range",
    "start": {"mode": "static", "date": "2026-09-01"},
    "end": {"mode": "static", "date": "2026-09-30"},
}])
def test_saved_date_reopens_and_renders_the_actual_query_range(setup, monkeypatch, tmp_path, expression):
    fake, user, request, _ = setup
    request = DashboardChartDateFilterUpdateRequest.model_validate({
        "dashboard_id": request.dashboard_id, "chart_id": request.chart_id,
        "expected_sql": SQL, "expected_datasource": 7,
        "date_filter": {"enabled": True, "parameterType": "yyyymmdd_number", "expression": expression},
    })
    engine = create_engine(f"sqlite:///{tmp_path / 'dates.db'}")
    CoreDashboard.__table__.create(engine)
    monkeypatch.setattr(service, "_load_dashboard_or_404", lambda session, board_id, _user: session.get(CoreDashboard, board_id))
    monkeypatch.setattr(service, "_prepare_dashboard_chart_item_query", PREPARE_QUERY)
    with SqlSession(engine) as session:
        session.add(fake.record)
        session.commit()
        original_get = session.get
        monkeypatch.setattr(session, "get", lambda model, *args, **kwargs:
                            fake.get(model, *args) if model is service.CoreDatasource else original_get(model, *args, **kwargs))
        service.update_chart_date_filter(session, user, request)
    # A new session proves this is persisted configuration, rather than a mutated in-memory chart.
    with SqlSession(engine) as reopened:
        chart = json.loads(reopened.get(CoreDashboard, "board").canvas_view_info)["a"]
        assert chart["dateFilter"]["expression"] == expression
        assert chart["data"]["data"] == []
        query = PREPARE_QUERY(fake.get(), chart, require_time_field=False)
        capability = query.date_filter_capability
        assert capability["expression"] == expression
        start = int(capability["resolvedStart"].replace("-", ""))
        end = int(capability["resolvedEnd"].replace("-", ""))
        reopened.execute(text("CREATE TABLE facts (dt BIGINT)"))
        for value in [start - 1, start, end, end + 1]:
            reopened.execute(text("INSERT INTO facts (dt) VALUES (:dt)"), {"dt": value})
        assert reopened.execute(text(query.source_sql)).scalars().all() == [start, end]
    engine.dispose()


def test_datasource_permission_failure_cannot_save_dates(setup, monkeypatch):
    session, user, request, before = setup
    monkeypatch.setattr(service, "_dashboard_chart_permission_audit", lambda *_args: ({"message": "没有表权限"}, False))
    with pytest.raises(HTTPException) as exc:
        service.update_chart_date_filter(session, user, request)
    assert exc.value.status_code == 403 and session.commits == 0
    assert json.loads(session.record.canvas_view_info) == before


def test_explicit_dates_are_not_filtered_again_by_an_old_pivot_range():
    pivot = {"enabled": True, "time_field": "dt", "metric_fields": ["amount"],
             "granularity": "day", "group_field": "country", "group_enabled": True,
             "range": "custom", "custom_start": "2026-10-05", "custom_end": "2026-10-11"}
    before = copy.deepcopy(pivot)
    query = service._prepare_dashboard_chart_query(
        SimpleNamespace(type="mysql"), SQL, pivot,
        date_filter=DashboardDateFilterRequest(parameter_type="yyyymmdd_number", expression=MONTH),
    )
    assert query.pivot["range"] == "source"
    assert query.pivot["custom_start"] == query.pivot["custom_end"] == ""
    assert query.pivot["group_field"] == "country" and query.pivot["granularity"] == "day"
    assert pivot == before


def test_date_save_audits_the_same_rendered_sql_as_the_query(setup, monkeypatch):
    session, user, request, _ = setup
    monkeypatch.setattr(service, "_prepare_dashboard_chart_item_query", PREPARE_QUERY)
    def audit(_session, _user, _datasource, sql, pivot):
        assert "{{dashboard_" not in sql
        assert pivot["range"] == "source"
        return None, False
    monkeypatch.setattr(service, "_dashboard_chart_permission_audit", audit)
    service.update_chart_date_filter(session, user, request)


def test_dates_can_be_saved_on_a_chart_inside_a_tab(setup):
    session, user, request, _ = setup
    session.record.component_data = json.dumps([{
        "id": "tab", "component": "SQTab", "propValue": [{
            "name": "tab-a", "componentData": [{"id": "a", "component": "SQView"}],
        }],
    }])
    service.update_chart_date_filter(session, user, request)
    assert json.loads(session.record.canvas_view_info)["a"]["dateFilter"]["expression"] == MONTH
