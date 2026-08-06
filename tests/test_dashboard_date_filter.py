from datetime import date

import pytest
from pydantic import ValidationError

from apps.dashboard.crud.dashboard_date_filter import (
    default_dashboard_date_range,
    prepare_dashboard_date_filter,
    resolve_dashboard_date_expression,
)
from apps.dashboard.models.dashboard_chart_config import DashboardDateFilterRequest
from common.core.config import Settings


def _pivot(parameter_type: str, **overrides):
    return {
        "time_field": "dt",
        "date_parameter_type": parameter_type,
        **overrides,
    }


@pytest.mark.parametrize(
    ("preset", "expected"),
    [
        ("yesterday", ("2026-07-27", "2026-07-27")),
        ("today", ("2026-07-28", "2026-07-28")),
        ("previous_week", ("2026-07-20", "2026-07-26")),
        ("current_week", ("2026-07-27", "2026-07-28")),
        ("previous_month", ("2026-06-01", "2026-06-30")),
        ("current_month", ("2026-07-01", "2026-07-28")),
        ("past_7_days", ("2026-07-21", "2026-07-27")),
        ("recent_7_days", ("2026-07-22", "2026-07-28")),
        ("past_30_days", ("2026-06-28", "2026-07-27")),
        ("recent_30_days", ("2026-06-29", "2026-07-28")),
        ("past_90_days", ("2026-04-29", "2026-07-27")),
        ("all_time", ("1000-01-01", "9999-12-31")),
    ],
)
def test_date_expression_presets(preset, expected):
    assert resolve_dashboard_date_expression(
        {"version": 1, "mode": "preset", "preset": preset},
        today=date(2026, 7, 28),
    ) == tuple(date.fromisoformat(item) for item in expected)


def test_date_expression_allows_today_and_renders_every_physical_scan():
    sql = " UNION ALL ".join(
        f"select dt from t{i} where dt >= {{{{dashboard_start_yyyymmdd}}}} "
        f"and dt <= {{{{dashboard_end_yyyymmdd}}}}"
        for i in range(4)
    )
    result = prepare_dashboard_date_filter(
        sql,
        ds_type="mysql",
        today=date(2026, 7, 28),
        pivot=_pivot(
            "yyyymmdd_number",
            date_expression={"version": 1, "mode": "preset", "preset": "today"},
        ),
    )

    assert result.capability["status"] == "available"
    assert result.start == result.end == "2026-07-28"
    assert result.sql.count("20260728") == 8


@pytest.mark.parametrize(
    "expression",
    [
        {"version": 2, "mode": "preset", "preset": "today"},
        {"version": 1, "mode": "preset", "preset": "unknown"},
        {
            "version": 1,
            "mode": "range",
            "start": {"mode": "dynamic", "unit": "day", "offset": 1},
            "end": {"mode": "dynamic", "unit": "day", "offset": 1},
        },
        {
            "version": 1,
            "mode": "range",
            "start": {"mode": "static", "date": "2026-08-01"},
            "end": {"mode": "static", "date": "2026-07-01"},
        },
    ],
)
def test_invalid_date_expression_fails_closed(expression):
    result = prepare_dashboard_date_filter(
        "select dt from t where dt between {{dashboard_start_yyyymmdd}} "
        "and {{dashboard_end_yyyymmdd}}",
        ds_type="mysql",
        today=date(2026, 7, 28),
        pivot=_pivot("yyyymmdd_number", date_expression=expression),
    )

    assert result.capability == {
        "status": "unconfigured",
        "reason": "invalid_date_expression",
    }


def test_dynamic_date_expression_overflow_fails_closed():
    result = prepare_dashboard_date_filter(
        "select dt from t where dt between {{dashboard_start_yyyymmdd}} "
        "and {{dashboard_end_yyyymmdd}}",
        ds_type="mysql",
        today=date(2026, 7, 28),
        pivot=_pivot(
            "yyyymmdd_number",
            date_expression={
                "version": 1,
                "mode": "range",
                "start": {"mode": "dynamic", "unit": "day", "offset": -(10**100)},
                "end": {"mode": "dynamic", "unit": "day", "offset": 0},
            },
        ),
    )

    assert result.capability == {
        "status": "unconfigured",
        "reason": "invalid_date_expression",
    }


@pytest.mark.parametrize("parameter_type", ["date", "timestamp"])
def test_all_time_rejects_parameter_types_without_safe_bounds(parameter_type):
    tokens = (
        ("{{dashboard_start_date}}", "{{dashboard_end_date}}")
        if parameter_type == "date"
        else ("{{dashboard_start_timestamp}}", "{{dashboard_end_exclusive_timestamp}}")
    )
    result = prepare_dashboard_date_filter(
        f"select dt from t where dt >= {tokens[0]} and dt <= {tokens[1]}",
        ds_type="mysql",
        today=date(2026, 7, 28),
        pivot=_pivot(
            parameter_type,
            date_expression={"version": 1, "mode": "preset", "preset": "all_time"},
        ),
    )

    assert result.capability["reason"] == "invalid_date_expression"


