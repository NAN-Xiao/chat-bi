"""
验证 Data Skill SQL 校验的结构化违规对象和旧文本接口兼容性。
"""
from __future__ import annotations

from types import SimpleNamespace

import orjson
import pytest

from apps.chat.models.chat_model import OperationEnum
from apps.chat.task import llm
from apps.chat.task.sql_repair import DataSkillSqlValidationError, DataSkillSqlViolation


def _data_skill(*rules: dict) -> str:
    return "<!-- data-skill-sql-validation: " + orjson.dumps(list(rules)).decode() + " -->"


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
