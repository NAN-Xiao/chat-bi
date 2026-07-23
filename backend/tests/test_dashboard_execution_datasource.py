"""验证看板图表执行数据源只能来自当前工作空间的绑定与 ROI 配置。"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from apps.dashboard.crud import dashboard_service
from apps.dashboard.models.dashboard_model import CoreDashboard, DashboardSqlPreview


class _Session:
    def get(self, _model, datasource_id: int):
        return SimpleNamespace(id=datasource_id, name=f"数据源{datasource_id}", status="success")


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=1001, tenant_id=2001)


def test_chart_execution_datasources_include_only_bound_and_roi(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """候选集只能包含当前空间的绑定数据源和 ROI 数据源。"""
    monkeypatch.setattr(dashboard_service, "get_bound_datasource_id_for_tenant", lambda *_args: 11)
    monkeypatch.setattr(dashboard_service, "get_roi_datasource_id_for_tenant", lambda *_args: 22)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 1)

    options = dashboard_service.list_chart_execution_datasources(_Session(), _user())

    assert [(item.id, item.role) for item in options] == [(11, "bound"), (22, "roi")]


def test_roi_chart_execution_datasource_does_not_require_user_grant(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """空间已配置的 ROI 数据源不依赖用户级数据源授权。"""
    monkeypatch.setattr(dashboard_service, "get_bound_datasource_id_for_tenant", lambda *_args: 11)
    monkeypatch.setattr(dashboard_service, "get_roi_datasource_id_for_tenant", lambda *_args: 22)

    def ensure_bound_access(_session, _user, datasource_id, **_kwargs):
        if datasource_id == 22:
            raise HTTPException(status_code=403, detail="用户未被单独授权")
        return datasource_id

    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", ensure_bound_access)

    options = dashboard_service.list_chart_execution_datasources(_Session(), _user())

    assert [(item.id, item.role) for item in options] == [(11, "bound"), (22, "roi")]
    assert dashboard_service.resolve_chart_execution_datasource(_Session(), _user(), 22) == 22


def test_chart_execution_datasources_deduplicate_roi_matching_bound(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ROI 数据源与绑定数据源相同不会产生重复选项。"""
    monkeypatch.setattr(dashboard_service, "get_bound_datasource_id_for_tenant", lambda *_args: 11)
    monkeypatch.setattr(dashboard_service, "get_roi_datasource_id_for_tenant", lambda *_args: 11)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 1)

    options = dashboard_service.list_chart_execution_datasources(_Session(), _user())

    assert [(item.id, item.role) for item in options] == [(11, "bound")]


def test_chart_execution_datasource_rejects_id_outside_current_workspace(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """构造其他空间或平台数据源 ID 必须被服务端拒绝。"""
    monkeypatch.setattr(dashboard_service, "get_bound_datasource_id_for_tenant", lambda *_args: 11)
    monkeypatch.setattr(dashboard_service, "get_roi_datasource_id_for_tenant", lambda *_args: 22)
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 1)

    with pytest.raises(HTTPException, match="当前空间未配置该图表执行数据源") as error:
        dashboard_service.resolve_chart_execution_datasource(_Session(), _user(), 99)

    assert error.value.status_code == 403


def test_dashboard_sql_preview_uses_resolved_chart_execution_datasource(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """预览 SQL 必须执行服务端解析后的图表数据源。"""
    resolved_calls: list[int] = []
    execute_calls: list[int] = []
    monkeypatch.setattr(
        dashboard_service,
        "resolve_chart_execution_datasource",
        lambda _session, _user, datasource_id: resolved_calls.append(datasource_id) or 22,
    )
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 11)
    monkeypatch.setattr(
        dashboard_service,
        "_dashboard_chart_permission_audit",
        lambda *_args, **_kwargs: (None, False),
    )
    monkeypatch.setattr(
        dashboard_service,
        "_execute_dashboard_chart_sql",
        lambda _session, _user, datasource_id, *_args, **_kwargs: execute_calls.append(datasource_id) or {
            "status": "success",
            "fields": ["value"],
            "data": [{"value": 1}],
            "message": "",
        },
    )

    result = dashboard_service.preview_sql(
        _Session(),
        _user(),
        DashboardSqlPreview(datasource=22, sql="select 1", force_refresh=True),
    )

    assert result["status"] == "success"
    assert resolved_calls == [22]
    assert execute_calls == [22]