def test_default_range_is_fourteen_complete_days():
    assert default_dashboard_date_range(today=date(2026, 7, 27)) == (
        date(2026, 7, 13),
        date(2026, 7, 26),
    )
    result = prepare_dashboard_date_filter(
        "select dt from orders where dt between {{dashboard_start_yyyymmdd}} "
        "and {{dashboard_end_yyyymmdd}}",
        ds_type="mysql",
        pivot=_pivot("yyyymmdd_number"),
        today=date(2026, 7, 27),
    )
    assert result.start == "2026-07-13"
    assert result.end == "2026-07-26"
    assert "20260713" in result.sql and "20260726" in result.sql
    assert result.capability["status"] == "available"


def test_end_only_date_parameter_renders_selected_range_end_for_snapshot_queries():
    result = prepare_dashboard_date_filter(
        "select * from user_snapshot where dt = {{dashboard_end_yyyymmdd}}",
        ds_type="mysql",
        pivot=_pivot(
            "yyyymmdd_number",
            date_parameter_mode="end_only",
            date_expression={"version": 1, "mode": "preset", "preset": "current_month"},
        ),
        today=date(2026, 7, 28),
    )

    assert result.capability["status"] == "available"
    assert result.capability["parameterMode"] == "end_only"
    assert result.start == "2026-07-01"
    assert result.end == "2026-07-28"
    assert "dt = 20260728" in result.sql


@pytest.mark.parametrize(
    ("parameter_type", "sql", "expected"),
    [
        (
            "date",
            "select dt from orders where dt between {{dashboard_start_date}} and {{dashboard_end_date}}",
            "'2026-07-13'",
        ),
        (
            "yyyymmdd_text",
            "select dt from orders where dt between {{dashboard_start_yyyymmdd}} and {{dashboard_end_yyyymmdd}}",
            "'20260713'",
        ),
        (
            "timestamp",
            "select dt from orders where dt >= {{dashboard_start_timestamp}} "
            "and dt < {{dashboard_end_exclusive_timestamp}}",
            "'2026-07-27 00:00:00'",
        ),
    ],
)
def test_parameter_families_render_controlled_literals(parameter_type, sql, expected):
    result = prepare_dashboard_date_filter(
        sql,
        ds_type="postgres",
        pivot=_pivot(parameter_type),
        today=date(2026, 7, 27),
    )
    assert result.capability["status"] == "available"
    assert expected in result.sql


def test_custom_range_is_validated_and_rendered():
    result = prepare_dashboard_date_filter(
        "select dt from orders where dt between {{dashboard_start_date}} and {{dashboard_end_date}}",
        ds_type="postgres",
        pivot=_pivot(
            "date",
            range="custom",
            custom_start="2026-05-01",
            custom_end="2026-05-31",
        ),
        today=date(2026, 7, 27),
    )
    assert result.start == "2026-05-01"
    assert result.end == "2026-05-31"
    assert "'2026-05-01'" in result.sql
    assert "'2026-05-31'" in result.sql


def test_custom_range_overrides_persisted_date_expression_for_card_filter():
    result = prepare_dashboard_date_filter(
        "select dt from orders where dt between {{dashboard_start_date}} and {{dashboard_end_date}}",
        ds_type="postgres",
        pivot=_pivot(
            "date",
            range="custom",
            custom_start="2026-05-01",
            custom_end="2026-05-31",
            date_expression={"version": 1, "mode": "preset", "preset": "past_30_days"},
        ),
        today=date(2026, 7, 27),
    )

    assert result.start == "2026-05-01"
    assert result.end == "2026-05-31"
    assert result.capability["expression"] is None


@pytest.mark.parametrize(
    "pivot",
    [
        {},
        _pivot(""),
        _pivot("date", range="custom", custom_start="2026-05-31", custom_end="2026-05-01"),
        _pivot("date", range="custom", custom_start="2026-05-01", custom_end="2026-07-27"),
    ],
)
def test_missing_configuration_and_invalid_ranges_fail_closed(pivot):
    sql = "select dt from orders where dt between {{dashboard_start_date}} and {{dashboard_end_date}}"
    result = prepare_dashboard_date_filter(
        sql,
        ds_type="postgres",
        pivot=pivot,
        today=date(2026, 7, 27),
    )
    assert result.capability["status"] == "unconfigured"
    assert result.capability["reason"]
    assert result.sql == sql


