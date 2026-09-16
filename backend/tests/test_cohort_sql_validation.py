"""Cohort cells distinguish future periods from observed zero activity."""
from __future__ import annotations

import sqlite3

import pytest

from apps.dashboard.crud import ai_sql_generator


def _config(model="retention", parameter_type="date"):
    return {
        "analysis_model": model,
        "time": {"date_parameter_type": parameter_type},
        "retention": {},
        "revenue": {"observationDays": 7, "metric": {"method": "count"}},
    }


def _query(guard=None, *, cutoff="CAST({{dashboard_end_date}} AS DATE)", outer=None):
    values = []
    for day in range(8):
        value = f"COUNT(DISTINCT CASE WHEN period_offset = {day} THEN entity_id END)"
        if guard:
            condition = guard.format(day=day, cutoff=cutoff)
            value = f"CASE WHEN {condition} THEN {value} ELSE NULL END"
        if outer:
            value = outer.format(value=value)
        values.append(f"{value} AS day_{day}")
    return "SELECT cohort_date, COUNT(DISTINCT entity_id) AS cohort_size, " + ", ".join(values) + " FROM matched GROUP BY cohort_date"


def _issues(sql, *, model="retention", parameter_type="date", dialect="mysql"):
    validate = getattr(ai_sql_generator, f"_{model}_sql_result_issues")
    return validate(sql, _config(model, parameter_type), sql_dialect=dialect)


@pytest.mark.parametrize("model", ["retention", "revenue"])
def test_rejects_future_cohort_cells_filled_by_unguarded_count(model):
    assert any("成熟" in issue for issue in _issues(_query(), model=model))


@pytest.mark.parametrize("outer", ["COALESCE({value}, 0)", "IFNULL({value}, 0)", "COUNT({value})"])
def test_rejects_outer_operations_that_replace_immature_null_with_zero(outer):
    sql = _query("DATE_ADD(cohort_date, INTERVAL {day} DAY) <= {cutoff}", outer=outer)
    assert any("成熟" in issue for issue in _issues(sql))


@pytest.mark.parametrize("guard", [
    "DATE_ADD(behavior_date, INTERVAL {day} DAY) <= {cutoff}",
    "DATE_ADD(cohort_date, INTERVAL 0 DAY) <= {cutoff}",
    "DATE_ADD(cohort_date, INTERVAL {day} DAY) <= CURRENT_DATE",
    "DATE_ADD(cohort_date, INTERVAL {day} DAY) <= {cutoff} OR cohort_date IS NOT NULL",
])
def test_rejects_guards_that_do_not_prove_the_actual_output_period_is_observed(guard):
    assert any("成熟" in issue for issue in _issues(_query(guard)))


def test_requires_explicit_date_parameter_configuration():
    sql = _query("DATE_ADD(cohort_date, INTERVAL {day} DAY) <= {cutoff}")
    assert any("日期参数" in issue for issue in _issues(sql, parameter_type=""))


@pytest.mark.parametrize("model", ["retention", "revenue"])
def test_accepts_guarded_zero_for_observed_cells(model):
    sql = _query("DATE_ADD(cohort_date, INTERVAL {day} DAY) <= {cutoff}")
    assert _issues(sql, model=model) == []


@pytest.mark.parametrize("parameter_type,dialect,cutoff,guard", [
    ("date", "postgres", "CAST({{dashboard_end_date}} AS DATE)", "cohort_date + {day} <= {cutoff}"),
    ("yyyymmdd_number", "mysql", "STR_TO_DATE(CAST({{dashboard_end_yyyymmdd}} AS CHAR), '%Y%m%d')", "DATE_ADD(cohort_date, INTERVAL {day} DAY) <= {cutoff}"),
    ("yyyymmdd_text", "postgres", "TO_DATE(CAST({{dashboard_end_yyyymmdd}} AS TEXT), 'YYYYMMDD')", "cohort_date + INTERVAL '{day} days' <= {cutoff}"),
    ("timestamp", "mysql", "CAST({{dashboard_end_exclusive_timestamp}} AS DATE)", "DATE_ADD(cohort_date, INTERVAL {day} DAY) < {cutoff}"),
    ("date", "mysql", "CAST({{dashboard_end_date}} AS DATE)", "DATEDIFF({cutoff}, cohort_date) >= {day}"),
])
def test_accepts_typed_dialect_specific_cutoffs(parameter_type, dialect, cutoff, guard):
    sql = _query(guard, cutoff=cutoff)
    if dialect == "mysql" and parameter_type.startswith("yyyymmdd"):
        sql = "WITH matched AS (SELECT cohort_date, entity_id, DATEDIFF(behavior_date, cohort_date) AS period_offset FROM event_rows) " + sql
    assert _issues(sql, parameter_type=parameter_type, dialect=dialect) == []


def test_rejects_inclusive_comparison_to_exclusive_timestamp_end():
    sql = _query("DATE_ADD(cohort_date, INTERVAL {day} DAY) <= {cutoff}", cutoff="CAST({{dashboard_end_exclusive_timestamp}} AS DATE)")
    assert any("成熟" in issue for issue in _issues(sql, parameter_type="timestamp"))


