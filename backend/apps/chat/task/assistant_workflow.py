"""
脚本说明：这个脚本放聊天问数据和 Agent里较长或较复杂的处理流程，把一次任务分成可维护的步骤。
"""
from __future__ import annotations

import time
import traceback
import uuid
from collections.abc import Callable, Iterator, MutableMapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import orjson
from sqlmodel import Session

from apps.chat.task.assistant_output import emit, sse
from apps.datasource.crud.permission_errors import PERMISSION_DENIED_ERROR_TYPE
from common.error import AppDBConnectionError, AppDBError, DataUnavailableError, SingleMessageError
from common.user_facing_errors import (
    DATA_UNAVAILABLE_ERROR_TYPE,
    classify_error,
    data_unavailable_error_payload,
    looks_like_data_unavailable_business_message,
)
from common.utils.utils import AppLogUtil

WorkflowState = MutableMapping[str, Any]
WorkflowNode = Callable[[Any], dict[str, Any]]
WorkflowErrorFormatter = Callable[[BaseException], str]


@dataclass(frozen=True)
class AssistantWorkflowConfig:
    """
    类说明：AssistantWorkflowConfig 放聊天问数据和 Agent的配置项，让后续流程能按同一套规则运行。
    """
    workflow_key: str
    run_id_prefix: str
    log_prefix: str


def record_id(service: Any) -> Any:
    """
    是什么：record_id 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return getattr(getattr(service, "record", None), "id", None)


def workflow_attr(workflow_key: str, name: str) -> str:
    """
    是什么：workflow_attr 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return f"_{workflow_key}_graph_{name}"


def new_workflow_run_id(service: Any, run_id_prefix: str) -> str:
    """
    是什么：new_workflow_run_id 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存聊天问数据和 Agent需要的东西，让后续流程能继续往下走。
    """
    current_record_id = record_id(service)
    record_part = str(current_record_id) if current_record_id is not None else "unknown"
    return f"{run_id_prefix}-{record_part}-{uuid.uuid4().hex[:12]}"


def init_workflow_run(service: Any, workflow_key: str, run_id_prefix: str) -> str:
    """
    是什么：init_workflow_run 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存聊天问数据和 Agent需要的东西，让后续流程能继续往下走。
    """
    run_id = new_workflow_run_id(service, run_id_prefix)
    setattr(service, workflow_attr(workflow_key, "run_id"), run_id)
    setattr(service, workflow_attr(workflow_key, "trace"), [])
    setattr(service, workflow_attr(workflow_key, "failed_node"), None)
    setattr(service, workflow_attr(workflow_key, "error_type"), None)
    return run_id


def classify_workflow_error(error: BaseException) -> str:
    """
    是什么：classify_workflow_error 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    if isinstance(error, DataUnavailableError):
        return DATA_UNAVAILABLE_ERROR_TYPE
    if isinstance(error, SingleMessageError) and looks_like_data_unavailable_business_message(str(error)):
        return DATA_UNAVAILABLE_ERROR_TYPE
    if isinstance(error, SingleMessageError):
        return "single_message"
    if isinstance(error, AppDBConnectionError):
        return "db_connection"
    if isinstance(error, AppDBError):
        return "exec_sql"
    classified = classify_error(error).error_type
    if classified in {DATA_UNAVAILABLE_ERROR_TYPE, PERMISSION_DENIED_ERROR_TYPE}:
        return classified
    return "unexpected"


def log_workflow_event(
    service: Any,
    *,
    workflow_key: str,
    log_prefix: str,
    run_id: str,
    event: str,
    node: str | None = None,
    **extra: Any,
) -> None:
    """
    是什么：log_workflow_event 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    payload: dict[str, Any] = {
        "workflow": workflow_key,
        "event": event,
        "run_id": run_id,
        "record_id": record_id(service),
    }
    if node:
        payload["node"] = node
    payload.update(extra)
    AppLogUtil.info(log_prefix + " " + orjson.dumps(payload, default=str).decode())


