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