def test_rejects_raw_yyyymmdd_cutoff_in_date_arithmetic():
    sql = _query("DATE_ADD(cohort_date, INTERVAL {day} DAY) <= {cutoff}", cutoff="{{dashboard_end_yyyymmdd}}")
    assert any("成熟" in issue for issue in _issues(sql, parameter_type="yyyymmdd_number"))


def test_traces_guard_and_cohort_date_through_cte_aliases():
    sql = """WITH bounds AS (SELECT CAST({{dashboard_end_date}} AS DATE) AS observed_until),
        matched AS (SELECT source_date AS cohort_date, entity_id, period_offset FROM event_rows),
        guarded AS (""" + _query(
            "DATE_ADD(cohort_date, INTERVAL {day} DAY) <= {cutoff}", cutoff="observed_until",
        ).replace("FROM matched", "FROM matched CROSS JOIN bounds") + ") SELECT cohort_date, cohort_size, " + ", ".join(f"day_{day}" for day in range(8)) + " FROM guarded"
    assert _issues(sql) == []
    corrupted = sql.replace("SELECT cohort_date, cohort_size, day_0", "SELECT cohort_date, cohort_size, COALESCE(day_0, 0) AS day_0")
    assert any("day_0" in issue for issue in _issues(corrupted))


def test_rejects_guard_using_other_instance_of_the_same_cte():
    sql = "WITH dates AS (SELECT event_date FROM event_rows) " + _query(
        "DATE_ADD(b.event_date, INTERVAL {day} DAY) <= {cutoff}",
    ).replace("SELECT cohort_date,", "SELECT a.event_date AS cohort_date,").replace(
        "FROM matched", "FROM dates a CROSS JOIN dates b CROSS JOIN matched",
    ).replace("GROUP BY cohort_date", "GROUP BY a.event_date")
    assert any("成熟" in issue for issue in _issues(sql))


def test_accepts_display_formatted_cohort_date_with_typed_guard():
    sql = _query("DATE_ADD(cohort_date, INTERVAL {day} DAY) <= {cutoff}")
    sql = sql.replace("SELECT cohort_date,", "SELECT DATE_FORMAT(cohort_date, '%Y-%m-%d') AS cohort_date,")
    assert _issues(sql) == []


@pytest.mark.parametrize("dialect", ["mysql", "postgres"])
def test_accepts_single_row_bound_aggregated_at_cohort_grain(dialect):
    guard = "cohort_date + {day} <= {cutoff}" if dialect == "postgres" else "DATE_ADD(cohort_date, INTERVAL {day} DAY) <= {cutoff}"
    sql = "WITH bounds AS (SELECT CAST({{dashboard_end_date}} AS DATE) AS end_date) " + _query(
        guard, cutoff="MAX(bounds.end_date)",
    ).replace("FROM matched", "FROM matched CROSS JOIN bounds")
    assert _issues(sql, dialect=dialect) == []


def test_guarded_count_inside_outer_null_preserving_round_is_valid():
    sql = _query("DATE_ADD(cohort_date, INTERVAL {day} DAY) <= {cutoff}", outer="ROUND({value} * 100.0 / 10, 2)")
    assert _issues(sql) == []


def test_inverse_guard_returns_null_only_before_target_day():
    sql = _query("DATE_ADD(cohort_date, INTERVAL {day} DAY) <= {cutoff}")
    sql = sql.replace("<= CAST", "> CAST")
    import re
    sql = re.sub(r"THEN (COUNT\(DISTINCT CASE WHEN period_offset = \d+ THEN entity_id END\)) ELSE NULL END", r"THEN NULL ELSE \1 END", sql)
    assert _issues(sql) == []


@pytest.mark.parametrize("model", ["retention", "revenue"])
def test_plan_passes_the_explicit_exclusive_cutoff_to_generation(model):
    config = _config(model, "timestamp")
    config["chart"] = {"type": "table"}
    contract = ai_sql_generator._build_sql_plan(config, {})["result_contract"]["maturity"]
    assert contract["observation_end_token"] == "{{dashboard_end_exclusive_timestamp}}"
    assert contract["end_inclusive"] is False
    assert contract["immature_value"] is None


def test_observed_zero_and_immature_null_are_distinct_at_execution():
    sql = _query("DATE_ADD(cohort_date, INTERVAL {day} DAY) <= {cutoff}")
    assert _issues(sql) == []
    # SQLite executes the same CASE/count semantics after dialect transpilation.
    import sqlglot
    sql = sql.replace("{{dashboard_end_date}}", "'2026-09-15'")
    rendered = sqlglot.transpile(sql, read="mysql", write="sqlite")[0]
    with sqlite3.connect(":memory:") as connection:
        connection.execute("CREATE TABLE matched(cohort_date TEXT, entity_id INT, period_offset INT)")
        connection.executemany("INSERT INTO matched VALUES (?, ?, ?)", [("2026-09-14", 1, None), ("2026-09-15", 2, None)])
        rows = connection.execute(rendered + " ORDER BY cohort_date").fetchall()
    assert rows[0][2:5] == (0, 0, None)
    assert rows[1][2:5] == (0, None, None)