def test_explicitly_disabled_range_is_unconfigured():
    sql = "select dt from orders where dt between {{dashboard_start_date}} and {{dashboard_end_date}}"

    result = prepare_dashboard_date_filter(
        sql,
        ds_type="postgres",
        pivot=_pivot("date", range_enabled=False),
        today=date(2026, 7, 27),
    )

    assert result.capability == {"status": "unconfigured", "reason": "range_disabled"}
    assert result.sql == sql


@pytest.mark.parametrize(
    ("ds_type", "date_literal", "timestamp_literal"),
    [
        ("postgres", "DATE '2026-07-13'", "TIMESTAMP '2026-07-13 00:00:00'"),
        ("mysql", "DATE('2026-07-13')", "TIMESTAMP('2026-07-13 00:00:00')"),
        ("oracle", "TO_DATE('2026-07-13', 'YYYY-MM-DD')", "TO_TIMESTAMP('2026-07-13 00:00:00', 'YYYY-MM-DD HH24:MI:SS')"),
        ("dm", "TO_DATE('2026-07-13', 'YYYY-MM-DD')", "TO_TIMESTAMP('2026-07-13 00:00:00', 'YYYY-MM-DD HH24:MI:SS')"),
        ("sqlserver", "CAST('2026-07-13' AS DATE)", "CAST('2026-07-13 00:00:00' AS DATETIME2)"),
        ("clickhouse", "toDate('2026-07-13')", "toDateTime('2026-07-13 00:00:00')"),
        ("hive", "TO_DATE('2026-07-13')", "CAST('2026-07-13 00:00:00' AS TIMESTAMP)"),
    ],
)
def test_date_and_timestamp_literals_are_explicit_for_each_dialect(
    ds_type,
    date_literal,
    timestamp_literal,
):
    date_result = prepare_dashboard_date_filter(
        "select dt from orders where dt between {{dashboard_start_date}} and {{dashboard_end_date}}",
        ds_type=ds_type,
        pivot=_pivot("date"),
        today=date(2026, 7, 27),
    )
    timestamp_result = prepare_dashboard_date_filter(
        "select dt from orders where dt >= {{dashboard_start_timestamp}} "
        "and dt < {{dashboard_end_exclusive_timestamp}}",
        ds_type=ds_type,
        pivot=_pivot("timestamp"),
        today=date(2026, 7, 27),
    )

    assert date_literal in date_result.sql
    assert timestamp_literal in timestamp_result.sql


def test_incomplete_mixed_and_inert_tokens_are_not_applied():
    incomplete = prepare_dashboard_date_filter(
        "select dt from orders where dt >= {{dashboard_start_date}}",
        ds_type="postgres",
        pivot=_pivot("date"),
        today=date(2026, 7, 27),
    )
    assert incomplete.capability == {"status": "unconfigured", "reason": "incomplete_parameters"}

    mixed = prepare_dashboard_date_filter(
        "select dt from orders where dt >= {{dashboard_start_date}} and dt <= {{dashboard_end_yyyymmdd}}",
        ds_type="postgres",
        pivot=_pivot("date"),
        today=date(2026, 7, 27),
    )
    assert mixed.capability == {"status": "unconfigured", "reason": "mixed_parameter_families"}

    inert = prepare_dashboard_date_filter(
        "select '{{dashboard_start_date}}' as literal, dt from orders "
        "-- {{dashboard_end_date}}\n/* {{dashboard_start_yyyymmdd}} */",
        ds_type="postgres",
        pivot=_pivot("date"),
        today=date(2026, 7, 27),
    )
    assert inert.capability == {"status": "unconfigured", "reason": "missing_parameters"}
    assert "{{dashboard_start_date}}" in inert.sql


def test_realtime_physical_table_hides_filter_but_cte_and_comments_do_not():
    realtime_sql = "select dt from analytics.`event_realtime` where dt={{dashboard_start_yyyymmdd}}"
    realtime = prepare_dashboard_date_filter(
        realtime_sql,
        ds_type="mysql",
        pivot=_pivot("yyyymmdd_number"),
        today=date(2026, 7, 27),
    )
    assert realtime.capability == {"status": "realtime", "reason": "realtime_table"}
    assert realtime.sql == realtime_sql
    assert realtime.physical_tables == {"event_realtime"}

    historical = prepare_dashboard_date_filter(
        "with event_realtime as (select dt from event) select dt from event_realtime "
        "where dt between {{dashboard_start_yyyymmdd}} and {{dashboard_end_yyyymmdd}} "
        "and 'event_realtime'='event_realtime' /* event_realtime */",
        ds_type="mysql",
        pivot=_pivot("yyyymmdd_number"),
        today=date(2026, 7, 27),
    )
    assert historical.capability["status"] == "available"
    assert historical.physical_tables == {"event"}


