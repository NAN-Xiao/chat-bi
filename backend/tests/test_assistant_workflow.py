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
    yield object()


def _events(chunks: list[Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for chunk in chunks:
        if isinstance(chunk, str) and chunk.startswith("data:"):
            events.append(json.loads(chunk[5:]))
    return events


class FakeWorkflowGraph:
    def __init__(self, chunks: list[Any] | None = None, error: BaseException | None = None) -> None:
        self.chunks = chunks or []
        self.error = error
        self.initial_state: dict[str, Any] | None = None
        self.stream_mode: str | None = None

    def stream(self, initial_state: dict[str, Any], stream_mode: str):
        self.initial_state = initial_state
        self.stream_mode = stream_mode
        if self.error is not None:
            raise self.error
        yield from self.chunks


class FakeWorkflowService:
    def __init__(self) -> None:
        self.record = SimpleNamespace(
            id=1001,
            question="workflow question",
            regenerate_record_id=9988,
        )
        self.saved_errors: list[str] = []
        self.finished = False

    def get_record(self):
        return self.record

    def trans(self, key: str):
        return f"{key}: "

    def save_error(self, *, session, message: str):
        assert session is not None
        self.saved_errors.append(message)

    def finish(self, session):
        assert session is not None
        self.finished = True


CONFIG = AssistantWorkflowConfig("unit_workflow", "unit", "Unit Workflow")


def test_run_assistant_workflow_streams_chunks_and_finishes() -> None:
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
