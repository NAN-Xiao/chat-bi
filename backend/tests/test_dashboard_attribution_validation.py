import sqlite3

import pytest
import sqlglot
from sqlglot import exp

from apps.dashboard.crud import ai_sql_generator as generator
from apps.dashboard.crud.sql_generation_validation import derived_column_issues, encoded_date_issues
from apps.dashboard.models.dashboard_model import DashboardAiSqlGenerateResponse
from attribution_sql_fixture import attribution_sql


def config(method="linear", mode="same_day"):
    return {"analysis_model": "attribution", "attribution": {
        "method": method, "window": {"mode": mode, "value": 7, "unit": "day"},
    }, "time": {"field": {"table": "events", "field": "dt"}, "date_parameter_type": "yyyymmdd_number"}}


@pytest.mark.parametrize("method", ["first", "last", "linear"])
@pytest.mark.parametrize("mode", ["same_day", "duration"])
def test_complete_attribution_queries_pass(method, mode):
    sql = attribution_sql(method=method, mode=mode)
    assert generator._attribution_sql_result_issues(sql, config(method, mode), sql_dialect="mysql") == []
    assert derived_column_issues(sqlglot.parse_one(sql, read="mysql")) == []


def test_same_day_plan_has_no_duration():
    normalized = config()
    plan = generator._build_sql_plan(normalized, {})["result_contract"]
    assert plan["window_mode"] == "same_day"
    assert plan["window_seconds"] is None
    normalized["attribution"]["window"]["mode"] = "duration"
    assert generator._build_sql_plan(normalized, {})["result_contract"]["window_seconds"] == 7 * 86400


@pytest.mark.parametrize("mutation, expected", [
    (lambda sql: sql.replace("t.target_date = tc.touch_date", "tc.touch_date >= t.target_date - INTERVAL 1 DAY"), "target_date = touch_date"),
    (lambda sql: sql.replace("PARTITION BY t.target_id", "PARTITION BY t.entity_id, t.target_date"), "target_id"),
    (lambda sql: sql.replace("COUNT(DISTINCT target_id)", "COUNT(DISTINCT entity_id)"), "target_count"),
    (lambda sql: sql.replace("tc.touch_time <= t.target_time", "tc.touch_time >= t.target_time"), "touch_time <= target_time"),
])
def test_rejects_wrong_window_or_target_grain(mutation, expected):
    issues = generator._attribution_sql_result_issues(mutation(attribution_sql()), config(), sql_dialect="mysql")
    assert any(expected in issue for issue in issues)


@pytest.mark.parametrize("mutation, expected", [
    (lambda sql: sql.replace("event_id AS target_id", "CONCAT(actor, occurred_at) AS target_id"), "target_id"),
    (lambda sql: sql.replace("1.0 / NULLIF(touch_count, 0)", "target_value / NULLIF(touch_count, 0)"), "linear_weight"),
    (lambda sql: sql.replace("COUNT(tc.touch_time)", "COUNT(*)"), "COUNT(*)"),
    (lambda sql: sql.replace("INTERVAL 7 DAY", "INTERVAL 1 DAY"), "精确回溯"),
])
def test_rejects_false_event_identity_weight_and_duration(mutation, expected):
    sql = mutation(attribution_sql(mode="duration"))
    issues = generator._attribution_sql_result_issues(sql, config(mode="duration"), sql_dialect="mysql")
    assert any(expected in issue for issue in issues)


def test_query_local_target_identity_preserves_duplicate_events():
    sql = attribution_sql().replace("event_id AS target_id", "ROW_NUMBER() OVER (ORDER BY actor, occurred_at) AS target_id")
    assert generator._attribution_sql_result_issues(sql, config(), sql_dialect="mysql") == []


def test_target_identity_cannot_hide_target_aggregation():
    sql = attribution_sql().replace("SELECT event_id AS target_id", "SELECT DISTINCT event_id AS target_id")
    assert any("去重或聚合" in issue for issue in generator._attribution_sql_result_issues(sql, config(), sql_dialect="mysql"))


def test_duration_executes_across_month_boundary_with_earlier_touch():
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE events(event_id INTEGER, actor TEXT, occurred_at TEXT, kind TEXT, channel TEXT)")
        db.executemany("INSERT INTO events VALUES (?, ?, ?, ?, ?)", [
            (1, "a", "2026-08-31 23:59:00", "email", "web"),
            (2, "a", "2026-09-01 00:01:00", "conversion", "web"),
            (3, "a", "2026-08-20 00:01:00", "search", "web"),
        ])
        query = attribution_sql(mode="duration")
        assert generator._attribution_sql_result_issues(query, config(mode="duration"), sql_dialect="mysql") == []
        # SQLite uses DATETIME modifiers instead of the SQL INTERVAL operator.
        def sqlite_interval(node):
            if isinstance(node, exp.Sub) and isinstance(node.expression, exp.Interval):
                interval = node.expression
                return exp.Anonymous(this="DATETIME", expressions=[
                    node.this.copy(), exp.Literal.string(f"-{interval.this.this} {interval.args['unit'].name}"),
                ])
            return node
        sqlite_query = sqlglot.parse_one(query, read="mysql").transform(sqlite_interval).sql(dialect="sqlite")
        assert db.execute(sqlite_query).fetchall() == [("email", 1, 1.0, 100.0)]


