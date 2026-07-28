from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

import enable_flam_month_card_retention_date_filter as migration


def _month_card_sql() -> str:
    return """
SELECT e.uid
FROM `event` e
WHERE e.dt BETWEEN CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 60 DAY), '%Y%m%d') AS SIGNED)
               AND CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 30 DAY), '%Y%m%d') AS SIGNED)
  AND e.event = 'ServerPayLog'
""".strip()


def test_configure_month_card_retention_shifts_selected_window_by_maturity_days():
    original = {
        "sql": _month_card_sql(),
        "chart": {"title": "购买月卡用户的30日留存", "xAxis": [{"value": "留存日"}]},
    }

    migrated = migration.configure_month_card_retention_view(original)

    assert original["sql"] == _month_card_sql()
    assert "{{dashboard_start_yyyymmdd}}" in migrated["sql"]
    assert "{{dashboard_end_yyyymmdd}}" in migrated["sql"]
    assert migrated["sql"].count("INTERVAL 30 DAY") == 2
    assert migrated["sourceConfig"]["sql"]["builder"]["dateExpressionPickerEnabled"] is True
    assert migrated["pivot"]["date_parameter_type"] == "yyyymmdd_number"
    assert migrated["pivot"]["date_expression"] == migration.DEFAULT_EXPRESSION


def test_configure_month_card_retention_rejects_unexpected_sql_window():
    original = {"sql": _month_card_sql().replace("INTERVAL 60 DAY", "INTERVAL 59 DAY")}

    try:
        migration.configure_month_card_retention_view(original)
    except ValueError as exc:
        assert "固定成熟窗口" in str(exc)
    else:
        raise AssertionError("应拒绝不符合预期的月卡留存 SQL")
