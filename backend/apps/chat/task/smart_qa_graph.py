from __future__ import annotations

from typing import Any, TypedDict

import orjson
import sqlparse
from langgraph.graph import END, StateGraph

from apps.chat.curd.chat import (
    end_log,
    format_json_data,
    get_chat_chart_data,
    rename_chat,
    start_log,
    trigger_log_error,
)
from apps.chat.models.chat_model import (
    AxisObj,
    ChatFinishStep,
    OperationEnum,
    RenameChat,
)
from apps.chat.task.assistant_output import (
    emit as _emit,
)
from apps.chat.task.assistant_output import (
    emit_chart_image,
    emit_markdown_table,
    emit_permission_denied_response,
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
    consume_generator_return as _consume_generator_return,
)
from apps.chat.task.assistant_workflow import (
    emit_record_metadata as _emit_workflow_record_metadata,
)
from apps.chat.task.assistant_workflow import (
    session_scope as _session_scope,
)
from apps.datasource.crud.datasource import get_table_schema
from apps.datasource.crud.permission_errors import (
    looks_like_permission_scope_error,
)
from apps.datasource.crud.query_executor import validate_user_query_sql_or_raise
from apps.datasource.models.datasource import CoreDatasource
from apps.db.db import check_connection
from common.error import AppDBConnectionError
from common.utils.data_format import DataFormat
from common.utils.utils import AppLogUtil, extract_nested_json

WORKFLOW_KEY = "smart_qa"
RUN_ID_PREFIX = "smartqa"
LOG_PREFIX = "Smart Q&A LangGraph"
WORKFLOW_CONFIG = AssistantWorkflowConfig(WORKFLOW_KEY, RUN_ID_PREFIX, LOG_PREFIX)


class SmartQAGraphState(TypedDict, total=False):
    service: Any
    in_chat: bool
    stream: bool
    finish_step: ChatFinishStep
    return_img: bool
    graph_run_id: str
    graph_trace: list[dict[str, Any]]
    last_node: str
    json_result: dict[str, Any]
    full_sql_text: str
    sql: str
    tables: list[str] | None
    chart_type: str | None
    dynamic_sql_result: dict[str, Any] | None
    app_temp_sql_text: str | None
    assistant_dynamic_sql: str | None
    real_execute_sql: str
    execute_scope_sql: str
    execute_allowed_tables: list[str] | set[str] | None
    result: dict[str, Any]
    chart: dict[str, Any]
    stop: bool


def _observe_node(node: str, handler):
    """
    是什么：_observe_node 是 backend/apps/chat/task/smart_qa_graph.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _observe_node 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
    """
    return observe_node(WORKFLOW_CONFIG, node, handler)


def _prepare_existing_context(state: SmartQAGraphState) -> dict[str, Any]:
    """
    是什么：_prepare_existing_context 是 backend/apps/chat/task/smart_qa_graph.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _prepare_existing_context 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
    """
    service = state["service"]

    if service.ds:
        from apps.chat.curd.custom_prompt import (
            CustomPromptTargetScopeEnum,
            CustomPromptTypeEnum,
        )

        with _session_scope() as session:
            ds_id = service.ds.id if isinstance(service.ds, CoreDatasource) else None
            service.load_data_skills(session, ds_id, CustomPromptTargetScopeEnum.SMART_QA)
            service.filter_custom_prompts(session, CustomPromptTypeEnum.GENERATE_SQL, ds_id)
            service.save_agent_context_snapshot(session, CustomPromptTargetScopeEnum.SMART_QA)
            service.load_tracking_config(session)
            service.init_messages(session)
    return {}


def _emit_record_metadata(state: SmartQAGraphState) -> dict[str, Any]:
    """
    是什么：_emit_record_metadata 是 backend/apps/chat/task/smart_qa_graph.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：组织聊天和 Agent的流式输出或异步等待，把事件和结果传递给调用方。
    """
    return _emit_workflow_record_metadata(
        state,
        include_question_in_chat=True,
        include_regenerate_id=True,
    )