def append_workflow_trace(
    state: WorkflowState,
    workflow_key: str,
    entry: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    是什么：append_workflow_trace 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    service = state["service"]
    existing_trace = state.get("graph_trace")
    if existing_trace is None:
        existing_trace = getattr(service, workflow_attr(workflow_key, "trace"), [])
    trace = [*existing_trace, entry]
    setattr(service, workflow_attr(workflow_key, "trace"), trace)
    return trace


def observe_workflow_node(
    *,
    workflow_key: str,
    run_id_prefix: str,
    log_prefix: str,
    node: str,
    handler: WorkflowNode,
) -> WorkflowNode:
    """
    是什么：observe_workflow_node 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    def _wrapped(state: WorkflowState) -> dict[str, Any]:
        """
        是什么：_wrapped 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
        谁调用：外层函数 observe_workflow_node 跑到对应步骤时会调用它。
        做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
        """
        service = state["service"]
        run_id = (
            state.get("graph_run_id")
            or getattr(service, workflow_attr(workflow_key, "run_id"), None)
            or new_workflow_run_id(service, run_id_prefix)
        )
        setattr(service, workflow_attr(workflow_key, "run_id"), run_id)
        started_at = time.perf_counter()
        log_workflow_event(
            service,
            workflow_key=workflow_key,
            log_prefix=log_prefix,
            run_id=run_id,
            event="node_start",
            node=node,
        )
        try:
            updates = handler(state) or {}
        except Exception as error:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            error_type = classify_workflow_error(error)
            trace = append_workflow_trace(
                state,
                workflow_key,
                {
                    "node": node,
                    "status": "error",
                    "duration_ms": duration_ms,
                    "error_type": error_type,
                },
            )
            setattr(service, workflow_attr(workflow_key, "trace"), trace)
            setattr(service, workflow_attr(workflow_key, "failed_node"), node)
            setattr(service, workflow_attr(workflow_key, "error_type"), error_type)
            log_workflow_event(
                service,
                workflow_key=workflow_key,
                log_prefix=log_prefix,
                run_id=run_id,
                event="node_error",
                node=node,
                duration_ms=duration_ms,
                error_type=error_type,
                error=str(error),
            )
            raise

        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        stop = bool(updates.get("stop", state.get("stop", False)))
        trace = append_workflow_trace(
            state,
            workflow_key,
            {
                "node": node,
                "status": "success",
                "duration_ms": duration_ms,
                "stop": stop,
            },
        )
        updates["graph_trace"] = trace
        updates["last_node"] = node
        log_workflow_event(
            service,
            workflow_key=workflow_key,
            log_prefix=log_prefix,
            run_id=run_id,
            event="node_finish",
            node=node,
            duration_ms=duration_ms,
            stop=stop,
        )
        return updates

    _wrapped.__name__ = f"{handler.__name__}_observed"
    return _wrapped


def observe_node(
    config: AssistantWorkflowConfig,
    node: str,
    handler: WorkflowNode,
) -> WorkflowNode:
    """
    是什么：observe_node 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return observe_workflow_node(
        workflow_key=config.workflow_key,
        run_id_prefix=config.run_id_prefix,
        log_prefix=config.log_prefix,
        node=node,
        handler=handler,
    )


def emit_record_metadata(
    state: WorkflowState,
    *,
    include_question_in_chat: bool,
    include_regenerate_id: bool,
) -> dict[str, Any]:
    """
    是什么：emit_record_metadata 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent处理过程中的消息或结果一段段传出去。
    """
    service = state["service"]
    in_chat = state["in_chat"]
    stream = state["stream"]
    json_result = state["json_result"]
    record = service.get_record()

    if in_chat:
        emit(sse({"type": "id", "id": record.id}))
        if include_regenerate_id and getattr(record, "regenerate_record_id", None):
            emit(sse({
                "type": "regenerate_record_id",
                "regenerate_record_id": record.regenerate_record_id,
            }))
        if include_question_in_chat:
            emit(sse({"type": "question", "question": record.question}))
    elif stream:
        emit("> " + service.trans("i18n_chat.record_id_in_mcp") + str(record.id) + "\n")
        emit("> " + record.question + "\n\n")

    if not stream:
        json_result["record_id"] = record.id
    return {"json_result": json_result}


def format_workflow_error(
    error: BaseException,
    *,
    service: Any,
    log_prefix: str,
    include_db_error_types: bool = False,
) -> str:
    """
    是什么：format_workflow_error 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    if isinstance(error, DataUnavailableError):
        error_msg = str(error)
        AppLogUtil.info(f"{log_prefix} data unavailable record_id={record_id(service)}: {error_msg}")
        return orjson.dumps(data_unavailable_error_payload(error_msg)).decode()

    if (
        isinstance(error, SingleMessageError)
        and looks_like_data_unavailable_business_message(str(error))
    ):
        error_msg = str(error)
        AppLogUtil.info(f"{log_prefix} business data unavailable record_id={record_id(service)}: {error_msg}")
        return orjson.dumps(data_unavailable_error_payload(error_msg)).decode()

    if isinstance(error, SingleMessageError):
        error_msg = str(error)
        AppLogUtil.info(f"{log_prefix} user-visible error record_id={record_id(service)}: {error_msg}")
        return error_msg

    if include_db_error_types and isinstance(error, AppDBConnectionError):
        traceback.print_exc()
        return orjson.dumps({
            "message": str(error),
            "type": "db-connection-err",
        }).decode()

    if include_db_error_types and isinstance(error, AppDBError):
        traceback.print_exc()
        return orjson.dumps({
            "message": "Execute SQL Failed",
            "traceback": str(error),
            "type": "exec-sql-err",
        }).decode()

    traceback.print_exc()
    return orjson.dumps({
        "message": str(error),
        "traceback": traceback.format_exc(limit=1),
    }).decode()


def run_assistant_workflow(
    *,
    config: AssistantWorkflowConfig,
    graph: Any,
    service: Any,
    initial_state: WorkflowState,
    run_start_fields: dict[str, Any] | None = None,
    format_error: WorkflowErrorFormatter | None = None,
    session_scope_factory: Callable[[], Any] | None = None,
) -> Iterator[Any]:
    """
    是什么：run_assistant_workflow 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent的主要流程跑起来，一步步调用需要的处理。
    """
    json_result = initial_state.setdefault("json_result", {"success": True})
    graph_run_id = init_workflow_run(service, config.workflow_key, config.run_id_prefix)
    initial_state["graph_run_id"] = graph_run_id
    initial_state["graph_trace"] = []
    initial_state.setdefault("stop", False)

    started_at = time.perf_counter()
    run_error_type = None
    log_workflow_event(
        service,
        workflow_key=config.workflow_key,
        log_prefix=config.log_prefix,
        run_id=graph_run_id,
        event="run_start",
        **(run_start_fields or {}),
    )
    try:
        yield from graph.stream(initial_state, stream_mode="custom")
    except Exception as error:
        run_error_type = classify_workflow_error(error)
        setattr(service, workflow_attr(config.workflow_key, "error_type"), run_error_type)
        log_workflow_event(
            service,
            workflow_key=config.workflow_key,
            log_prefix=config.log_prefix,
            run_id=graph_run_id,
            event="run_error",
            error_type=run_error_type,
            failed_node=getattr(service, workflow_attr(config.workflow_key, "failed_node"), None),
            error=str(error),
        )
        error_msg = (
            format_error(error)
            if format_error
            else format_workflow_error(error, service=service, log_prefix=config.log_prefix)
        )
        scope_factory = session_scope_factory or session_scope
        with scope_factory() as session:
            service.save_error(session=session, message=error_msg)

        in_chat = bool(initial_state.get("in_chat", True))
        stream = bool(initial_state.get("stream", True))
        if in_chat:
            yield sse({"content": error_msg, "type": "error"})
        elif stream:
            yield "&#x274c; **ERROR:**\n"
            yield f"> {error_msg}\n"
        else:
            json_result["success"] = False
            json_result["message"] = error_msg
            yield json_result
    finally:
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        trace = getattr(service, workflow_attr(config.workflow_key, "trace"), [])
        log_workflow_event(
            service,
            workflow_key=config.workflow_key,
            log_prefix=config.log_prefix,
            run_id=graph_run_id,
            event="run_finish",
            duration_ms=duration_ms,
            status="error" if run_error_type else "success",
            error_type=run_error_type,
            node_count=len(trace),
        )
        scope_factory = session_scope_factory or session_scope
        with scope_factory() as session:
            service.finish(session)


def consume_generator_return(generator: Any, on_chunk: Callable[[Any], None]) -> Any:
    """
    是什么：consume_generator_return 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    while True:
        try:
            chunk = next(generator)
        except StopIteration as stop:
            return stop.value
        on_chunk(chunk)


@contextmanager
def session_scope() -> Iterator[Session]:
    """
    是什么：session_scope 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    from apps.chat.task.llm import session_maker

    session = session_maker()
    try:
        yield session
    finally:
        session_maker.remove()
