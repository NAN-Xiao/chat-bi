from __future__ import annotations

import sqlite3

import pytest

from apps.dashboard.crud import ai_sql_generator
from funnel_sql_fixture import funnel_sql


CONFIG = {
    "analysis_model": "funnel",
    "time": {"field": {"table": "events", "field": "dt"}, "date_parameter_type": "yyyymmdd_number"},
    "funnel": {"entityField": {"table": "events", "field": "uid"},
               "window": {"mode": "duration", "value": 1, "unit": "day"}, "steps": [{}, {}, {}]},
}


def schema(encoding="epoch_seconds", data_type="bigint"):
    return f"# Table: events\n[\n(dt:integer, role=partition_date),\n(occurred_at:{data_type}, role=event_time; encoding={encoding})\n]"


def issues(sql, *, metadata=None, window=None, dialect="mysql"):
    config = {**CONFIG, "funnel": {**CONFIG["funnel"], "window": window or CONFIG["funnel"]["window"]}}
    return ai_sql_generator._funnel_sql_result_issues(
        sql, config, schema=schema() if metadata is None else metadata, sql_dialect=dialect,
    )


def test_funnel_fixed_output_columns_do_not_make_date_only_timing_valid():
    sql = funnel_sql(time="STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d')",
                     bound="DATEDIFF(e.event_time, p.first_step_time) <= 1")
    assert ai_sql_generator._funnel_sql_result_issues(sql, CONFIG)


def test_exact_epoch_chain_excludes_reversed_over24h_and_cumulative_over24h_events():
    sql = funnel_sql()
    assert issues(sql) == []
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE events(uid INTEGER, action TEXT, occurred_at INTEGER, dt INTEGER)")
    db.executemany("INSERT INTO events VALUES (?, ?, ?, 20260901)", [
        (1, "begin", 0), (1, "middle", 3600), (1, "finish", 86400),
        (2, "begin", 7200), (2, "middle", 3600), (2, "finish", 10800),
        (3, "begin", 0), (3, "middle", 108000), (3, "finish", 111600),
        (4, "begin", 0), (4, "middle", 72000), (4, "finish", 144000),
        (5, "begin", 0), (5, "middle", 0), (5, "finish", 0),
    ])
    assert [row[2] for row in db.execute(sql)] == [5, 3, 2]
    db.close()


@pytest.mark.parametrize("order", ["DATE(e.event_time) >= DATE(p.step_time)", "e.event_time <= p.step_time", "1 = 1"])
def test_step_order_must_compare_full_event_timestamps(order):
    assert issues(funnel_sql(order=order))


@pytest.mark.parametrize("bound", [
    "DATEDIFF(e.event_time, p.first_step_time) <= 1",
    "TIMESTAMPDIFF(DAY, p.first_step_time, e.event_time) <= 1",
    "e.event_time - p.first_step_time <= 172800",
    "(e.event_time - p.first_step_time <= 86400 OR e.action = 'finish')",
])
def test_duration_requires_exact_configured_elapsed_time(bound):
    assert issues(funnel_sql(bound=bound))


def test_third_step_cannot_restart_duration_from_second_step():
    assert issues(funnel_sql(third_bound="e.event_time - p.step_time <= 86400"))


def test_first_time_must_be_carried_from_first_step_not_recomputed():
    sql = funnel_sql().replace("SELECT p.entity_id, p.first_step_time, MIN", "SELECT p.entity_id, p.step_time AS first_step_time, MIN")
    assert issues(sql)


def test_next_step_time_cannot_be_reused_from_the_previous_aggregate():
    sql = funnel_sql().replace("MIN(e.event_time)", "MIN(p.step_time)").replace("e.event_time >= p.step_time", "p.step_time >= p.step_time").replace("e.event_time - p.first_step_time", "p.step_time - p.first_step_time")
    assert issues(sql)


