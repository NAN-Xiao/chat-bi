from __future__ import annotations

from typing import Any, Literal, TypedDict

import pandas as pd
from langgraph.graph import END, StateGraph

from apps.chat.curd.chat import (
    format_json_data,
    get_chat_chart_config,
    get_chat_chart_data,
    get_chat_predict_data,
)
from apps.chat.task.assistant_workflow import (
    AssistantWorkflowConfig,
    emit_record_metadata as _emit_workflow_record_metadata,
    format_workflow_error,
    observe_node,
    run_assistant_workflow,
)
from apps.chat.task.assistant_workflow import (
    emit as _emit,
)
from apps.chat.task.assistant_workflow import (
    session_scope as _session_scope,
)
from apps.chat.task.assistant_workflow import (
    sse as _sse,
)
from common.utils.data_format import DataFormat
from common.utils.utils import AppLogUtil

ChartInsightAction = Literal["analysis", "predict"]

WORKFLOW_KEY = "chart_insight"
RUN_ID_PREFIX = "chartinsight"
LOG_PREFIX = "Chart Insight LangGraph"
WORKFLOW_CONFIG = AssistantWorkflowConfig(WORKFLOW_KEY, RUN_ID_PREFIX, LOG_PREFIX)


class ChartInsightGraphState(TypedDict, total=False):
    service: Any
    action_type: ChartInsightAction
    in_chat: bool
    stream: bool
    graph_run_id: str
    graph_trace: list[dict[str, Any]]
    last_node: str
    json_result: dict[str, Any]
    full_text: str
    has_predict_data: bool
    stop: bool


def _log_node(service: Any, node: str) -> None:
    from apps.chat.task.assistant_workflow import record_id

    AppLogUtil.info(f"Chart Insight LangGraph node={node} record_id={record_id(service)}")


def _observe_node(node: str, handler):
    return observe_node(WORKFLOW_CONFIG, node, handler)


def _emit_record_metadata(state: ChartInsightGraphState) -> dict[str, Any]:
    service = state["service"]
    _log_node(service, "emit_record_metadata")
    return _emit_workflow_record_metadata(
        state,
        include_question_in_chat=False,
        include_regenerate_id=False,
    )


def _generate_analysis(state: ChartInsightGraphState) -> dict[str, Any]:
    service = state["service"]
    _log_node(service, "generate_analysis")
    in_chat = state["in_chat"]
    stream = state["stream"]
    json_result = state["json_result"]

    full_text = ""
    with _session_scope() as session:
        for chunk in service.generate_analysis(session):
            content = chunk.get("content") or ""
            full_text += content
            if in_chat:
                _emit(_sse({
                    "content": content,
                    "reasoning_content": chunk.get("reasoning_content"),
                    "type": "analysis-result",
                }))
            elif stream:
                _emit(content)

    if in_chat:
        _emit(_sse({"type": "info", "msg": "analysis generated"}))
        _emit(_sse({"type": "analysis_finish"}))
    elif stream:
        _emit("\n\n")

    if not stream:
        json_result["content"] = full_text
        _emit(json_result)

    return {"json_result": json_result, "full_text": full_text, "stop": True}


def _generate_predict(state: ChartInsightGraphState) -> dict[str, Any]:
    service = state["service"]
    _log_node(service, "generate_predict")
    in_chat = state["in_chat"]
    json_result = state["json_result"]

    full_text = ""
    with _session_scope() as session:
        for chunk in service.generate_predict(session):
            content = chunk.get("content") or ""
            full_text += content
            if in_chat:
                _emit(_sse({
                    "content": content,
                    "reasoning_content": chunk.get("reasoning_content"),
                    "type": "predict-result",
                }))

        if in_chat:
            _emit(_sse({"type": "info", "msg": "predict generated"}))

        has_data = service.check_save_predict_data(session=session, res=full_text)

    return {
        "json_result": json_result,
        "full_text": full_text,
        "has_predict_data": has_data,
        "stop": False,
    }


