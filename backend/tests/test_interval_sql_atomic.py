from dataclasses import replace
import sqlite3

import pytest
import sqlglot

from apps.dashboard.crud.interval_sql_compiler import compile_interval_sql
from test_interval_sql_plan import plan, config, field


def execute(rows, c=None):
    p = plan(c, dialect="mysql")
    p = replace(p, time=replace(p.time, scaffold="dashboard_dates AS (SELECT '2026-09-01' AS calendar_date UNION ALL SELECT '2026-09-02' UNION ALL SELECT '2026-09-03')"))
    sql = compile_interval_sql(p).replace("{{dashboard_start_date}}", "'2026-09-01'").replace("{{dashboard_end_date}}", "'2026-09-03'")
    with sqlite3.connect(":memory:") as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE events(subject TEXT,action TEXT,occurred_at INT,day TEXT,sequence INT,category TEXT,link TEXT,record_id INT,payload TEXT)")
        conn.executemany("INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?)", rows)
        return [dict(r) for r in conn.execute(sqlglot.transpile(sql, read="mysql", write="sqlite")[0])]


def row(action, time, sequence, *, subject="u", group="g", link="x", day="2026-09-01"):
    return (subject, action, time, day, sequence, group, link, sequence, "{}")


def test_equal_full_keys_emit_error_for_both_input_orders():
    rows = [row("open", 0, 1), row("close", 0, 1)]
    for items in (rows, rows[::-1]):
        result = execute(items)
        assert len(result) == 1 and result[0]["__interval_order_error"] == 1
        assert result[0]["interval_count"] is None


def test_null_order_key_fails_and_distinct_subjects_do_not_conflict():
    assert execute([row("open", 0, None)])[0]["__interval_order_error"] == 1
    results = execute([row("open", 0, 1, subject="a"), row("open", 0, 1, subject="b")])
    assert all(r["__interval_order_error"] == 0 for r in results)


def test_zero_scaffold_and_real_start_group_domain():
    empty = execute([])
    assert len(empty) == 3 and all(r["interval_count"] == 0 and r["avg_interval_seconds"] is None for r in empty)
    c = config(); c["groups"] = [field("category")]
    assert execute([], c) == []
    result = execute([row("open", 0, 1, group="a"), row("open", 0, 1, group="b", subject="v")], c)
    assert len(result) == 6 and all(r["interval_count"] == 0 for r in result)


def test_adjacent_same_event_and_fractional_duration():
    c = config(); c["interval"]["endEvent"]["eventName"] = "open"
    result = execute([row("open", t, i) for i, t in enumerate([0, 250, 1250, 3500])], c)[0]
    assert result["interval_count"] == 3
    assert result["median_interval_seconds"] == 1
    assert result["p25_interval_seconds"] == pytest.approx(.625)


def test_conflicts_outside_filters_are_not_included():
    c = config(); c["filters"] = {"rules": [{"field": field("subject"), "operator": "eq", "value": "u"}]}
    result = execute([row("open", 0, 1), row("close", 500, 2), row("open", 0, 1, subject="other"), row("close", 0, 1, subject="other")], c)
    assert result[0]["interval_count"] == 1 and result[0]["avg_interval_seconds"] == .5
