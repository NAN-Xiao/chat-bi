"""验证分析助手生成 SQL 时会显式接收语义字段表达式。"""

from types import SimpleNamespace

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


def test_sql_repair_keeps_data_skill_when_tracking_context_is_large() -> None:
    """失败重试不能让长埋点上下文截断数据源专属 SQL 示例。"""
    class CaptureLLM:
        def __init__(self) -> None:
            self.messages = []

        def invoke(self, messages):
            self.messages = messages
            return SimpleNamespace(content='{"sql":"SELECT 1"}')

    llm = CaptureLLM()
    data_skill = "D7 规则\n" + "d" * 19000 + "\n## 七日留存 SQL 示例\nWITH bounds AS (...)"
    tracking_context = "埋点上下文\n" + "t" * 25000

    analysis_api._repair_sql(
        llm,
        question="近14天的七日留存趋势",
        raw_query={"title": "七日留存趋势", "purpose": "查看 D7 留存"},
        failed_sql="SELECT broken",
        error=ValueError("执行失败"),
        schema="",
        sample_data="",
        tracking_context=tracking_context,
        data_skill=data_skill,
    )

    prompt = llm.messages[-1].content
    assert "## 七日留存 SQL 示例" in prompt
    assert "工作空间数据字典/埋点方案" in prompt
    assert tracking_context[:12000] in prompt
    assert tracking_context[12000:] not in prompt
