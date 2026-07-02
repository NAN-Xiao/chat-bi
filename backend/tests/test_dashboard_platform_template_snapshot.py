"""
脚本说明：验证平台看板模板会保存静态图表数据快照。
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from apps.dashboard.crud import dashboard_service
from apps.dashboard.models.dashboard_model import CoreDashboard


def _source_dashboard() -> CoreDashboard:
    return CoreDashboard(
        id="dashboard-1",
        tenant_id=2001,
        name="活跃看板",
        datasource=7,
        node_type="leaf",
        canvas_view_info="{}",
    )


def _user():
    return SimpleNamespace(id=1001, tenant_id=2001, workspace_status="platform_workspace_delegate")


def test_materialize_platform_template_canvas_view_info_stores_query_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    是什么：复制为平台模板时，应把源图表查询结果固化到模板快照里，并清掉数据源绑定。
    """
    monkeypatch.setattr(dashboard_service, "_dashboard_chart_permission_audit", lambda *_args, **_kwargs: (None, False))
    monkeypatch.setattr(
        dashboard_service,
        "_execute_dashboard_chart_sql",
        lambda *_args, **_kwargs: {
            "status": "success",
            "fields": ["day", "dau"],
            "data": [{"day": "2026-06-30", "dau": 100}],
            "message": "",
            "refreshed_at": 1782864000000,
        },
    )

    canvas_view_info = json.dumps(
        {
            "view-1": {
                "id": "view-1",
                "datasource": 7,
                "sql": "select day, dau from fact_active",
                "chart": {
                    "id": "view-1",
                    "type": "line",
                    "xAxis": [{"value": "day"}],
                    "yAxis": [{"value": "dau"}],
                },
                "data": {},
            }
        }
    )

    result = json.loads(
        dashboard_service._materialize_dashboard_template_canvas_view_info(
            object(),
            _user(),
            _source_dashboard(),
            canvas_view_info,
        )
    )

    view = result["view-1"]
    assert view["datasource"] is None
    assert view["status"] == "success"
    assert view["dataState"] == "ready"
    assert view["fields"] == ["day", "dau"]
    assert view["data"]["fields"] == ["day", "dau"]
    assert view["data"]["data"] == [{"day": "2026-06-30", "dau": 100}]
    assert view["data"]["snapshotRefreshedAt"] == 1782864000000


def test_clone_dashboard_canvas_payload_aligns_view_info_to_sqview_component_ids() -> None:
    """
    是什么：源看板组件 id 与 canvas_view_info key 不一致时，模板快照仍应按组件 id 组织。
    """
    component_data = json.dumps(
        [
            {"id": "component-1", "component": "SQView", "_dragId": "component-1"},
            {"id": "component-2", "component": "SQView", "_dragId": "component-2"},
        ]
    )
    canvas_view_info = json.dumps(
        {
            "view-a": {
                "id": "view-a",
                "chart": {"id": "view-a", "title": "DAU"},
                "data": {"data": [{"day": "2026-06-30", "dau": 100}], "fields": ["day", "dau"]},
            },
            "view-b": {
                "id": "view-b",
                "chart": {"id": "view-b", "title": "WAU"},
                "data": {"data": [{"week": "2026-W26", "wau": 200}], "fields": ["week", "wau"]},
            },
        }
    )

    cloned_component_data, _, cloned_canvas_view_info = dashboard_service._clone_dashboard_canvas_payload(
        component_data,
        "{}",
        canvas_view_info,
    )

    cloned_components = json.loads(cloned_component_data)
    cloned_views = json.loads(cloned_canvas_view_info)
    cloned_component_ids = [item["id"] for item in cloned_components]

    assert list(cloned_views.keys()) == cloned_component_ids
    assert cloned_views[cloned_component_ids[0]]["chart"]["title"] == "DAU"
    assert cloned_views[cloned_component_ids[0]]["id"] == cloned_component_ids[0]
    assert cloned_views[cloned_component_ids[0]]["chart"]["id"] == cloned_component_ids[0]
    assert cloned_views[cloned_component_ids[1]]["chart"]["title"] == "WAU"


