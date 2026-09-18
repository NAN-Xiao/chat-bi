from __future__ import annotations

import sqlite3
from types import SimpleNamespace

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


def native_window_funnel_sql(*, unsafe_value_windows: bool = False) -> str:
    step_metrics = """
    SELECT step_order, step_name, step_count,
           MAX(CASE WHEN step_order = 1 THEN step_count END) OVER () AS first_step_count,
           LAG(step_count) OVER (ORDER BY step_order) AS previous_step_count
    FROM step_counts
""" if unsafe_value_windows else """
    SELECT sc.step_order, sc.step_name, sc.step_count,
           (SELECT first_sc.step_count FROM step_counts first_sc WHERE first_sc.step_order = 1) AS first_step_count,
           (SELECT previous_sc.step_count FROM step_counts previous_sc WHERE previous_sc.step_order = sc.step_order - 1) AS previous_step_count
    FROM step_counts sc
"""
    return f"""
WITH dashboard_params AS (
    SELECT CAST({{{{dashboard_start_yyyymmdd}}}} AS SIGNED) AS start_dt,
           CAST({{{{dashboard_end_yyyymmdd}}}} AS SIGNED) AS end_dt
), scoped_event AS (
    SELECT e.uid, e.event, e.`time` AS event_time
    FROM `event` AS e CROSS JOIN dashboard_params AS p
    WHERE e.prod = 110000038
      AND e.dt BETWEEN p.start_dt AND p.end_dt
), user_depth AS (
    SELECT uid, window_funnel(
        CAST(86400 AS INTEGER), 'default', event_time,
        event = 'register', event = 'login', event = 'purchase'
    ) AS max_depth
    FROM scoped_event
    GROUP BY uid
), step_counts AS (
    SELECT 1 AS step_order, '注册' AS step_name,
           COUNT(CASE WHEN max_depth >= 1 THEN 1 END) AS step_count
    FROM user_depth
    UNION ALL
    SELECT 2, '登录', COUNT(CASE WHEN max_depth >= 2 THEN 1 END)
    FROM user_depth
    UNION ALL
    SELECT 3, '购买', COUNT(CASE WHEN max_depth >= 3 THEN 1 END)
    FROM user_depth
), step_metrics AS (
{step_metrics.rstrip()}
)
SELECT step_order, step_name, step_count,
       step_count / NULLIF(first_step_count, 0) AS step_rate,
       step_count / NULLIF(previous_step_count, 0) AS step_conversion_rate,
       1 - step_count / NULLIF(previous_step_count, 0) AS step_dropoff_rate
FROM step_metrics
ORDER BY step_order
"""


def native_window_funnel_config() -> dict:
    steps = [
        {
            "event": {
                "eventTable": "event",
                "eventNameField": "event",
                "eventName": event_name,
            }
        }
        for event_name in ("register", "login", "purchase")
    ]
    return {
        **CONFIG,
        "time": {"field": {"table": "event", "field": "dt"}, "date_parameter_type": "yyyymmdd_number"},
        "funnel": {
            **CONFIG["funnel"],
            "entityField": {"table": "event", "field": "uid"},
            "window": {"mode": "duration", "value": 1, "unit": "day"},
            "steps": steps,
        },
    }


def native_issues(
        sql: str,
        *,
        metadata: str | None = None,
        config: dict | None = None,
) -> list[str]:
    return ai_sql_generator._funnel_sql_result_issues(
        sql,
        config or native_window_funnel_config(),
        schema=metadata or "# Table: event\n[\n(time:bigint, role=event_time; encoding=epoch_seconds),\n(dt:integer, role=partition_date)\n]",
        sql_dialect="mysql",
        datasource=SimpleNamespace(type="mysql", type_name="AnalyticDB for MySQL"),
    )


def issues(sql, *, metadata=None, window=None, dialect="mysql"):
    config = {**CONFIG, "funnel": {**CONFIG["funnel"], "window": window or CONFIG["funnel"]["window"]}}
    return ai_sql_generator._funnel_sql_result_issues(
        sql, config, schema=schema() if metadata is None else metadata, sql_dialect=dialect,
    )


