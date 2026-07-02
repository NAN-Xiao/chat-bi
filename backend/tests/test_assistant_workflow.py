"""
脚本说明：这个脚本是测试文件，用来验证对应功能在常见情况下能按预期工作。
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

from apps.chat.task.assistant_workflow import (
    AssistantWorkflowConfig,
    classify_workflow_error,
    emit_record_metadata,
    format_workflow_error,
    run_assistant_workflow,
)
from common.error import AppDBError, DataUnavailableError, SingleMessageError
from common.user_facing_errors import DATA_UNAVAILABLE_ERROR_TYPE


@contextmanager
def _fake_session_scope():
    """
    是什么：_fake_session_scope 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：测试代码会调用它，用来准备数据或检查结果。
    做了什么：把测试里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    yield object()


def _events(chunks: list[Any]) -> list[dict[str, Any]]:
    """
    是什么：_events 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：测试代码会调用它，用来准备数据或检查结果。
    做了什么：把测试里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    events: list[dict[str, Any]] = []
    for chunk in chunks:
        if isinstance(chunk, str) and chunk.startswith("data:"):
            events.append(json.loads(chunk[5:]))
    return events


class FakeWorkflowGraph:
    """
    类说明：FakeWorkflowGraph 把测试相关的数据和行为放在一起，便于其他代码直接复用。
    """
    def __init__(self, chunks: list[Any] | None = None, error: BaseException | None = None) -> None:
        """
        是什么：FakeWorkflowGraph.__init__ 是 FakeWorkflowGraph 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把这个对象刚创建时需要的信息先放好。
        """
        self.chunks = chunks or []
        self.error = error
        self.initial_state: dict[str, Any] | None = None
        self.stream_mode: str | None = None

    def stream(self, initial_state: dict[str, Any], stream_mode: str):
        """
        是什么：FakeWorkflowGraph.stream 是 FakeWorkflowGraph 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试处理过程中的消息或结果一段段传出去。
        """
        self.initial_state = initial_state
        self.stream_mode = stream_mode
        if self.error is not None:
            raise self.error
        yield from self.chunks


class FakeWorkflowService:
    """
    类说明：FakeWorkflowService 把测试的一组操作放在一起，对外提供更容易调用的业务能力。
    """
    def __init__(self) -> None:
        """
        是什么：FakeWorkflowService.__init__ 是 FakeWorkflowService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把这个对象刚创建时需要的信息先放好。
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
        是什么：FakeWorkflowService.get_record 是 FakeWorkflowService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试需要的数据找出来，整理成后面好用的样子。
        """
        return self.record

    def trans(self, key: str):
        """
        是什么：FakeWorkflowService.trans 是 FakeWorkflowService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        return f"{key}: "

    def save_error(self, *, session, message: str):
        """
        是什么：FakeWorkflowService.save_error 是 FakeWorkflowService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：创建或保存测试需要的东西，让后续流程能继续往下走。
        """
        assert session is not None
        self.saved_errors.append(message)

    def finish(self, session):
        """
        是什么：FakeWorkflowService.finish 是 FakeWorkflowService 里的一个步骤，帮它完成测试相关的一件事。
        谁调用：测试代码会调用它，用来准备数据或检查结果。
        做了什么：把测试这次处理做收尾，记录结果并关掉不再需要的资源。
        """
        assert session is not None
        self.finished = True


CONFIG = AssistantWorkflowConfig("unit_workflow", "unit", "Unit Workflow")


def test_run_assistant_workflow_streams_chunks_and_finishes() -> None:
    """
    是什么：test_run_assistant_workflow_streams_chunks_and_finishes 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
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
    是什么：test_run_assistant_workflow_formats_single_message_errors 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
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


def test_format_workflow_error_keeps_sql_exec_detail() -> None:
    """
    是什么：真正 SQL 执行失败应继续保留查看详情所需的 traceback。
    """
    service = FakeWorkflowService()

    payload = json.loads(
        format_workflow_error(
            AppDBError("database timeout"),
            service=service,
            log_prefix=CONFIG.log_prefix,
            include_db_error_types=True,
        )
    )

    assert payload["type"] == "exec-sql-err"
    assert payload["message"] == "Execute SQL Failed"
    assert payload["traceback"] == "database timeout"


def test_format_workflow_error_data_unavailable_is_business_payload() -> None:
    """
    是什么：缺表/缺字段/缺埋点属于业务提示，不应携带 traceback。
    """
    service = FakeWorkflowService()
    message = "当前数据源缺少本次问题所需的表、字段或埋点数据。"

    payload = json.loads(
        format_workflow_error(
            DataUnavailableError(message),
            service=service,
            log_prefix=CONFIG.log_prefix,
            include_db_error_types=True,
        )
    )

    assert payload["error_type"] == DATA_UNAVAILABLE_ERROR_TYPE
    assert payload["type"] == DATA_UNAVAILABLE_ERROR_TYPE
    assert payload["message"] == message
    assert "traceback" not in payload


def test_classify_workflow_error_data_unavailable() -> None:
    """
    是什么：工作流日志也应把数据不可用归到标准类型。
    """
    assert classify_workflow_error(DataUnavailableError("缺少埋点")) == DATA_UNAVAILABLE_ERROR_TYPE
    assert (
        classify_workflow_error(SingleMessageError("当前数据库 Schema 中不存在 fact_sessions 表"))
        == DATA_UNAVAILABLE_ERROR_TYPE
    )


def test_run_assistant_workflow_formats_data_unavailable_as_structured_error() -> None:
    """
    是什么：兜底工作流遇到数据不可用时，保存结构化业务错误，前端不展示详情按钮。
    """
    service = FakeWorkflowService()
    message = "当前数据源缺少本次问题所需的表、字段或埋点数据。"
    graph = FakeWorkflowGraph(error=DataUnavailableError(message))

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
                include_db_error_types=True,
            ),
            session_scope_factory=_fake_session_scope,
        )
    )

    error_event = _events(chunks)[-1]
    payload = json.loads(error_event["content"])

    assert payload["error_type"] == DATA_UNAVAILABLE_ERROR_TYPE
    assert payload["message"] == message
    assert "traceback" not in payload
    assert service.saved_errors == [error_event["content"]]
    assert service.finished is True
    assert service._unit_workflow_graph_error_type == DATA_UNAVAILABLE_ERROR_TYPE


def test_emit_record_metadata_for_smart_qa_shape(monkeypatch) -> None:
    """
    是什么：test_emit_record_metadata_for_smart_qa_shape 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
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
    是什么：test_emit_record_metadata_for_chart_insight_shape 是一段测试代码，用来确认测试的某个场景没有问题。
    谁调用：跑测试时 pytest 会找到并执行它。
    做了什么：准备一个具体场景，然后检查结果是不是和预期一样。
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
