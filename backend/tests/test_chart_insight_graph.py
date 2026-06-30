from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest

from apps.chat.task import chart_insight_graph as graph
from apps.chat.task import llm
from common.error import SingleMessageError


@contextmanager
def _fake_session_scope():
    """
    是什么：_fake_session_scope 是 backend/tests/test_chart_insight_graph.py 中的同步测试函数。
    谁调用：由测试用例、测试夹具或被测代码在测试过程中调用。
    做了什么：围绕 _fake_session_scope 的语义处理测试场景相关逻辑，并把结果返回或写入状态。
    """
    yield object()


def _events(chunks: list[Any]) -> list[dict[str, Any]]:
    """
    是什么：_events 是 backend/tests/test_chart_insight_graph.py 中的同步测试函数。
    谁调用：由测试用例、测试夹具或被测代码在测试过程中调用。
    做了什么：围绕 _events 的语义处理测试场景相关逻辑，并把结果返回或写入状态。
    """
    events: list[dict[str, Any]] = []
    for chunk in chunks:
        if isinstance(chunk, str) and chunk.startswith("data:"):
            events.append(json.loads(chunk[5:]))
    return events


@pytest.fixture(autouse=True)
def _patch_graph_runtime(monkeypatch: pytest.MonkeyPatch):
    """
    是什么：_patch_graph_runtime 是 backend/tests/test_chart_insight_graph.py 中的同步测试函数。
    谁调用：由测试用例、测试夹具或被测代码在测试过程中调用。
    做了什么：围绕 _patch_graph_runtime 的语义处理测试场景相关逻辑，并把结果返回或写入状态。
    """
    monkeypatch.setattr(graph, "_session_scope", _fake_session_scope)


class FakeChartInsightService:
    def __init__(
        self,
        *,
        analysis_chunks: list[dict[str, str]] | None = None,
        predict_chunks: list[dict[str, str]] | None = None,
        predict_has_data: bool = True,
    ) -> None:
        """
        是什么：FakeChartInsightService.__init__ 是 backend/tests/test_chart_insight_graph.py 中的同步测试函数。
        谁调用：由测试用例、测试夹具或被测代码在测试过程中调用。
        做了什么：初始化实例属性、依赖对象和后续运行所需的基础状态。
        """
        self.record = SimpleNamespace(id=7001, chat_id=7000, question="chart question")
        self.analysis_chunks = analysis_chunks or [
            {"content": "A", "reasoning_content": "think A"},
            {"content": "B", "reasoning_content": ""},
        ]
        self.predict_chunks = predict_chunks or [
            {"content": '{"value": 2}', "reasoning_content": "predicting"},
        ]
        self.predict_has_data = predict_has_data
        self.predict_saved_text: str | None = None
        self.saved_errors: list[str] = []
        self.finished = False

    def get_record(self):
        """
        是什么：FakeChartInsightService.get_record 是 backend/tests/test_chart_insight_graph.py 中的同步测试函数。
        谁调用：由测试用例、测试夹具或被测代码在测试过程中调用。
        做了什么：读取或查询测试场景相关数据，整理后返回给调用方。
        """
        return self.record

    def trans(self, key: str):
        """
        是什么：FakeChartInsightService.trans 是 backend/tests/test_chart_insight_graph.py 中的同步测试函数。
        谁调用：由测试用例、测试夹具或被测代码在测试过程中调用。
        做了什么：围绕 trans 的语义处理测试场景相关逻辑，并把结果返回或写入状态。
        """
        return f"{key}: "

    def generate_analysis(self, session):
        """
        是什么：FakeChartInsightService.generate_analysis 是 backend/tests/test_chart_insight_graph.py 中的同步测试函数。
        谁调用：由测试用例、测试夹具或被测代码在测试过程中调用。
        做了什么：基于输入上下文生成测试场景相关结果，并保存或返回给调用方。
        """
        assert session is not None
        yield from self.analysis_chunks

    def generate_predict(self, session):
        """
        是什么：FakeChartInsightService.generate_predict 是 backend/tests/test_chart_insight_graph.py 中的同步测试函数。
        谁调用：由测试用例、测试夹具或被测代码在测试过程中调用。
        做了什么：基于输入上下文生成测试场景相关结果，并保存或返回给调用方。
        """
        assert session is not None
        yield from self.predict_chunks

    def check_save_predict_data(self, *, session, res: str) -> bool:
        """
        是什么：FakeChartInsightService.check_save_predict_data 是 backend/tests/test_chart_insight_graph.py 中的同步测试函数。
        谁调用：由测试用例、测试夹具或被测代码在测试过程中调用。
        做了什么：校验测试场景相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
        """
        assert session is not None
        self.predict_saved_text = res
        return self.predict_has_data

    def save_error(self, *, session, message: str):
        """
        是什么：FakeChartInsightService.save_error 是 backend/tests/test_chart_insight_graph.py 中的同步测试函数。
        谁调用：由测试用例、测试夹具或被测代码在测试过程中调用。
        做了什么：创建、初始化或组装测试场景相关对象和数据，并返回或写入对应状态。
        """
        assert session is not None
        self.saved_errors.append(message)

    def finish(self, session):
        """
        是什么：FakeChartInsightService.finish 是 backend/tests/test_chart_insight_graph.py 中的同步测试函数。
        谁调用：由测试用例、测试夹具或被测代码在测试过程中调用。
        做了什么：完成或关闭测试场景流程，释放资源并记录最终状态。
        """
        assert session is not None
        self.finished = True