def test_align_canvas_view_info_to_component_ids_repairs_existing_template_payload() -> None:
    """
    是什么：已有模板快照错位时，加载响应可以不跑 SQL，直接把快照按组件 id 对齐。
    """
    views = {
        "view-a": {"id": "view-a", "chart": {"id": "view-a", "title": "DAU"}},
        "view-b": {"id": "view-b", "chart": {"id": "view-b", "title": "WAU"}},
    }

    aligned = dashboard_service._align_canvas_view_info_to_component_ids(
        ["component-1", "component-2"],
        views,
    )

    assert list(aligned.keys()) == ["component-1", "component-2"]
    assert aligned["component-1"]["chart"]["title"] == "DAU"
    assert aligned["component-1"]["chart"]["id"] == "component-1"
    assert aligned["component-2"]["chart"]["title"] == "WAU"


def test_platform_template_empty_sql_chart_needs_repair() -> None:
    """
    是什么：旧模板里有 SQL 但没有 rows 和 fields 时，应判定为缺少快照并触发修复。
    """
    template = CoreDashboard(
        id="template-1",
        tenant_id=dashboard_service.DEFAULT_TENANT_ID,
        datasource=None,
        content_id="0",
        source=dashboard_service.DASHBOARD_SOURCE_PLATFORM_TEMPLATE,
        node_type="leaf",
        canvas_view_info=json.dumps(
            {
                "view-1": {
                    "id": "view-1",
                    "datasource": None,
                    "sql": "select day, dau from fact_active",
                    "chart": {"id": "view-1", "type": "line"},
                    "data": {"data": [], "fields": []},
                    "fields": [],
                    "status": "success",
                    "dataState": "ready",
                }
            }
        ),
    )

    assert dashboard_service._platform_template_needs_snapshot_repair(template) is True


def test_platform_template_field_only_zero_timestamp_snapshot_needs_repair() -> None:
    """
    是什么：旧模板可能只保存了字段和 0 时间戳，也应回源刷新真实图表数据。
    """
    template = CoreDashboard(
        id="template-1",
        tenant_id=dashboard_service.DEFAULT_TENANT_ID,
        datasource=None,
        content_id="0",
        source=dashboard_service.DASHBOARD_SOURCE_PLATFORM_TEMPLATE,
        node_type="leaf",
        canvas_view_info=json.dumps(
            {
                "view-1": {
                    "id": "view-1",
                    "datasource": None,
                    "sql": "select day, dau from fact_active",
                    "chart": {"id": "view-1", "type": "line"},
                    "data": {"data": [], "fields": ["day", "dau"], "snapshotRefreshedAt": 0},
                    "fields": ["day", "dau"],
                    "status": "success",
                    "dataState": "ready",
                    "snapshotRefreshedAt": 0,
                }
            }
        ),
    )

    assert dashboard_service._platform_template_needs_snapshot_repair(template) is True


def test_platform_template_empty_materialized_snapshot_does_not_need_repair() -> None:
    """
    是什么：已经固化过的空结果模板快照，不应每次打开都反复回源查询。
    """
    template = CoreDashboard(
        id="template-1",
        tenant_id=dashboard_service.DEFAULT_TENANT_ID,
        datasource=None,
        content_id="0",
        source=dashboard_service.DASHBOARD_SOURCE_PLATFORM_TEMPLATE,
        node_type="leaf",
        canvas_view_info=json.dumps(
            {
                "view-1": {
                    "id": "view-1",
                    "datasource": None,
                    "sql": "select day, dau from fact_active",
                    "chart": {"id": "view-1", "type": "line"},
                    "data": {"data": [], "fields": [], "snapshotRefreshedAt": 1782864000000},
                    "fields": [],
                    "status": "success",
                    "dataState": "ready",
                    "snapshotRefreshedAt": 1782864000000,
                }
            }
        ),
    )

    assert dashboard_service._platform_template_needs_snapshot_repair(template) is False
