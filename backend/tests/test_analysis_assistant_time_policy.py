from datetime import date

import pytest

from apps.analysis_assistant.service.analysis_time_policy import (
    AnalysisTimeAnchor,
    AnalysisTimeSource,
    parse_analysis_time_intent,
    parse_data_skill_time_directive,
    resolve_analysis_time_policy,
)

ANCHOR = AnalysisTimeAnchor(table="fact_orders", field="business_date")


def _resolve(
    question: str,
    *,
    history: list[str] | None = None,
    skill: str = "",
    anchor_date: date = date(2026, 7, 26),
):
    intent = parse_analysis_time_intent(question, history or [])
    window_days, warnings = parse_data_skill_time_directive(skill)
    return resolve_analysis_time_policy(
        intent,
        skill_window_days=window_days,
        anchor=ANCHOR,
        anchor_date=anchor_date,
        warnings=warnings,
    )


def test_default_window_contains_latest_fourteen_calendar_days() -> None:
    resolution = _resolve("分析渠道收入变化")
    assert resolution.status == "resolved"
    assert resolution.policy is not None
    assert resolution.policy.source is AnalysisTimeSource.DEFAULT_14_DAYS
    assert resolution.policy.start_date == date(2026, 7, 13)
    assert resolution.policy.end_date == date(2026, 7, 26)
    assert resolution.policy.start_inclusive is True
    assert resolution.policy.end_inclusive is True


def test_structured_data_skill_window_overrides_default_only() -> None:
    resolution = _resolve(
        "分析渠道收入变化",
        skill='<!-- data-skill-analysis-time:{"window_days":30,"anchor":"latest_available"} -->',
    )
    assert resolution.policy is not None
    assert resolution.policy.source is AnalysisTimeSource.DATA_SKILL
    assert resolution.policy.start_date == date(2026, 6, 27)


def test_sql_example_does_not_override_default_window() -> None:
    resolution = _resolve("分析渠道收入变化", skill="示例 SQL：WHERE day >= CURRENT_DATE - 30")
    assert resolution.policy is not None
    assert resolution.policy.source is AnalysisTimeSource.DEFAULT_14_DAYS


@pytest.mark.parametrize(
    ("question", "expected_boundary", "inclusive", "expected_trace_start"),
    [
        ("分析14日之后的数据", date(2026, 7, 14), False, "2026-07-15"),
        ("从14号开始分析", date(2026, 7, 14), True, "2026-07-14"),
        ("分析14日起的数据", date(2026, 7, 14), True, "2026-07-14"),
        ("分析14日及以后的数据", date(2026, 7, 14), True, "2026-07-14"),
    ],
)
def test_day_only_open_ranges_have_deterministic_inclusion(
    question: str,
    expected_boundary: date,
    inclusive: bool,
    expected_trace_start: str,
) -> None:
    resolution = _resolve(question)
    assert resolution.policy is not None
    assert resolution.policy.source is AnalysisTimeSource.USER
    assert resolution.policy.start_date == expected_boundary
    assert resolution.policy.start_inclusive is inclusive
    assert expected_trace_start in resolution.traces[0]


def test_day_only_uses_previous_month_when_day_has_not_occurred() -> None:
    resolution = _resolve("从14号开始分析", anchor_date=date(2026, 7, 10))
    assert resolution.policy is not None
    assert resolution.policy.start_date == date(2026, 6, 14)
    assert resolution.policy.end_date == date(2026, 7, 10)


def test_current_question_month_overrides_history_month() -> None:
    resolution = _resolve("分析8月14日之后的数据", history=["看一下 2026 年 6 月收入"])
    assert resolution.policy is not None
    assert resolution.policy.start_date == date(2025, 8, 14)


def test_explicit_year_is_not_rewritten_when_it_is_after_anchor() -> None:
    resolution = _resolve("分析2026年8月14日之后的数据")
    assert resolution.policy is not None
    assert resolution.policy.start_date == date(2026, 8, 14)
    assert resolution.policy.start_inclusive is False


def test_recent_history_supplies_missing_month_and_year() -> None:
    resolution = _resolve("从14号开始", history=["继续", "看一下 2026 年 6 月收入"])
    assert resolution.policy is not None
    assert resolution.policy.start_date == date(2026, 6, 14)


def test_day_only_uses_year_month_from_current_question_before_history() -> None:
    resolution = _resolve(
        "分析 2026 年 8 月收入，14 日之后",
        history=["看一下 2026 年 6 月收入"],
    )
    assert resolution.policy is not None
    assert resolution.policy.start_date == date(2026, 8, 14)


def test_day_only_uses_month_from_current_question_without_history_year() -> None:
    intent = parse_analysis_time_intent(
        "分析 8月收入，14日之后",
        ["2026年6月收入"],
    )
    resolution = resolve_analysis_time_policy(
        intent,
        skill_window_days=None,
        anchor=ANCHOR,
        anchor_date=date(2026, 7, 26),
    )
    assert intent.year is None
    assert intent.month == 8
    assert resolution.policy is not None
    assert resolution.policy.start_date == date(2025, 8, 14)


