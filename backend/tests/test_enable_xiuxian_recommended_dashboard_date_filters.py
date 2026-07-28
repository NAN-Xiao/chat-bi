from __future__ import annotations

import json
import sys
from importlib import import_module
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

migration = import_module("enable_xiuxian_recommended_dashboard_date_filters")


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


def test_is_safe_candidate_allows_nested_current_date_range() -> None:
    sql = """
SELECT e.dt, COUNT(*)
FROM `event` e
WHERE e.dt BETWEEN CAST(DATE_FORMAT(DATE_SUB(DATE_SUB(CURDATE(), INTERVAL 1 DAY), INTERVAL 29 DAY), '%Y%m%d') AS SIGNED)
  AND CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
  AND e.event = 'ServerPayLog'
  AND EXISTS (
      SELECT 1 FROM `user` u
      WHERE u.dt = CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
  )
""".strip()

    assert migration.is_safe_candidate(sql) is True


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


def test_migrate_canvas_does_not_touch_unregistered_drawer() -> None:
    canvas = {
        "registered": _view(_partition_sql()),
        "unregistered": _view(_partition_sql()),
    }

    migrated, target_ids, unchanged = migration.migrate_canvas(
        canvas, allowed_ids={"registered"}
    )

    assert target_ids == ["registered"]
    assert migrated["unregistered"] == canvas["unregistered"]
    assert migration.stable_json_hash(migrated["unregistered"]) == unchanged["unregistered"]


class _FakeCursor:
    def __init__(self) -> None:
        self.sql = ""
        self.params = ()

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.sql = sql
        self.params = params

    def fetchall(self) -> list[dict]:
        return []


def test_select_recommended_dashboards_is_scoped_to_xiuxian_default_tree() -> None:
    cursor = _FakeCursor()

    assert migration._select_recommended_dashboards(cursor, lock=False) == []

    normalized = " ".join(cursor.sql.split()).upper()
    assert "CORE_DASHBOARD_TREE" in normalized
    assert "T.SCOPE = 'DEFAULT'" in normalized
    assert cursor.params == (migration.TENANT_ID, migration.DATASOURCE_ID)


def test_locking_recommended_dashboard_query_avoids_distinct() -> None:
    cursor = _FakeCursor()

    migration._select_recommended_dashboards(cursor, lock=True)

    assert "SELECT DISTINCT" not in " ".join(cursor.sql.split()).upper()
    assert "FOR UPDATE" in " ".join(cursor.sql.split()).upper()


def test_build_migration_plan_preserves_original_canvas_for_cas() -> None:
    original_canvas = {
        "registered": _view(_partition_sql()),
        "unregistered": _view(_partition_sql()),
    }
    raw_canvas = json.dumps(original_canvas, ensure_ascii=False, separators=(",", ":"))
    row = {
        "id": "dashboard-1",
        "tenant_id": migration.TENANT_ID,
        "datasource": migration.DATASOURCE_ID,
        "canvas_view_info": raw_canvas,
    }

    plan = migration.build_migration_plan(row, allowed_ids={"registered"})

    assert plan is not None
    assert plan["old_canvas"] == raw_canvas
    assert plan["target_ids"] == ["registered"]
    assert json.loads(plan["new_canvas"])["unregistered"] == original_canvas["unregistered"]
