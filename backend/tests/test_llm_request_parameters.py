"""通过真实 SDK 请求体回归各入口的模型参数，避免供应商参数污染请求。"""

import asyncio
import copy
import json
import sqlite3
from types import SimpleNamespace

import httpx
import pytest
from openai import BadRequestError

from apps.ai_model.model_factory import LLMConfig, LLMFactory, OpenAILLM
from apps.analysis_assistant.api import analysis_assistant
from apps.chat.api import chat as chat_api
from apps.chat.models.chat_model import ChatQuestion
from apps.chat.task import llm as chat_llm
from apps.dashboard.crud import ai_sql_generator


async def _surface_llm(surface, config, monkeypatch):
    async def load_config(model_id=None):
        assert model_id == 7
        return config

    if surface == "dashboard":
        monkeypatch.setattr(ai_sql_generator, "get_default_config", load_config)
        return await ai_sql_generator._create_dashboard_ai_sql_llm(7)
    if surface == "analysis_assistant":
        monkeypatch.setattr(analysis_assistant, "get_default_config", load_config)
        model, returned_config = await analysis_assistant._create_llm(7)
        assert returned_config == config
        return model

    user = SimpleNamespace(id=1001, tenant_id=2001, language="zh-CN")
    chat = SimpleNamespace(id=3001, create_by=1001, tenant_id=2001, datasource=None)
    session = SimpleNamespace(get=lambda *_args: chat)
    for name in ("list_generate_sql_logs", "list_generate_chart_logs"):
        monkeypatch.setattr(chat_llm, name, lambda **_kwargs: [])
    monkeypatch.setattr(chat_llm, "get_chat_brief_generate", lambda **_kwargs: False)
    monkeypatch.setattr(chat_llm, "get_last_execute_sql_error", lambda *_args: None)
    monkeypatch.setattr(chat_llm, "is_dashboard_date_filter_excluded", lambda *_args: False)

    if surface == "smart_qa":
        service = chat_llm.LLMService(session, user, ChatQuestion(chat_id=3001), config=config)
        return service.llm

    created = []

    async def create_service(*args, **kwargs):
        service = chat_llm.LLMService(*args, **kwargs, config=config)
        created.append(service)
        return service

    async def no_rate_limit(*_args):
        return None

    record = SimpleNamespace(id=4001, create_by=1001, chat_id=3001, question="测试问题")
    monkeypatch.setattr(chat_api, "_tenant_rate_limit_response", no_rate_limit)
    monkeypatch.setattr(chat_api, "get_chat_record_by_id", lambda *_args: record)
    monkeypatch.setattr(chat_llm.LLMService, "create", create_service)
    monkeypatch.setattr(chat_llm.LLMService, "set_record", lambda *_args: None)
    monkeypatch.setattr(chat_llm.LLMService, "run_recommend_questions_task_async", lambda *_args: None)
    monkeypatch.setattr(chat_llm.LLMService, "await_result", lambda *_args: iter(()))
    await chat_api.ask_recommend_questions(session, user, 4001, None)
    assert len(created) == 1, "推荐问题入口必须成功创建模型"
    return created[0].llm


@pytest.mark.parametrize("surface", ["dashboard", "analysis_assistant", "smart_qa", "recommendation"])
@pytest.mark.parametrize("params", [
    {},
    {"reasoning_effort": "low"},
    {"extra_body": {"enable_thinking": False}},
    {"temperature": 0.6, "top_p": 0.8, "extra_body": {"enable_thinking": True, "vendor_option": "value"}},
])
def test_model_requests_use_only_configured_parameters(surface, params, monkeypatch):
    original = copy.deepcopy(params)
    config = LLMConfig(model_id=7, model_type="openai", model_name="test-model",
                       api_base_url="https://model.test/v1", api_key="test-key",
                       additional_params=copy.deepcopy(params))
    requests = []

    def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        expected = {key: value for key, value in params.items() if key != "extra_body"}
        expected.update(params.get("extra_body", {}))
        # 像严格的模型服务一样拒绝未经声明的参数，不在异常后删除参数重试。
        for key in ("enable_thinking", "temperature", "top_p", "reasoning_effort", "vendor_option"):
            if key in body and key not in expected:
                return httpx.Response(400, json={"error": {"message": f"Unknown parameter: '{key}'."}})
            if key in expected:
                assert body[key] == expected[key]
        assert body["model"] == "test-model"
        return httpx.Response(200, json={
            "id": "test-completion", "object": "chat.completion", "created": 1, "model": "test-model",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": '{"success":true,"sql":"SELECT 1 AS result"}'}}],
        })

    async def run():
        with httpx.Client(transport=httpx.MockTransport(handle)) as sync_client:
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as async_client:
                def factory(received_config):
                    assert received_config == config
                    transport_config = received_config.model_copy(update={"additional_params": {
                        **received_config.additional_params,
                        "http_client": sync_client, "http_async_client": async_client,
                    }})
                    return OpenAILLM(transport_config)

                monkeypatch.setattr(LLMFactory, "create_llm", factory)
                model = await _surface_llm(surface, config, monkeypatch)
                result = await ai_sql_generator._async_invoke_llm_json(model, ["生成只读 SQL"])
                assert result.success
                with sqlite3.connect(":memory:") as db:
                    assert db.execute(result.sql).fetchall() == [(1,)]

    asyncio.run(run())
    assert len(requests) == 1
    assert config.additional_params == original


def test_explicit_invalid_parameter_is_reported_without_silent_retry(monkeypatch):
    config = LLMConfig(model_id=7, model_type="openai", model_name="test-model",
                       api_base_url="https://model.test/v1", api_key="test-key",
                       additional_params={"extra_body": {"enable_thinking": True}})
    requests = []

    def reject(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["enable_thinking"] is True
        return httpx.Response(400, json={"error": {
            "message": "Unknown parameter: 'enable_thinking'.", "type": "invalid_request_error"}})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(reject)) as client:
            monkeypatch.setattr(LLMFactory, "create_llm", lambda value: OpenAILLM(value.model_copy(
                update={"additional_params": {**value.additional_params, "http_async_client": client}})))
            model = await _surface_llm("dashboard", config, monkeypatch)
            with pytest.raises(BadRequestError, match="enable_thinking"):
                await ai_sql_generator._async_invoke_llm_json(model, ["生成 SQL"])

    asyncio.run(run())
    assert len(requests) == 1
