"""验证分析助手生成 SQL 时会显式接收语义字段表达式。"""

from apps.analysis_assistant.api import analysis_assistant as analysis_api


def test_sql_generation_semantic_mappings_preserve_json_expression() -> None:
    """JSON 子字段必须在生成 SQL 前以可执行表达式提供给模型。"""
    schema = """
# Table: user
[
(remain:json, 用户留存标记 JSON),
(remain.remain7:boolean_flag, 注册后第 7 日留存标记; role=json_path_flag; source=remain; json_path=$.remain7; expression=JSON_UNQUOTE(JSON_EXTRACT(`user`.`remain`, '$.remain7')); SQL must use expression instead of this dictionary field name)
]
"""

    mappings = analysis_api._sql_generation_semantic_mappings(schema)

    assert "逻辑字段：remain.remain7" in mappings
    assert "SQL 表达式：JSON_UNQUOTE(JSON_EXTRACT(`user`.`remain`, '$.remain7'))" in mappings
    assert "不得把 JSON 子字段末段 remain7 当作物理列" in mappings


def test_all_sql_generation_prompts_require_aggregate_bounds_outside_where() -> None:
    """所有 SQL 生成链路都必须引导模型先计算聚合边界再筛选。"""
    prompts = (
        analysis_api.PLAN_PROMPT,
        analysis_api.FORECAST_PLAN_PROMPT,
        analysis_api.SQL_REPAIR_PROMPT,
    )

    for prompt in prompts:
        assert "聚合函数或窗口函数不得出现在同一查询层级的 WHERE" in prompt
        assert "WITH bounds AS" in prompt
        assert "FROM source_table" in prompt
