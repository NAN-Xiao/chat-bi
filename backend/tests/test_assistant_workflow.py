from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from apps.chat.task.assistant_workflow import (
    AssistantWorkflowConfig,
    emit_record_metadata,
    format_workflow_error,
    run_assistant_workflow,
)
from common.error import SingleMessageError


@contextmanager
def _fake_session_scope():
    """
    是什么：_fake_session_scope 是 backend/tests/test_assistant_workflow.py 中的同步测试函数。
    谁调用：由测试用例、测试夹具或被测代码在测试过程中调用。
    做了什么：围绕 _fake_session_scope 的语义处理测试场景相关逻辑，并把结果返回或写入状态。
    """
    yield object()


def _events(chunks: list[Any]) -> list[dict[str, Any]]:
    """
    是什么：_events 是 backend/tests/test_assistant_workflow.py 中的同步测试函数。
    谁调用：由测试用例、测试夹具或被测代码在测试过程中调用。
    做了什么：围绕 _events 的语义处理测试场景相关逻辑，并把结果返回或写入状态。
    """
    events: list[dict[str, Any]] = []
    for chunk in chunks:
        if isinstance(chunk, str) and chunk.startswith("data:"):
            events.append(json.loads(chunk[5:]))
    return events


class FakeWorkflowGraph:
    def __init__(self, chunks: list[Any] | None = None, error: BaseException | None = None) -> None:
        """
        是什么：FakeWorkflowGraph.__init__ 是 backend/tests/test_assistant_workflow.py 中的同步测试函数。
        谁调用：由测试用例、测试夹具或被测代码在测试过程中调用。
        做了什么：初始化实例属性、依赖对象和后续运行所需的基础状态。
        """
        self.chunks = chunks or []
        self.error = error
        self.initial_state: dict[str, Any] | None = None
        self.stream_mode: str | None = None

    def stream(self, initial_state: dict[str, Any], stream_mode: str):
        """
        是什么：FakeWorkflowGraph.stream 是 backend/tests/test_assistant_workflow.py 中的同步测试函数。
        谁调用：由测试用例、测试夹具或被测代码在测试过程中调用。
        做了什么：组织测试场景的流式输出或异步等待，把事件和结果传递给调用方。
        """
        self.initial_state = initial_state
        self.stream_mode = stream_mode
        if self.error is not None:
            raise self.error
        yield from self.chunks


class FakeWorkflowService:
    def __init__(self) -> None:
        """
        是什么：FakeWorkflowService.__init__ 是 backend/tests/test_assistant_workflow.py 中的同步测试函数。
        谁调用：由测试用例、测试夹具或被测代码在测试过程中调用。
        做了什么：初始化实例属性、依赖对象和后续运行所需的基础状态。
        """
        self.record = SimpleNamespace(
            id=1001,
            question="workflow question",
            regenerate_record_id=9988,
        )
        self.saved_errors: list[str] = []
        self.finished = False

    def get_record(self):
        """
        是什么：FakeWorkflowService.get_record 是 backend/tests/test_assistant_workflow.py 中的同步测试函数。
        谁调用：由测试用例、测试夹具或被测代码在测试过程中调用。
        做了什么：读取或查询测试场景相关数据，整理后返回给调用方。
        """
        return self.record

    def trans(self, key: str):
        """
        是什么：FakeWorkflowService.trans 是 backend/tests/test_assistant_workflow.py 中的同步测试函数。
        谁调用：由测试用例、测试夹具或被测代码在测试过程中调用。
        做了什么：围绕 trans 的语义处理测试场景相关逻辑，并把结果返回或写入状态。
        """
        return f"{key}: "

    def save_error(self, *, session, message: str):
        """
        是什么：FakeWorkflowService.save_error 是 backend/tests/test_assistant_workflow.py 中的同步测试函数。
        谁调用：由测试用例、测试夹具或被测代码在测试过程中调用。
        做了什么：创建、初始化或组装测试场景相关对象和数据，并返回或写入对应状态。
        """
        assert session is not None
        self.saved_errors.append(message)

    def finish(self, session):
        """
        是什么：FakeWorkflowService.finish 是 backend/tests/test_assistant_workflow.py 中的同步测试函数。
        谁调用：由测试用例、测试夹具或被测代码在测试过程中调用。
        做了什么：完成或关闭测试场景流程，释放资源并记录最终状态。
        """
        assert session is not None
        self.finished = True


