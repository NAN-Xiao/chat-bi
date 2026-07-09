"""
脚本说明：验证手动看板 AI SQL 生成器的模型响应解析和异步调用行为。
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import HumanMessage

from apps.ai_model.model_factory import LLMConfig
from apps.dashboard.crud import ai_sql_generator
from apps.dashboard.models.dashboard_model import DashboardAiSqlGenerateRequest


class _Chunk:
    def __init__(self, content: Any) -> None:
        self.content = content


class _AsyncInvokePreferredLlm:
    def __init__(self, content: str) -> None:
        self.content = content
        self.ainvoke_called = False

    def stream(self, _messages: list[Any]):
        raise AssertionError("async graph nodes must not call sync stream")

    async def astream(self, _messages: list[Any]):
        raise AssertionError("dashboard AI SQL generation must not call streaming astream")

    async def ainvoke(self, _messages: list[Any]):
        self.ainvoke_called = True
        return _Chunk(self.content)


class _SyncInvokeOnlyLlm:
    def __init__(self, content: str) -> None:
        self.content = content
        self.invoke_called = False

    def stream(self, _messages: list[Any]):
        raise AssertionError("dashboard AI SQL generation must not call streaming stream")

    def invoke(self, _messages: list[Any]):
        self.invoke_called = True
        return _Chunk(self.content)


def test_response_from_model_text_parses_string_false_as_failed() -> None:
    """
    是什么：LLM 把 success 返回成字符串 false 时不能误判为成功。
    """
    response = ai_sql_generator._response_from_model_text(
        '{"success":"false","sql":"select 1","message":"配置不完整"}',
    )

    assert response.success is False
    assert response.sql == "select 1"
    assert response.message == "配置不完整"


def test_text_chunk_content_skips_unknown_complex_list_items() -> None:
    """
    是什么：复杂 chunk 项没有文本字段时，不把对象 repr 拼进 JSON 文本。
    """
    content = ai_sql_generator._text_chunk_content([
        {"text": '{"success":true'},
        SimpleNamespace(value="repr should not leak"),
        {"content": ',"sql":"select 1"}'},
    ])

    assert "repr should not leak" not in content
    assert content == '{"success":true,"sql":"select 1"}'


def test_async_invoke_llm_json_uses_ainvoke_not_streaming() -> None:
    """
    是什么：异步图节点的 LLM 调用走 ainvoke，避免手动看板生成 SQL 使用流式输出。
    """
    llm = _AsyncInvokePreferredLlm('{"success":true,"sql":"select 1"}')

    response = asyncio.run(ai_sql_generator._async_invoke_llm_json(llm, [HumanMessage(content="生成 SQL")]))

    assert llm.ainvoke_called is True
    assert response.success is True
    assert response.sql == "select 1"


def test_invoke_llm_json_uses_invoke_not_streaming() -> None:
    """
    是什么：同步兜底调用也走 invoke，避免手动看板生成 SQL 使用流式输出。
    """
    llm = _SyncInvokeOnlyLlm('{"success":true,"sql":"select 1"}')

    response = ai_sql_generator._invoke_llm_json(llm, [HumanMessage(content="生成 SQL")])

    assert llm.invoke_called is True
    assert response.success is True
    assert response.sql == "select 1"


def test_create_dashboard_ai_sql_llm_disables_enable_thinking(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：手动看板三次 LLM 调用创建模型时，要统一关闭模型思考输出。
    """
    config = LLMConfig(
        model_id=7,
        model_type="openai",
        model_name="qwen3.5-plus",
        api_key="test-key",
        api_base_url="https://example.test/v1",
        additional_params={
            "temperature": 0.6,
            "extra_body": {"enable_thinking": True, "foo": "bar"},
        },
    )
    captured: dict[str, Any] = {}

    async def _fake_config(_model_id: int | None = None):
        return config

    def _fake_create_llm(updated_config: LLMConfig):
        captured["config"] = updated_config
        return SimpleNamespace(llm="fake-llm")

    monkeypatch.setattr(ai_sql_generator, "get_default_config", _fake_config)
    monkeypatch.setattr(ai_sql_generator.LLMFactory, "create_llm", _fake_create_llm)

    llm = asyncio.run(ai_sql_generator._create_dashboard_ai_sql_llm(7))

    assert llm == "fake-llm"
    assert captured["config"].additional_params["temperature"] == 0.6
    assert captured["config"].additional_params["extra_body"] == {
        "enable_thinking": False,
        "foo": "bar",
    }


