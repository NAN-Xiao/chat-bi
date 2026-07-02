"""
脚本说明：验证平台看板模板委托接口不会继承工作空间侧 ChatBI 依赖。
"""
from __future__ import annotations

from fastapi.routing import APIRoute

from apps.dashboard.api import dashboard_api
from apps.system.schemas.business_access import require_chatbi_business_user


def _route_dependencies(router, path: str, method: str = "GET") -> list[object]:
    method = method.upper()
    for route in router.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path == path and method in route.methods:
            return [dependency.call for dependency in route.dependant.dependencies]
    raise AssertionError(f"Route {method} {path} not found")


def test_platform_delegate_template_routes_do_not_require_chatbi_business_user() -> None:
    """
    是什么：平台委托模板接口应由自身业务权限判断，不应先被工作空间业务权限拦截。
    """
    assert require_chatbi_business_user not in _route_dependencies(
        dashboard_api.platform_delegate_router,
        "/dashboard/platform-delegate/template/list",
    )
    assert require_chatbi_business_user not in _route_dependencies(
        dashboard_api.platform_delegate_router,
        "/dashboard/platform-delegate/template/copy-from-dashboard",
        "POST",
    )
    assert require_chatbi_business_user not in _route_dependencies(
        dashboard_api.platform_delegate_router,
        "/dashboard/platform-delegate/template/copy-to-workspace",
        "POST",
    )
    assert require_chatbi_business_user not in _route_dependencies(
        dashboard_api.platform_router,
        "/dashboard/platform-template/refresh",
        "POST",
    )


def test_workspace_dashboard_routes_still_require_chatbi_business_user() -> None:
    """
    是什么：普通看板接口仍然必须保留工作空间侧 ChatBI 访问约束。
    """
    assert require_chatbi_business_user in _route_dependencies(
        dashboard_api.router,
        "/dashboard/list_resource",
        "POST",
    )