def _ensure_datasource(state: SmartQAGraphState) -> dict[str, Any]:
    """
    是什么：_ensure_datasource 是 backend/apps/chat/task/smart_qa_graph.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：校验聊天和 Agent相关输入、权限、配置或运行状态，不满足条件时返回失败或抛出异常。
    """
    service = state["service"]
    in_chat = state["in_chat"]

    with _session_scope() as session:
        if not service.ds:
            for chunk in service.select_datasource(session):
                AppLogUtil.info(chunk)
                if in_chat:
                    _emit(_sse({
                        "content": chunk.get("content"),
                        "reasoning_content": chunk.get("reasoning_content"),
                        "type": "datasource-result",
                    }))
            if in_chat:
                _emit(_sse({
                    "id": service.ds.id,
                    "datasource_name": service.ds.name,
                    "engine_type": service.ds.type_name or service.ds.type,
                    "type": "datasource",
                }))
        else:
            service.validate_history_ds(session)

    connected = check_connection(ds=service.ds, trans=None)
    if not connected:
        raise AppDBConnectionError("Connect DB failed")
    return {}


def _generate_sql(state: SmartQAGraphState) -> dict[str, Any]:
    """
    是什么：_generate_sql 是 backend/apps/chat/task/smart_qa_graph.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：基于输入上下文生成聊天和 Agent相关结果，并保存或返回给调用方。
    """
    service = state["service"]
    in_chat = state["in_chat"]

    with _session_scope() as session:
        full_sql_text = _consume_generator_return(
            service.generate_sql_text_streaming_reasoning(session, in_chat=in_chat),
            _emit,
        )
    AppLogUtil.info(full_sql_text)
    return {"full_sql_text": full_sql_text}