def test_write_llm_output_debug_file_writes_jsonl(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：手动看板点击计算/生成时，LLM 原始输出要能落到 JSONL 文件便于排查。
    """
    output_file = tmp_path / "dashboard-ai-sql-llm-output.jsonl"
    monkeypatch.setattr(ai_sql_generator, "DASHBOARD_AI_SQL_LLM_OUTPUT_FILE", output_file)

    ai_sql_generator._write_llm_output_debug_file(
        node="generate_sql",
        full_text='{"success":true,"sql":"select 1"}',
        require_sql=True,
    )

    lines = output_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["node"] == "generate_sql"
    assert payload["require_sql"] is True
    assert payload["output"] == '{"success":true,"sql":"select 1"}'
    assert payload["created_at"]


def test_dashboard_prompt_describes_formula_metrics_contract() -> None:
    """
    是什么：手动图表 SQL 生成提示词必须明确公式指标结构和除零规则。
    """
    prompt = ai_sql_generator._dashboard_config_prompt(
        DashboardAiSqlGenerateRequest(
            datasource=1,
            intent="看转化率",
            chart_type="line",
            context={
                "metrics": [{"id": "m1", "alias": "注册人数"}, {"id": "m2", "alias": "登录人数"}],
                "formulaMetrics": [
                    {
                        "id": "f1",
                        "alias": "注册登录比",
                        "decimalPlaces": 2,
                        "tokens": [
                            {"type": "metric", "metricId": "m1", "metricAlias": "注册人数"},
                            {"type": "operator", "value": "/"},
                            {"type": "metric", "metricId": "m2", "metricAlias": "登录人数"},
                        ],
                    }
                ],
                "groups": [],
                "filters": {},
                "selectedFields": [],
            },
        ),
        datasource=SimpleNamespace(name="测试数据源", type="postgresql", type_name="PostgreSQL"),
        data_skill="",
        tracking_config="",
    )

    assert "formulaMetrics" in prompt
    assert "atomicMetric" in prompt
    assert "NULLIF" in prompt
    assert "ROUND" in prompt
    assert "外层 SELECT" in prompt


def test_dashboard_prompt_for_mysql_forbids_full_outer_join() -> None:
    """
    是什么：MySQL 数据源下手动图表 SQL 生成提示词要禁止生成 FULL OUTER JOIN。
    """
    prompt = ai_sql_generator._dashboard_config_prompt(
        DashboardAiSqlGenerateRequest(
            datasource=1,
            intent="看美国地区 ARPU",
            chart_type="table",
            context={
                "time": {"field": {"table": "event", "field": "dt"}, "grain": "day", "range": "30d"},
                "metrics": [{"alias": "后端充值"}, {"alias": "当日活跃"}],
                "formulaMetrics": [{"alias": "ARPU"}],
                "groups": [],
                "filters": {"logic": "and", "rules": [{"field": {"table": "event", "field": "country"}, "operator": "eq", "value": "US"}]},
                "selectedFields": [],
            },
        ),
        datasource=SimpleNamespace(name="测试数据源", type="mysql", type_name="MySQL"),
        data_skill="",
        tracking_config="",
        sql_dialect="mysql",
    )

    assert "FULL OUTER JOIN" in prompt
    assert "不能使用" in prompt
    assert "UNION" in prompt
    assert "条件聚合" in prompt


def test_dashboard_prompt_requires_tracking_event_prefilter_for_multiple_event_metrics() -> None:
    """
    是什么：多个事件类指标共用事件名字段时，提示词要要求先用 WHERE IN 收窄扫描范围。
    """
    prompt = ai_sql_generator._dashboard_config_prompt(
        DashboardAiSqlGenerateRequest(
            datasource=1,
            intent="看英雄养成事件",
            chart_type="table",
            context={
                "metrics": [
                    {
                        "alias": "英雄升星次数",
                        "field": {
                            "kind": "tracking-event",
                            "eventTable": "event",
                            "eventNameField": "event",
                            "eventName": "HeroStarUp",
                        },
                        "aggregation": "count",
                    },
                    {
                        "alias": "英雄升级次数",
                        "field": {
                            "kind": "tracking-event",
                            "eventTable": "event",
                            "eventNameField": "event",
                            "eventName": "HeroLevelUp",
                        },
                        "aggregation": "count",
                    },
                ],
                "groups": [],
                "filters": {},
                "selectedFields": [],
            },
        ),
        datasource=SimpleNamespace(name="测试数据源", type="mysql", type_name="MySQL"),
        data_skill="",
        tracking_config="",
    )

    assert "WHERE" in prompt
    assert "IN" in prompt
    assert "收窄扫描范围" in prompt


def test_dashboard_prompt_treats_event_metric_filters_as_optional() -> None:
    """
    是什么：事件指标没有筛选条件也是合法配置，不能要求每个事件都补筛选。
    """
    prompt = ai_sql_generator._dashboard_config_prompt(
        DashboardAiSqlGenerateRequest(
            datasource=1,
            intent="看 DAU",
            chart_type="line",
            context={
                "metrics": [],
                "formulaMetrics": [
                    {
                        "id": "f1",
                        "alias": "DAU",
                        "decimalPlaces": 2,
                        "tokens": [
                            {
                                "type": "atomicMetric",
                                "metric": {
                                    "field": {
                                        "kind": "tracking-event",
                                        "eventTable": "event",
                                        "eventNameField": "event",
                                        "eventName": "UserActive",
                                    },
                                    "aggregation": "count_distinct",
                                    "metric": {"table": "event", "field": "uid"},
                                    "filters": {"logic": "and", "rules": []},
                                },
                            }
                        ],
                    }
                ],
                "groups": [{"field": {"table": "event", "field": "country"}}],
                "filters": {},
                "selectedFields": [],
            },
        ),
        datasource=SimpleNamespace(name="测试数据源", type="mysql", type_name="MySQL"),
        data_skill="",
        tracking_config="",
    )

    assert "指标内筛选 rules 是可选配置" in prompt
    assert "没有 rules" in prompt
    assert "不要要求补筛选条件" in prompt
    assert "不要生成空 WHERE" in prompt


def test_dashboard_diagnosis_prompt_does_not_require_extra_event_filter() -> None:
    """
    是什么：诊断节点不能把事件指标的额外事件筛选条件当成必填项。
    """
    prompt = ai_sql_generator._dashboard_diagnosis_system_prompt()

    assert "事件指标自带事件名限定" in prompt
    assert "不要因为没有额外事件筛选条件" in prompt
    assert "success=false" in prompt


def test_dashboard_diagnosis_prompt_does_not_block_on_time_range_limit() -> None:
    """
    是什么：配置诊断不能把时间范围当成必须限定的阻断条件。
    """
    prompt = ai_sql_generator._dashboard_diagnosis_system_prompt()

    assert "时间范围只是查询窗口" in prompt
    assert "不能因为未配置时间范围" in prompt
    assert "success=false" in prompt


def test_tracking_event_filter_false_block_is_downgraded() -> None:
    """
    是什么：公式原子指标的 tracking-event 字段已经表达事件名时，诊断模型不能再因 filters 为空阻断。
    """
    request = DashboardAiSqlGenerateRequest(
        datasource=1,
        intent="看 ARPU 和 ARPPU",
        chart_type="line",
        context={
            "formulaMetrics": [
                {
                    "id": "arpu",
                    "alias": "ARPU",
                    "tokens": [
                        {
                            "type": "atomicMetric",
                            "metric": {
                                "field": "tracking-event:event.event:ServerPayLog",
                                "metric": "tracking-property:event.event:ServerPayLog:personal.money",
                                "aggregation": "sum",
                                "label": "后端充值.求和",
                                "filters": [],
                            },
                        },
                        {"type": "operator", "value": "/"},
                        {
                            "type": "atomicMetric",
                            "metric": {
                                "field": "tracking-event:event.event:UserActive",
                                "metric": "event.uid",
                                "aggregation": "count_distinct",
                                "label": "当日活跃.去重数",
                                "filters": [],
                            },
                        },
                    ],
                }
            ],
            "metrics": [],
            "groups": [],
            "filters": {},
            "selectedFields": [],
        },
    )
    response = ai_sql_generator.DashboardAiSqlGenerateResponse(
        success=False,
        message="原子指标未正确关联事件筛选。",
        issues=[
            "原子指标“后端充值.求和”未配置事件筛选条件，缺少“事件名 = ServerPayLog”的限定。",
            "原子指标“当日活跃.去重数”未配置事件筛选条件，缺少“事件名 = UserActive”的限定。",
            "计算指标中引用的原子指标别名显示错误，与实际业务含义不符。",
        ],
        suggestions=["建议检查指标别名。"],
    )

    fixed = ai_sql_generator._downgrade_tracking_event_filter_false_block(response, request)

    assert fixed.success is True
    assert fixed.sql == ""
    assert fixed.issues == []
    assert any("后端充值.求和" in suggestion for suggestion in fixed.suggestions)
    assert any("别名显示错误" in suggestion for suggestion in fixed.suggestions)


def test_tracking_event_filter_downgrade_keeps_real_blocking_issue() -> None:
    """
    是什么：如果除了隐式事件筛选误判外还存在真实缺失，诊断仍要保持阻断。
    """
    request = DashboardAiSqlGenerateRequest(
        datasource=1,
        intent="看 ARPU",
        chart_type="line",
        context={
            "formulaMetrics": [
                {
                    "id": "arpu",
                    "alias": "ARPU",
                    "tokens": [
                        {
                            "type": "atomicMetric",
                            "metric": {
                                "field": "tracking-event:event.event:ServerPayLog",
                                "metric": "tracking-property:event.event:ServerPayLog:personal.money",
                                "aggregation": "sum",
                                "label": "后端充值.求和",
                                "filters": [],
                            },
                        },
                    ],
                }
            ],
            "metrics": [],
            "groups": [],
            "filters": {},
            "selectedFields": [],
        },
    )
    response = ai_sql_generator.DashboardAiSqlGenerateResponse(
        success=False,
        issues=[
            "原子指标“后端充值.求和”未配置事件筛选条件，缺少“事件名 = ServerPayLog”的限定。",
            "计算指标缺少分母，无法表达 ARPU。",
        ],
    )

    fixed = ai_sql_generator._downgrade_tracking_event_filter_false_block(response, request)

    assert fixed.success is False
    assert fixed.issues == ["计算指标缺少分母，无法表达 ARPU。"]
    assert fixed.suggestions == [
        "原子指标“后端充值.求和”未配置事件筛选条件，缺少“事件名 = ServerPayLog”的限定。"
    ]


def test_tracking_event_selected_fields_detail_warning_does_not_block_sql_generation() -> None:
    """
    是什么：selectedFields 是配置器内部字段上下文，不应被诊断成表格展示维度并阻断生成。
    """
    request = DashboardAiSqlGenerateRequest(
        datasource=1,
        intent="看近 30 天 ARPU",
        chart_type="table",
        context={
            "formulaMetrics": [
                {
                    "id": "arpu",
                    "alias": "ARPU",
                    "tokens": [
                        {
                            "type": "atomicMetric",
                            "metric": {
                                "field": "tracking-event:event.event:ServerPayLog",
                                "metric": "tracking-property:event.event:ServerPayLog:personal.money",
                                "aggregation": "sum",
                                "label": "后端充值.求和",
                                "filters": [],
                            },
                        },
                        {"type": "operator", "value": "/"},
                        {
                            "type": "atomicMetric",
                            "metric": {
                                "field": "tracking-event:event.event:UserActive",
                                "metric": "event.uid",
                                "aggregation": "count_distinct",
                                "label": "当日活跃.去重数",
                                "filters": [],
                            },
                        },
                    ],
                }
            ],
            "metrics": [],
            "groups": [],
            "filters": {},
            "selectedFields": [
                {"value": "event.uid", "displayName": "用户 ID"},
                {"value": "tracking-event:event.event:ServerPayLog", "displayName": "ServerPayLog"},
                {"value": "tracking-event:event.event:UserActive", "displayName": "UserActive"},
            ],
        },
    )
    response = ai_sql_generator.DashboardAiSqlGenerateResponse(
        success=False,
        message="当前配置在表格中包含了高基数的明细字段，且分子分母事件筛选条件缺失。",
        issues=[
            "selectedFields 中包含 event.uid 及多个 tracking-event 类型字段（ServerPayLog, UserActive），这些作为维度会导致数据行数爆炸且破坏按日聚合逻辑。",
            "计算指标 arpu 的分子原子指标（后端充值）未配置事件筛选条件，未限定 event = 'ServerPayLog'。",
            "计算指标 arpu 的分母原子指标（当日活跃）未配置事件筛选条件，未限定 event = 'UserActive'。",
        ],
        suggestions=[],
    )

    fixed = ai_sql_generator._downgrade_tracking_event_filter_false_block(response, request)

    assert fixed.success is True
    assert fixed.issues == []
    assert any("selectedFields" in suggestion for suggestion in fixed.suggestions)
    assert any("ServerPayLog" in suggestion for suggestion in fixed.suggestions)
    assert any("UserActive" in suggestion for suggestion in fixed.suggestions)


def test_atomic_tracking_metric_does_not_require_metrics_list_entry() -> None:
    """
    是什么：公式内部 atomicMetric 是直接插入的基础聚合，不需要用户再手动添加同名分析指标。
    """
    request = DashboardAiSqlGenerateRequest(
        datasource=1,
        intent="看 ARPU 和 ARPPU",
        chart_type="table",
        context={
            "formulaMetrics": [
                {
                    "id": "arpu",
                    "alias": "ARPU",
                    "tokens": [
                        {
                            "type": "atomicMetric",
                            "metric": {
                                "field": "tracking-event:event.event:ServerPayLog",
                                "metric": "tracking-property:event.event:ServerPayLog:personal.money",
                                "aggregation": "sum",
                                "label": "后端充值.求和",
                                "filters": [],
                            },
                        },
                        {"type": "operator", "value": "/"},
                        {
                            "type": "atomicMetric",
                            "metric": {
                                "field": "tracking-event:event.event:UserActive",
                                "metric": "event.uid",
                                "aggregation": "count_distinct",
                                "label": "当日活跃.去重数",
                                "filters": [],
                            },
                        },
                    ],
                }
            ],
            "metrics": [],
            "groups": [],
            "filters": {},
            "selectedFields": [],
        },
    )
    response = ai_sql_generator.DashboardAiSqlGenerateResponse(
        success=False,
        message="ARPU/ARPPU 公式中的分子未正确关联到 ServerPayLog 事件的金额字段。",
        issues=[
            "计算指标 arpu/arppu 的分子原子指标虽然选了 ServerPayLog 事件，但其聚合字段配置为 tracking-property:event.event:ServerPayLog:personal.money，而在 metrics 列表中并未显式定义该基础指标，导致公式引用可能失效或逻辑混乱。",
            "计算指标 arpu 的分母原子指标选择了 UserActive 事件，但聚合字段配置为 event.uid，未在 metrics 中显式定义为“当日活跃去重数”基础指标。",
            "缺少明确的“后端充值总额”基础分析指标配置：应基于 ServerPayLog 事件，对 personal.money 字段求和。",
            "缺少明确的“当日活跃用户数”基础分析指标配置：应基于 UserActive 事件，对 uid 字段去重计数。",
        ],
    )

    fixed = ai_sql_generator._downgrade_tracking_event_filter_false_block(response, request)

    assert fixed.success is True
    assert fixed.issues == []
    assert any("metrics 列表" in suggestion for suggestion in fixed.suggestions)
    assert any("基础分析指标配置" in suggestion for suggestion in fixed.suggestions)


def test_tracking_event_filter_downgrade_handles_compact_event_equals_text() -> None:
    """
    是什么：诊断模型写成“事件=ServerPayLog/筛选限定”时，也要识别为 tracking-event 隐式事件限定误判。
    """
    request = DashboardAiSqlGenerateRequest(
        datasource=1,
        intent="看 ARPPU",
        chart_type="table",
        context={
            "formulaMetrics": [
                {
                    "id": "arppu",
                    "alias": "ARPPU",
                    "tokens": [
                        {
                            "type": "atomicMetric",
                            "metric": {
                                "field": "tracking-event:event.event:ServerPayLog",
                                "metric": "event.uid",
                                "aggregation": "count_distinct",
                                "label": "后端充值.去重数",
                                "filters": [],
                            },
                        }
                    ],
                }
            ],
            "metrics": [],
            "groups": [],
            "filters": {},
            "selectedFields": [],
        },
    )
    response = ai_sql_generator.DashboardAiSqlGenerateResponse(
        success=False,
        message="分母指标的筛选条件缺失导致逻辑错误。",
        advice="请为 ARPPU 的分母添加‘后端充值’事件筛选。",
        issues=[
            "ARPPU 计算公式的分母应为‘当日付费用户数’，但当前配置的原子指标仅选择了‘后端充值’事件下的 uid 去重，未在该指标内部添加‘事件=ServerPayLog’的筛选限定，导致分母可能统计错误。"
        ],
    )

    fixed = ai_sql_generator._downgrade_tracking_event_filter_false_block(response, request)

    assert fixed.success is True
    assert fixed.issues == []
    assert any("事件=ServerPayLog" in suggestion for suggestion in fixed.suggestions)


def test_global_dimension_filter_false_block_is_downgraded_for_formula_metrics() -> None:
    """
    是什么：同一事件明细表上的全局国家筛选是合法口径，诊断模型不能误判为分母被充值用户收窄。
    """
    request = DashboardAiSqlGenerateRequest(
        datasource=1,
        intent="看 US 近 30 天每日 ARPU",
        chart_type="table",
        context={
            "formulaMetrics": [
                {
                    "id": "arpu",
                    "alias": "ARPU",
                    "tokens": [
                        {
                            "type": "atomicMetric",
                            "metric": {
                                "field": "tracking-event:event.event:ServerPayLog",
                                "metric": "tracking-property:event.event:ServerPayLog:personal.money",
                                "aggregation": "sum",
                                "label": "后端充值.求和",
                                "filters": [],
                            },
                        },
                        {"type": "operator", "value": "/"},
                        {
                            "type": "atomicMetric",
                            "metric": {
                                "field": "tracking-event:event.event:UserActive",
                                "metric": "event.uid",
                                "aggregation": "count_distinct",
                                "label": "当日活跃.去重数",
                                "filters": [],
                            },
                        },
                    ],
                }
            ],
            "metrics": [],
            "groups": [],
            "filters": {
                "logic": "and",
                "rules": [
                    {
                        "field": {"table": "event", "field": "currentinfo.country", "displayName": "国家"},
                        "operator": "eq",
                        "value": "US",
                    }
                ],
            },
            "selectedFields": [],
        },
    )
    response = ai_sql_generator.DashboardAiSqlGenerateResponse(
        success=False,
        message="全局筛选条件错误地限制了分母指标。",
        advice="移除全局筛选中的国家限制，改为在计算指标的分子和分母原子指标中分别添加国家=US。",
        issues=[
            "全局筛选条件“国家=US”同时作用于分子（ServerPayLog）和分母（UserActive），导致分母被错误收窄为发生过充值的 US 用户中的活跃记录，违背 ARPU=总充值/全量活跃用户的业务口径。"
        ],
        suggestions=[
            "全局筛选：删除“国家”相关的筛选规则，保持全局无国家限制。",
        ],
    )

    fixed = ai_sql_generator._downgrade_tracking_event_filter_false_block(response, request)

    assert fixed.success is True
    assert fixed.issues == []
    assert fixed.message == "当前事件指标配置可以继续生成 SQL。"
    assert fixed.advice == ""
    assert any("全局筛选条件" in suggestion for suggestion in fixed.suggestions)


def test_dashboard_prompt_recommends_cte_layers_for_complex_analysis() -> None:
    """
    是什么：手动图表 SQL 生成提示词要把复杂分析优先引导为 CTE 分层结构。
    """
    prompt = ai_sql_generator._dashboard_sql_system_prompt() + "\n" + ai_sql_generator._dashboard_config_prompt(
        DashboardAiSqlGenerateRequest(
            datasource=1,
            intent="按渠道看新增留存",
            chart_type="table",
            context={
                "time": {"field": {"table": "users", "field": "created_at"}, "grain": "day", "range": "过去30天"},
                "metrics": [{"alias": "用户注册用户数", "aggregation": "count_distinct"}],
                "groups": [{"field": {"table": "users", "field": "channel"}}],
                "filters": {},
                "selectedFields": [],
            },
        ),
        datasource=SimpleNamespace(name="测试数据源", type="postgresql", type_name="PostgreSQL"),
        data_skill="",
        tracking_config="",
    )

    assert "复杂分析" in prompt
    assert "CTE" in prompt
    assert "bounds" in prompt
    assert "cohort" in prompt
    assert "behavior" in prompt
    assert "matched" in prompt
    assert "aggregated" in prompt
    assert "成熟窗口" in prompt


def test_understand_config_marks_fallback_when_llm_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：理解节点失败时，把降级状态写入 config_summary，供后续诊断感知。
    """

    async def _fake_config(_model_id: int | None = None):
        return LLMConfig(
            model_id=1,
            model_type="openai",
            model_name="qwen3.5-plus",
            api_key="test-key",
            api_base_url="https://example.test/v1",
            additional_params={},
        )

    def _raising_invoke(*_args: Any, **_kwargs: Any):
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(ai_sql_generator, "get_default_config", _fake_config)
    monkeypatch.setattr(ai_sql_generator.LLMFactory, "create_llm", lambda _config: SimpleNamespace(llm=object()))
    monkeypatch.setattr(ai_sql_generator, "_async_invoke_llm_json", _raising_invoke)

    result = asyncio.run(ai_sql_generator._async_node_understand_config({
        "request": DashboardAiSqlGenerateRequest(
            datasource=1,
            intent="看收入",
            chart_type="line",
            context={"metrics": [], "groups": [], "filters": {}, "selectedFields": []},
        ),
        "datasource": SimpleNamespace(name="测试数据源", type_name="PostgreSQL", type="pg"),
        "graph_trace": [],
    }))

    summary = result["config_summary"]
    assert summary["intent"] == "看收入"
    assert summary["understanding_failed"] is True
    assert summary["understanding_error"] == "LLM unavailable"


def test_collect_context_uses_business_sql_context_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：看板 AI 生成 SQL 前通过 SQL Engine 统一业务库上下文取 schema、字典和 Data Skill。
    """
    request = DashboardAiSqlGenerateRequest(
        datasource=1,
        intent="看登录人数",
        chart_type="line",
        context={"selectedFields": []},
    )
    datasource = SimpleNamespace(id=1, name="业务库", type="postgresql", type_name="PostgreSQL")
    business_context = SimpleNamespace(
        datasource=datasource,
        schema="【Schema】\n# Table: event",
        sql_dialect="postgres",
        allowed_tables=["event"],
        data_skill="<Data-Skills>口径</Data-Skills>",
        tracking_config="<Tracking>事件字典</Tracking>",
        skill_model_id=99,
        warnings=[],
        business_context_hash="ctx",
    )
    calls: list[dict[str, Any]] = []

    class _Session:
        def get(self, model, obj_id):
            if getattr(model, "__name__", "") == "CoreDatasource":
                return datasource
            return None

    def _build(**kwargs):
        calls.append(kwargs)
        return business_context

    monkeypatch.setattr(ai_sql_generator, "require_current_tenant_id", lambda _user: 2001)
    monkeypatch.setattr(ai_sql_generator.BusinessSqlContextService, "build", staticmethod(_build))

    result = ai_sql_generator._node_collect_context({
        "session": _Session(),
        "current_user": SimpleNamespace(id=1001, tenant_id=2001),
        "request": request,
        "graph_trace": [],
    })

    assert result["business_sql_context"] is business_context
    assert result["schema"] == business_context.schema
    assert result["sql_dialect"] == "postgres"
    assert result["allowed_tables"] == ["event"]
    assert result["data_skill"] == business_context.data_skill
    assert result["tracking_config"] == business_context.tracking_config
    assert calls[0]["tenant_id"] == 2001
    assert calls[0]["datasource_id"] == 1
    assert calls[0]["target_scope"] == ai_sql_generator.CustomPromptTargetScopeEnum.SMART_QA


def test_timed_graph_node_logs_sync_node_elapsed(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：同步 graph 节点执行完成后，要记录节点名、状态、耗时和请求上下文。
    """
    logs: list[str] = []

    monkeypatch.setattr(ai_sql_generator.AppLogUtil, "info", lambda message: logs.append(message))

    def _handler(_state: dict[str, Any]) -> dict[str, Any]:
        return {"result": "ok"}

    result = asyncio.run(ai_sql_generator._timed_graph_node(
        "collect_context",
        _handler,
        {
            "request": DashboardAiSqlGenerateRequest(datasource=3),
            "current_user": SimpleNamespace(id=1001, tenant_id=2001),
        },
    ))

    assert result == {"result": "ok"}
    assert len(logs) == 1
    assert "Dashboard manual chart graph node finished" in logs[0]
    assert "node=collect_context" in logs[0]
    assert "status=ok" in logs[0]
    assert "elapsed_ms=" in logs[0]
    assert "datasource_id=3" in logs[0]
    assert "tenant_id=2001" in logs[0]
    assert "user_id=1001" in logs[0]


def test_timed_graph_node_logs_async_node_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：异步 graph 节点异常时，也要记录失败状态和耗时，然后继续抛出原异常。
    """
    warnings: list[str] = []

    monkeypatch.setattr(ai_sql_generator.AppLogUtil, "warning", lambda message: warnings.append(message))

    async def _handler(_state: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("LLM unavailable")

    with pytest.raises(RuntimeError, match="LLM unavailable"):
        asyncio.run(ai_sql_generator._timed_graph_node(
            "diagnose_config",
            _handler,
            {
                "request": DashboardAiSqlGenerateRequest(datasource=3),
                "tenant_id": 2001,
                "current_user": SimpleNamespace(id=1001, tenant_id=2001),
            },
        ))

    assert len(warnings) == 1
    assert "Dashboard manual chart graph node failed" in warnings[0]
    assert "node=diagnose_config" in warnings[0]
    assert "status=error" in warnings[0]
    assert "elapsed_ms=" in warnings[0]
    assert "datasource_id=3" in warnings[0]
    assert "tenant_id=2001" in warnings[0]
    assert "user_id=1001" in warnings[0]
    assert "error=LLM unavailable" in warnings[0]
