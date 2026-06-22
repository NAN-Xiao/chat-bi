import os

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

os.environ["LOG_FORMAT"] = "%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s"

from apps.chat.curd import custom_prompt_manage
from apps.chat.curd.custom_prompt import (
    CustomPromptTargetScopeEnum,
    CustomPromptTypeEnum,
    CustomPromptVisibilityScopeEnum,
)
from apps.system.api import custom_prompt as custom_prompt_api


def _trans(key: str) -> str:
    return {
        "i18n_custom_prompt.ask_sql": "报表 SQL",
        "i18n_custom_prompt.data_analysis": "数据分析",
        "i18n_custom_prompt.data_prediction": "数据预测",
        "i18n_custom_prompt.target_scope_smart_qa": "智能报表",
        "i18n_custom_prompt.target_scope_analysis_assistant": "分析助手",
        "i18n_custom_prompt.target_scope_all": "全部",
    }.get(key, key)


def test_all_types_aliases_mean_no_type_filter():
    assert custom_prompt_api._parse_optional_type("ALL_TYPES") is None
    assert custom_prompt_api._parse_optional_type("ALL") is None
    assert custom_prompt_api._parse_optional_type("GENERATE_SQL") == CustomPromptTypeEnum.GENERATE_SQL


def test_management_query_supports_all_type_filters():
    stmt = custom_prompt_manage._build_query(
        None,
        custom_prompt_types=[CustomPromptTypeEnum.ANALYSIS],
        target_scopes=[CustomPromptTargetScopeEnum.ANALYSIS_ASSISTANT],
        visibility_scopes=[CustomPromptVisibilityScopeEnum.ADMIN_PUBLIC],
        active_values=[True],
    )

    sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

    assert "custom_prompt.type IN ('ANALYSIS')" in sql
    assert "custom_prompt.target_scope IN ('ANALYSIS_ASSISTANT')" in sql
    assert "custom_prompt.visibility_scope IN ('ADMIN_PUBLIC')" in sql
    assert "custom_prompt.active = true" in sql


def test_type_cell_strict_mode_rejects_invalid_or_blank_values():
    with pytest.raises(ValueError, match="Agent type is required"):
        custom_prompt_api._parse_type_cell("", _trans, required=True)

    with pytest.raises(ValueError, match="Unsupported custom prompt type"):
        custom_prompt_api._parse_type_cell("not a type", _trans, required=True)

    assert custom_prompt_api._parse_type_cell("数据分析", _trans, required=True) == CustomPromptTypeEnum.ANALYSIS


def test_target_scope_cell_rejects_invalid_values_but_keeps_blank_compatibility():
    with pytest.raises(ValueError, match="Unsupported custom prompt target scope"):
        custom_prompt_api._parse_target_scope_cell("not a scope", _trans)

    assert custom_prompt_api._parse_target_scope_cell("", _trans) == CustomPromptTargetScopeEnum.SMART_QA


def test_active_query_values_are_validated():
    assert custom_prompt_api._parse_active_values(["true", "0"]) == [True, False]

    with pytest.raises(HTTPException):
        custom_prompt_api._parse_active_values(["maybe"])


def test_query_value_split_keeps_enum_underscores():
    assert custom_prompt_api._split_query_values(["GENERATE_SQL", "SMART_QA,ANALYSIS_ASSISTANT"]) == [
        "GENERATE_SQL",
        "SMART_QA",
        "ANALYSIS_ASSISTANT",
    ]