def test_funnel_fixed_output_columns_do_not_make_date_only_timing_valid():
    sql = funnel_sql(time="STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d')",
                     bound="DATEDIFF(e.event_time, p.first_step_time) <= 1")
    assert ai_sql_generator._funnel_sql_result_issues(sql, CONFIG)


def test_step_1_must_keep_every_candidate_first_step_occurrence():
    sql = funnel_sql().replace(
        "SELECT entity_id, event_time AS first_step_time, event_time AS step_time\n"
        "    FROM scoped_events WHERE action = 'begin'",
        "SELECT entity_id, MIN(event_time) AS first_step_time, MIN(event_time) AS step_time\n"
        "    FROM scoped_events WHERE action = 'begin' GROUP BY entity_id",
    )
    validation_issues = issues(sql)

    assert any("候选首步" in issue for issue in validation_issues)


def test_mysql_funnel_rejects_value_window_functions_for_step_metrics():
    validation_issues = native_issues(native_window_funnel_sql(unsafe_value_windows=True))

    assert any("MAX/LAG" in issue for issue in validation_issues)


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
        (6, "begin", 0), (6, "begin", 200000), (6, "middle", 200100), (6, "finish", 200200),
    ])
    assert [row[2] for row in db.execute(sql)] == [6, 4, 3]
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
        "SELECT entity_id, event_time AS first_step_time, event_time AS step_time\n    FROM scoped_events WHERE action = 'begin'",
        "SELECT other.entity_id, actual.event_time AS first_step_time, actual.event_time AS step_time\n"
        "    FROM scoped_events actual CROSS JOIN scoped_events other WHERE actual.action = 'begin'",
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
    sql = funnel_sql().replace("FROM step_metrics ORDER BY step_order", "FROM unrelated_totals ORDER BY step_order")
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


def test_analyticdb_window_funnel_reference_uses_event_time_and_dashboard_partition_filter():
    sql = native_window_funnel_sql()
    config = native_window_funnel_config()
    metadata = "# Table: event\n[\n(time:bigint, role=event_time; encoding=epoch_seconds),\n(dt:integer, role=partition_date)\n]"

    assert ai_sql_generator._funnel_sql_result_issues(
        sql,
        config,
        schema=metadata,
        sql_dialect="mysql",
        datasource=SimpleNamespace(type="mysql", type_name="AnalyticDB for MySQL"),
    ) == []


def test_window_funnel_is_rejected_when_datasource_is_not_confirmed_analyticdb():
    issues = ai_sql_generator._funnel_sql_result_issues(
        native_window_funnel_sql(),
        native_window_funnel_config(),
        schema="# Table: event\n[\n(time:bigint, role=event_time; encoding=epoch_seconds),\n(dt:integer, role=partition_date)\n]",
        sql_dialect="mysql",
        datasource=SimpleNamespace(type="mysql", type_name="MySQL"),
    )

    assert any("AnalyticDB" in issue for issue in issues)


def test_window_funnel_timestamp_must_resolve_to_declared_event_time():
    sql = native_window_funnel_sql().replace(
        "'default', event_time,",
        "'default', dt,",
    ).replace(
        "SELECT e.uid, e.event, e.`time` AS event_time",
        "SELECT e.uid, e.event, e.`time` AS event_time, e.dt",
    )
    issues = ai_sql_generator._funnel_sql_result_issues(
        sql,
        native_window_funnel_config(),
        schema="# Table: event\n[\n(time:bigint, role=event_time; encoding=epoch_seconds),\n(dt:integer, role=partition_date)\n]",
        sql_dialect="mysql",
        datasource=SimpleNamespace(type="mysql", type_name="AnalyticDB for MySQL"),
    )

    assert any("event_time" in issue for issue in issues)