def test_timing_predicates_must_constrain_the_counted_join_alias():
    sql = funnel_sql().replace("ON e.entity_id = p.entity_id", "ON e.entity_id = p.entity_id JOIN scoped_events other ON other.entity_id = p.entity_id")
    sql = sql.replace("e.event_time >=", "other.event_time >=").replace("e.event_time -", "other.event_time -")
    assert issues(sql)


@pytest.mark.parametrize("join", ["1=1", "e.entity_id <> p.entity_id", "e.entity_id=p.entity_id OR e.action='middle'"])
def test_step_chain_must_join_the_same_configured_entity(join):
    assert issues(funnel_sql().replace("e.entity_id = p.entity_id", join))


def test_missing_entity_join_creates_false_conversion_in_real_fixture():
    good = funnel_sql()
    bad = good.replace("e.entity_id = p.entity_id", "1=1")
    with sqlite3.connect(":memory:") as connection:
        connection.execute("CREATE TABLE events(uid INTEGER, action TEXT, occurred_at INTEGER, dt INTEGER)")
        connection.executemany("INSERT INTO events VALUES (?, ?, ?, 20260901)", [
            (1, "begin", 0), (2, "middle", 10), (2, "finish", 20),
        ])
        assert [row[2] for row in connection.execute(good)] == [1, 0, 0]
        assert [row[2] for row in connection.execute(bad)] == [1, 1, 1]
    assert issues(bad)


def test_entity_equality_can_be_reversed_or_in_where():
    assert issues(funnel_sql().replace("e.entity_id = p.entity_id", "p.entity_id = e.entity_id")) == []
    sql = funnel_sql().replace("ON e.entity_id = p.entity_id", "ON 1=1").replace(
        "WHERE e.action", "WHERE e.entity_id=p.entity_id AND e.action")
    assert issues(sql) == []


def test_entity_equality_on_another_scan_does_not_join_current_step():
    sql = funnel_sql().replace("ON e.entity_id = p.entity_id", "ON 1=1 JOIN scoped_events other ON other.entity_id=p.entity_id")
    assert issues(sql)


def test_first_step_and_following_entity_outputs_cannot_change_the_configured_subject():
    assert issues(funnel_sql().replace("e.uid AS entity_id", "e.dt AS entity_id"))
    assert issues(funnel_sql().replace("SELECT p.entity_id,", "SELECT 1 AS entity_id,"))


def test_first_step_subject_must_come_from_its_actual_event_occurrence():
    sql = funnel_sql().replace(
        "SELECT entity_id, MIN(event_time) AS first_step_time, MIN(event_time) AS step_time\n    FROM scoped_events WHERE action = 'begin' GROUP BY entity_id",
        "SELECT other.entity_id, MIN(actual.event_time) AS first_step_time, MIN(actual.event_time) AS step_time\n"
        "    FROM scoped_events actual CROSS JOIN scoped_events other WHERE actual.action = 'begin' GROUP BY other.entity_id",
    )
    assert issues(sql)


def test_postgres_duration_day_is_elapsed_24_hours_not_dst_calendar_day():
    assert issues(funnel_sql(bound="e.event_time <= p.first_step_time + INTERVAL '1 day'"),
                  metadata=schema("native_timestamp", "timestamp with time zone"), dialect="postgres")


@pytest.mark.parametrize(("encoding", "multiplier"), [("epoch_seconds", 1), ("epoch_milliseconds", 1000)])
@pytest.mark.parametrize(("unit", "value", "seconds"), [("minute", 15, 900), ("hour", 6, 21600), ("day", 1, 86400)])
def test_epoch_duration_uses_declared_encoding_and_window_unit(encoding, multiplier, unit, value, seconds):
    window = {"mode": "duration", "value": value, "unit": unit}
    assert issues(funnel_sql(bound=f"e.event_time - p.first_step_time <= {seconds * multiplier}"),
                  metadata=schema(encoding), window=window) == []
    assert issues(funnel_sql(bound=f"e.event_time - p.first_step_time <= {seconds * (1 if multiplier == 1000 else 1000)}"),
                  metadata=schema(encoding), window=window)