def test_analysis_graph_streams_chat_events_and_trace() -> None:
    """
    是什么：test_analysis_graph_streams_chat_events_and_trace 是 backend/tests/test_chart_insight_graph.py 中的同步测试函数。
    谁调用：由 pytest 测试运行器收集并执行。
    做了什么：构造测试场景的测试条件，断言实际结果符合预期。
    """
    service = FakeChartInsightService()

    chunks = list(graph.run_chart_insight_graph(service, "analysis", in_chat=True, stream=True))
    events = _events(chunks)

    assert [event["type"] for event in events] == [
        "id",
        "analysis-result",
        "analysis-result",
        "info",
        "analysis_finish",
    ]
    assert events[1]["content"] == "A"
    assert events[1]["reasoning_content"] == "think A"
    assert service.finished is True
    assert service._chart_insight_graph_run_id.startswith("chartinsight-7001-")
    assert service._chart_insight_graph_failed_node is None
    assert service._chart_insight_graph_error_type is None
    assert [entry["node"] for entry in service._chart_insight_graph_trace] == [
        "emit_record_metadata",
        "generate_analysis",
    ]


def test_predict_graph_streams_chat_success_events() -> None:
    """
    是什么：test_predict_graph_streams_chat_success_events 是 backend/tests/test_chart_insight_graph.py 中的同步测试函数。
    谁调用：由 pytest 测试运行器收集并执行。
    做了什么：构造测试场景的测试条件，断言实际结果符合预期。
    """
    service = FakeChartInsightService(predict_has_data=True)

    chunks = list(graph.run_chart_insight_graph(service, "predict", in_chat=True, stream=True))
    events = _events(chunks)

    assert [event["type"] for event in events] == [
        "id",
        "predict-result",
        "info",
        "predict-success",
        "predict_finish",
    ]
    assert service.predict_saved_text == '{"value": 2}'
    assert service.finished is True
    assert [entry["node"] for entry in service._chart_insight_graph_trace] == [
        "emit_record_metadata",
        "generate_predict",
        "finalize_predict",
    ]


