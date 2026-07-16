"""验证独立 ROI 看板 API 的路由、DTO 和安全边界。"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from apps import api as apps_api
from apps.dashboard.api import dashboard_api
from apps.roi_dashboard import api as roi_api
from apps.roi_dashboard.schemas import (
    RoiChartCreate,
    RoiChartListResponse,
    RoiChartPreviewRequest,
    RoiChartUpdate,
    RoiConfigUpdate,
    RoiDashboardCreate,
    RoiDashboardUpdate,
    RoiDatasourceOption,
)
from apps.roi_dashboard.service import list_roi_charts
from apps.system.schemas.business_access import require_chatbi_business_user


def make_user(
    *,
    tenant_id: int | None = 11,
    tenant_role: str = "admin",
    system_role: str = "viewer",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=7,
        tenant_id=tenant_id,
        tenant_role=tenant_role,
        system_role=system_role,
        isAdmin=system_role in {"system_admin", "collab_admin"},
        workspace_status="active",
    )


def route_method_map(router) -> dict[str, set[str]]:
    methods: dict[str, set[str]] = {}
    for route in router.routes:
        if isinstance(route, APIRoute):
            methods.setdefault(route.path, set()).update(route.methods or set())
    return methods


def route_dependencies(router, path: str, method: str = "GET") -> list[object]:
    for route in router.routes:
        if (
            isinstance(route, APIRoute)
            and route.path == path
            and method.upper() in (route.methods or set())
        ):
            return [dependency.call for dependency in route.dependant.dependencies]
    raise AssertionError(f"未找到路由：{method} {path}")


def test_roi_routes_are_registered_with_expected_methods() -> None:
    methods = route_method_map(roi_api.router)

    assert methods["/dashboard/roi/datasources"] == {"GET"}
    assert methods["/dashboard/roi/config"] == {"GET", "PUT"}
    assert methods["/dashboard/roi/list"] == {"GET"}
    assert methods["/dashboard/roi"] == {"POST"}
    assert methods["/dashboard/roi/{dashboard_id}"] == {"PATCH", "DELETE"}
    assert methods["/dashboard/roi/reorder"] == {"POST"}
    assert methods["/dashboard/roi/{dashboard_id}/charts"] == {"GET", "POST"}
    assert methods["/dashboard/roi/{dashboard_id}/charts/preview"] == {"POST"}
    assert methods["/dashboard/roi/{dashboard_id}/charts/{chart_id}"] == {
        "PUT",
        "DELETE",
    }
    assert methods["/dashboard/roi/{dashboard_id}/charts/reorder"] == {"POST"}


def test_roi_router_requires_chatbi_business_user() -> None:
    assert require_chatbi_business_user in route_dependencies(
        roi_api.router,
        "/dashboard/roi/config",
    )


def test_roi_request_dtos_do_not_accept_tenant_or_chart_datasource_forgery() -> None:
    request_models = (
        RoiConfigUpdate,
        RoiDashboardCreate,
        RoiDashboardUpdate,
        RoiChartPreviewRequest,
        RoiChartCreate,
        RoiChartUpdate,
    )
    assert all("tenant_id" not in model.model_fields for model in request_models)
    assert "datasource_id" in RoiConfigUpdate.model_fields
    assert "datasource_id" not in RoiChartPreviewRequest.model_fields
    assert "datasource_id" not in RoiChartCreate.model_fields
    assert "datasource_id" not in RoiChartUpdate.model_fields


def test_roi_datasource_response_contains_only_non_sensitive_fields() -> None:
    response = RoiDatasourceOption.model_validate(
        {
            "id": 101,
            "name": "ROI 数据源",
            "type": "pg",
            "type_name": "PostgreSQL",
            "configuration": '{"password":"secret"}',
        }
    )

    assert response.model_dump() == {
        "id": 101,
        "name": "ROI 数据源",
        "type": "pg",
        "type_name": "PostgreSQL",
    }


def test_roi_datasource_endpoint_maps_attribute_rows_without_credentials(
    monkeypatch,
) -> None:
    class FakeResult:
        def all(self):
            return [
                SimpleNamespace(
                    id=101,
                    name="ROI 数据源",
                    type="pg",
                    type_name="PostgreSQL",
                    configuration='{"password":"secret"}',
                )
            ]

    class FakeSession:
        def exec(self, _statement):
            return FakeResult()

    monkeypatch.setattr(
        roi_api,
        "list_roi_accessible_datasource_ids",
        lambda _session, _user: {101},
    )

    response = roi_api.list_roi_datasources_api(FakeSession(), make_user())

    assert [item.model_dump() for item in response] == [
        {
            "id": 101,
            "name": "ROI 数据源",
            "type": "pg",
            "type_name": "PostgreSQL",
        }
    ]


def test_roi_chart_list_response_hides_sql_without_datasource_access() -> None:
    response = RoiChartListResponse.model_validate(
        {
            "id": 901,
            "tenant_id": 11,
            "roi_dashboard_id": 301,
            "title": "付费趋势",
            "sql": "SELECT password FROM secret_table",
            "chart_type": "line",
            "chart_config": {},
            "layout_span": "full",
            "sort": 0,
            "status": 1,
            "version": 1,
            "create_by": 7,
            "update_by": 7,
            "create_time": 100,
            "update_time": 100,
            "can_execute": False,
            "can_edit": False,
            "error": "当前账号无此数据源权限",
            "query_result": None,
        }
    )

    assert response.sql is None
    assert response.can_execute is False
    assert response.can_edit is False


def test_roi_path_ids_remain_strings_until_service_boundary(monkeypatch) -> None:
    received: dict[str, object] = {}

    def fake_preview(_session, _current_user, dashboard_id, _request):
        received["dashboard_id"] = dashboard_id
        return {"status": "success", "fields": [], "data": [], "message": ""}

    monkeypatch.setattr(roi_api, "preview_roi_chart", fake_preview)
    request = RoiChartPreviewRequest(
        title="预览",
        sql="SELECT 1",
        chart_type="table",
    )

    roi_api.preview_chart_api("9007199254740993", request, None, make_user())

    assert received["dashboard_id"] == "9007199254740993"


def test_roi_service_safely_rejects_invalid_path_id() -> None:
    with pytest.raises(HTTPException) as exc:
        list_roi_charts(None, make_user(), "not-a-snowflake")

    assert exc.value.status_code == 400


@pytest.mark.parametrize(
    "user",
    [
        make_user(tenant_role="member"),
        make_user(tenant_role="owner", system_role="system_admin"),
    ],
)
def test_member_and_platform_identity_still_pass_through_service_gate(user) -> None:
    with pytest.raises(HTTPException) as exc:
        roi_api.list_roi_dashboards_api(None, user)

    assert exc.value.status_code == 403


def test_roi_router_is_registered_without_changing_regular_dashboard_router() -> None:
    assert any(
        getattr(route, "original_router", None) is roi_api.router
        for route in apps_api.api_router.routes
    )
    assert require_chatbi_business_user in route_dependencies(
        dashboard_api.router,
        "/dashboard/list_resource",
        "POST",
    )
