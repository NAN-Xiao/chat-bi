"""
验证 Data Skill SQL 校验的结构化违规对象和旧文本接口兼容性。
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import orjson
import pytest

from apps.chat.models.chat_model import OperationEnum
from apps.chat.task import llm
from apps.chat.task.sql_repair import DataSkillSqlValidationError, DataSkillSqlViolation


TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

platform_skill = importlib.import_module("seed_platform_realtime_event_table_skill")


def _data_skill(*rules: dict) -> str:
    return "<!-- data-skill-sql-validation: " + orjson.dumps(list(rules)).decode() + " -->"


@pytest.mark.parametrize(
    "question",
    [
        "当前等级的活跃用户分布",
        "截至目前的历史累计付费趋势",
        "截至当前的完整历史日付费",
    ],
)
def test_generic_current_phrases_do_not_activate_realtime_rule(question: str) -> None:
    rule = json.loads(platform_skill.SQL_VALIDATION_RULE)
    data_skill = _data_skill(rule)
    sql = "SELECT COUNT(DISTINCT e.uid) FROM event e WHERE e.dt=20260726"

    assert llm._data_skill_sql_validation_violation(question, sql, data_skill) is None


def test_realtime_rule_only_forces_realtime_table_for_current_day_scope() -> None:
    rule = json.loads(platform_skill.SQL_VALIDATION_RULE)
    data_skill = _data_skill(rule)

    assert (
        llm._data_skill_sql_validation_violation(
            "实时收入",
            "SELECT SUM(amount) FROM event",
            data_skill,
        )
        is not None
    )
    assert (
        llm._data_skill_sql_validation_violation(
            "当前小时收入",
            "SELECT SUM(amount) FROM event",
            data_skill,
        )
        is not None
    )
    assert (
        llm._data_skill_sql_validation_violation(
            "昨天实时收入",
            "SELECT SUM(amount) FROM event",
            data_skill,
        )
        is None
    )
    assert (
        llm._data_skill_sql_validation_violation(
            "本月实时收入",
            "SELECT SUM(amount) FROM event",
            data_skill,
        )
        is None
    )


def test_required_items_are_returned_as_structured_violation() -> None:
    data_skill = _data_skill(
        {"match": "其它问题", "required_sql_contains": ["ignored_table"]},
        {
            "match": "DAU",
            "message": "必须按 DAU 口径生成 SQL",
            "required_sql_contains": ["fact_events"],
            "required_sql_all_contains": [["player_id", "event_time"]],
            "required_sql_patterns": [r"date\s*="],
        },
    )

    violation = llm._data_skill_sql_validation_violation(
        "查询 DAU",
        "select player_id from fact_events where event_name = 'login'",
        data_skill,
    )

    assert violation == DataSkillSqlViolation(
        message="必须按 DAU 口径生成 SQL",
        rule_index=1,
        missing_required_contains=("event_time",),
        missing_required_patterns=(r"date\s*=",),
        matched_forbidden_contains=(),
        matched_forbidden_patterns=(),
        matched_forbidden_groups=(),
    )


def test_forbidden_items_and_select_groups_are_collected() -> None:
    data_skill = _data_skill(
        {
            "match": "订单",
            "message": "禁止使用旧口径",
            "forbidden_sql_contains": ["legacy_table"],
            "forbidden_sql_all_contains": [["orders", "amount"]],
            "forbidden_sql_patterns": [r"select\s+\*"],
            "forbidden_sql_select_all_contains": [["fact_events", "event_name"]],
        }
    )

    violation = llm._data_skill_sql_validation_violation(
        "查询订单",
        "select * from fact_events join legacy_table using (id) "
        "where event_name = 'pay' and orders.amount > 0",
        data_skill,
    )

    assert violation is not None
    assert violation.message == "禁止使用旧口径"
    assert violation.rule_index == 0
    assert violation.matched_forbidden_contains == ("legacy_table",)
    assert violation.matched_forbidden_patterns == (r"select\s+\*",)
    assert violation.matched_forbidden_groups == (
        ("fact_events", "event_name"),
        ("orders", "amount"),
    )


def test_match_and_allow_when_semantics_are_preserved() -> None:
    data_skill = _data_skill(
        {
            "match": "收入",
            "allow_when": ["退款收入"],
            "required_sql_contains": ["required_table"],
        },
        {"match": "用户数", "required_sql_contains": ["required_table"]},
    )

    assert llm._data_skill_sql_validation_violation("查询退款收入", "select 1", data_skill) is None
    assert llm._data_skill_sql_validation_violation("查询订单", "select 1", data_skill) is None
    assert (
        llm._data_skill_sql_validation_violation("查询用户数", "select 1", data_skill)
        is not None
    )


def test_sql_scope_patterns_limit_validation_to_matching_tables() -> None:
    event_table_pattern = r"\b(?:from|join)\s+`?event(?:_realtime)?`?(?=\s|,|$)"
    realtime_table_pattern = r"\b(?:from|join)\s+`?event_realtime`?(?=\s|,|$)"
    history_table_pattern = r"\b(?:from|join)\s+`?event`?(?=\s|,|$)"
    data_skill = _data_skill(
        {
            "match": ["今天", "当前", "实时"],
            "when_sql_patterns": [event_table_pattern],
            "required_sql_patterns": [realtime_table_pattern],
            "forbidden_sql_patterns": [history_table_pattern],
        }
    )

    assert (
        llm._data_skill_sql_validation_violation(
            "当前玩家等级分布",
            "SELECT level, COUNT(*) FROM user GROUP BY level",
            data_skill,
        )
        is None
    )
    assert (
        llm._data_skill_sql_validation_violation(
            "今天每小时新增用户",
            "SELECT COUNT(*) FROM event_realtime WHERE event='UserRegister'",
            data_skill,
        )
        is None
    )
    assert (
        llm._data_skill_sql_validation_violation(
            "今天每小时新增用户",
            "SELECT COUNT(*) FROM `event_realtime` WHERE event='UserRegister'",
            data_skill,
        )
        is None
    )
    violation = llm._data_skill_sql_validation_violation(
        "今天每小时新增用户",
        "SELECT COUNT(*) FROM event WHERE event='UserRegister'",
        data_skill,
    )
    assert violation is not None
    assert violation.missing_required_patterns == (realtime_table_pattern,)
    assert violation.matched_forbidden_patterns == (history_table_pattern,)


def test_structured_group_scope_distinguishes_time_fields_from_dimensions() -> None:
    data_skill = _data_skill(
        {
            "match": "每小时",
            "when_sql_has_non_time_group_by": True,
            "required_outer_select_cross_join": True,
        }
    )
    time_only_sql = """
        SELECT biz_date, HOUR(event_time), COUNT(*)
        FROM events
        GROUP BY biz_date, HOUR(event_time)
    """
    grouped_sql = """
        SELECT biz_date, HOUR(event_time), region_code, COUNT(*)
        FROM events
        GROUP BY biz_date, HOUR(event_time), region_code
    """

    assert llm._data_skill_sql_validation_violation("每小时趋势", time_only_sql, data_skill) is None
    violation = llm._data_skill_sql_validation_violation("每小时各地区趋势", grouped_sql, data_skill)
    assert violation is not None
    assert violation.missing_required_patterns == ("outer SELECT CROSS JOIN",)


def test_intermediate_dedup_group_does_not_change_final_result_grain() -> None:
    data_skill = _data_skill(
        {
            "match": "每日",
            "when_sql_has_non_time_group_by": True,
            "required_outer_select_cross_join": True,
        }
    )
    sql = """
        WITH date_spine AS (
            SELECT dt FROM calendar
        ), user_day_flags AS (
            SELECT dt, uid, MAX(is_active) AS is_active
            FROM events
            GROUP BY dt, uid
        ), daily_metrics AS (
            SELECT dt, SUM(is_active) AS active_users
            FROM user_day_flags
            GROUP BY dt
        )
        SELECT d.dt, COALESCE(m.active_users, 0) AS active_users
        FROM date_spine d
        LEFT JOIN daily_metrics m ON m.dt = d.dt
    """

    assert llm._data_skill_sql_validation_violation("每日活跃用户趋势", sql, data_skill) is None


def test_final_aggregate_dimension_still_requires_cross_join() -> None:
    data_skill = _data_skill(
        {
            "match": "每日",
            "when_sql_has_non_time_group_by": True,
            "required_outer_select_cross_join": True,
        }
    )
    sql = """
        WITH date_spine AS (
            SELECT dt FROM calendar
        ), user_day_flags AS (
            SELECT dt, uid, region_code, MAX(is_active) AS is_active
            FROM events
            GROUP BY dt, uid, region_code
        ), daily_metrics AS (
            SELECT dt, region_code, SUM(is_active) AS active_users
            FROM user_day_flags
            GROUP BY dt, region_code
        )
        SELECT d.dt, m.region_code, COALESCE(m.active_users, 0) AS active_users
        FROM date_spine d
        LEFT JOIN daily_metrics m ON m.dt = d.dt
    """

    violation = llm._data_skill_sql_validation_violation("每日各地区活跃用户趋势", sql, data_skill)
    assert violation is not None
    assert violation.missing_required_patterns == ("outer SELECT CROSS JOIN",)


def test_outer_cross_join_requirement_ignores_cross_join_inside_cte() -> None:
    data_skill = _data_skill(
        {
            "when_sql_has_non_time_group_by": True,
            "required_outer_select_cross_join": True,
        }
    )
    sql = """
        WITH date_series AS (
            SELECT DATE_ADD(p.start_date, INTERVAL n DAY) AS dt
            FROM params p CROSS JOIN numbers n
        ), metrics AS (
            SELECT dt, region_code, COUNT(*) AS value
            FROM events
            GROUP BY dt, region_code
        )
        SELECT d.dt, m.region_code, COALESCE(m.value, 0)
        FROM date_series d
        LEFT JOIN metrics m ON m.dt = d.dt
    """

    violation = llm._data_skill_sql_validation_violation("每日各地区趋势", sql, data_skill)
    assert violation is not None
    assert violation.missing_required_patterns == ("outer SELECT CROSS JOIN",)


def test_consumed_date_generator_cross_join_is_not_a_dimension_scaffold() -> None:
    data_skill = _data_skill(
        {
            "when_sql_has_non_time_group_by": True,
            "required_outer_select_cross_join": True,
        }
    )
    sql = """
        WITH date_series AS (
            SELECT DATE_ADD(p.start_date, INTERVAL n.value DAY) AS dt, n.value AS offset_day
            FROM params p CROSS JOIN numbers n
        ), metrics AS (
            SELECT dt, region_code, COUNT(*) AS value
            FROM events
            GROUP BY dt, region_code
        )
        SELECT d.dt, m.region_code, COALESCE(m.value, 0)
        FROM date_series d
        LEFT JOIN metrics m ON m.dt = d.dt
    """

    violation = llm._data_skill_sql_validation_violation("每日各地区趋势", sql, data_skill)
    assert violation is not None
    assert violation.missing_required_patterns == ("outer SELECT CROSS JOIN",)


def test_outer_unrelated_cross_join_cannot_borrow_metric_dimension() -> None:
    data_skill = _data_skill(
        {
            "when_sql_has_non_time_group_by": True,
            "required_outer_select_cross_join": True,
        }
    )
    sql = """
        WITH metrics AS (
            SELECT dt, region_code, COUNT(*) AS value
            FROM events
            GROUP BY dt, region_code
        )
        SELECT d.dt, m.region_code, COALESCE(m.value, 0)
        FROM date_series d
        CROSS JOIN params p
        LEFT JOIN metrics m ON m.dt = d.dt
    """

    violation = llm._data_skill_sql_validation_violation("每日各地区趋势", sql, data_skill)
    assert violation is not None
    assert violation.missing_required_patterns == ("outer SELECT CROSS JOIN",)


def test_invalid_regular_expression_falls_back_to_case_insensitive_contains() -> None:
    data_skill = _data_skill(
        {
            "required_sql_patterns": ["legacy["],
            "forbidden_sql_patterns": ["blocked["],
        }
    )

    assert (
        llm._data_skill_sql_validation_violation("任意问题", "select LEGACY[ from t", data_skill)
        is None
    )
    violation = llm._data_skill_sql_validation_violation(
        "任意问题", "select blocked[ from t", data_skill
    )
    assert violation is not None
    assert violation.matched_forbidden_patterns == ("blocked[",)


def test_legacy_text_interface_formats_structured_violation() -> None:
    data_skill = _data_skill({"required_sql_contains": ["required_table"], "message": "旧接口消息"})

    assert (
        llm._data_skill_sql_validation_error("任意问题", "select 1", data_skill)
        == "旧接口消息"
    )
    assert llm._data_skill_sql_validation_error("任意问题", "select required_table", data_skill) is None


def test_check_sql_raises_shared_structured_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    service = llm.LLMService.__new__(llm.LLMService)
    service.current_logs = {OperationEnum.GENERATE_SQL: object()}
    service.dashboard_date_filter_enabled = False
    service.chat_question = SimpleNamespace(
        question="查询 DAU",
        data_skill=_data_skill({"match": "DAU", "required_sql_contains": ["fact_events"]}),
    )
    monkeypatch.setattr(llm, "_parse_sql_answer_data", lambda _: {"success": True, "sql": "select 1"})
    monkeypatch.setattr(llm, "trigger_log_error", lambda *_args: None)

    with pytest.raises(DataSkillSqlValidationError) as exc_info:
        service.check_sql(None, '{"success": true}', OperationEnum.GENERATE_SQL)

    error = exc_info.value
    assert error.violation is not None
    assert isinstance(error.violation, DataSkillSqlViolation)
    assert error.violation.rule_index == 0
    assert error.violation.missing_required_contains == ("fact_events",)
    assert str(error) == error.violation.message
    assert llm.DataSkillSqlValidationError is DataSkillSqlValidationError