def _prepare_sql(state: SmartQAGraphState) -> dict[str, Any]:
    """
    是什么：_prepare_sql 是 backend/apps/chat/task/smart_qa_graph.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _prepare_sql 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
    """
    from apps.chat.task.llm import (
        APP_TEMP_SQL_TEXT_KEY,
        DataSkillSqlValidationError,
        _get_temp_sql_text,
        _remove_temp_sql_text,
        dynamic_ds_types,
        dynamic_subsql_prefix,
    )

    service = state["service"]
    in_chat = state["in_chat"]
    stream = state["stream"]
    finish_step = state["finish_step"]
    json_result = state["json_result"]
    full_sql_text = state["full_sql_text"]

    with _session_scope() as session:
        use_dynamic_ds = service.current_assistant and service.current_assistant.type in dynamic_ds_types
        dynamic_sql_result = None
        app_temp_sql_text = None
        assistant_dynamic_sql = None
        sql_operate = OperationEnum.GENERATE_SQL

        try:
            sql, tables = service.check_sql(session=session, res=full_sql_text, operate=sql_operate)
        except DataSkillSqlValidationError as semantic_error:
            full_sql_text = _consume_generator_return(
                service.regenerate_sql_after_validation_error_streaming_reasoning(
                    session,
                    str(semantic_error),
                    in_chat=in_chat,
                ),
                _emit,
            )
            AppLogUtil.info(full_sql_text)
            sql, tables = service.check_sql(session=session, res=full_sql_text, operate=sql_operate)

        chart_type = service.get_chart_type_from_sql_answer(full_sql_text)

        if service.change_title:
            llm_brief = service.get_brief_from_sql_answer(full_sql_text)
            llm_brief_generated = bool(llm_brief)
            if llm_brief_generated or (service.chat_question.question and service.chat_question.question.strip() != ""):
                save_brief = llm_brief if llm_brief else service.chat_question.question.strip()[:20]
                brief = rename_chat(
                    session=session,
                    rename_object=RenameChat(
                        id=service.get_record().chat_id,
                        brief=save_brief,
                        brief_generate=llm_brief_generated,
                    ),
                )
                if in_chat:
                    _emit(_sse({"type": "brief", "brief": brief}))
                if not stream:
                    json_result["title"] = brief

        if in_chat:
            json_str = extract_nested_json(full_sql_text)
            if json_str:
                try:
                    answer_data = orjson.loads(json_str)
                    _emit(_sse({
                        "content": orjson.dumps(answer_data).decode(),
                        "reasoning_content": "",
                        "type": "sql-result",
                    }))
                except Exception:
                    _emit(_sse({
                        "content": full_sql_text,
                        "reasoning_content": "",
                        "type": "sql-result",
                    }))
            else:
                _emit(_sse({
                    "content": full_sql_text,
                    "reasoning_content": "",
                    "type": "sql-result",
                }))
            _emit(_sse({"type": "info", "msg": "sql generated"}))

        try:
            if use_dynamic_ds:
                dynamic_sql_result = service.generate_assistant_dynamic_sql(session, sql, tables)
                app_temp_sql_text = _get_temp_sql_text(dynamic_sql_result)
                if dynamic_sql_result and app_temp_sql_text:
                    sql_operate = OperationEnum.GENERATE_DYNAMIC_SQL
                    assistant_dynamic_sql = service.check_save_sql(
                        session=session,
                        res=app_temp_sql_text,
                        operate=sql_operate,
                    )
                else:
                    sql = service.check_save_sql(session=session, res=full_sql_text, operate=sql_operate)
            else:
                checked_sql, _actual_tables = validate_user_query_sql_or_raise(
                    session=session,
                    current_user=service.current_user,
                    datasource=service.ds,
                    sql=sql,
                    allowed_tables=service.table_name_list,
                )
                sql = service.save_checked_sql(session=session, sql=checked_sql)
        except Exception as permission_error:
            if not looks_like_permission_scope_error(str(permission_error)):
                raise
            sql = service.save_checked_sql(session=session, sql=sql)
            failed_result = service.save_permission_denied_data(session=session)
            format_sql = sqlparse.format(sql, reindent=True)
            emit_permission_denied_response(
                in_chat=in_chat,
                stream=stream,
                json_result=json_result,
                sql=sql,
                failed_result=failed_result,
                formatted_sql=format_sql,
                emit_sql=True,
            )
            return {"json_result": json_result, "stop": True}

    AppLogUtil.info("sql: " + sql)

    if not stream:
        json_result["sql"] = sql

    format_sql = sqlparse.format(sql, reindent=True)
    if in_chat:
        _emit(_sse({"content": format_sql, "type": "sql"}))
    elif stream:
        _emit(f"```sql\n{format_sql}\n```\n\n")

    real_execute_sql = sql
    execute_scope_sql = sql
    execute_allowed_tables = service.table_name_list

    if app_temp_sql_text and assistant_dynamic_sql:
        execute_scope_sql = assistant_dynamic_sql
        execute_allowed_tables = [
            f"app_dynamic_temp_table_{origin_table}"
            for origin_table in dynamic_sql_result
            if origin_table != APP_TEMP_SQL_TEXT_KEY
        ]
        _remove_temp_sql_text(dynamic_sql_result)
        for origin_table, subsql in dynamic_sql_result.items():
            assistant_dynamic_sql = assistant_dynamic_sql.replace(
                f"{dynamic_subsql_prefix}{origin_table}",
                subsql,
            )
        real_execute_sql = assistant_dynamic_sql

    if finish_step.value <= ChatFinishStep.GENERATE_SQL.value:
        if in_chat:
            _emit(_sse({"type": "finish"}))
        if not stream:
            _emit(json_result)
        return {
            "json_result": json_result,
            "full_sql_text": full_sql_text,
            "sql": sql,
            "tables": tables,
            "chart_type": chart_type,
            "stop": True,
        }

    return {
        "json_result": json_result,
        "full_sql_text": full_sql_text,
        "sql": sql,
        "tables": tables,
        "chart_type": chart_type,
        "dynamic_sql_result": dynamic_sql_result,
        "app_temp_sql_text": app_temp_sql_text,
        "assistant_dynamic_sql": assistant_dynamic_sql,
        "real_execute_sql": real_execute_sql,
        "execute_scope_sql": execute_scope_sql,
        "execute_allowed_tables": execute_allowed_tables,
        "stop": False,
    }


