"""Manual refresh saves the authoritative query result and restores it with the same context."""
import copy
import json
import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from apps.dashboard.crud import dashboard_service as service
from apps.dashboard.models.dashboard_chart_config import DashboardDateFilterRequest
from test_dashboard_chart_date_filter_update import setup, PREPARE_QUERY, SQL, MONTH
from sqlmodel import Session as SqlSession, create_engine
from sqlalchemy import text
from apps.dashboard.models.dashboard_model import CoreDashboard

PREVIEW_SQL = service.preview_sql


@pytest.fixture
def refreshed(setup, monkeypatch):
    session, user, _, canvas = setup
    canvas["a"]["configVersion"] = 2
    session.record.canvas_view_info = json.dumps(canvas)
    monkeypatch.setattr(service, "_prepare_dashboard_chart_item_query", PREPARE_QUERY)
    calls = []
    result = {"status": "success", "message": "", "fields": ["dt"], "data": [{"dt": 20261010}]}
    def preview(_session, _user, request):
        calls.append(request)
        prepared = service._prepare_dashboard_chart_query(
            session.get(), request.sql, request.pivot, date_filter=request.date_filter, require_time_field=False)
        return {**copy.deepcopy(result), "date_filter_capability": prepared.date_filter_capability}
    monkeypatch.setattr(service, "preview_sql", preview)
    request = SimpleNamespace(dashboard_id="board", chart_id="a", expected_sql=SQL, expected_datasource=7,
                              pivot=None, date_filter=None, apply_date_filter=False)
    return session, user, request, calls, result


def refresh(*args):
    method = getattr(service, "refresh_chart_snapshot", None)
    assert callable(method), "Manual refresh must save the server query result, not just its cache"
    return method(*args)


def test_manual_refresh_saves_server_results_without_replacing_other_charts(refreshed):
    session, user, request, calls, result = refreshed
    before = json.loads(session.record.canvas_view_info)
    response = refresh(session, user, request)
    after = json.loads(session.record.canvas_view_info)
    assert len(calls) == 1 and calls[0].force_refresh
    assert session.commits == 1 and session.locked
    assert after["a"]["data"]["data"] == result["data"] == response["data"]
    assert after["a"]["fields"] == result["fields"]
    assert after["a"]["snapshotRefreshedAt"] > 0
    assert after["a"]["snapshotContext"]["fingerprint"]
    assert response["snapshot_saved"] is True
    assert after["a"]["sql"] == before["a"]["sql"]
    assert after["a"]["chart"] == before["a"]["chart"]
    assert after["b"] == before["b"]


def test_a_successful_empty_result_replaces_the_previous_saved_rows(refreshed):
    session, user, request, _, result = refreshed
    result["data"] = []
    refresh(session, user, request)
    chart = json.loads(session.record.canvas_view_info)["a"]
    assert chart["data"]["data"] == []
    assert chart["status"] == "success" and chart["dataState"] == "ready"
    assert chart["snapshotContext"]


@pytest.mark.parametrize("patch", [{"status": "failed"}, {"refresh_deferred": True}, {"cache_stale": True}])
def test_failed_or_deferred_queries_never_overwrite_a_saved_snapshot(refreshed, patch):
    session, user, request, _, result = refreshed
    before = session.record.canvas_view_info
    result.update(patch)
    response = refresh(session, user, request)
    assert response["status"] == "failed" and not response.get("snapshot_saved")
    assert session.commits == 0 and session.record.canvas_view_info == before


def test_read_only_user_cannot_save_a_refresh(refreshed, monkeypatch):
    session, user, request, calls, _ = refreshed
    def denied(*_args):
        raise HTTPException(403, "没有编辑权限")
    monkeypatch.setattr(service, "_require_edit_permission", denied)
    with pytest.raises(HTTPException) as error:
        refresh(session, user, request)
    assert error.value.status_code == 403 and not calls and session.commits == 0


@pytest.mark.parametrize("change", ["sql", "datasource", "dateFilter"])
def test_configuration_changed_while_querying_rejects_the_old_result(refreshed, change):
    session, user, request, _, _ = refreshed
    canvas = json.loads(session.record.canvas_view_info)
    canvas["a"][change] = {"sql": "SELECT 2", "datasource": 8,
                          "dateFilter": {"enabled": True, "parameterType": "yyyymmdd_number", "expression": MONTH}}[change]
    session.concurrent_canvas = json.dumps(canvas)
    with pytest.raises(HTTPException) as error:
        refresh(session, user, request)
    assert error.value.status_code == 409 and session.commits == 0


def test_unrelated_concurrent_edits_survive_refresh_save(refreshed):
    session, user, request, _, _ = refreshed
    canvas = json.loads(session.record.canvas_view_info)
    canvas["b"]["sql"] = "SELECT 1234"
    canvas["a"]["chart"]["title"] = "New title"
    session.concurrent_canvas = json.dumps(canvas)
    refresh(session, user, request)
    after = json.loads(session.record.canvas_view_info)
    assert after["b"] == canvas["b"] and after["a"]["chart"]["title"] == "New title"


def test_an_older_query_cannot_replace_a_newer_refresh_snapshot(refreshed):
    session, user, request, _, _ = refreshed
    canvas = json.loads(session.record.canvas_view_info)
    canvas["a"]["snapshotContext"] = {"version": 1, "queryStartedAt": str(time.time_ns() + 10_000_000_000)}
    session.concurrent_canvas = json.dumps(canvas)
    with pytest.raises(HTTPException) as error:
        refresh(session, user, request)
    assert error.value.status_code == 409 and session.commits == 0


