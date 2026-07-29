from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import sqlglot


ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

repair = importlib.import_module("repair_xiuxian_dashboard_date_filter_gaps")


def test_level_distribution_merges_duplicate_with_clause():
    source = """WITH params AS (SELECT 1 AS start_dt, 2 AS end_dt)
WITH user_level AS (SELECT 1 AS uid)
SELECT uid FROM user_level"""

    rewritten = repair.repair_level_distribution_sql(source)

    assert rewritten.count("WITH") == 1
    sqlglot.parse_one(rewritten, read="mysql")


def test_next_day_retention_restores_register_active_and_retained_ctes():
    source = """WITH cohort AS (SELECT 1 AS cohort_dt), retained AS (
      SELECT c.cohort_dt FROM cohort c JOIN active AS a ON a.uid = c.uid
    ) SELECT * FROM retained"""

    rewritten = repair.repair_new_user_d1_retention_sql(source)
    tree = sqlglot.parse_one(rewritten, read="mysql")
    cte_names = {cte.alias_or_name.lower() for cte in tree.args["with_"].expressions}

    assert cte_names == {"cohort", "active", "retained"}
    assert rewritten.count(repair.START_TOKEN) == 2
    assert rewritten.count(repair.END_TOKEN) == 2
    assert "e.event = 'UserRegister'" in rewritten
    assert "e.event = 'UserActive'" in rewritten
    assert "INTERVAL 1 DAY" in rewritten


def test_configure_view_writes_v2_and_preserves_explicit_expression():
    expression = repair.dynamic_range(-31, -2)
    view = {
        "sql": f"SELECT * FROM event WHERE dt BETWEEN {repair.START_TOKEN} AND {repair.END_TOKEN}",
        "pivot": {"date_parameter_type": "yyyymmdd_number", "date_expression": {"version": 1}},
    }

    configured = repair.configure_view(view, {"expression": expression})

    assert configured["configVersion"] == 2
    assert configured["dateFilter"] == {
        "enabled": True,
        "parameterType": "yyyymmdd_number",
        "expression": expression,
    }
    assert "date_parameter_type" not in configured["pivot"]
    assert "date_expression" not in configured["pivot"]
