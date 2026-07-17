"""验证 ROI 专用看板迁移定义。"""

import importlib.util
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest


def load_migration(filename: str) -> ModuleType:
    module_path = (
        Path(__file__).resolve().parents[1] / "alembic" / "versions" / filename
    )
    spec = importlib.util.spec_from_file_location(module_path.stem, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_roi_dashboard_migration_definition() -> None:
    module = load_migration("145_roi_dashboard.py")
    assert module.revision == "145roidashboard"
    assert module.down_revision == "144dashboardname"
    assert set(module.TABLE_NAMES) == {
        "core_roi_workspace_config",
        "core_roi_dashboard",
        "core_roi_dashboard_chart",
    }
    assert module.ROI_LAYOUT_SPANS == ("full", "half", "third")


def test_roi_dashboard_models_follow_table_contract() -> None:
    from apps.roi_dashboard.models import (
        CoreRoiDashboard,
        CoreRoiDashboardChart,
        CoreRoiWorkspaceConfig,
    )

    assert CoreRoiWorkspaceConfig.__tablename__ == "core_roi_workspace_config"
    assert CoreRoiDashboard.__tablename__ == "core_roi_dashboard"
    assert CoreRoiDashboardChart.__tablename__ == "core_roi_dashboard_chart"
    assert (
        CoreRoiWorkspaceConfig(
            version=1, tenant_id=1, datasource_id=2, create_time=3, update_time=4
        ).deleted
        is False
    )
    assert (
        CoreRoiDashboard(tenant_id=1, name="ROI", create_time=3, update_time=4).sort
        == 0
    )
    assert (
        CoreRoiDashboardChart(
            tenant_id=1,
            roi_dashboard_id=2,
            title="收入",
            sql="SELECT 1",
            chart_type="line",
            chart_config={},
            create_time=3,
            update_time=4,
        ).layout_span
        == "full"
    )


def test_roi_request_dto_validation_and_defaults() -> None:
    from apps.roi_dashboard.schemas import (
        RoiChartCreate,
        RoiChartPreviewRequest,
        RoiChartUpdate,
        RoiConfigUpdate,
        RoiDashboardCreate,
        RoiDashboardUpdate,
    )

    assert RoiConfigUpdate(datasource_id=7).version is None
    assert RoiDashboardCreate(name="  ROI 看板  ").name == "ROI 看板"
    assert RoiDashboardUpdate(name="  新名称  ", version=2).name == "新名称"
    preview = RoiChartPreviewRequest(
        title="  收入趋势  ",
        sql="  SELECT 1  ",
        chart_type="  line  ",
    )
    assert (preview.title, preview.sql, preview.chart_type) == (
        "收入趋势",
        "SELECT 1",
        "line",
    )
    assert preview.chart_config == {}
    assert preview.layout_span == "full"
    assert RoiChartCreate(title="图", sql="SELECT 1", chart_type="bar").sort == 0
    assert (
        RoiChartUpdate(title="图", sql="SELECT 1", chart_type="bar", version=3).version
        == 3
    )

    with pytest.raises(ValueError, match="名称"):
        RoiDashboardCreate(name="   ")
    with pytest.raises(ValueError, match="标题"):
        RoiChartPreviewRequest(title="   ", sql="SELECT 1", chart_type="line")
    with pytest.raises(ValueError, match="SQL"):
        RoiChartPreviewRequest(title="图", sql="   ", chart_type="line")
    with pytest.raises(ValueError, match="图表类型"):
        RoiChartPreviewRequest(title="图", sql="SELECT 1", chart_type="   ")
    with pytest.raises(ValueError):
        RoiChartPreviewRequest(
            title="图", sql="SELECT 1", chart_type="line", layout_span="quarter"
        )


def test_roi_reorder_dto_uses_string_resource_ids() -> None:
    from apps.roi_dashboard.schemas import (
        RoiChartReorderRequest,
        RoiDashboardReorderRequest,
    )

    dashboards = RoiDashboardReorderRequest(
        items=[{"id": "9007199254740993", "sort": 1, "version": 2}]
    )
    charts = RoiChartReorderRequest(
        items=[
            {"id": "9007199254740995", "sort": 2, "layout_span": "half", "version": 3}
        ]
    )
    assert dashboards.items[0].id == "9007199254740993"
    assert charts.items[0].id == "9007199254740995"


def test_roi_response_dto_serializes_snowflake_ids_as_strings() -> None:
    from apps.roi_dashboard.schemas import (
        RoiChartResponse,
        RoiConfigResponse,
        RoiDashboardResponse,
    )

    config = RoiConfigResponse(
        id=9007199254740993,
        tenant_id=9007199254740994,
        datasource_id=7,
        datasource_name=None,
        version=1,
        can_execute=True,
        can_edit=True,
    )
    dashboard = RoiDashboardResponse(
        id=9007199254740995,
        tenant_id=9007199254740994,
        name="ROI",
        sort=0,
        status=1,
        version=1,
        create_by=9007199254740996,
        update_by=None,
        create_time=1,
        update_time=2,
    )
    chart = RoiChartResponse(
        id=9007199254740997,
        tenant_id=9007199254740994,
        roi_dashboard_id=9007199254740995,
        title="收入",
        sql="SELECT 1",
        chart_type="line",
        chart_config={},
        layout_span="third",
        sort=0,
        status=1,
        version=1,
        create_by=None,
        update_by=9007199254740998,
        create_time=1,
        update_time=2,
    )

    assert config.model_dump()["id"] == "9007199254740993"
    assert config.model_dump()["tenant_id"] == "9007199254740994"
    assert dashboard.model_dump()["create_by"] == "9007199254740996"
    assert chart.model_dump()["roi_dashboard_id"] == "9007199254740995"
    assert chart.model_dump()["update_by"] == "9007199254740998"

def test_roi_chart_request_validates_date_range() -> None:
    from apps.roi_dashboard.schemas import RoiChartPreviewRequest

    request = RoiChartPreviewRequest(
        title="图",
        sql="SELECT 1",
        chart_type="table",
        start_date=date(2026, 7, 10),
        end_date=date(2026, 7, 16),
    )
    assert request.start_date == date(2026, 7, 10)
    assert request.end_date == date(2026, 7, 16)

    with pytest.raises(ValueError, match="必须同时提供"):
        RoiChartPreviewRequest(
            title="图",
            sql="SELECT 1",
            chart_type="table",
            start_date=date(2026, 7, 10),
        )
    with pytest.raises(ValueError, match="不能晚于"):
        RoiChartPreviewRequest(
            title="图",
            sql="SELECT 1",
            chart_type="table",
            start_date=date(2026, 7, 17),
            end_date=date(2026, 7, 16),
        )