def test_dashboard_chart_execution_marks_resolved_datasource_as_prevalidated(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """图表执行器不得对已完成空间级 ROI 校验的数据源重复做用户级校验。"""
    execution_options: list[bool] = []
    monkeypatch.setattr(dashboard_service, "get_bound_datasource_id_for_tenant", lambda *_args: 11)
    monkeypatch.setattr(dashboard_service, "get_roi_datasource_id_for_tenant", lambda *_args: 22)
    monkeypatch.setattr(
        dashboard_service,
        "execute_user_query",
        lambda *_args, **kwargs: execution_options.append(
            kwargs.get("datasource_access_checked", False)
        ) or {
            "status": "success",
            "fields": ["value"],
            "data": [{"value": 1}],
            "message": "",
        },
    )

    result = dashboard_service._execute_dashboard_chart_sql(
        _Session(), _user(), 22, "select 1"
    )

    assert result["status"] == "success"
    assert execution_options == [True]


def test_dashboard_api_exposes_execution_datasource_candidates() -> None:
    """编辑器只能通过专用只读接口取得当前空间候选集。"""
    from apps.dashboard.api import dashboard_api

    assert hasattr(dashboard_api, "execution_datasources_api")


def test_dashboard_refresh_uses_saved_roi_chart_datasource(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已保存的 ROI 图表刷新时必须执行 ROI 数据源，而非被看板默认数据源拒绝。"""
    execute_calls: list[int] = []
    monkeypatch.setattr(
        dashboard_service,
        "resolve_chart_execution_datasource",
        lambda _session, _user, datasource_id: 11 if datasource_id is None else datasource_id,
    )
    monkeypatch.setattr(dashboard_service, "_ensure_datasource_access", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(dashboard_service, "_dashboard_refresh_policy_from_skills", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(dashboard_service, "_user_name", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(dashboard_service, "_can_edit_dashboard", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(dashboard_service, "_can_share_dashboard", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(dashboard_service, "_can_set_default_dashboard", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        dashboard_service,
        "_execute_dashboard_chart_sql",
        lambda _session, _user, datasource_id, *_args, **_kwargs: execute_calls.append(datasource_id) or {
            "status": "success",
            "fields": ["value"],
            "data": [{"value": 1}],
            "message": "",
        },
    )
    record = CoreDashboard(
        id="dashboard-1",
        tenant_id=2001,
        name="任意名称看板",
        pid="root",
        datasource=11,
        node_type="leaf",
        type="dashboard",
        canvas_style_data="{}",
        component_data="[]",
        canvas_view_info=json.dumps({"chart-1": {"id": "chart-1", "datasource": 22, "sql": "select 1"}}),
        status=1,
        delete_flag=0,
    )

    result = dashboard_service._dashboard_payload(
        _Session(),
        _user(),
        record,
        default_context=True,
        include_data=True,
    )

    chart = json.loads(result["canvas_view_info"])["chart-1"]
    assert execute_calls == [22]
    assert chart["data"]["data"] == [{"value": 1}]


def test_canvas_validation_accepts_saved_roi_chart_datasource(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """保存看板时，ROI 图表应通过当前空间候选集校验而非强制等于看板默认数据源。"""
    calls: list[int | None] = []
    monkeypatch.setattr(
        dashboard_service,
        "resolve_chart_execution_datasource",
        lambda _session, _user, datasource_id: calls.append(datasource_id) or 22,
    )
    dashboard = SimpleNamespace(
        canvas_view_info=json.dumps({"chart-1": {"datasource": 22, "sql": "select 1"}}),
    )

    dashboard_service._validate_canvas_datasources(_Session(), _user(), dashboard)

    assert calls == [22]
    assert json.loads(dashboard.canvas_view_info)["chart-1"]["datasource"] == 22