def _execute_sql(state: SmartQAGraphState) -> dict[str, Any]:
    """
    是什么：_execute_sql 是 backend/apps/chat/task/smart_qa_graph.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：执行聊天和 Agent主流程，协调下游服务并处理结果或异常。
    """
    service = state["service"]
    in_chat = state["in_chat"]
    stream = state["stream"]
    finish_step = state["finish_step"]
    json_result = state["json_result"]
    sql = state["sql"]
    real_execute_sql = state["real_execute_sql"]
    execute_scope_sql = state["execute_scope_sql"]
    execute_allowed_tables = state["execute_allowed_tables"]

    with _session_scope() as session:
        service.current_logs[OperationEnum.EXECUTE_SQL] = start_log(
            session=session,
            operate=OperationEnum.EXECUTE_SQL,
            record_id=service.record.id,
            local_operation=True,
        )
        try:
            result = service.execute_sql(
                session=session,
                sql=real_execute_sql,
                scope_sql=execute_scope_sql,
                scope_allowed_tables=execute_allowed_tables,
            )
        except Exception as execute_error:
            if not looks_like_permission_scope_error(str(execute_error)):
                raise
            trigger_log_error(session, service.current_logs[OperationEnum.EXECUTE_SQL])
            failed_result = service.save_permission_denied_data(session=session)
            emit_permission_denied_response(
                in_chat=in_chat,
                stream=stream,
                json_result=json_result,
                sql=sql,
                failed_result=failed_result,
                include_reason=True,
            )
            return {"json_result": json_result, "stop": True}

        service.current_logs[OperationEnum.EXECUTE_SQL] = end_log(
            session=session,
            log=service.current_logs[OperationEnum.EXECUTE_SQL],
            full_message={"sql": real_execute_sql, "count": len(result.get("data"))},
        )

        data = DataFormat.convert_large_numbers_in_object_array(result.get("data"))
        data = DataFormat.normalize_qualified_sql_column_keys_in_object_array(data)
        result["data"] = data

        service.save_sql_data(session=session, data_obj=result)
        if in_chat:
            _emit(_sse({"content": "execute-success", "type": "sql-data"}))
        if not stream:
            json_result["data"] = get_chat_chart_data(session, service.record.id)

    if finish_step.value <= ChatFinishStep.QUERY_DATA.value:
        if stream:
            if in_chat:
                _emit(_sse({"type": "finish"}))
            else:
                column_list = [AxisObj(name=field, value=field) for field in result.get("fields")]
                _md_data, fields_list = DataFormat.convert_object_array_for_pandas(
                    column_list,
                    result.get("data"),
                )
                emit_markdown_table(
                    data,
                    fields_list,
                    empty_message="The SQL execution result is empty.",
                )
        else:
            _emit(json_result)
        return {"json_result": json_result, "result": result, "stop": True}

    return {"json_result": json_result, "result": result, "stop": False}


def _generate_chart(state: SmartQAGraphState) -> dict[str, Any]:
    """
    是什么：_generate_chart 是 backend/apps/chat/task/smart_qa_graph.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：基于输入上下文生成聊天和 Agent相关结果，并保存或返回给调用方。
    """
    service = state["service"]
    in_chat = state["in_chat"]
    stream = state["stream"]
    return_img = state["return_img"]
    json_result = state["json_result"]
    result = state["result"]
    tables = state.get("tables")
    chart_type = state.get("chart_type")

    with _session_scope() as session:
        if service.out_ds_instance:
            used_tables_schema, _used_tables = service.out_ds_instance.get_db_schema(
                service.ds.id,
                service.chat_question.question,
                embedding=False,
                table_list=tables,
            )
        else:
            used_tables_schema, _used_tables = get_table_schema(
                session=session,
                current_user=service.current_user,
                ds=service.ds,
                question=service.chat_question.question,
                embedding=False,
                table_list=tables,
            )
        AppLogUtil.info("used_tables_schema: \n" + used_tables_schema)

        full_chart_text = emit_stream_text(
            service.generate_chart(session, chart_type, used_tables_schema),
            in_chat=in_chat,
            stream=False,
            event_type="chart-result",
        )
        if in_chat:
            _emit(_sse({"type": "info", "msg": "chart generated"}))

        AppLogUtil.info(full_chart_text)
        chart = service.check_save_chart(session=session, res=full_chart_text, result=result)
        AppLogUtil.info(chart)

        if not stream:
            json_result["chart"] = chart

        if in_chat:
            _emit(_sse({"content": orjson.dumps(chart).decode(), "type": "chart"}))
            _emit(_sse({"type": "finish"}))
        elif stream:
            md_data, fields_list = DataFormat.convert_data_fields_for_pandas(
                chart,
                result.get("fields"),
                result.get("data"),
            )
            emit_markdown_table(
                md_data,
                fields_list,
                empty_message="The SQL execution result is empty.",
            )
        else:
            emit_chart_image(
                session=session,
                service=service,
                chart=chart,
                data=format_json_data(result),
                return_img=return_img,
                json_result=json_result,
                log_operation=True,
            )
            _emit(json_result)

        if not in_chat and stream:
            emit_chart_image(
                session=session,
                service=service,
                chart=chart,
                data=format_json_data(result),
                return_img=return_img,
                emit_markdown=True,
                log_operation=True,
            )

    return {"json_result": json_result, "chart": chart}


