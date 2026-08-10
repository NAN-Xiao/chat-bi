import pytest

from apps.chat.service.chat_date_filter import (
    ChatDateFilterConfigurationError,
    DASHBOARD_DATE_FILTER_DISABLED_GUIDANCE,
    ensure_chat_date_filter_allowed,
)


def test_excluded_tenant_cannot_use_dashboard_date_tokens_or_payload():
    with pytest.raises(ChatDateFilterConfigurationError, match="dashboard_date_filter_disabled"):
        ensure_chat_date_filter_allowed(
            False,
            {"time_field": "dt", "date_parameter_type": "date"},
            "select dt from orders where dt between {{dashboard_start_yyyymmdd}} and {{dashboard_end_yyyymmdd}}",
        )


def test_excluded_tenant_can_use_explicit_sql_dates_without_dashboard_capability():
    ensure_chat_date_filter_allowed(
        False,
        None,
        "select dt from orders where dt between DATE '2026-07-20' and DATE '2026-07-26'",
    )


def test_disabled_date_guidance_overrides_global_dashboard_date_contract():
    assert "不得返回 date_filter 字段" in DASHBOARD_DATE_FILTER_DISABLED_GUIDANCE
    assert "不得使用任何 {{dashboard_start_*}}" in DASHBOARD_DATE_FILTER_DISABLED_GUIDANCE
    assert "可执行的日期字面量" in DASHBOARD_DATE_FILTER_DISABLED_GUIDANCE
