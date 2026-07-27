"""验证分析助手生成 SQL 时会显式接收语义字段表达式。"""

from datetime import date
from types import SimpleNamespace

import pytest
from sqlglot import exp, parse_one

from apps.analysis_assistant.api import analysis_assistant as analysis_api
from apps.analysis_assistant.service.analysis_time_policy import (
    AnalysisTimeAnchor,
    AnalysisTimePolicy,
    AnalysisTimeResolution,
    AnalysisTimeSource,
)
from apps.analysis_assistant.service.analysis_time_sql import (
    AnalysisTimeSqlError,
    enforce_analysis_time_sql,
)

SCHEMA_TIME_FIELDS = {
    "fact_orders": ("business_date",),
    "fact_refunds": ("refund_date",),
}


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


def _enforce(
    sql: str, fields: list[dict[str, str]], *, rewrite: bool = False
) -> str:
    return enforce_analysis_time_sql(
        sql,
        policy=_resolved_time().policy,
        declared_time_fields=fields,
        schema_time_fields=SCHEMA_TIME_FIELDS,
        dialect="postgres",
        allow_rewrite=rewrite,
    )


def test_time_sql_accepts_exact_constant_bounds() -> None:
    sql = "SELECT business_date, SUM(amount) FROM fact_orders WHERE business_date >= DATE '2026-07-13' AND business_date <= DATE '2026-07-26' GROUP BY business_date"

    assert "2026-07-13" in _enforce(
        sql, [{"table": "fact_orders", "field": "business_date"}]
    )


def test_time_sql_rejects_dynamic_max_boundary() -> None:
    sql = "WITH bounds AS (SELECT MAX(business_date) end_date FROM fact_orders) SELECT * FROM fact_orders CROSS JOIN bounds WHERE business_date <= end_date"

    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        _enforce(sql, [{"table": "fact_orders", "field": "business_date"}])


def test_time_sql_rejects_conflicting_constant_range() -> None:
    sql = "SELECT * FROM fact_orders WHERE business_date >= DATE '2026-01-01' AND business_date <= DATE '2026-01-31'"

    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        _enforce(sql, [{"table": "fact_orders", "field": "business_date"}])


def test_time_sql_rewrites_only_one_unambiguous_target() -> None:
    rewritten = _enforce(
        "SELECT * FROM fact_orders",
        [{"table": "fact_orders", "field": "business_date"}],
        rewrite=True,
    )

    assert "2026-07-13" in rewritten
    assert "2026-07-26" in rewritten


def test_time_sql_requires_each_declared_fact_scan() -> None:
    sql = "SELECT * FROM fact_orders o JOIN fact_refunds r ON r.order_id = o.id WHERE o.business_date >= DATE '2026-07-13' AND o.business_date <= DATE '2026-07-26'"

    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        _enforce(
            sql,
            [
                {"table": "fact_orders", "field": "business_date"},
                {"table": "fact_refunds", "field": "refund_date"},
            ],
        )


def test_time_sql_does_not_choose_first_field_when_declaration_is_ambiguous() -> None:
    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        enforce_analysis_time_sql(
            "SELECT * FROM fact_orders",
            policy=_resolved_time().policy,
            declared_time_fields=[],
            schema_time_fields={"fact_orders": ("business_date", "created_at")},
            dialect="postgres",
            allow_rewrite=True,
        )


def test_time_sql_allows_dimension_query_without_temporal_fields() -> None:
    sql = enforce_analysis_time_sql(
        "SELECT region_id, region_name FROM dim_region",
        policy=_resolved_time().policy,
        declared_time_fields=[],
        schema_time_fields=SCHEMA_TIME_FIELDS,
        dialect="postgres",
        allow_rewrite=False,
    )

    assert "dim_region" in sql


def test_time_sql_ignores_irrelevant_declarations_for_dimension_query() -> None:
    sql = enforce_analysis_time_sql(
        "SELECT region_id, region_name FROM dim_region",
        policy=_resolved_time().policy,
        declared_time_fields=[{"table": "", "field": ""}],
        schema_time_fields=SCHEMA_TIME_FIELDS,
        dialect="postgres",
        allow_rewrite=False,
    )

    assert "dim_region" in sql


def test_time_sql_error_message_never_exposes_sql_or_fields() -> None:
    raw_sql = "SELECT * FROM fact_orders WHERE"

    with pytest.raises(AnalysisTimeSqlError) as caught:
        _enforce(
            raw_sql,
            [{"table": "fact_orders", "field": "business_date"}],
        )

    assert str(caught.value) == "时间边界校验未通过，当前分析角度未执行。"
    assert raw_sql not in str(caught.value)
    assert "business_date" not in str(caught.value)


def test_time_sql_accepts_qualified_alias_bounds() -> None:
    sql = "SELECT * FROM fact_orders AS Orders WHERE Orders.business_date >= DATE '2026-07-13' AND Orders.business_date <= DATE '2026-07-26'"

    assert "2026-07-26" in _enforce(
        sql, [{"table": "FACT_ORDERS", "field": "BUSINESS_DATE"}]
    )


def test_time_sql_rewrite_preserves_quoted_alias_identifier() -> None:
    rewritten = _enforce(
        'SELECT * FROM fact_orders AS "Orders"',
        [{"table": "fact_orders", "field": "business_date"}],
        rewrite=True,
    )
    where = parse_one(rewritten, read="postgres").args["where"]
    qualifiers = [column.args.get("table") for column in where.find_all(exp.Column)]

    assert qualifiers
    assert all(qualifier.name == "Orders" for qualifier in qualifiers)
    assert all(qualifier.args.get("quoted") is True for qualifier in qualifiers)


