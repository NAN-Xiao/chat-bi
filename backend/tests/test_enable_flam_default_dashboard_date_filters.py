from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

import enable_flam_default_dashboard_date_filters as migration


def _sql() -> str:
    return """
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`, COUNT(*) AS `事件数`
FROM `event` e
WHERE e.dt BETWEEN CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 29 DAY), '%Y%m%d') AS SIGNED)
  AND CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
  AND e.event = 'demo'
GROUP BY e.dt
""".strip()


def test_replace_unique_partition_range_uses_controlled_tokens():
    migrated = migration.replace_unique_partition_range(_sql())

    assert "e.dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}" in migrated
    assert "CURDATE()" not in migrated
    assert "{{dashboard_end_yyyymmdd}} AND e.event" in migrated
    assert "AND e.event = 'demo'" in migrated


def test_replace_unique_partition_range_rejects_multiple_windows():
    with pytest.raises(ValueError, match="唯一"):
        migration.replace_unique_partition_range(_sql() + "\nAND e.dt BETWEEN 20260701 AND 20260702")


def test_configure_view_preserves_chart_and_enables_date_parameters():
    original = {
        "sql": _sql(),
        "chart": {"title": "测试趋势", "xAxis": [{"value": "日期"}]},
        "sourceConfig": {"sql": {"keep": "value"}},
        "pivot": {"enabled": False, "keep": "value"},
    }

    migrated = migration.configure_view(original)

    assert original["sql"] == _sql()
    assert migrated["chart"] == original["chart"]
    assert migrated["sourceConfig"]["sql"]["keep"] == "value"
    assert migrated["pivot"]["keep"] == "value"
    assert migrated["pivot"]["time_field"] == "日期"
    assert migrated["pivot"]["date_parameter_type"] == "yyyymmdd_number"
    assert migrated["pivot"]["range_enabled"] is True
    assert migrated["pivot"]["date_expression"] == migration.DEFAULT_EXPRESSION


def test_repair_existing_migrated_sql_restores_boundary_whitespace():
    corrupted = migration.configure_view({"sql": _sql(), "pivot": {}, "sourceConfig": {}})
    corrupted["sql"] = corrupted["sql"].replace("}} AND e.event", "}}AND e.event")

    repaired = migration.repair_existing_migrated_view(corrupted)

    assert repaired["sql"] != corrupted["sql"]
    assert "{{dashboard_end_yyyymmdd}} AND e.event" in repaired["sql"]


def test_is_safe_candidate_rejects_snapshot_and_maturity_queries():
    assert migration.is_safe_candidate(_sql()) is True
    assert migration.is_safe_candidate("SELECT * FROM t WHERE e.dt = 20260727") is False
    assert migration.is_safe_candidate(_sql() + "\n-- retention cohort d7") is False


def test_migrate_channel_retention_sql_uses_selected_cohort_window():
    source = """
WITH
params AS (
  SELECT
    DATE_SUB(CURRENT_DATE, INTERVAL 15 DAY) AS start_date,
    DATE_SUB(CURRENT_DATE, INTERVAL 1 DAY) AS end_date
),
day_offsets AS (
  SELECT 0 AS n UNION ALL SELECT 1 UNION ALL SELECT 2
),
calendar AS (
  SELECT DATE_ADD(p.start_date, INTERVAL d.n DAY) AS cohort_date
  FROM params AS p CROSS JOIN day_offsets AS d
)
SELECT cohort_date
FROM calendar
WHERE cohort_date <= DATE_SUB(CURRENT_DATE, INTERVAL 8 DAY)
""".strip()

    migrated = migration.migrate_channel_retention_sql(source)

    assert migrated.startswith("WITH\n")
    assert "WITH RECURSIVE" not in migrated
    assert "digit_offsets AS" in migrated
    assert "{{dashboard_start_yyyymmdd}}" in migrated
    assert "{{dashboard_end_yyyymmdd}}" in migrated
    assert "WHERE d.n <= DATEDIFF(p.end_date, p.start_date)" in migrated
    assert "DATEDIFF(p.end_date, p.start_date)" in migrated
    assert "DATE_SUB(STR_TO_DATE(CAST({{dashboard_end_yyyymmdd}} AS CHAR), '%Y%m%d'), INTERVAL 7 DAY)" in migrated


