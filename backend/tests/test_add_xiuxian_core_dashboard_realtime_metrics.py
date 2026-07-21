"""验证修仙核心看板实时指标卡的 SQL 与布局契约。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import add_xiuxian_core_dashboard_realtime_metrics as repair  # noqa: E402


def test_metric_specs_use_realtime_table_and_authoritative_events() -> None:
    specs = {spec.title: spec for spec in repair.METRIC_SPECS}

    assert list(specs) == ["活跃用户", "新增用户", "充值人数", "充值总额"]
    for spec in specs.values():
        assert "event_realtime" in spec.sql
        assert "prod = 110000047" in spec.sql
        assert "DATE_FORMAT(CURDATE(), '%Y%m%d')" in spec.sql
        assert "`日期`" in spec.sql

    assert "event = 'UserActive'" in specs["活跃用户"].sql
    assert "COUNT(DISTINCT uid)" in specs["活跃用户"].sql
    assert "event = 'UserRegister'" in specs["新增用户"].sql
    assert "COUNT(DISTINCT uid)" in specs["新增用户"].sql
    assert "event = 'ServerPayLog'" in specs["充值人数"].sql
    assert "COUNT(DISTINCT uid)" in specs["充值人数"].sql
    assert "event = 'ServerPayLog'" in specs["充值总额"].sql
    assert "$.money" in specs["充值总额"].sql
    assert "/ 10000" in specs["充值总额"].sql


def test_rewrite_dashboard_adds_four_top_metrics_and_shifts_existing_components() -> None:
    components = [
        {"id": "old-a", "x": 1, "y": 1, "sizeX": 36, "sizeY": 13},
        {"id": "old-b", "x": 37, "y": 14, "sizeX": 36, "sizeY": 13},
    ]
    canvas = {"old-a": {"id": "old-a"}, "old-b": {"id": "old-b"}}
    rows = {
        spec.view_id: {"日期": "2026-07-20", spec.field: index}
        for index, spec in enumerate(repair.METRIC_SPECS, start=1)
    }

    new_components, new_canvas = repair.rewrite_dashboard(components, canvas, rows)

    old_components = {item["id"]: item for item in new_components if item["id"].startswith("old-")}
    assert old_components["old-a"]["y"] == 9
    assert old_components["old-b"]["y"] == 22

    metric_components = [
        item for item in new_components if item["id"] in repair.METRIC_VIEW_IDS
    ]
    assert [(item["x"], item["y"], item["sizeX"], item["sizeY"]) for item in metric_components] == [
        (1, 1, 18, 8),
        (19, 1, 18, 8),
        (37, 1, 18, 8),
        (55, 1, 18, 8),
    ]
    assert set(canvas).issubset(new_canvas)
    for spec in repair.METRIC_SPECS:
        view = new_canvas[spec.view_id]
        assert view["chart"]["type"] == "metric"
        assert view["chart"]["title"] == spec.title
        assert view["chart"]["xAxis"] == [{"value": "日期", "type": "other-info"}]
        assert view["chart"]["yAxis"] == [{"value": spec.field, "type": "y"}]
        assert view["data"]["data"] == [rows[spec.view_id]]


def test_rewrite_dashboard_is_idempotent() -> None:
    components = [{"id": "old", "x": 1, "y": 1, "sizeX": 72, "sizeY": 13}]
    canvas = {"old": {"id": "old"}}
    rows = {
        spec.view_id: {"日期": "2026-07-20", spec.field: 0}
        for spec in repair.METRIC_SPECS
    }

    first_components, first_canvas = repair.rewrite_dashboard(components, canvas, rows)
    second_components, second_canvas = repair.rewrite_dashboard(
        first_components, first_canvas, rows
    )

    old_component = next(item for item in second_components if item["id"] == "old")
    assert old_component["y"] == 9
    assert second_components == first_components
    assert second_canvas == first_canvas
