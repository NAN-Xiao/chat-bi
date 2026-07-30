from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = ROOT / "tools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

import enable_xiuxian_roi_dashboard_date_filters as migration


def test_targets_xiuxian_workspace_tenant_only():
    assert migration.TENANT_ID == 7482727237662281728


def _roi_sql() -> str:
    return """
SELECT *
FROM revenue r
WHERE r.dt >= CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 21 DAY), '%Y%m%d') AS BIGINT)
  AND r.dt <= CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS BIGINT)
UNION ALL
SELECT *
FROM spending s
WHERE s.dt >= CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 21 DAY), '%Y%m%d') AS BIGINT)
  AND s.dt <= CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), '%Y%m%d') AS BIGINT)
""".strip()


def test_configure_roi_view_shifts_every_cohort_window_by_360_days():
    original = {"sql": _roi_sql(), "chart": {"title": "ROI总览"}}

    migrated = migration.configure_roi_view(original)

    assert original["sql"] == _roi_sql()
    assert migrated["sql"].count("{{dashboard_start_yyyymmdd}}") == 2
    assert migrated["sql"].count("{{dashboard_end_yyyymmdd}}") == 2
    assert migrated["sql"].count("INTERVAL 360 DAY") == 4
    assert migrated["sourceConfig"]["sql"]["builder"]["dateExpressionPickerEnabled"] is True
    assert migrated["pivot"]["time_field"] == "投放日期"
    assert migrated["pivot"]["date_parameter_type"] == "yyyymmdd_number"


def test_configure_roi_view_rejects_nonstandard_cohort_window():
    with pytest.raises(ValueError, match="固定 ROI cohort 窗口"):
        migration.configure_roi_view({"sql": _roi_sql().replace("INTERVAL 21 DAY", "INTERVAL 20 DAY", 1)})