def test_revenue_lineage_failure_reports_missing_column():
    sql = """WITH base AS (SELECT uid, STR_TO_DATE(CAST(dt AS CHAR), '%Y%m%d') AS cohort_date FROM events),
    cohort AS (SELECT cohort_date, COUNT(DISTINCT uid) AS cohort_size FROM base GROUP BY cohort_date),
    joined AS (SELECT c.cohort_date, c.uid FROM cohort c)
    SELECT cohort_date FROM joined"""
    issues = generator._revenue_date_output_issues(sql, config(), sql_dialect="mysql")
    assert any("uid" in issue for issue in issues)
    assert not any("必须将 YYYYMMDD" in issue for issue in issues)


@pytest.mark.parametrize("method", ["first", "last"])
def test_first_last_requires_selection_after_ranking(method):
    sql = attribution_sql(method=method).replace("WHERE touch_rank = 1", "")
    issues = generator._attribution_sql_result_issues(sql, config(method), sql_dialect="mysql")
    assert any("序号 = 1" in issue for issue in issues)


@pytest.mark.parametrize("dialect, expression", [
    ("postgres", "TO_DATE(CAST(dt AS TEXT), 'YYYYMMDD') + INTERVAL '1 day'"),
    ("mysql", "DATE_ADD(STR_TO_DATE(CAST(dt AS CHAR), '%Y%m%d'), INTERVAL 1 DAY)"),
])
def test_valid_date_conversion_across_dialects(dialect, expression):
    statement = sqlglot.parse_one(f"SELECT {expression} FROM events", read=dialect)
    assert encoded_date_issues(statement, {"table": "events", "field": "dt"}, "yyyymmdd_number") == []


@pytest.mark.parametrize("sql, invalid", [
    ("WITH a AS (SELECT uid FROM events) SELECT a.target_value FROM a", True),
    ("WITH a AS (SELECT uid FROM events) SELECT target_value FROM a", True),
    ("WITH a AS (SELECT uid FROM events) SELECT uid FROM a", False),
    ("WITH a AS (SELECT * FROM events) SELECT target_value FROM a", False),
    ("WITH a(uid) AS (SELECT actor FROM events) SELECT uid FROM a", False),
    ("WITH a AS (SELECT uid FROM events UNION ALL SELECT actor FROM events) SELECT uid FROM a", False),
    ("WITH a AS (SELECT uid FROM events) SELECT uid AS target_id FROM a ORDER BY target_id", False),
])
def test_derived_column_scope(sql, invalid):
    assert bool(derived_column_issues(sqlglot.parse_one(sql))) is invalid


@pytest.mark.parametrize("expression, invalid", [
    ("dt - INTERVAL 1 DAY", True),
    ("CAST(dt AS SIGNED) - 1", True),
    ("DATEDIFF(dt, dt)", True),
    ("DATE_SUB(dt, INTERVAL 1 DAY)", True),
    ("DATE_SUB(STR_TO_DATE(CAST(dt AS CHAR), '%Y%m%d'), INTERVAL 1 DAY)", False),
    ("dt >= 20260901", False),
    ("amount - 1", False),
])
def test_encoded_date_arithmetic(expression, invalid):
    sql = f"WITH a AS (SELECT dt, amount FROM events) SELECT {expression} AS value FROM a"
    assert bool(encoded_date_issues(sqlglot.parse_one(sql, read="mysql"), {"table": "events", "field": "dt"}, "yyyymmdd_number")) is invalid


def test_missing_cte_field_routes_to_repair_with_accurate_issue():
    sql = attribution_sql().replace("SELECT target_id, target_value, group_1,", "SELECT target_id, group_1,")
    state = {"normalized_config": config(), "sql_dialect": "mysql",
             "response": DashboardAiSqlGenerateResponse(success=True, sql=sql)}
    result = generator._node_validate_sql(state)
    assert result["response"].success is False
    assert any("target_value" in issue for issue in result["response"].issues)
    assert generator._route_after_sql_validate({**state, **result}) == "repair_sql"
    assert generator._route_after_sql_validate({**state, **result, "sql_repair_attempts": 1}) == "explain_advice"


@pytest.mark.parametrize("method, expected", [
    ("linear", {"email": (2, 1.5), "search": (1, 0.5), "direct": (1, 1.0)}),
    ("first", {"email": (2, 2.0), "direct": (1, 1.0)}),
    ("last", {"email": (1, 1.0), "search": (1, 1.0), "direct": (1, 1.0)}),
])
@pytest.mark.parametrize("include_direct", [True, False])
def test_event_level_results_conserve_target_values(method, expected, include_direct):
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE events(event_id INTEGER, actor TEXT, occurred_at TEXT, kind TEXT, channel TEXT)")
        db.executemany("INSERT INTO events VALUES (?, ?, ?, ?, ?)", [
            (1, "a", "2026-08-31 23:59:00", "search", "web"),
            (2, "a", "2026-09-01 08:00:00", "email", "web"),
            (3, "a", "2026-09-01 09:00:00", "conversion", "web"),
            (4, "a", "2026-09-01 10:00:00", "search", "web"),
            (5, "a", "2026-09-01 11:00:00", "conversion", "web"),
            (6, "b", "2026-09-01 12:00:00", "conversion", "web"),
            (7, "b", "2026-09-01 13:00:00", "email", "web"),
        ])
        sql = attribution_sql(method=method, include_direct=include_direct)
        assert generator._attribution_sql_result_issues(sql, config(method), sql_dialect="mysql") == []
        rows = db.execute(sql).fetchall()
        expected = {key: value for key, value in expected.items() if include_direct or key != "direct"}
        assert {row[0]: row[1:3] for row in rows} == expected
        assert sum(row[2] for row in rows) == (3 if include_direct else 2)
        assert sum(row[3] for row in rows) == pytest.approx(100)