def _finalize_predict(state: ChartInsightGraphState) -> dict[str, Any]:
    from apps.chat.task.llm import request_picture

    service = state["service"]
    _log_node(service, "finalize_predict")
    in_chat = state["in_chat"]
    stream = state["stream"]
    json_result = state["json_result"]
    full_text = state.get("full_text", "")
    has_data = bool(state.get("has_predict_data"))

    with _session_scope() as session:
        if has_data:
            if in_chat:
                _emit(_sse({"type": "predict-success"}))
            else:
                chart = get_chat_chart_config(session, service.record.id)
                origin_data = get_chat_chart_data(session, service.record.id)
                predict_data = get_chat_predict_data(session, service.record.id)

                if stream:
                    md_data, fields_list = DataFormat.convert_data_fields_for_pandas(
                        chart,
                        origin_data.get("fields"),
                        predict_data,
                    )
                    if not md_data or not fields_list:
                        _emit("Predict data result is empty.\n\n")
                    else:
                        df = pd.DataFrame(md_data, columns=fields_list)
                        df_safe = DataFormat.safe_convert_to_string(df)
                        _emit(df_safe.to_markdown(index=False) + "\n\n")
                else:
                    json_result["origin_data"] = origin_data
                    json_result["predict_data"] = predict_data

                try:
                    if chart.get("type") != "table":
                        combined_data = get_chat_chart_data(session, service.record.id)
                        combined_data["data"] = combined_data.get("data") + predict_data

                        image_url, error = request_picture(
                            service.record.chat_id,
                            service.record.id,
                            chart,
                            format_json_data(combined_data),
                        )
                        AppLogUtil.info(image_url)
                        if stream:
                            _emit(f'![{chart.get("type")}]({image_url})')
                        else:
                            json_result["image_url"] = image_url
                        if error is not None:
                            raise error
                except Exception as error:
                    if stream and chart.get("type") != "table":
                        _emit("generate or fetch chart picture error.\n\n")
                    raise error
        else:
            if in_chat:
                _emit(_sse({"type": "predict-failed"}))
            elif stream:
                _emit(full_text + "\n\n")
            if not stream:
                json_result["success"] = False
                json_result["message"] = full_text

    if in_chat:
        _emit(_sse({"type": "predict_finish"}))
    elif not stream:
        _emit(json_result)

    return {"json_result": json_result, "stop": True}


def _route_action(state: ChartInsightGraphState) -> str:
    return "generate_analysis" if state["action_type"] == "analysis" else "generate_predict"


def _build_graph():
    graph = StateGraph(ChartInsightGraphState)
    graph.add_node("emit_record_metadata", _observe_node("emit_record_metadata", _emit_record_metadata))
    graph.add_node("generate_analysis", _observe_node("generate_analysis", _generate_analysis))
    graph.add_node("generate_predict", _observe_node("generate_predict", _generate_predict))
    graph.add_node("finalize_predict", _observe_node("finalize_predict", _finalize_predict))

    graph.set_entry_point("emit_record_metadata")
    graph.add_conditional_edges("emit_record_metadata", _route_action)
    graph.add_edge("generate_analysis", END)
    graph.add_edge("generate_predict", "finalize_predict")
    graph.add_edge("finalize_predict", END)
    return graph.compile()


CHART_INSIGHT_GRAPH = _build_graph()


def run_chart_insight_graph(
    service: Any,
    action_type: ChartInsightAction,
    in_chat: bool = True,
    stream: bool = True,
):
    json_result: dict[str, Any] = {"success": True}
    initial_state: ChartInsightGraphState = {
        "service": service,
        "action_type": action_type,
        "in_chat": in_chat,
        "stream": stream,
        "json_result": json_result,
        "stop": False,
    }
    yield from run_assistant_workflow(
        config=WORKFLOW_CONFIG,
        graph=CHART_INSIGHT_GRAPH,
        service=service,
        initial_state=initial_state,
        run_start_fields={
            "action_type": action_type,
            "in_chat": in_chat,
            "stream": stream,
        },
        format_error=lambda error: format_workflow_error(
            error,
            service=service,
            log_prefix=LOG_PREFIX,
        ),
        session_scope_factory=_session_scope,
    )