def test_window_funnel_counts_each_step_by_maximum_depth_threshold():
    sql = native_window_funnel_sql().replace("max_depth >= 2", "max_depth = 2")
    issues = ai_sql_generator._funnel_sql_result_issues(
        sql,
        native_window_funnel_config(),
        schema="# Table: event\n[\n(time:bigint, role=event_time; encoding=epoch_seconds),\n(dt:integer, role=partition_date)\n]",
        sql_dialect="mysql",
        datasource=SimpleNamespace(type="mysql", type_name="AnalyticDB for MySQL"),
    )

    assert any("max_depth >= 2" in issue for issue in issues)


@pytest.mark.parametrize(
    "partition_predicate",
    [
        "e.dt IS NOT NULL",
        "e.dt >= p.start_dt AND e.dt <= p.start_dt",
        "e.dt >= p.end_dt AND e.dt <= p.end_dt",
    ],
)
def test_window_funnel_partition_filter_must_bind_both_dashboard_boundaries(
        partition_predicate: str,
) -> None:
    sql = native_window_funnel_sql().replace(
        "e.dt BETWEEN p.start_dt AND p.end_dt",
        partition_predicate,
    )

    assert any("起止日期范围" in issue for issue in native_issues(sql))


@pytest.mark.parametrize(
    "predicate",
    [
        "event <> 'login'",
        "NOT event = 'login'",
        "event = 'login' OR 1 = 1",
    ],
)
def test_window_funnel_step_event_requires_positive_unconditional_equality(predicate: str) -> None:
    sql = native_window_funnel_sql().replace("event = 'login'", predicate)

    assert any("第 2 个事件条件" in issue for issue in native_issues(sql))


def test_window_funnel_depth_count_rejects_else_zero_case() -> None:
    sql = native_window_funnel_sql().replace("THEN 1 END", "THEN 1 ELSE 0 END")

    assert any("max_depth >=" in issue for issue in native_issues(sql))


def test_window_funnel_depth_thresholds_in_unused_cte_do_not_validate_counts() -> None:
    sql = native_window_funnel_sql().replace(
        "), step_counts AS (",
        "), unused_depth AS (\n"
        "    SELECT max_depth FROM user_depth\n"
        "    WHERE max_depth >= 1 AND max_depth >= 2 AND max_depth >= 3\n"
        "), step_counts AS (",
    )
    sql = sql.replace("COUNT(CASE WHEN max_depth >= 1 THEN 1 END)", "COUNT(*)")
    sql = sql.replace("COUNT(CASE WHEN max_depth >= 2 THEN 1 END)", "COUNT(*)")
    sql = sql.replace("COUNT(CASE WHEN max_depth >= 3 THEN 1 END)", "COUNT(*)")

    assert any("max_depth >=" in issue for issue in native_issues(sql))


def test_window_funnel_final_step_count_must_derive_from_depth_counts() -> None:
    prefix, _separator, _final = native_window_funnel_sql().rpartition(
        "SELECT step_order, step_name, step_count,"
    )
    sql = prefix + """SELECT
    1 AS step_order,
    '常量' AS step_name,
    999 AS step_count,
    1.0 AS step_rate,
    1.0 AS step_conversion_rate,
    0.0 AS step_dropoff_rate
"""

    assert any("最终 step_count" in issue for issue in native_issues(sql))


def test_window_funnel_grouping_must_use_exact_subject_grain() -> None:
    sql = native_window_funnel_sql().replace("GROUP BY uid", "GROUP BY uid, event")

    assert any("分析主体" in issue for issue in native_issues(sql))


@pytest.mark.parametrize(
    "subject_clause",
    [
        "GROUP BY uid HAVING max_depth = 3",
        "GROUP BY uid LIMIT 1",
    ],
)
def test_window_funnel_subject_depth_layer_cannot_remove_grouped_subjects(subject_clause: str) -> None:
    sql = native_window_funnel_sql().replace("GROUP BY uid", subject_clause)

    assert any("最大深度聚合层" in issue for issue in native_issues(sql))


