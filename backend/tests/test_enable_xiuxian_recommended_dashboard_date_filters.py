from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

import enable_xiuxian_recommended_dashboard_date_filters as migration


def _partition_sql() -> str:
    return """
SELECT e.dt AS `日期`, COUNT(*) AS `事件数`
FROM `event` e
WHERE e.dt BETWEEN CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 29 DAY), '%Y%m%d') AS SIGNED)
  AND CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
  AND e.event = 'demo'
GROUP BY e.dt
""".strip()


def test_configure_view_replaces_one_dt_window_and_preserves_metadata() -> None:
    original = {
        "sql": _partition_sql(),
        "chart": {"title": "趋势", "xAxis": [{"value": "日期"}]},
        "sourceConfig": {"sql": {"keep": "value"}},
        "pivot": {"enabled": False, "keep": "value"},
    }

    migrated = migration.configure_view(original)

    assert original["sql"] == _partition_sql()
    assert migrated["sql"].count(migration.START_TOKEN) == 1
    assert migrated["sql"].count(migration.END_TOKEN) == 1
    assert migrated["sourceConfig"]["sql"]["keep"] == "value"
    assert migrated["pivot"]["keep"] == "value"
    assert migrated["pivot"]["date_expression"] == migration.DEFAULT_EXPRESSION
    assert migrated["sourceConfig"]["sql"]["builder"]["dateExpressionPickerEnabled"] is True


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM event_realtime WHERE dt BETWEEN 20260701 AND 20260702",
        _partition_sql() + " -- retention cohort d7",
        _partition_sql() + " AND e.dt BETWEEN 20260701 AND 20260702",
        "SELECT 1",
    ],
)
def test_is_safe_candidate_rejects_unsupported_sql(sql: str) -> None:
    assert migration.is_safe_candidate(sql) is False


def _view(sql: str) -> dict:
    return {
        "sql": sql,
        "chart": {"title": "测试图表"},
        "sourceConfig": {"sql": {}},
        "pivot": {},
    }


def test_migrate_canvas_changes_only_safe_drawers() -> None:
    canvas = {
        "safe": _view(_partition_sql()),
        "realtime": _view("SELECT * FROM event_realtime WHERE dt BETWEEN 20260701 AND 20260702"),
        "cohort": _view(_partition_sql() + " -- retention d7"),
    }

    migrated, target_ids, unchanged = migration.migrate_canvas(canvas)

    assert target_ids == ["safe"]
    assert migrated["safe"]["pivot"]["date_expression"] == migration.DEFAULT_EXPRESSION
    assert migration.stable_json_hash(migrated["realtime"]) == unchanged["realtime"]
    assert migration.stable_json_hash(migrated["cohort"]) == unchanged["cohort"]
    assert migration.verify_canvas(migrated, target_ids=target_ids, unchanged=unchanged)["safe"]
