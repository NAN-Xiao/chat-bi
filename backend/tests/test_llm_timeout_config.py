import json
from types import SimpleNamespace

from apps.chat.task import llm as llm_module
from apps.chat.task.llm import LLMService
from common.core.config import Settings


def test_model_engine_label_omits_datasource_server_version():
    datasource = SimpleNamespace(type="mysql", type_name="MySQL")

    assert llm_module.model_engine_label(datasource) == "MySQL"


def test_llm_timeout_defaults_are_decoupled(monkeypatch):
    monkeypatch.delenv("LLM_REQUEST_TIMEOUT", raising=False)
    monkeypatch.delenv("LLM_TASK_MAX_WAIT_SECONDS", raising=False)

    timeout_settings = Settings(_env_file=None)

    assert timeout_settings.LLM_REQUEST_TIMEOUT == 120
    assert timeout_settings.LLM_TASK_MAX_WAIT_SECONDS == 900


def test_llm_timeout_values_support_environment_overrides(monkeypatch):
    monkeypatch.setenv("LLM_REQUEST_TIMEOUT", "150")
    monkeypatch.setenv("LLM_TASK_MAX_WAIT_SECONDS", "600")

    timeout_settings = Settings(_env_file=None)

    assert timeout_settings.LLM_REQUEST_TIMEOUT == 150
    assert timeout_settings.LLM_TASK_MAX_WAIT_SECONDS == 600


def test_await_result_uses_independent_task_max_wait(monkeypatch):
    service = object.__new__(LLMService)
    service.stream_keepalive_enabled = True
    service.future = type("Future", (), {"cancel": lambda self: None})()
    service.record = type("Record", (), {"id": 1})()
    service.is_running = lambda: True
    service.pop_chunk = lambda: None

    monotonic_values = iter((0.0, 10.0))
    monkeypatch.setattr(llm_module.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(llm_module.settings, "LLM_REQUEST_TIMEOUT", 1)
    monkeypatch.setattr(llm_module.settings, "LLM_TASK_MAX_WAIT_SECONDS", 5, raising=False)

    chunk = next(service.await_result())
    payload = json.loads(chunk.removeprefix("data:").strip())

    assert payload["type"] == "error"
    assert "请求超时" in payload["content"]
