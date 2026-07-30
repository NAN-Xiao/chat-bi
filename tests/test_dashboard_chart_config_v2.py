"""看板日期筛选 V2 配置和迁移期 V1 读取器测试。"""

from __future__ import annotations

from apps.dashboard.crud.dashboard_date_filter_legacy import (
    resolve_dashboard_chart_date_filter,
)


RANGE_SQL = (
    "select * from orders "
    "where dt >= {{dashboard_start_yyyymmdd}} "
    "and dt <= {{dashboard_end_yyyymmdd}}"
)


def test_v2_date_filter_is_independent_from_disabled_pivot() -> None:
    result = resolve_dashboard_chart_date_filter(
        {
            "configVersion": 2,
            "sql": RANGE_SQL,
            "dateFilter": {
                "enabled": True,
                "parameterType": "yyyymmdd_number",
                "expression": {
                    "version": 1,
                    "mode": "preset",
                    "preset": "past_7_days",
                },
            },
            "pivot": {"enabled": False},
        },
        allow_legacy=True,
    )

    assert result.status == "v2"
    assert result.error_type == ""
    assert result.date_filter is not None
    assert result.date_filter.parameter_type == "yyyymmdd_number"
    assert result.date_filter.expression["preset"] == "past_7_days"


def test_complete_v1_is_deterministically_read_but_not_persisted() -> None:
    result = resolve_dashboard_chart_date_filter(
        {
            "sql": RANGE_SQL,
            "pivot": {
                "enabled": False,
                "date_parameter_type": "yyyymmdd_number",
                "date_expression": {
                    "version": 1,
                    "mode": "preset",
                    "preset": "past_7_days",
                },
            },
        },
        allow_legacy=True,
    )

    assert result.status == "legacy"
    assert result.date_filter is not None
    assert result.date_filter.parameter_type == "yyyymmdd_number"


def test_incomplete_v1_requires_explicit_migration() -> None:
    result = resolve_dashboard_chart_date_filter(
        {"sql": RANGE_SQL, "pivot": {"enabled": False}},
        allow_legacy=True,
    )

    assert result.status == "migration_required"
    assert result.error_type == "dashboard_date_filter_migration_required"
    assert result.date_filter is None


def test_v1_reader_rejects_parameter_family_mismatch() -> None:
    result = resolve_dashboard_chart_date_filter(
        {
            "sql": RANGE_SQL,
            "pivot": {
                "date_parameter_type": "date",
                "date_expression": {
                    "version": 1,
                    "mode": "preset",
                    "preset": "past_7_days",
                },
            },
        },
        allow_legacy=True,
    )

    assert result.status == "invalid"
    assert result.error_type == "dashboard_date_filter_invalid_template"


def test_sql_without_date_tokens_has_no_date_filter_capability() -> None:
    result = resolve_dashboard_chart_date_filter(
        {"configVersion": 2, "sql": "select * from orders", "pivot": {"enabled": False}},
        allow_legacy=True,
    )

    assert result.status == "none"
    assert result.date_filter is None


def test_v1_reader_can_be_disabled_without_silent_fallback() -> None:
    result = resolve_dashboard_chart_date_filter(
        {
            "sql": RANGE_SQL,
            "pivot": {
                "date_parameter_type": "yyyymmdd_number",
                "date_expression": {
                    "version": 1,
                    "mode": "preset",
                    "preset": "past_7_days",
                },
            },
        },
        allow_legacy=False,
    )

    assert result.status == "migration_required"
    assert result.error_type == "dashboard_date_filter_migration_required"
