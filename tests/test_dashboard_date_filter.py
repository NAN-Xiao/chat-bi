from datetime import date

import pytest
from pydantic import ValidationError

from apps.dashboard.crud.dashboard_date_filter import (
    default_dashboard_date_range,
    prepare_dashboard_date_filter,
)
from common.core.config import Settings


def _pivot(parameter_type: str, **overrides):
    return {
        "time_field": "dt",
        "date_parameter_type": parameter_type,
        **overrides,
    }


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
    assert "dt between '2026-07-13' and '2026-07-26'" in postgres.sql

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
