"""flam 核心看板指标抽屉高度迁移契约。"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import resize_flam_core_dashboard_metric_drawers as migration  # noqa: E402


def _components(metric_height: int = 8) -> list[dict]:
    metrics = [
        {
            "id": chart_id,
            "x": 1 + index * 18,
            "y": 1,
            "sizeX": 18,
            "sizeY": metric_height,
            "style": {"keep": index},
        }
        for index, chart_id in enumerate(migration.METRIC_IDS)
    ]
    return [
        *metrics,
        {"id": "chart-a", "x": 1, "y": 9, "sizeX": 36, "sizeY": 13},
        {"id": "chart-b", "x": 37, "y": 22, "sizeX": 36, "sizeY": 13},
    ]


def test_resize_metric_drawers_expands_target_row_and_shifts_following_components() -> None:
    original = _components()
    snapshot = copy.deepcopy(original)

    migrated = migration.resize_metric_drawers(original)
    by_id = {item["id"]: item for item in migrated}

    assert original == snapshot
    assert all(by_id[chart_id]["sizeY"] == 10 for chart_id in migration.METRIC_IDS)
    assert by_id["chart-a"]["y"] == 11
    assert by_id["chart-b"]["y"] == 24
    assert by_id[migration.METRIC_IDS[0]]["style"] == {"keep": 0}


def test_resize_metric_drawers_is_idempotent() -> None:
    once = migration.resize_metric_drawers(_components())

    assert migration.resize_metric_drawers(once) == once


def test_resize_metric_drawers_rejects_partial_or_mixed_target_row() -> None:
    partial = _components()[:-3]
    with pytest.raises(RuntimeError, match="完整|缺失"):
        migration.resize_metric_drawers(partial)

    mixed = _components()
    mixed[0]["sizeY"] = 10
    with pytest.raises(RuntimeError, match="高度"):
        migration.resize_metric_drawers(mixed)


def test_resize_metric_drawers_rejects_duplicate_target_component_ids() -> None:
    components = _components()
    components.append(copy.deepcopy(components[0]))

    with pytest.raises(RuntimeError, match="重复"):
        migration.resize_metric_drawers(components)


def test_resize_metric_drawers_rejects_overlapping_following_component() -> None:
    components = _components()
    components[-2]["y"] = 8

    with pytest.raises(RuntimeError, match="重叠"):
        migration.resize_metric_drawers(components)


class _Cursor:
    rowcount = 0

    def __init__(self) -> None:
        self.sql = ""
        self.params = None

    def execute(self, sql: str, params: tuple) -> None:
        self.sql = sql
        self.params = params


def test_cas_update_requires_exact_owned_dashboard_row() -> None:
    cursor = _Cursor()

    with pytest.raises(RuntimeError, match="CAS"):
        migration.cas_update_dashboard(cursor, old_raw="old", new_raw="new")

    assert "tenant_id = %s" in cursor.sql
    assert "component_data = %s" in cursor.sql
    assert migration.DASHBOARD_ID in cursor.params
