import sqlite3

import pytest
import sqlglot

from apps.dashboard.crud import ai_sql_generator as generator
from interval_sql_fixture import interval_sql


CONFIG = {"analysis_model": "interval", "time": {
    "field": {"table": "events", "field": "event_day"}, "date_parameter_type": "date",
}}


def issues(sql):
    return generator._interval_sql_result_issues(sql, CONFIG, sql_dialect="mysql")


@pytest.mark.parametrize("mode", ["adjacent", "different", "lag", "lead"])
def test_interval_date_must_come_from_actual_start_occurrence(mode):
    assert issues(interval_sql(mode)) == []
    assert issues(interval_sql(mode, wrong_date=True))


def test_unused_start_date_does_not_validate_end_date_output():
    sql = interval_sql(wrong_date=True).replace(
        "WITH ordered_events", "WITH unused AS (SELECT event_day AS start_date FROM events), ordered_events")
    assert issues(sql)


def test_mismatched_lag_window_cannot_supply_the_start_date():
    sql = interval_sql("lag").replace("LAG(event_day) OVER", "LAG(event_day,2) OVER")
    assert issues(sql)


def test_date_lineage_survives_extra_projection_and_display_formatting():
    sql = interval_sql().replace("SELECT interval_date,COUNT", "SELECT DATE_FORMAT(interval_date,'%Y-%m-%d') AS interval_date,COUNT")
    assert issues(sql) == []


def test_timestampdiff_uses_start_argument_not_end_argument():
    for wrong in (False, True):
        sql = interval_sql(wrong_date=wrong).replace("end_time-start_time", "TIMESTAMPDIFF(SECOND,start_time,end_time)")
        assert bool(issues(sql)) is wrong


def test_cross_midnight_pair_is_counted_on_start_day_at_execution():
    with sqlite3.connect(":memory:") as connection:
        connection.execute("CREATE TABLE events(entity_id INT,event_id INT,event_day TEXT,occurred_at INT,action TEXT)")
        connection.executemany("INSERT INTO events VALUES(1,?,?,?,'open')", [
            (1,"2026-09-14",86390),(2,"2026-09-15",86410),
        ])
        actual = []
        for wrong in (False, True):
            tree = sqlglot.parse_one(interval_sql(wrong_date=wrong), read="mysql")
            tree.set("expressions", [item for item in tree.expressions if item.alias_or_name in {"interval_date", "interval_count", "avg_interval_seconds"}])
            actual.append(connection.execute(tree.sql(dialect="sqlite")).fetchall())
        assert actual == [[("2026-09-14",1,20.0)],[("2026-09-15",1,20.0)]]
    assert issues(interval_sql(wrong_date=True))


def test_generator_reports_end_date_attribution_without_llm_repair():
    state = {"normalized_config": {"analysis_model": "interval"}, "sql_dialect": "mysql", "graph_trace": [],
             "response": generator.DashboardAiSqlGenerateResponse(success=True, sql=interval_sql(wrong_date=True))}
    state.update(generator._node_validate_sql(state))
    assert not state["response"].success
    assert generator._route_after_sql_validate(state) == "explain_advice"