def test_date_apply_saves_the_new_date_and_its_results_in_one_commit(refreshed):
    session, user, request, _, result = refreshed
    request.date_filter = DashboardDateFilterRequest(parameter_type="yyyymmdd_number", expression=MONTH)
    request.apply_date_filter = True
    refresh(session, user, request)
    after = json.loads(session.record.canvas_view_info)["a"]
    assert session.commits == 1
    assert after["dateFilter"]["expression"] == MONTH
    assert after["data"]["data"] == result["data"]
    assert after["dateFilterCapability"]["expression"] == MONTH
    assert after["sourceConfig"]["sql"]["builder"]["timeExpression"] == MONTH


def allow_loading(monkeypatch):
    for name, value in [("_ensure_datasource_access", 3), ("_user_name", ""),
                        ("_dashboard_refresh_policy_from_skills", {}), ("_can_edit_dashboard", True),
                        ("_can_share_dashboard", True), ("_can_set_default_dashboard", False)]:
        monkeypatch.setattr(service, name, lambda *_args, _value=value, **_kwargs: _value)


def test_reopening_restores_saved_rows_without_running_another_query(refreshed, monkeypatch):
    session, user, request, _, result = refreshed
    refresh(session, user, request)
    allow_loading(monkeypatch)
    monkeypatch.setattr(service, "_execute_dashboard_chart_sql", lambda *_args: pytest.fail("Saved results should be restored"))
    response = service._dashboard_payload(session, user, session.record, include_data=False)
    chart = json.loads(response["canvas_view_info"])["a"]
    assert chart["data"]["data"] == result["data"]
    assert chart["snapshotContext"] and chart["dataState"] == "ready"


@pytest.mark.parametrize("reason", ["date", "sql", "row_permission", "another_user"])
def test_reopening_rejects_a_snapshot_with_different_query_or_access_context(refreshed, monkeypatch, reason):
    session, user, request, _, _ = refreshed
    refresh(session, user, request)
    allow_loading(monkeypatch)
    canvas = json.loads(session.record.canvas_view_info)
    if reason == "date":
        canvas["a"]["dateFilter"]["expression"] = MONTH
    elif reason == "sql":
        canvas["a"]["sql"] = SQL.replace("facts", "other_facts")
    elif reason == "row_permission":
        monkeypatch.setattr(service, "_dashboard_chart_permission_audit", lambda *_args: (None, True))
    else:
        user.id = 102
    session.record.canvas_view_info = json.dumps(canvas)
    response = service._dashboard_payload(session, user, session.record, include_data=False)
    chart = json.loads(response["canvas_view_info"])["a"]
    assert chart["data"]["data"] == []
    assert "snapshotContext" not in chart


def test_server_refresh_persists_results_across_database_sessions(refreshed, monkeypatch, tmp_path):
    fake, user, request, _, _ = refreshed
    engine = create_engine(f"sqlite:///{tmp_path / 'snapshots.db'}")
    CoreDashboard.__table__.create(engine)
    monkeypatch.setattr(service, "_load_dashboard_or_404", lambda session, board_id, _user: session.get(CoreDashboard, board_id))
    monkeypatch.setattr(service, "preview_sql", PREVIEW_SQL)
    monkeypatch.setattr(service, "_dashboard_sql_preview_redis_enabled", lambda: False)
    monkeypatch.setattr(service, "_dashboard_sql_preview_cache_set", lambda *_args: None)
    queries = []
    def execute(session, _user, _datasource, sql, _pivot):
        queries.append(sql)
        rows = session.execute(text(sql)).mappings().all()
        return {"status": "success", "message": "", "fields": ["dt"], "data": [dict(row) for row in rows]}
    monkeypatch.setattr(service, "_execute_dashboard_chart_sql", execute)
    with SqlSession(engine) as session:
        session.add(fake.record)
        session.commit()
        original_get = session.get
        monkeypatch.setattr(session, "get", lambda model, *args, **kwargs:
                            fake.get() if model is service.CoreDatasource else original_get(model, *args, **kwargs))
        session.execute(text("CREATE TABLE facts (dt BIGINT)"))
        prepared = PREPARE_QUERY(fake.get(), json.loads(fake.record.canvas_view_info)["a"], require_time_field=False)
        end = int(prepared.date_filter_capability["resolvedEnd"].replace("-", ""))
        session.execute(text("INSERT INTO facts (dt) VALUES (:dt)"), {"dt": end})
        session.commit()
        refresh(session, user, request)
    assert len(queries) == 1
    allow_loading(monkeypatch)
    with SqlSession(engine) as reopened:
        original_get = reopened.get
        monkeypatch.setattr(reopened, "get", lambda model, *args, **kwargs:
                            fake.get() if model is service.CoreDatasource else original_get(model, *args, **kwargs))
        response = service._dashboard_payload(reopened, user, reopened.get(CoreDashboard, "board"), include_data=False)
        chart = json.loads(response["canvas_view_info"])["a"]
        assert chart["data"]["data"] == [{"dt": end}]
        assert chart["snapshotContext"]
    assert len(queries) == 1
    engine.dispose()