def _should_continue_after_sql(state: SmartQAGraphState) -> str:
    """
    是什么：_should_continue_after_sql 是 backend/apps/chat/task/smart_qa_graph.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _should_continue_after_sql 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
    """
    return END if state.get("stop") else "execute_sql"


def _should_continue_after_execute(state: SmartQAGraphState) -> str:
    """
    是什么：_should_continue_after_execute 是 backend/apps/chat/task/smart_qa_graph.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _should_continue_after_execute 的语义处理聊天和 Agent相关逻辑，并把结果返回或写入状态。
    """
    return END if state.get("stop") else "generate_chart"


def _build_graph():
    """
    是什么：_build_graph 是 backend/apps/chat/task/smart_qa_graph.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：创建、初始化或组装聊天和 Agent相关对象和数据，并返回或写入对应状态。
    """
    graph = StateGraph(SmartQAGraphState)
    graph.add_node("prepare_context", _observe_node("prepare_context", _prepare_existing_context))
    graph.add_node("emit_record_metadata", _observe_node("emit_record_metadata", _emit_record_metadata))
    graph.add_node("ensure_datasource", _observe_node("ensure_datasource", _ensure_datasource))
    graph.add_node("generate_sql", _observe_node("generate_sql", _generate_sql))
    graph.add_node("prepare_sql", _observe_node("prepare_sql", _prepare_sql))
    graph.add_node("execute_sql", _observe_node("execute_sql", _execute_sql))
    graph.add_node("generate_chart", _observe_node("generate_chart", _generate_chart))

    graph.set_entry_point("prepare_context")
    graph.add_edge("prepare_context", "emit_record_metadata")
    graph.add_edge("emit_record_metadata", "ensure_datasource")
    graph.add_edge("ensure_datasource", "generate_sql")
    graph.add_edge("generate_sql", "prepare_sql")
    graph.add_conditional_edges("prepare_sql", _should_continue_after_sql)
    graph.add_conditional_edges("execute_sql", _should_continue_after_execute)
    graph.add_edge("generate_chart", END)
    return graph.compile()


SMART_QA_GRAPH = _build_graph()


def run_smart_qa_graph(
    service: Any,
    in_chat: bool = True,
    stream: bool = True,
    finish_step: ChatFinishStep = ChatFinishStep.GENERATE_CHART,
    return_img: bool = True,
):
    """
    是什么：run_smart_qa_graph 是 backend/apps/chat/task/smart_qa_graph.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：执行聊天和 Agent主流程，协调下游服务并处理结果或异常。
    """
    json_result: dict[str, Any] = {"success": True}
    initial_state: SmartQAGraphState = {
        "service": service,
        "in_chat": in_chat,
        "stream": stream,
        "finish_step": finish_step,
        "return_img": return_img,
        "json_result": json_result,
        "stop": False,
    }
    yield from run_assistant_workflow(
        config=WORKFLOW_CONFIG,
        graph=SMART_QA_GRAPH,
        service=service,
        initial_state=initial_state,
        run_start_fields={
            "in_chat": in_chat,
            "stream": stream,
            "finish_step": finish_step.name,
        },
        format_error=lambda error: format_workflow_error(
            error,
            service=service,
            log_prefix=LOG_PREFIX,
            include_db_error_types=True,
        ),
        session_scope_factory=_session_scope,
    )