CONFIG = AssistantWorkflowConfig("unit_workflow", "unit", "Unit Workflow")


def test_run_assistant_workflow_streams_chunks_and_finishes() -> None:
    """
    是什么：test_run_assistant_workflow_streams_chunks_and_finishes 是 backend/tests/test_assistant_workflow.py 中的同步测试函数。
    谁调用：由 pytest 测试运行器收集并执行。
    做了什么：构造测试场景的测试条件，断言实际结果符合预期。
    """
    service = FakeWorkflowService()
    graph = FakeWorkflowGraph(["chunk-a", {"chunk": "b"}])

    chunks = list(
        run_assistant_workflow(
            config=CONFIG,
            graph=graph,
            service=service,
            initial_state={
                "service": service,
                "in_chat": True,
                "stream": True,
                "json_result": {"success": True},
            },
            run_start_fields={"case": "success"},
            session_scope_factory=_fake_session_scope,
        )
    )

    assert chunks == ["chunk-a", {"chunk": "b"}]
    assert graph.stream_mode == "custom"
    assert graph.initial_state is not None
    assert graph.initial_state["graph_run_id"].startswith("unit-1001-")
    assert graph.initial_state["graph_trace"] == []
    assert service.finished is True
    assert service._unit_workflow_graph_failed_node is None
    assert service._unit_workflow_graph_error_type is None


def test_run_assistant_workflow_formats_single_message_errors() -> None:
    """
    是什么：test_run_assistant_workflow_formats_single_message_errors 是 backend/tests/test_assistant_workflow.py 中的同步测试函数。
    谁调用：由 pytest 测试运行器收集并执行。
    做了什么：构造测试场景的测试条件，断言实际结果符合预期。
    """
    service = FakeWorkflowService()
    graph = FakeWorkflowGraph(error=SingleMessageError("visible failure"))

    chunks = list(
        run_assistant_workflow(
            config=CONFIG,
            graph=graph,
            service=service,
            initial_state={
                "service": service,
                "in_chat": True,
                "stream": True,
                "json_result": {"success": True},
            },
            format_error=lambda error: format_workflow_error(
                error,
                service=service,
                log_prefix=CONFIG.log_prefix,
            ),
            session_scope_factory=_fake_session_scope,
        )
    )

    assert _events(chunks)[-1] == {"content": "visible failure", "type": "error"}
    assert service.saved_errors == ["visible failure"]
    assert service.finished is True
    assert service._unit_workflow_graph_error_type == "single_message"


def test_emit_record_metadata_for_smart_qa_shape(monkeypatch) -> None:
    """
    是什么：test_emit_record_metadata_for_smart_qa_shape 是 backend/tests/test_assistant_workflow.py 中的同步测试函数。
    谁调用：由 pytest 测试运行器收集并执行。
    做了什么：构造测试场景的测试条件，断言实际结果符合预期。
    """
    service = FakeWorkflowService()
    emitted: list[str] = []
    monkeypatch.setattr("apps.chat.task.assistant_workflow.emit", emitted.append)

    result = emit_record_metadata(
        {
            "service": service,
            "in_chat": True,
            "stream": True,
            "json_result": {"success": True},
        },
        include_question_in_chat=True,
        include_regenerate_id=True,
    )

    assert result["json_result"] == {"success": True}
    assert _events(emitted) == [
        {"type": "id", "id": 1001},
        {"type": "regenerate_record_id", "regenerate_record_id": 9988},
        {"type": "question", "question": "workflow question"},
    ]


def test_emit_record_metadata_for_chart_insight_shape(monkeypatch) -> None:
    """
    是什么：test_emit_record_metadata_for_chart_insight_shape 是 backend/tests/test_assistant_workflow.py 中的同步测试函数。
    谁调用：由 pytest 测试运行器收集并执行。
    做了什么：构造测试场景的测试条件，断言实际结果符合预期。
    """
    service = FakeWorkflowService()
    emitted: list[str] = []
    monkeypatch.setattr("apps.chat.task.assistant_workflow.emit", emitted.append)

    emit_record_metadata(
        {
            "service": service,
            "in_chat": True,
            "stream": True,
            "json_result": {"success": True},
        },
        include_question_in_chat=False,
        include_regenerate_id=False,
    )

    assert _events(emitted) == [{"type": "id", "id": 1001}]
