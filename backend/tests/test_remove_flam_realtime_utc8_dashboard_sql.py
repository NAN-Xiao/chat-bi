"""Regression tests for removing fixed UTC+8 expressions from flam dashboards."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


def test_rewrite_canvas_removes_fixed_utc8_from_all_sql_storage_locations() -> None:
    from remove_flam_realtime_utc8_dashboard_sql import rewrite_canvas

    old_sql = (
        "SELECT DATE_ADD(FROM_UNIXTIME(`t`.`time` / 1000), INTERVAL 8 HOUR), "
        "DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR)"
    )
    canvas = {
        "view": {
            "sql": old_sql,
            "raw": old_sql,
            "sourceConfig": {
                "sql": {
                    "sql": old_sql,
                    "builder": {"agentAdvice": {"raw": old_sql}},
                }
            },
        },
        "unrelated": {"text": "INTERVAL 8 HOUR"},
    }

    rewritten, changed = rewrite_canvas(canvas)

    assert changed == 1
    assert rewritten["view"]["sql"] == (
        "SELECT FROM_UNIXTIME(`t`.`time` / 1000), UTC_TIMESTAMP()"
    )
    assert rewritten["view"]["raw"] == rewritten["view"]["sql"]
    assert rewritten["view"]["sourceConfig"]["sql"]["sql"] == rewritten["view"]["sql"]
    assert rewritten["view"]["sourceConfig"]["sql"]["builder"]["agentAdvice"]["raw"] == rewritten["view"]["sql"]
    assert rewritten["unrelated"]["text"] == "INTERVAL 8 HOUR"
