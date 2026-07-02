"""
脚本说明：这个脚本放聊天问数据和 Agent里较长或较复杂的处理流程，把一次任务分成可维护的步骤。
"""
from __future__ import annotations

from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph

from apps.chat.curd.chat import (
    format_json_data,
    get_chart_data_with_user,
    get_chat_chart_config,
    get_chat_predict_data_with_user,
)
from apps.chat.task.assistant_output import (
    emit as _emit,
)
from apps.chat.task.assistant_output import (
    emit_chart_image,
    emit_markdown_table,
    emit_stream_text,
)
from apps.chat.task.assistant_output import (
    sse as _sse,
)
from apps.chat.task.assistant_workflow import (
    AssistantWorkflowConfig,
    format_workflow_error,
    observe_node,
    run_assistant_workflow,
)
from apps.chat.task.assistant_workflow import (
    emit_record_metadata as _emit_workflow_record_metadata,
)
from apps.chat.task.assistant_workflow import (
    session_scope as _session_scope,
)
from common.utils.data_format import DataFormat

ChartInsightAction = Literal["analysis", "predict"]

WORKFLOW_KEY = "chart_insight"
RUN_ID_PREFIX = "chartinsight"
LOG_PREFIX = "Chart Insight LangGraph"
WORKFLOW_CONFIG = AssistantWorkflowConfig(WORKFLOW_KEY, RUN_ID_PREFIX, LOG_PREFIX)


class ChartInsightGraphState(TypedDict, total=False):
    """
    类说明：ChartInsightGraphState 把聊天问数据和 Agent相关的数据和行为放在一起，便于其他代码直接复用。
    """
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


def _observe_node(node: str, handler):
    """
    是什么：_observe_node 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return observe_node(WORKFLOW_CONFIG, node, handler)


def _emit_record_metadata(state: ChartInsightGraphState) -> dict[str, Any]:
    """
    是什么：_emit_record_metadata 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent处理过程中的消息或结果一段段传出去。
    """
    return _emit_workflow_record_metadata(
        state,
        include_question_in_chat=False,
        include_regenerate_id=False,
    )


def _generate_analysis(state: ChartInsightGraphState) -> dict[str, Any]:
    """
    是什么：_generate_analysis 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：根据已有信息生成聊天问数据和 Agent的结果，比如答案、SQL、图表或建议。
    """
    service = state["service"]
    in_chat = state["in_chat"]
    stream = state["stream"]
    json_result = state["json_result"]

    with _session_scope() as session:
        full_text = emit_stream_text(
            service.generate_analysis(session),
            in_chat=in_chat,
            stream=stream,
            event_type="analysis-result",
            emit_plain_text=True,
        )

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
    """
    是什么：_generate_predict 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：根据已有信息生成聊天问数据和 Agent的结果，比如答案、SQL、图表或建议。
    """
    service = state["service"]
    in_chat = state["in_chat"]
    json_result = state["json_result"]

    with _session_scope() as session:
        full_text = emit_stream_text(
            service.generate_predict(session),
            in_chat=in_chat,
            stream=False,
            event_type="predict-result",
        )

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
    """
    是什么：_finalize_predict 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    service = state["service"]
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
                origin_data = get_chart_data_with_user(session, service.current_user, service.record.id)
                predict_data = get_chat_predict_data_with_user(session, service.current_user, service.record.id)

                if stream:
                    md_data, fields_list = DataFormat.convert_data_fields_for_pandas(
                        chart,
                        origin_data.get("fields"),
                        predict_data,
                    )
                    emit_markdown_table(
                        md_data,
                        fields_list,
                        empty_message="Predict data result is empty.",
                    )
                else:
                    json_result["origin_data"] = origin_data
                    json_result["predict_data"] = predict_data

                try:
                    if chart.get("type") != "table":
                        combined_data = get_chart_data_with_user(session, service.current_user, service.record.id)
                        combined_data["data"] = combined_data.get("data") + predict_data

                        emit_chart_image(
                            session=session,
                            service=service,
                            chart=chart,
                            data=format_json_data(combined_data),
                            json_result=json_result,
                            emit_markdown=stream,
                            emit_error_message=False,
                        )
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
    """
    是什么：_route_action 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return "generate_analysis" if state["action_type"] == "analysis" else "generate_predict"


def _build_graph():
    """
    是什么：_build_graph 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存聊天问数据和 Agent需要的东西，让后续流程能继续往下走。
    """
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
    """
    是什么：run_chart_insight_graph 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent的主要流程跑起来，一步步调用需要的处理。
    """
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