def test_window_funnel_epoch_milliseconds_must_convert_to_integer_seconds() -> None:
    metadata = "# Table: event\n[\n(time:bigint, role=event_time; encoding=epoch_milliseconds),\n(dt:integer, role=partition_date)\n]"
    raw_sql = native_window_funnel_sql()
    decimal_sql = raw_sql.replace(
        "'default', event_time,",
        "'default', event_time / 1000.0,",
    )
    integer_seconds_sql = raw_sql.replace(
        "'default', event_time,",
        "'default', CAST(event_time / 1000 AS SIGNED),",
    )

    assert any("BIGINT 秒" in issue for issue in native_issues(raw_sql, metadata=metadata))
    assert any("BIGINT 秒" in issue for issue in native_issues(decimal_sql, metadata=metadata))
    assert native_issues(integer_seconds_sql, metadata=metadata) == []


def test_window_funnel_partition_filter_must_use_the_actual_event_scan() -> None:
    sql = native_window_funnel_sql().replace(
        "FROM `event` AS e CROSS JOIN dashboard_params AS p",
        "FROM `event` AS e CROSS JOIN dashboard_params AS p\n"
        "    CROSS JOIN (\n"
        "        SELECT 1\n"
        "        FROM `event` AS side_event CROSS JOIN dashboard_params AS side_params\n"
        "        WHERE side_event.dt BETWEEN side_params.start_dt AND side_params.end_dt\n"
        "    ) AS date_guard",
    ).replace(
        "e.dt BETWEEN p.start_dt AND p.end_dt",
        "e.dt IS NOT NULL",
    )

    assert any("起止日期范围" in issue for issue in native_issues(sql))


def test_window_funnel_partition_filter_cannot_be_borrowed_from_another_shared_cte_reference() -> None:
    sql = native_window_funnel_sql().replace(
        "), scoped_event AS (\n"
        "    SELECT e.uid, e.event, e.`time` AS event_time\n"
        "    FROM `event` AS e CROSS JOIN dashboard_params AS p",
        "), all_events AS (\n"
        "    SELECT e.uid, e.event, e.`time` AS event_time, e.dt, e.prod\n"
        "    FROM `event` AS e\n"
        "), scoped_event AS (\n"
        "    SELECT e.uid, e.event, e.event_time\n"
        "    FROM all_events AS e CROSS JOIN dashboard_params AS p\n"
        "    CROSS JOIN (\n"
        "        SELECT 1\n"
        "        FROM all_events AS side_event CROSS JOIN dashboard_params AS side_params\n"
        "        WHERE side_event.dt BETWEEN side_params.start_dt AND side_params.end_dt\n"
        "    ) AS date_guard",
    ).replace(
        "e.dt BETWEEN p.start_dt AND p.end_dt",
        "e.dt IS NOT NULL",
    )

    assert any("起止日期范围" in issue for issue in native_issues(sql))


def test_window_funnel_depth_counts_reject_join_multiplication() -> None:
    sql = native_window_funnel_sql().replace(
        "FROM user_depth",
        "FROM user_depth CROSS JOIN (SELECT 1 AS multiplier UNION ALL SELECT 2) AS multipliers",
    )

    assert any("最大深度结果" in issue for issue in native_issues(sql))


@pytest.mark.parametrize(
    "final_clause",
    [
        "FROM step_metrics CROSS JOIN (SELECT 1 AS multiplier UNION ALL SELECT 2) AS multipliers",
        "FROM step_metrics WHERE step_order = 1",
    ],
)
def test_window_funnel_rejects_row_changes_after_depth_counts(final_clause: str) -> None:
    sql = native_window_funnel_sql().replace("FROM step_metrics", final_clause)

    assert any("最终 step_count" in issue for issue in native_issues(sql))


@pytest.mark.parametrize("union_limit", ["LIMIT 1", "LIMIT 1 OFFSET 2"])
def test_window_funnel_step_count_union_cannot_trim_steps(union_limit: str) -> None:
    sql = native_window_funnel_sql().replace(
        "FROM user_depth\n), step_metrics AS (",
        f"FROM user_depth\n    ORDER BY step_order {union_limit}\n), step_metrics AS (",
        1,
    )

    assert any("最终 step_count" in issue for issue in native_issues(sql))