def test_time_sql_accepts_reversed_constant_comparisons() -> None:
    sql = "SELECT * FROM fact_orders o WHERE DATE '2026-07-13' <= o.business_date AND DATE '2026-07-26' >= o.business_date"

    assert "2026-07-13" in _enforce(
        sql, [{"table": "fact_orders", "field": "business_date"}]
    )


def test_time_sql_accepts_exact_between_bounds() -> None:
    sql = "SELECT * FROM fact_orders o WHERE o.business_date BETWEEN DATE '2026-07-13' AND DATE '2026-07-26'"

    assert "BETWEEN" in _enforce(
        sql, [{"table": "fact_orders", "field": "business_date"}]
    )


def test_time_sql_normalizes_qualified_table_without_losing_schema() -> None:
    rewritten = enforce_analysis_time_sql(
        "SELECT * FROM Analytics.Fact_Orders AS Orders",
        policy=_resolved_time().policy,
        declared_time_fields=[
            {"table": "analytics.fact_orders", "field": "business_date"}
        ],
        schema_time_fields={"ANALYTICS.FACT_ORDERS": ("BUSINESS_DATE",)},
        dialect="postgres",
        allow_rewrite=True,
    )

    assert "2026-07-13" in rewritten
    assert "2026-07-26" in rewritten


def test_time_sql_does_not_mix_same_table_name_from_different_schemas() -> None:
    sql = "SELECT * FROM analytics.fact_orders current_orders JOIN archive.fact_orders archived_orders ON archived_orders.id = current_orders.id WHERE current_orders.business_date >= DATE '2026-07-13' AND current_orders.business_date <= DATE '2026-07-26'"

    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        enforce_analysis_time_sql(
            sql,
            policy=_resolved_time().policy,
            declared_time_fields=[
                {"table": "analytics.fact_orders", "field": "business_date"},
                {"table": "archive.fact_orders", "field": "archived_date"},
            ],
            schema_time_fields={
                "analytics.fact_orders": ("business_date",),
                "archive.fact_orders": ("archived_date",),
            },
            dialect="postgres",
            allow_rewrite=False,
        )


def test_time_sql_rewrites_the_select_that_owns_the_unique_scan() -> None:
    rewritten = _enforce(
        "SELECT * FROM (SELECT * FROM fact_orders o) nested_orders",
        [{"table": "fact_orders", "field": "business_date"}],
        rewrite=True,
    )
    tree = parse_one(rewritten, read="postgres")
    inner_select = tree.find(exp.Subquery).this

    assert tree.args.get("where") is None
    assert isinstance(inner_select, exp.Select)
    assert inner_select.args.get("where") is not None


def test_time_sql_scopes_repeated_aliases_in_different_subqueries() -> None:
    sql = "SELECT * FROM (SELECT * FROM fact_orders o WHERE o.business_date >= DATE '2026-07-13' AND o.business_date <= DATE '2026-07-26') bounded JOIN (SELECT * FROM fact_orders o) unbounded ON TRUE"

    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        _enforce(
            sql,
            [{"table": "fact_orders", "field": "business_date"}],
            rewrite=False,
        )


def test_time_sql_rewrites_one_missing_repeated_alias_in_its_own_scope() -> None:
    sql = "SELECT * FROM (SELECT * FROM fact_orders o WHERE o.business_date >= DATE '2026-07-13' AND o.business_date <= DATE '2026-07-26') bounded JOIN (SELECT * FROM fact_orders o) unbounded ON TRUE"

    rewritten = _enforce(
        sql,
        [{"table": "fact_orders", "field": "business_date"}],
        rewrite=True,
    )

    assert rewritten.count("2026-07-13") == 2
    assert rewritten.count("2026-07-26") == 2


def test_time_sql_rewrite_adds_only_the_missing_partial_boundary() -> None:
    sql = "SELECT * FROM fact_orders o WHERE o.business_date >= DATE '2026-07-13'"

    rewritten = _enforce(
        sql,
        [{"table": "fact_orders", "field": "business_date"}],
        rewrite=True,
    )

    assert rewritten.count("2026-07-13") == 1
    assert rewritten.count("2026-07-26") == 1


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM fact_orders o WHERE o.business_date > DATE '2026-07-13'",
        "SELECT * FROM fact_orders o WHERE o.business_date >= DATE '2026-07-13' AND o.business_date <= CURRENT_DATE",
    ],
)
def test_time_sql_rewrite_rejects_existing_non_policy_boundaries(sql: str) -> None:
    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        _enforce(
            sql,
            [{"table": "fact_orders", "field": "business_date"}],
            rewrite=True,
        )


def test_time_sql_rejects_unqualified_same_named_fields_across_tables() -> None:
    sql = "SELECT * FROM fact_orders o JOIN fact_shipments s ON s.order_id = o.id WHERE business_date >= DATE '2026-07-13' AND business_date <= DATE '2026-07-26'"

    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        enforce_analysis_time_sql(
            sql,
            policy=_resolved_time().policy,
            declared_time_fields=[
                {"table": "fact_orders", "field": "business_date"},
                {"table": "fact_shipments", "field": "business_date"},
            ],
            schema_time_fields={
                "fact_orders": ("business_date",),
                "fact_shipments": ("business_date",),
            },
            dialect="postgres",
            allow_rewrite=False,
        )


def test_time_sql_rejects_duplicate_aliases_in_one_select_scope() -> None:
    sql = "SELECT * FROM fact_orders o JOIN fact_orders o ON o.parent_id = o.id WHERE o.business_date >= DATE '2026-07-13' AND o.business_date <= DATE '2026-07-26'"

    with pytest.raises(AnalysisTimeSqlError, match="时间边界校验未通过"):
        _enforce(
            sql,
            [{"table": "fact_orders", "field": "business_date"}],
            rewrite=False,
        )


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
