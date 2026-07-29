from datetime import date

import pytest

from apps.chat.service.chat_date_filter import (
    ChatDateFilterConfigurationError,
    normalize_chat_date_filter,
    render_chat_date_filter_sql,
)


DATE_TEMPLATE_SQL = (
    "SELECT * FROM event "
    "WHERE dt BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}"
)
DATE_FILTER = {
    "time_field": "dt",
    "date_parameter_type": "yyyymmdd_number",
    "date_expression": {"version": 1, "mode": "preset", "preset": "past_7_days"},
}


def test_normalize_accepts_complete_past_seven_days_yyyymmdd_template():
    pivot = normalize_chat_date_filter(DATE_FILTER, DATE_TEMPLATE_SQL, "line")

    assert pivot == {"enabled": False, **DATE_FILTER}


def test_normalize_rejects_token_without_configuration():
    with pytest.raises(ChatDateFilterConfigurationError, match="missing_date_filter"):
        normalize_chat_date_filter(None, DATE_TEMPLATE_SQL, "line")


def test_normalize_rejects_fixed_metric_date_configuration():
    with pytest.raises(ChatDateFilterConfigurationError, match="metric_chart"):
        normalize_chat_date_filter(DATE_FILTER, DATE_TEMPLATE_SQL, "metric")


def test_normalize_rejects_current_date_function_for_date_filter():
    with pytest.raises(ChatDateFilterConfigurationError, match="database_current_date"):
        normalize_chat_date_filter(
            DATE_FILTER,
            "SELECT * FROM event WHERE dt >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)",
            "line",
        )


def test_render_uses_past_seven_days_before_execution():
    sql = render_chat_date_filter_sql(
        DATE_TEMPLATE_SQL,
        "mysql",
        {"enabled": False, **DATE_FILTER},
        today=date(2026, 7, 29),
    )

    assert "20260722" in sql
    assert "20260728" in sql
    assert "{{dashboard_start_yyyymmdd}}" not in sql
    assert "{{dashboard_end_yyyymmdd}}" not in sql