def test_realtime_physical_table_is_not_hidden_by_same_named_cte():
    sql = (
        "with event_realtime as (select dt from analytics.event_realtime) "
        "select dt from event_realtime where dt between "
        "{{dashboard_start_yyyymmdd}} and {{dashboard_end_yyyymmdd}}"
    )

    result = prepare_dashboard_date_filter(
        sql,
        ds_type="mysql",
        pivot={"time_field": "dt", "date_parameter_type": "yyyymmdd_number"},
        today=date(2026, 7, 27),
    )

    assert result.capability == {"status": "realtime", "reason": "realtime_table"}
    assert result.sql == sql
    assert result.physical_tables == {"event_realtime"}


def test_tokens_inside_dollar_quoted_and_backslash_escaped_strings_are_ignored():
    postgres_sql = (
        "select $$ {{dashboard_start_date}} $$ as note, dt from orders "
        "where dt between {{dashboard_start_date}} and {{dashboard_end_date}}"
    )
    postgres = prepare_dashboard_date_filter(
        postgres_sql,
        ds_type="postgresql",
        pivot={"time_field": "dt", "date_parameter_type": "date"},
        today=date(2026, 7, 27),
    )
    assert "$$ {{dashboard_start_date}} $$" in postgres.sql
    assert "dt between DATE '2026-07-13' and DATE '2026-07-26'" in postgres.sql

    mysql_sql = (
        r"select 'ignored \' {{dashboard_start_yyyymmdd}}' as note, dt from orders "
        "where dt between {{dashboard_start_yyyymmdd}} and {{dashboard_end_yyyymmdd}}"
    )
    mysql = prepare_dashboard_date_filter(
        mysql_sql,
        ds_type="mysql",
        pivot={"time_field": "dt", "date_parameter_type": "yyyymmdd_number"},
        today=date(2026, 7, 27),
    )
    assert "'ignored \\' {{dashboard_start_yyyymmdd}}'" in mysql.sql
    assert "dt between 20260713 and 20260726" in mysql.sql


def test_sql_parse_failure_is_unconfigured():
    result = prepare_dashboard_date_filter(
        "select ( from orders where dt between {{dashboard_start_date}} and {{dashboard_end_date}}",
        ds_type="postgres",
        pivot=_pivot("date"),
        today=date(2026, 7, 27),
    )
    assert result.capability == {"status": "unconfigured", "reason": "sql_parse_failed"}


def test_invalid_business_timezone_fails_configuration_validation():
    with pytest.raises(ValidationError, match="DASHBOARD_BUSINESS_TIMEZONE"):
        Settings(_env_file=None, DASHBOARD_BUSINESS_TIMEZONE="Invalid/Timezone")


def test_independent_date_filter_renders_yyyymmdd_without_pivot():
    result = prepare_dashboard_date_filter(
        "select dt from orders where dt between {{dashboard_start_yyyymmdd}} "
        "and {{dashboard_end_yyyymmdd}}",
        ds_type="mysql",
        pivot={"enabled": False},
        date_filter=DashboardDateFilterRequest(
            parameter_type="yyyymmdd_number",
            custom_start="2026-05-01",
            custom_end="2026-05-31",
        ),
        require_time_field=False,
        today=date(2026, 7, 28),
    )

    assert result.capability["status"] == "available"
    assert "20260501" in result.sql
    assert "20260531" in result.sql


def test_independent_date_filter_accepts_today_custom_range_from_dashboard_refresh():
    result = prepare_dashboard_date_filter(
        "select dt from orders where dt = {{dashboard_end_yyyymmdd}}",
        ds_type="mysql",
        pivot={"enabled": False},
        date_filter=DashboardDateFilterRequest(
            parameter_type="yyyymmdd_number",
            expression={"version": 1, "mode": "preset", "preset": "today"},
            custom_start="2026-07-28",
            custom_end="2026-07-28",
        ),
        require_time_field=False,
        today=date(2026, 7, 28),
    )

    assert result.capability["status"] == "available"
    assert result.capability["parameterMode"] == "end_only"
    assert result.capability["expression"] is None
    assert result.start == result.end == "2026-07-28"
    assert "dt = 20260728" in result.sql


def test_independent_date_filter_rejects_partial_custom_range():
    result = prepare_dashboard_date_filter(
        "select dt from orders where dt between {{dashboard_start_yyyymmdd}} "
        "and {{dashboard_end_yyyymmdd}}",
        ds_type="mysql",
        pivot={"enabled": False},
        date_filter=DashboardDateFilterRequest(
            parameter_type="yyyymmdd_number",
            custom_start="2026-05-01",
        ),
        require_time_field=False,
        today=date(2026, 7, 28),
    )

    assert result.capability == {"status": "unconfigured", "reason": "invalid_date_range"}