def test_migrate_next_day_retention_sql_offsets_the_observation_window():
    source = """
SELECT *
FROM `event` AS `e`
WHERE `e`.`dt` BETWEEN
  CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 31 DAY), '%Y%m%d') AS SIGNED)
  AND CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 2 DAY), '%Y%m%d') AS SIGNED)
LEFT JOIN `event` AS `act`
  ON `act`.`dt` BETWEEN
    CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 30 DAY), '%Y%m%d') AS SIGNED)
    AND CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
""".strip()

    migrated = migration.migrate_next_day_retention_sql(source)

    assert migrated.count("{{dashboard_start_yyyymmdd}}") == 2
    assert migrated.count("{{dashboard_end_yyyymmdd}}") == 2
    assert "DATE_ADD(STR_TO_DATE(CAST({{dashboard_start_yyyymmdd}} AS CHAR), '%Y%m%d'), INTERVAL 1 DAY)" in migrated
    assert "DATE_SUB(STR_TO_DATE(CAST({{dashboard_end_yyyymmdd}} AS CHAR), '%Y%m%d'), INTERVAL 1 DAY)" in migrated


def test_migrate_active_retention_sql_uses_selected_range_for_cohorts():
    source = """
WITH
params AS (
  SELECT
    DATE_SUB(DATE_SUB(CURRENT_DATE, INTERVAL 1 DAY), INTERVAL 14 DAY) AS start_date,
    DATE_SUB(CURRENT_DATE, INTERVAL 1 DAY) AS end_date
),
day_offsets AS (
  SELECT 0 AS day_offset UNION ALL SELECT 1 UNION ALL SELECT 2
),
calendar AS (
  SELECT DATE_ADD(p.start_date, INTERVAL d.day_offset DAY) AS cohort_date
  FROM params p CROSS JOIN day_offsets d
)
SELECT * FROM calendar
""".strip()

    migrated = migration.migrate_active_retention_sql(source)

    assert migrated.startswith("WITH\n")
    assert "WITH RECURSIVE" not in migrated
    assert "digit_offsets AS" in migrated
    assert "{{dashboard_start_yyyymmdd}}" in migrated
    assert "{{dashboard_end_yyyymmdd}}" in migrated
    assert "WHERE d.day_offset <= DATEDIFF(p.end_date, p.start_date)" in migrated


def test_configure_explicit_date_view_keeps_existing_metadata():
    original = {
        "sql": "SELECT legacy",
        "chart": {"title": "留存趋势", "xAxis": [{"value": "日期"}]},
        "sourceConfig": {"sql": {"keep": "value"}},
        "pivot": {"enabled": False, "keep": "value"},
    }

    migrated = migration.configure_explicit_date_view(
        original,
        "SELECT {{dashboard_start_yyyymmdd}}, {{dashboard_end_yyyymmdd}}",
    )

    assert migrated["sql"].count("{{dashboard_start_yyyymmdd}}") == 1
    assert migrated["sourceConfig"]["sql"]["keep"] == "value"
    assert migrated["sourceConfig"]["sql"]["builder"]["dateExpressionPickerEnabled"] is True
    assert migrated["pivot"]["time_field"] == "日期"
    assert migrated["pivot"]["date_expression"] == migration.DEFAULT_EXPRESSION


def test_migrate_canvas_applies_explicit_channel_retention_target():
    source = """
WITH
params AS (
  SELECT DATE_SUB(CURRENT_DATE, INTERVAL 15 DAY) AS start_date,
         DATE_SUB(CURRENT_DATE, INTERVAL 1 DAY) AS end_date
),
day_offsets AS (
  SELECT 0 AS n UNION ALL SELECT 1 UNION ALL SELECT 2
),
calendar AS (
  SELECT DATE_ADD(p.start_date, INTERVAL d.n DAY) AS cohort_date
  FROM params AS p CROSS JOIN day_offsets AS d
)
SELECT * FROM calendar
""".strip()
    canvas = {
        "b55382d46c664f1dbd465964cc5e8da2": {
            "sql": source,
            "chart": {"title": "各渠道新增留存", "xAxis": [{"value": "日期"}]},
            "sourceConfig": {"sql": {}},
            "pivot": {},
        }
    }

    migrated, unchanged = migration.migrate_canvas(
        canvas,
        dashboard_id="8f86e50234794606bd2a33ec41ffa660",
    )

    view = migrated["b55382d46c664f1dbd465964cc5e8da2"]
    assert unchanged == {}
    assert view["sql"].startswith("WITH\n")
    assert view["sourceConfig"]["sql"]["builder"]["dateExpressionPickerEnabled"] is True


def test_repair_explicit_retention_sql_replaces_recursive_offsets_with_non_recursive_series():
    broken = """
WITH RECURSIVE
params AS (SELECT 1 AS start_date, 2 AS end_date),
day_offsets (n) AS (SELECT 0 AS n UNION ALL SELECT n + 1 AS n FROM day_offsets),
calendar AS (
  SELECT 1 FROM params AS p CROSS JOIN day_offsets AS d
)
SELECT * FROM calendar
""".strip()

    repaired = migration.repair_explicit_retention_sql(broken, column_name="n")

    assert repaired.startswith("WITH\n")
    assert "digit_offsets AS" in repaired
    assert "WHERE d.n <= DATEDIFF(p.end_date, p.start_date)" in repaired
