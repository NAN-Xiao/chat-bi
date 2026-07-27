"""验证分析助手生成 SQL 时会显式接收语义字段表达式。"""

from datetime import date
from types import SimpleNamespace

from apps.analysis_assistant.api import analysis_assistant as analysis_api
from apps.analysis_assistant.service.analysis_time_policy import (
    AnalysisTimeAnchor,
    AnalysisTimePolicy,
    AnalysisTimeResolution,
    AnalysisTimeSource,
)


def _resolved_time() -> AnalysisTimeResolution:
    policy = AnalysisTimePolicy(
        source=AnalysisTimeSource.DEFAULT_14_DAYS,
        window_days=14,
        anchor_date=date(2026, 7, 26),
        start_date=date(2026, 7, 13),
        end_date=date(2026, 7, 26),
        start_inclusive=True,
        end_inclusive=True,
        anchor=AnalysisTimeAnchor("fact_orders", "business_date"),
        description="最近 14 个自然日",
    )
    return AnalysisTimeResolution(policy=policy, status="resolved")


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


def test_all_sql_generation_prompts_require_backend_resolved_time_policy() -> None:
    """计划与预测必须返回时间字段元数据并服从后端常量边界。"""
    plan_prompts = (
        analysis_api.PLAN_PROMPT,
        analysis_api.FORECAST_PLAN_PROMPT,
    )

    for prompt in plan_prompts:
        assert "后端提供的时间策略是最终约束，不得重新解释或扩大" in prompt
        assert "具体日期常量" in prompt
        assert "不得使用动态 MAX(date)、bounds CTE 或 CROSS JOIN bounds" in prompt
        assert '每个 query 必须返回 time_fields 数组，元素格式为 {"table":"物理表名","field":"物理时间字段"}' in prompt
        assert "图表标题、分析说明和最终结论必须说明实际使用的时间范围" in prompt
        assert "WITH bounds AS (SELECT MAX" not in prompt


def test_sql_repair_prompt_only_requires_preserving_backend_time_bounds() -> None:
    """SQL 修复输出只能包含 SQL，不承担计划或回答元数据契约。"""
    prompt = analysis_api.SQL_REPAIR_PROMPT

    assert '"sql": "修正后的只读 SQL"' in prompt
    assert "后端提供的时间策略是最终约束，不得重新解释或扩大" in prompt
    assert "具体起止日期和包含关系" in prompt
    assert "不得使用动态 MAX(date)、bounds CTE 或 CROSS JOIN bounds" in prompt
    assert "time_fields" not in prompt
    assert "图表标题、分析说明和最终结论" not in prompt


def test_plan_prompt_receives_backend_resolved_constant_time_policy() -> None:
    class CaptureLLM:
        def __init__(self) -> None:
            self.messages = []

        def invoke(self, messages):
            self.messages = messages
            return SimpleNamespace(
                content=(
                    '{"intro":"分析","queries":[{"id":"q1","title":"趋势",'
                    '"purpose":"趋势","sql":"SELECT 1","time_fields":[]}]}'
                )
            )

    llm = CaptureLLM()
    request = analysis_api.AnalysisAssistantRequest(
        datasource_id=1,
        messages=[analysis_api.AnalysisAssistantMessage(role="user", content="分析收入")],
    )

    analysis_api._build_plan(
        llm,
        request,
        "",
        "",
        SimpleNamespace(name="测试", type="pg"),
        time_resolution=_resolved_time(),
    )

    prompt = llm.messages[-1].content
    assert "2026-07-13" in prompt
    assert "2026-07-26" in prompt
    assert "不得重新解释或扩大" in prompt
    assert "具体日期常量" in prompt


