"""推荐看板抽屉尺寸迁移契约。"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import resize_recommended_dashboard_drawers as migration  # noqa: E402


def _dashboard_components() -> tuple[list[dict], dict[str, dict]]:
    components = [
        {"id": "metric", "x": 1, "y": 1, "sizeX": 18, "sizeY": 8},
        {"id": "line-a", "x": 19, "y": 1, "sizeX": 54, "sizeY": 13},
        {"id": "table", "x": 1, "y": 14, "sizeX": 72, "sizeY": 14},
        {"id": "pie", "x": 1, "y": 28, "sizeX": 36, "sizeY": 15},
    ]
    views = {
        "metric": {"chart": {"type": "metric"}},
        "line-a": {"chart": {"type": "line"}},
        "table": {"chart": {"type": "table"}},
        "pie": {"chart": {"type": "pie"}},
    }
    return components, views


def test_resize_recommended_drawers_expands_chart_types_and_shifts_following_rows() -> None:
    original, views = _dashboard_components()
    snapshot = copy.deepcopy(original)

    migrated = migration.resize_dashboard_components(original, views)
    by_id = {item["id"]: item for item in migrated}

    assert original == snapshot
    assert by_id["metric"]["sizeY"] == 10
    assert by_id["line-a"]["sizeY"] == 16
    assert by_id["table"]["sizeY"] == 14
    assert by_id["pie"]["sizeY"] == 16
    assert by_id["table"]["y"] == 17
    assert by_id["pie"]["y"] == 31


def test_resize_recommended_drawers_is_idempotent_and_rejects_overlap() -> None:
    components, views = _dashboard_components()
    once = migration.resize_dashboard_components(components, views)
    assert migration.resize_dashboard_components(once, views) == once

    invalid = copy.deepcopy(components)
    invalid[-1]["y"] = 10
    with pytest.raises(RuntimeError, match="重叠"):
        migration.resize_dashboard_components(invalid, views)


def test_resize_recommended_drawers_rejects_missing_view_metadata() -> None:
    components, views = _dashboard_components()
    del views["line-a"]

    with pytest.raises(RuntimeError, match="图表配置"):
        migration.resize_dashboard_components(components, views)