def test_predict_graph_non_stream_success_returns_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：test_predict_graph_non_stream_success_returns_json 是 backend/tests/test_chart_insight_graph.py 中的同步测试函数。
    谁调用：由 pytest 测试运行器收集并执行。
    做了什么：构造测试场景的测试条件，断言实际结果符合预期。
    """
    service = FakeChartInsightService(predict_has_data=True)
    origin_data = {"fields": ["value"], "data": [{"value": 1}]}
    predict_data = [{"value": 2}]

    monkeypatch.setattr(graph, "get_chat_chart_config", lambda session, record_id: {"type": "table"})
    monkeypatch.setattr(graph, "get_chat_chart_data", lambda session, record_id: origin_data)
    monkeypatch.setattr(graph, "get_chat_predict_data", lambda session, record_id: predict_data)

    chunks = list(graph.run_chart_insight_graph(service, "predict", in_chat=False, stream=False))

    assert chunks == [
        {
            "success": True,
            "record_id": 7001,
            "origin_data": origin_data,
            "predict_data": predict_data,
        },
    ]
    assert service.finished is True


def test_predict_graph_non_stream_failure_returns_message() -> None:
    """
    是什么：test_predict_graph_non_stream_failure_returns_message 是 backend/tests/test_chart_insight_graph.py 中的同步测试函数。
    谁调用：由 pytest 测试运行器收集并执行。
    做了什么：构造测试场景的测试条件，断言实际结果符合预期。
    """
    service = FakeChartInsightService(
        predict_chunks=[{"content": "cannot predict", "reasoning_content": ""}],
        predict_has_data=False,
    )

    chunks = list(graph.run_chart_insight_graph(service, "predict", in_chat=False, stream=False))

    assert chunks == [
        {
            "success": False,
            "record_id": 7001,
            "message": "cannot predict",
        },
    ]
    assert service.finished is True


def test_chart_insight_graph_saves_single_message_error() -> None:
    """
    是什么：test_chart_insight_graph_saves_single_message_error 是 backend/tests/test_chart_insight_graph.py 中的同步测试函数。
    谁调用：由 pytest 测试运行器收集并执行。
    做了什么：构造测试场景的测试条件，断言实际结果符合预期。
    """
    service = FakeChartInsightService()

    def _raise_analysis(session):
        """
        是什么：_raise_analysis 是 backend/tests/test_chart_insight_graph.py 中的同步测试函数。
        谁调用：由测试用例、测试夹具或被测代码在测试过程中调用。
        做了什么：围绕 _raise_analysis 的语义处理测试场景相关逻辑，并把结果返回或写入状态。
        """
        assert session is not None
        raise SingleMessageError("analysis failed")
        yield

    service.generate_analysis = _raise_analysis

    chunks = list(graph.run_chart_insight_graph(service, "analysis", in_chat=True, stream=True))
    events = _events(chunks)

    assert events[-1] == {"content": "analysis failed", "type": "error"}
    assert service.saved_errors == ["analysis failed"]
    assert service.finished is True
    assert service._chart_insight_graph_failed_node == "generate_analysis"
    assert service._chart_insight_graph_error_type == "single_message"
    assert service._chart_insight_graph_trace[-1]["status"] == "error"


def test_llm_service_routes_chart_insight_to_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    是什么：test_llm_service_routes_chart_insight_to_graph 是 backend/tests/test_chart_insight_graph.py 中的同步测试函数。
    谁调用：由 pytest 测试运行器收集并执行。
    做了什么：构造测试场景的测试条件，断言实际结果符合预期。
    """
    service = llm.LLMService.__new__(llm.LLMService)
    service.record = SimpleNamespace(id=8001)
    calls: list[dict[str, Any]] = []

    def _fake_graph(service_arg, *, action_type: str, in_chat: bool, stream: bool):
        """
        是什么：_fake_graph 是 backend/tests/test_chart_insight_graph.py 中的同步测试函数。
        谁调用：由测试用例、测试夹具或被测代码在测试过程中调用。
        做了什么：围绕 _fake_graph 的语义处理测试场景相关逻辑，并把结果返回或写入状态。
        """
        calls.append({"service": service_arg, "action_type": action_type, "in_chat": in_chat, "stream": stream})
        yield "graph-result"

    monkeypatch.setattr(graph, "run_chart_insight_graph", _fake_graph)

    assert list(service.run_analysis_or_predict_task("analysis", in_chat=False, stream=False)) == ["graph-result"]
    assert calls == [
        {
            "service": service,
            "action_type": "analysis",
            "in_chat": False,
            "stream": False,
        },
    ]
