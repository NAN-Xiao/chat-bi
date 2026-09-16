import asyncio
from types import SimpleNamespace

from apps.ai_model.model_factory import LLMConfig, LLMFactory
from apps.chat.models.chat_model import ChatQuestion
from apps.chat.task import llm as chat_llm


def _config(model_name: str = "qwen3.5-plus", additional_params=None) -> LLMConfig:
    return LLMConfig(
        model_id=7,
        model_type="openai",
        model_name=model_name,
        api_key="test-key",
        api_base_url="https://model.test/v1",
        additional_params=additional_params or {},
    )


def _patch_service_context(monkeypatch, config: LLMConfig, captured: list[LLMConfig]):
    async def load_config(model_id=None):
        assert model_id is None
        return config

    async def load_chat_params(*_args, **_kwargs):
        return []

    user = SimpleNamespace(id=1001, tenant_id=2001, language="zh-CN")
    chat = SimpleNamespace(id=3001, create_by=1001, tenant_id=2001, datasource=None)
    monkeypatch.setattr(chat_llm, "get_default_config", load_config)
    monkeypatch.setattr(chat_llm, "get_groups", load_chat_params)
    monkeypatch.setattr(chat_llm, "list_generate_sql_logs", lambda **_kwargs: [])
    monkeypatch.setattr(chat_llm, "list_generate_chart_logs", lambda **_kwargs: [])
    monkeypatch.setattr(chat_llm, "get_chat_brief_generate", lambda **_kwargs: False)
    monkeypatch.setattr(chat_llm, "get_last_execute_sql_error", lambda *_args: None)
    monkeypatch.setattr(chat_llm, "is_dashboard_date_filter_excluded", lambda *_args: False)
    monkeypatch.setattr(
        LLMFactory,
        "create_llm",
        lambda received_config: captured.append(received_config) or SimpleNamespace(llm=object()),
    )
    return SimpleNamespace(get=lambda *_args: chat), user


def test_recommendation_mode_disables_qwen_thinking_without_mutating_default_config(monkeypatch):
    config = _config(additional_params={"temperature": 0.6})
    captured = []
    session, user = _patch_service_context(monkeypatch, config, captured)

    asyncio.run(
        chat_llm.LLMService.create(
            session,
            user,
            ChatQuestion(chat_id=3001),
            None,
            recommendation_mode=True,
        )
    )

    assert captured[0].additional_params == {
        "temperature": 0.6,
        "extra_body": {"enable_thinking": False},
    }
    assert config.additional_params == {"temperature": 0.6}


def test_recommendation_mode_preserves_other_vendor_parameters(monkeypatch):
    config = _config(
        additional_params={
            "temperature": 0.6,
            "extra_body": {"enable_thinking": True, "vendor_option": "value"},
        }
    )
    captured = []
    session, user = _patch_service_context(monkeypatch, config, captured)

    asyncio.run(
        chat_llm.LLMService.create(
            session,
            user,
            ChatQuestion(chat_id=3001),
            None,
            recommendation_mode=True,
        )
    )

    assert captured[0].additional_params["extra_body"] == {
        "enable_thinking": False,
        "vendor_option": "value",
    }


def test_recommendation_mode_does_not_inject_qwen_parameter_into_other_models(monkeypatch):
    config = _config(model_name="gpt-4.1", additional_params={"temperature": 0.6})
    captured = []
    session, user = _patch_service_context(monkeypatch, config, captured)

    asyncio.run(
        chat_llm.LLMService.create(
            session,
            user,
            ChatQuestion(chat_id=3001),
            None,
            recommendation_mode=True,
        )
    )

    assert captured[0].additional_params == {"temperature": 0.6}


def test_normal_smart_qa_keeps_qwen_thinking_configuration(monkeypatch):
    config = _config(
        additional_params={"extra_body": {"enable_thinking": True, "vendor_option": "value"}}
    )
    captured = []
    session, user = _patch_service_context(monkeypatch, config, captured)

    asyncio.run(
        chat_llm.LLMService.create(session, user, ChatQuestion(chat_id=3001), None)
    )

    assert captured[0] == config