def test_forecast_plan_prompt_receives_same_backend_time_policy() -> None:
    class CaptureLLM:
        def __init__(self) -> None:
            self.messages = []

        def invoke(self, messages):
            self.messages = messages
            return SimpleNamespace(
                content=(
                    '{"intro":"预测","queries":[{"id":"q1","title":"预测趋势",'
                    '"purpose":"预测","sql":"SELECT 1","time_fields":[]}]}'
                )
            )

    llm = CaptureLLM()
    request = analysis_api.AnalysisAssistantRequest(
        datasource_id=1,
        messages=[analysis_api.AnalysisAssistantMessage(role="user", content="预测收入")],
    )

    analysis_api._build_forecast_plan(
        llm,
        request,
        "",
        "",
        SimpleNamespace(name="测试", type="pg"),
        time_resolution=_resolved_time(),
    )

    prompt = llm.messages[-1].content
    assert "2026-07-13" in prompt
    assert "2026-07-26" in prompt


def test_initial_outline_receives_backend_resolved_time_policy() -> None:
    request = analysis_api.AnalysisAssistantRequest(
        datasource_id=1,
        messages=[analysis_api.AnalysisAssistantMessage(role="user", content="分析收入")],
    )

    messages = analysis_api._initial_outline_messages(
        request,
        time_resolution=_resolved_time(),
    )

    prompt = messages[-1].content
    assert "2026-07-13" in prompt
    assert "2026-07-26" in prompt


def test_unresolved_time_policy_context_limits_plan_scope() -> None:
    context = analysis_api._time_policy_context(
        AnalysisTimeResolution(policy=None, status="unresolved")
    )

    assert "当前无法确认最大业务日期" in context
    assert "只生成能够明确证明时间边界的数据块" in context


def test_summary_and_final_answer_receive_backend_resolved_time_policy() -> None:
    class CaptureLLM:
        def __init__(self) -> None:
            self.messages = []

        def invoke(self, messages):
            self.messages = messages
            return SimpleNamespace(content="时间范围内收入稳定")

    llm = CaptureLLM()
    block = {
        "title": "收入趋势",
        "purpose": "查看收入",
        "sql": "SELECT 1",
        "fields": ["收入"],
        "data": [{"收入": 1}],
    }
    time_resolution = _resolved_time()

    analysis_api._summarise_block(
        llm,
        "分析收入",
        block,
        time_resolution=time_resolution,
    )
    summary_prompt = llm.messages[-1].content

    analysis_api._final_answer(
        llm,
        "分析收入",
        "分析收入趋势",
        [block],
        time_resolution=time_resolution,
    )
    final_prompt = llm.messages[-1].content

    for prompt in (summary_prompt, final_prompt):
        assert "2026-07-13" in prompt
        assert "2026-07-26" in prompt
        assert "不得重新解释或扩大" in prompt
        assert "必须说明实际使用的时间范围" in prompt
        assert "无适用时间字段时不得虚构时间过滤" in prompt


def test_empty_summary_reports_resolved_time_policy_without_calling_llm() -> None:
    class UnexpectedLLM:
        def invoke(self, _messages):
            raise AssertionError("空结果摘要不应调用 LLM")

    summary = analysis_api._summarise_block(
        UnexpectedLLM(),
        "分析收入",
        {"title": "收入趋势", "data": [], "time_fields": []},
        time_resolution=_resolved_time(),
    )

    assert summary.startswith("后端为本次分析确定的时间范围是")
    assert "2026-07-13（含）" in summary
    assert "2026-07-26（含）" in summary
    assert "没有返回数据" in summary
    assert "已添加时间过滤" not in summary


def test_empty_summary_reports_unresolved_time_policy_without_calling_llm() -> None:
    class UnexpectedLLM:
        def invoke(self, _messages):
            raise AssertionError("空结果摘要不应调用 LLM")

    summary = analysis_api._summarise_block(
        UnexpectedLLM(),
        "分析收入",
        {"title": "收入趋势", "data": []},
        time_resolution=AnalysisTimeResolution(policy=None, status="unresolved"),
    )

    assert "没有返回数据" in summary
    assert "无法确认时间边界" in summary
    assert "已添加时间过滤" not in summary


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
        time_resolution=_resolved_time(),
    )

    prompt = llm.messages[-1].content
    assert "## 七日留存 SQL 示例" in prompt
    assert "工作空间数据字典/埋点方案" in prompt
    assert tracking_context[:12000] in prompt
    assert tracking_context[12000:] not in prompt
    assert "2026-07-13" in prompt
    assert "2026-07-26" in prompt
