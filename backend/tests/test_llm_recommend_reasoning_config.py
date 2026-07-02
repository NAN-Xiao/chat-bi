from apps.ai_model.model_factory import LLMConfig
from apps.chat.task.llm import _disable_reasoning_for_recommendation


def _config(additional_params=None) -> LLMConfig:
    return LLMConfig(
        model_id=1,
        model_type="openai",
        model_name="qwen3.5-plus",
        api_key="test-key",
        api_base_url="https://example.test/v1",
        additional_params=additional_params or {},
    )


def test_disable_reasoning_adds_extra_body_when_missing():
    config = _config({"temperature": 0.6})

    _disable_reasoning_for_recommendation(config)

    assert config.additional_params["temperature"] == 0.6
    assert config.additional_params["extra_body"] == {"enable_thinking": False}


def test_disable_reasoning_adds_extra_body_to_empty_params():
    config = _config()

    _disable_reasoning_for_recommendation(config)

    assert config.additional_params["extra_body"] == {"enable_thinking": False}


def test_disable_reasoning_overrides_existing_enable_thinking():
    config = _config({"extra_body": {"enable_thinking": True}})

    _disable_reasoning_for_recommendation(config)

    assert config.additional_params["extra_body"]["enable_thinking"] is False


def test_disable_reasoning_preserves_other_extra_body_params():
    config = _config({"extra_body": {"foo": "bar", "enable_thinking": True}})

    _disable_reasoning_for_recommendation(config)

    assert config.additional_params["extra_body"] == {
        "foo": "bar",
        "enable_thinking": False,
    }