@pytest.mark.parametrize("set_operator", ["INTERSECT ALL", "EXCEPT ALL"])
def test_window_funnel_step_counts_require_union_all(set_operator: str) -> None:
    sql = native_window_funnel_sql().replace("UNION ALL", set_operator)

    assert any("最终 step_count" in issue for issue in native_issues(sql))


def test_window_funnel_depth_counts_require_provably_non_null_match_value() -> None:
    sql = native_window_funnel_sql().replace("THEN 1 END", "THEN NULLIF(1, 1) END")

    assert any("max_depth >=" in issue for issue in native_issues(sql))


def test_window_funnel_depth_counts_reject_simple_case_with_false_base() -> None:
    sql = native_window_funnel_sql().replace(
        "COUNT(CASE WHEN max_depth",
        "COUNT(CASE 0 WHEN max_depth",
    )

    assert any("max_depth >=" in issue for issue in native_issues(sql))


def test_window_funnel_timestampdiff_requires_a_fixed_origin() -> None:
    metadata = "# Table: event\n[\n(time:timestamp, role=event_time),\n(dt:integer, role=partition_date)\n]"
    invalid_sql = native_window_funnel_sql().replace(
        "'default', event_time,",
        "'default', TIMESTAMPDIFF(SECOND, event_time, event_time),",
    )
    valid_sql = native_window_funnel_sql().replace(
        "'default', event_time,",
        "'default', TIMESTAMPDIFF(SECOND, '1970-01-01 00:00:00', event_time),",
    )

    assert any("固定起点" in issue for issue in native_issues(invalid_sql, metadata=metadata))
    assert native_issues(valid_sql, metadata=metadata) == []


def test_window_funnel_rejects_related_property_configuration() -> None:
    config = native_window_funnel_config()
    config["funnel"] = {
        **config["funnel"],
        "relatedPropertyEnabled": True,
        "relatedProperty": {"table": "event", "field": "item_id"},
    }

    assert any("关联属性" in issue for issue in native_issues(native_window_funnel_sql(), config=config))


def test_window_funnel_accepts_mandatory_partition_range_in_inner_join() -> None:
    sql = native_window_funnel_sql().replace(
        "FROM `event` AS e CROSS JOIN dashboard_params AS p",
        "FROM `event` AS e INNER JOIN dashboard_params AS p\n"
        "      ON e.dt BETWEEN p.start_dt AND p.end_dt",
    ).replace(
        "\n      AND e.dt BETWEEN p.start_dt AND p.end_dt",
        "",
    )

    assert native_issues(sql) == []


def test_window_funnel_final_step_order_must_share_depth_count_lineage() -> None:
    prefix, separator, final = native_window_funnel_sql().rpartition(
        "SELECT step_order, step_name, step_count,"
    )
    sql = prefix + separator.replace("step_order", "99 AS step_order", 1) + final

    assert any("step_order" in issue for issue in native_issues(sql))


def test_window_funnel_fixed_columns_must_come_from_outermost_select() -> None:
    sql = "WITH complete_result AS (\n" + native_window_funnel_sql().strip().rstrip(";") + "\n)\nSELECT step_count FROM complete_result"

    assert any("最终 SELECT" in issue for issue in native_issues(sql))


def test_window_funnel_rejects_analyticdb_for_postgresql_datasource() -> None:
    issues = ai_sql_generator._funnel_sql_result_issues(
        native_window_funnel_sql(),
        native_window_funnel_config(),
        schema="# Table: event\n[\n(time:bigint, role=event_time; encoding=epoch_seconds),\n(dt:integer, role=partition_date)\n]",
        sql_dialect="postgresql",
        datasource=SimpleNamespace(type="postgresql", type_name="AnalyticDB for PostgreSQL"),
    )

    assert any("AnalyticDB for MySQL" in issue for issue in issues)