@pytest.mark.parametrize("dialect,bound", [
    ("mysql", "e.event_time <= DATE_ADD(p.first_step_time, INTERVAL 86400 SECOND)"),
    ("postgres", "e.event_time <= p.first_step_time + INTERVAL '86400 seconds'"),
])
def test_native_timestamps_use_exact_timestamp_boundary(dialect, bound):
    assert issues(funnel_sql(bound=bound), metadata=schema("native_timestamp", "timestamp"), dialect=dialect) == []


def test_epoch_conversion_checks_divisor_and_preserves_milliseconds():
    bound = "e.event_time <= DATE_ADD(p.first_step_time, INTERVAL 86400 SECOND)"
    assert issues(funnel_sql(time="FROM_UNIXTIME(e.occurred_at / 1000.0)", bound=bound), metadata=schema("epoch_milliseconds")) == []
    assert issues(funnel_sql(time="FROM_UNIXTIME(e.occurred_at)", bound=bound), metadata=schema("epoch_milliseconds"))
    assert issues(funnel_sql(time="DATE(FROM_UNIXTIME(e.occurred_at / 1000))", bound=bound), metadata=schema("epoch_milliseconds"))


def test_same_day_preserves_timestamp_order_and_calendar_day_boundary():
    window = {"mode": "same_day", "value": 1, "unit": "day"}
    metadata = schema("native_timestamp", "timestamp")
    assert issues(funnel_sql(bound="DATE(e.event_time) = DATE(p.first_step_time)"), metadata=metadata, window=window) == []
    assert issues(funnel_sql(bound="e.event_time <= DATE_ADD(p.first_step_time, INTERVAL 24 HOUR)"), metadata=metadata, window=window)
    assert issues(funnel_sql(bound="DATE(e.event_time) = DATE(p.first_step_time)", order="DATE(e.event_time) >= DATE(p.step_time)"), metadata=metadata, window=window)


@pytest.mark.parametrize("encoding, divisor", [("epoch_seconds", ""), ("epoch_milliseconds", "/ 1000.0")])
def test_same_day_accepts_calendar_dates_from_declared_epoch_units(encoding, divisor):
    bound = f"DATE(FROM_UNIXTIME(e.event_time {divisor})) = DATE(FROM_UNIXTIME(p.first_step_time {divisor}))"
    assert issues(funnel_sql(bound=bound), metadata=schema(encoding),
                  window={"mode": "same_day", "value": 1, "unit": "day"}) == []


@pytest.mark.parametrize("metadata", ["", schema("", "bigint"), schema("native_date", "date"), schema().replace("events", "unrelated_events")])
def test_missing_or_unusable_event_time_metadata_is_explicit(metadata):
    assert issues(funnel_sql(), metadata=metadata)


def test_unused_valid_steps_cannot_validate_unrelated_output():
    sql = funnel_sql().replace("FROM step_counts ORDER BY step_order", "FROM unrelated_totals ORDER BY step_order")
    assert issues(sql)


@pytest.mark.parametrize("valid", [True, False])
def test_generation_validation_passes_metadata_and_routes_bad_timing_to_repair(valid):
    sql = funnel_sql(third_bound=None if valid else "e.event_time - p.step_time <= 86400")
    sql = sql.replace("FROM events e", "FROM events e WHERE e.dt >= {{dashboard_start_yyyymmdd}} AND e.dt <= {{dashboard_end_yyyymmdd}}")
    response = ai_sql_generator._node_validate_sql({
        "response": ai_sql_generator.DashboardAiSqlGenerateResponse(success=True, sql=sql, chart_type="funnel", analysis_model="funnel"),
        "normalized_config": CONFIG,
        "sql_dialect": "mysql",
        "schema": schema(),
        "graph_trace": [],
    })["response"]
    assert response.success is valid, response.issues
    if not valid:
        assert any("first_step_time" in issue for issue in response.issues)
        assert ai_sql_generator._route_after_sql_validate({"response": response, "normalized_config": CONFIG, "sql_repair_attempts": 0}) == "repair_sql"