def test_day_only_searches_previous_month_for_latest_valid_month_end() -> None:
    resolution = _resolve("31日之后", anchor_date=date(2026, 4, 10))
    assert resolution.policy is not None
    assert resolution.policy.start_date == date(2026, 3, 31)
    assert resolution.policy.start_inclusive is False
    assert "2026-04-01" in resolution.traces[0]


def test_day_only_searches_previous_leap_day_when_available() -> None:
    resolution = _resolve("29日之后", anchor_date=date(2024, 3, 1))
    assert resolution.policy is not None
    assert resolution.policy.start_date == date(2024, 2, 29)
    assert resolution.policy.start_inclusive is False
    assert "2024-03-01" in resolution.traces[0]


def test_month_without_year_searches_previous_year_for_latest_valid_leap_day() -> None:
    resolution = _resolve("2月29日之后", anchor_date=date(2025, 3, 1))
    assert resolution.policy is not None
    assert resolution.policy.start_date == date(2024, 2, 29)
    assert resolution.policy.start_inclusive is False
    assert "2024-03-01" in resolution.traces[0]


@pytest.mark.parametrize("question", ["4月31日之后", "2025年2月29日之后"])
def test_invalid_explicit_month_day_is_not_rewritten_to_another_year(question: str) -> None:
    resolution = _resolve(question, anchor_date=date(2025, 3, 1))
    assert resolution.status == "unresolved"
    assert resolution.policy is None
    assert resolution.warnings == ("用户指定的日期无效，无法确定时间策略。",)


def test_explicit_absolute_range_does_not_need_anchor() -> None:
    intent = parse_analysis_time_intent("分析 2026-07-01 到 2026-07-10", [])
    resolution = resolve_analysis_time_policy(
        intent,
        skill_window_days=None,
        anchor=None,
        anchor_date=None,
    )
    assert intent.requires_anchor is False
    assert resolution.policy is not None
    assert resolution.policy.start_date == date(2026, 7, 1)
    assert resolution.policy.end_date == date(2026, 7, 10)


def test_anchor_required_intent_is_unresolved_without_anchor() -> None:
    intent = parse_analysis_time_intent("最近7天收入", [])
    resolution = resolve_analysis_time_policy(
        intent,
        skill_window_days=None,
        anchor=None,
        anchor_date=date(2026, 7, 26),
    )
    assert resolution.status == "unresolved"
    assert resolution.policy is None
    assert resolution.warnings == (
        "无法确认当前数据源的时间锚点，本次仅执行能够确认时间边界的分析块。",
    )


@pytest.mark.parametrize(
    "question",
    [
        "分析2026年4月31日之后的数据",
        "分析 2026-02-30 到 2026-03-01",
    ],
)
def test_invalid_calendar_date_is_unresolved_without_substitution(question: str) -> None:
    intent = parse_analysis_time_intent(question, [])
    resolution = resolve_analysis_time_policy(
        intent,
        skill_window_days=None,
        anchor=ANCHOR,
        anchor_date=date(2026, 7, 26),
    )
    assert resolution.status == "unresolved"
    assert resolution.policy is None
    assert resolution.warnings == ("用户指定的日期无效，无法确定时间策略。",)


def test_leap_day_absolute_range_is_resolved() -> None:
    intent = parse_analysis_time_intent("分析 2024-02-29 到 2024-02-29", [])
    resolution = resolve_analysis_time_policy(
        intent,
        skill_window_days=None,
        anchor=None,
        anchor_date=None,
    )
    assert resolution.status == "resolved"
    assert resolution.policy is not None
    assert resolution.policy.start_date == date(2024, 2, 29)
    assert resolution.policy.end_date == date(2024, 2, 29)


def test_month_end_absolute_range_is_resolved() -> None:
    intent = parse_analysis_time_intent("分析 2026-04-30 到 2026-04-30", [])
    resolution = resolve_analysis_time_policy(
        intent,
        skill_window_days=None,
        anchor=None,
        anchor_date=None,
    )
    assert resolution.status == "resolved"
    assert resolution.policy is not None
    assert resolution.policy.start_date == date(2026, 4, 30)
    assert resolution.policy.end_date == date(2026, 4, 30)


def test_descending_absolute_range_is_unresolved() -> None:
    intent = parse_analysis_time_intent("分析 2026-07-10 到 2026-07-01", [])
    resolution = resolve_analysis_time_policy(
        intent,
        skill_window_days=None,
        anchor=None,
        anchor_date=None,
    )
    assert resolution.status == "unresolved"
    assert resolution.policy is None
    assert resolution.warnings == ("用户指定的时间范围倒序，无法确定时间策略。",)


@pytest.mark.parametrize("question", ["最近7天收入", "近两周收入", "昨天收入", "本月收入"])
def test_explicit_relative_time_never_uses_platform_default(question: str) -> None:
    resolution = _resolve(question)
    assert resolution.policy is not None
    assert resolution.policy.source is AnalysisTimeSource.USER


def test_invalid_skill_directive_is_visible_and_falls_back_to_default() -> None:
    resolution = _resolve(
        "分析渠道收入变化",
        skill='<!-- data-skill-analysis-time:{"window_days":0,"anchor":"today"} -->',
    )
    assert resolution.policy is not None
    assert resolution.policy.source is AnalysisTimeSource.DEFAULT_14_DAYS
    assert resolution.warnings == ("Data Skill 时间声明无效，已使用平台默认时间策略。",)
