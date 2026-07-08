"""
脚本说明：验证手动看板 AI SQL 生成器的模型响应解析和异步调用行为。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import HumanMessage

from apps.dashboard.crud import ai_sql_generator
from apps.dashboard.models.dashboard_model import DashboardAiSqlGenerateRequest


class _Chunk:
    def __init__(self, content: Any) -> None:
        self.content = content


class _AsyncStreamOnlyLlm:
    def __init__(self, content: str) -> None:
        self.content = content
        self.astream_called = False

    def stream(self, _messages: list[Any]):
        raise AssertionError("async graph nodes must not call sync stream")

    async def astream(self, _messages: list[Any]):
        self.astream_called = True
        yield _Chunk(self.content)


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


def test_async_invoke_llm_json_uses_astream_not_sync_stream() -> None:
    """
    是什么：异步图节点的 LLM 调用走 astream，避免直接阻塞事件循环。
    """
    llm = _AsyncStreamOnlyLlm('{"success":true,"sql":"select 1"}')

    response = asyncio.run(ai_sql_generator._async_invoke_llm_json(llm, [HumanMessage(content="生成 SQL")]))

    assert llm.astream_called is True
    assert response.success is True
    assert response.sql == "select 1"


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
        return SimpleNamespace()

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
