"""
脚本说明：这个脚本封装手动看板里的 AI SQL 生成能力。
"""
from __future__ import annotations

import json
import re
from asyncio import to_thread
from datetime import datetime
from typing import Any, TypedDict

import orjson
from fastapi import HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from apps.ai_model.model_factory import LLMFactory, get_default_config
from apps.chat.curd.custom_prompt import CustomPromptTargetScopeEnum, find_data_skills
from apps.dashboard.models.dashboard_model import DashboardAiSqlGenerateRequest, DashboardAiSqlGenerateResponse
from apps.datasource.crud.permission import has_datasource_access
from apps.datasource.models.datasource import CoreDatasource
from apps.system.crud.tenant import TENANT_ADMIN_ROLES, normalize_tenant_role
from apps.system.crud.tracking_config import find_tracking_prompt_context
from apps.system.crud.user import is_platform_admin, is_platform_workspace_delegate, is_system_admin
from apps.system.schemas.access_context import require_current_tenant_id
from common.core.deps import CurrentUser, SessionDep
from common.utils.utils import AppLogUtil, extract_nested_json


class DashboardManualChartGraphState(TypedDict, total=False):
    """
    类说明：DashboardManualChartGraphState 表示手动看板配置 Agent 图的运行状态。
    """
    session: SessionDep
    current_user: CurrentUser
    request: DashboardAiSqlGenerateRequest
    datasource: CoreDatasource
    tenant_id: int
    data_skill: str
    tracking_config: str
    skill_model_id: int | None
    config_summary: dict[str, Any]
    diagnosis: DashboardAiSqlGenerateResponse
    response: DashboardAiSqlGenerateResponse
    graph_trace: list[dict[str, Any]]
    last_node: str


def _can_manage_platform_prompt_runtime(user: CurrentUser) -> bool:
    return bool(user is not None and is_platform_admin(user) and not is_platform_workspace_delegate(user))


def _can_manage_tenant_prompt_runtime(user: CurrentUser) -> bool:
    if user is None or _can_manage_platform_prompt_runtime(user):
        return False
    if is_system_admin(user):
        return True
    return normalize_tenant_role(getattr(user, "tenant_role", None)) in TENANT_ADMIN_ROLES


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime,)):
        return value.isoformat()
    return str(value)


def _safe_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=_json_default)
    except Exception:
        return json.dumps({}, ensure_ascii=False)


def _text_chunk_content(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return _text_chunk_content(value.get("text") or value.get("content") or "")
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                parts.append(_text_chunk_content(item.get("text") or item.get("content") or ""))
            elif isinstance(item, (str, int, float, bool)):
                parts.append(str(item))
            elif hasattr(item, "text"):
                parts.append(_text_chunk_content(getattr(item, "text", "")))
            elif hasattr(item, "content"):
                parts.append(_text_chunk_content(getattr(item, "content", "")))
        return "".join(parts)
    if isinstance(value, (int, float, bool)):
        return str(value)
    if hasattr(value, "text"):
        return _text_chunk_content(getattr(value, "text", ""))
    if hasattr(value, "content"):
        return _text_chunk_content(getattr(value, "content", ""))
    return ""


def _coerce_model_success(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("", "false", "0", "no"):
            return False
        return True
    return bool(value)


def _extract_sql_from_text(text: str) -> str:
    match = re.search(r"```(?:sql)?\s*(.*?)```", text or "", flags=re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    stripped = (text or "").strip()
    if re.search(r"\bselect\b|\bwith\b", stripped, flags=re.IGNORECASE):
        return stripped
    return ""


def _response_from_model_text(text: str, require_sql: bool = True) -> DashboardAiSqlGenerateResponse:
    json_str = extract_nested_json(text or "")
    if not json_str:
        sql = _extract_sql_from_text(text)
        return DashboardAiSqlGenerateResponse(
            success=bool(sql),
            sql=sql,
            message="" if sql else "AI 未返回可识别的 SQL。",
            advice="" if sql else "当前 AI 返回内容中没有可识别的 SQL 或配置建议，请补充生成意图或检查指标配置。",
            raw=text or "",
        )

    try:
        payload = orjson.loads(json_str)
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        return DashboardAiSqlGenerateResponse(success=False, message="AI 返回格式不是 JSON 对象。", raw=text or "")

    sql = str(payload.get("sql") or payload.get("SQL") or "").strip()
    success = _coerce_model_success(payload.get("success"), default=bool(sql))
    chart_type = str(payload.get("chart_type") or payload.get("chart-type") or payload.get("chartType") or "").strip()
    title = str(payload.get("brief") or payload.get("title") or payload.get("name") or "").strip()
    tables = payload.get("tables") if isinstance(payload.get("tables"), list) else []
    intent = str(payload.get("intent") or payload.get("user_intent") or payload.get("userIntent") or "").strip()
    message = str(payload.get("message") or payload.get("reason") or "").strip()
    advice = str(payload.get("advice") or payload.get("diagnosis") or payload.get("analysis") or "").strip()
    issues = payload.get("issues") if isinstance(payload.get("issues"), list) else []
    suggestions = payload.get("suggestions") if isinstance(payload.get("suggestions"), list) else []
    return DashboardAiSqlGenerateResponse(
        success=success and (bool(sql) if require_sql else True),
        sql=sql,
        title=title,
        chart_type=chart_type,
        tables=[str(item) for item in tables if str(item or "").strip()],
        intent=intent,
        message=message if success and (sql or not require_sql) else message or "AI 未生成可执行 SQL。",
        advice=advice,
        issues=[str(item) for item in issues if str(item or "").strip()],
        suggestions=[str(item) for item in suggestions if str(item or "").strip()],
        raw=text or "",
    )


def _dashboard_diagnosis_system_prompt() -> str:
    return (
        "你是 BI 手动看板配置诊断节点。先使用 understand_config 节点对用户当前配置的理解，再结合业务口径、字段字典、事件字典判断配置是否能表达用户意图；不生成 SQL。\n"
        "输出必须是单个 JSON 对象："
        '{"success":true,"sql":"","tables":[],"chart_type":"","brief":"","intent":"一句话用户意图","message":"一句话错误结论","advice":"一句话核心改法","issues":["异常点"],"suggestions":["修改建议"]}。\n'
        "intent 只说用户想用当前配置看什么；issues 只写当前配置与该意图/业务口径不一致或缺失的地方；suggestions 只写当前界面怎么点。\n"
        "只有字段、聚合、筛选条件、计算指标公式、时间范围与业务口径不一致，或缺少生成查询必需配置时，success 才能是 false。"
        "标题、图表类型、指标别名、是否添加国家/渠道/平台分组、信息密度、展示美观、字段已选但未使用，只能作为 suggestions/advice，不能放进阻断性 issues，也不能让 success=false。\n"
        "不要输出 selectedFields、manual-dashboard-context、context、raw、Data Skills、Schema、系统口径、SQL 已转换、已自动添加、已自动应用、UTC+8 等内部技术或执行过程。\n"
        "不要告诉用户系统已经自动做了什么；只告诉用户在当前界面还要怎么显式配置。不要从表名/字段名/示例里臆造业务事件值或指标公式；业务口径必须来自已给的业务口径文本、字段字典、事件字典或用户当前配置。缺少口径时要明确说“缺少这个指标的业务口径配置”。\n"
        "重要：时间范围里的粒度（按天/按周/按月）已经是时间分组，不要建议用户再到“分组项”里添加时间字段。分组项只用于国家、平台、渠道等额外维度。\n"
        "一个分析指标可以有多个筛选条件或条件组；不要把多个筛选条件合并成一句含糊建议。涉及复合指标时，要同时说明“分析指标”和“计算指标”怎么配置。\n"
        "配置建议必须具体到界面动作，例如："
        "“时间范围：字段选「事件时间 event.time」，粒度选「按天」，范围选「过去7天」”；"
        "“分析指标1：字段选「用户ID event.uid」，聚合选「去重数」，计算字段选「用户ID event.uid」，别名填「业务指标名」”；"
        "“分析指标1筛选条件：字段选「事件名 event.event」，条件选「等于」，最右侧值输入框手动填「业务口径里的事件值」”；"
        "“计算指标1：左侧选「指标A」，运算选「除以」，右侧选「指标B」，倍率填「1」，别名填「业务指标名」”；"
        "“分组项：添加「国家 event.userinfo.country」”。"
    )


def _dashboard_understanding_system_prompt() -> str:
    return (
        "你是 BI 手动看板配置意图理解节点。只读取用户当前手动配置，推断用户可能想分析什么；不要生成 SQL，不要纠错，不要套业务口径。\n"
        "输出必须是单个 JSON 对象："
        '{"success":true,"sql":"","tables":[],"chart_type":"","brief":"","intent":"当前配置表达的分析意图","message":"一句话概括当前配置","advice":"","issues":["仅列出无法从配置确定的疑点"],"suggestions":[]}。\n'
        "理解依据只能是用户填写的生成意图、图表标题、时间范围、分析指标、计算指标、筛选、全局筛选、分组项和字段中文名。"
        "如果指标别名是“指标1/指标2”这种默认名，要结合字段、聚合和筛选推断意图，但保留不确定性。"
        "不要使用业务口径、事件字典去替用户补配置；这些留给诊断节点处理。标题、别名、分组维度不明确只是疑点，不代表配置无法表达意图。"
    )


def _trim_text(value: Any, limit: int = 12000) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[:limit] + "\n...（已截断）"


def _dashboard_config_prompt(
        request: DashboardAiSqlGenerateRequest,
        datasource: CoreDatasource,
        data_skill: str,
        tracking_config: str,
) -> str:
    context = dict(request.context or {})
    if request.chart_type and not context.get("chartType"):
        context["chartType"] = request.chart_type
    if request.title and not context.get("title"):
        context["title"] = request.title
    return "\n".join([
        "请处理下面的手动图表配置。",
        "",
        f"用户意图：{(request.intent or '').strip() or '根据当前图表配置生成查询'}",
        f"数据源：{datasource.name} / {datasource.type_name or datasource.type}",
        "",
        "<manual-dashboard-context>",
        _safe_json(context),
        "</manual-dashboard-context>",
        "",
        "<data-skill>",
        _trim_text(data_skill, 10000),
        "</data-skill>",
        "",
        "<tracking-config>",
        _trim_text(tracking_config, 8000),
        "</tracking-config>",
        "",
        "当前配置器可配置的控件：时间范围(time.field/time.grain/time.range)、分析指标(metrics: 字段/聚合/计算字段/别名/指标内筛选树)、计算指标(calculatedMetrics: 左指标/运算符/右指标/倍率/小数/别名)、全局筛选、分组项(groups)。",
        "配置器规则：time.field + time.grain 会自动生成日期维度；groups 只表示额外维度，不包含时间维度也不是错误。",
        "只允许使用 manual-dashboard-context 里的 selectedFields/metrics/calculatedMetrics/groups/filters 字段信息生成 SQL；不要编造未提供字段。",
    ])


def _dashboard_understanding_user_prompt(state: DashboardManualChartGraphState) -> str:
    return "\n".join([
        "请先理解当前手动图表配置表达的分析意图。",
        "",
        _dashboard_config_prompt(
            state["request"],
            state["datasource"],
            "",
            "",
        ),
    ])


def _dashboard_diagnosis_user_prompt(state: DashboardManualChartGraphState) -> str:
    request = state["request"]
    datasource = state["datasource"]
    return "\n".join([
        "请诊断当前配置是否能表达 understand_config 节点理解出的用户意图。",
        "工作顺序：1) 先复述当前配置表达的分析意图；2) 对照业务口径/字段字典/事件字典检查缺什么；3) 用当前配置器控件给出逐条配置方式。",
        "如果用户当前配置表达的是 ARPU/ARPPU/付费率/留存/转化率等复合指标，建议里要拆成基础分析指标和计算指标：例如分子、分母分别怎么配，计算指标怎么选左指标/运算符/右指标/倍率/别名。",
        "如果一个指标需要多个筛选条件，要逐条输出：分析指标N筛选条件1、分析指标N筛选条件2；不要合并成一句。",
        "",
        "<understood-intent>",
        _safe_json(state.get("config_summary") or {}),
        "</understood-intent>",
        "",
        _dashboard_config_prompt(
            request,
            datasource,
            state.get("data_skill", ""),
            state.get("tracking_config", ""),
        ),
    ])


def _dashboard_sql_system_prompt() -> str:
    return (
        "你是 BI 手动看板 SQL 生成节点。诊断节点已经通过，你只负责根据当前配置生成只读 SELECT SQL。\n"
        "必须使用配置里的时间字段、时间粒度、指标、筛选、分组、计算指标；time.field + time.grain 要生成日期维度；groups 只生成额外维度。不要编造未提供字段。只能输出单个 JSON 对象："
        '{"success":true,"sql":"SELECT ...","tables":["..."],"chart_type":"table|line|bar|column|pie|area|metric|scatter|heatmap|funnel|sankey|treemap","brief":"图表标题","intent":"一句话用户意图","message":"","advice":"","issues":[],"suggestions":[]}。'
    )


def _dashboard_sql_user_prompt(state: DashboardManualChartGraphState) -> str:
    request = state["request"]
    datasource = state["datasource"]
    diagnosis = state.get("diagnosis")
    return "\n".join([
        "诊断已通过，请生成 SQL。",
        "",
        "<diagnosis>",
        _safe_json(diagnosis.model_dump() if diagnosis else {}),
        "</diagnosis>",
        "",
        "<understood-intent>",
        _safe_json(state.get("config_summary") or {}),
        "</understood-intent>",
        "",
        _dashboard_config_prompt(
            request,
            datasource,
            state.get("data_skill", ""),
            state.get("tracking_config", ""),
        ),
    ])


def _append_trace(state: DashboardManualChartGraphState, node: str, status: str = "ok") -> list[dict[str, Any]]:
    trace = list(state.get("graph_trace") or [])
    trace.append({"node": node, "status": status})
    return trace


def _invoke_llm_json(llm: Any, messages: list[Any], require_sql: bool = True) -> DashboardAiSqlGenerateResponse:
    full_text = ""
    for chunk in llm.stream(messages):
        full_text += _text_chunk_content(getattr(chunk, "content", ""))
    AppLogUtil.info(f"Dashboard manual chart graph raw node result: {full_text}")
    return _response_from_model_text(full_text, require_sql=require_sql)


async def _async_invoke_llm_json(
    llm: Any,
    messages: list[Any],
    require_sql: bool = True,
) -> DashboardAiSqlGenerateResponse:
    full_text = ""
    if hasattr(llm, "astream"):
        async for chunk in llm.astream(messages):
            full_text += _text_chunk_content(getattr(chunk, "content", chunk))
    elif hasattr(llm, "ainvoke"):
        result = await llm.ainvoke(messages)
        full_text = _text_chunk_content(getattr(result, "content", result))
    else:
        return await to_thread(_invoke_llm_json, llm, messages, require_sql)
    AppLogUtil.info(f"Dashboard manual chart graph raw node result: {full_text}")
    return _response_from_model_text(full_text, require_sql=require_sql)


def _node_collect_context(state: DashboardManualChartGraphState) -> dict[str, Any]:
    session = state["session"]
    current_user = state["current_user"]
    request = state["request"]

    if not request.datasource:
        raise HTTPException(status_code=400, detail="Dashboard datasource is required")
    if not has_datasource_access(session, current_user, request.datasource):
        raise HTTPException(status_code=403, detail=f"当前用户无权访问项目 {request.datasource}")

    datasource = session.get(CoreDatasource, int(request.datasource))
    if datasource is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    tenant_id = require_current_tenant_id(current_user)
    question_text = _dashboard_config_prompt(request, datasource, "", "")
    data_skill, _skill_list, skill_model_id = find_data_skills(
        session,
        int(request.datasource),
        CustomPromptTargetScopeEnum.SMART_QA,
        request.data_skill_id,
        getattr(current_user, "id", None),
        is_system_admin(current_user),
        tenant_id,
        question=question_text,
        can_manage_public=_can_manage_tenant_prompt_runtime(current_user),
        can_manage_platform_public=_can_manage_platform_prompt_runtime(current_user),
    )
    tracking_config, _tracking_list = find_tracking_prompt_context(session, tenant_id, int(request.datasource))
    return {
        "datasource": datasource,
        "tenant_id": tenant_id,
        "data_skill": data_skill,
        "tracking_config": tracking_config,
        "skill_model_id": skill_model_id,
        "graph_trace": _append_trace(state, "collect_context"),
        "last_node": "collect_context",
    }


async def _async_node_understand_config(state: DashboardManualChartGraphState) -> dict[str, Any]:
    request = state["request"]
    context = dict(request.context or {})
    metrics = context.get("metrics") if isinstance(context.get("metrics"), list) else []
    groups = context.get("groups") if isinstance(context.get("groups"), list) else []
    filters = context.get("filters") if isinstance(context.get("filters"), dict) else {}
    summary = {
        "intent": (request.intent or "").strip(),
        "chart_type": request.chart_type or context.get("chart", {}).get("type"),
        "metric_count": len(metrics),
        "group_count": len(groups),
        "has_filters": bool(filters.get("rules")),
        "selected_field_count": len(context.get("selectedFields") or []),
    }
    try:
        config = await get_default_config(state.get("skill_model_id"))
        llm = LLMFactory.create_llm(config).llm
        understanding = await _async_invoke_llm_json(llm, [
            SystemMessage(content=_dashboard_understanding_system_prompt()),
            HumanMessage(content=_dashboard_understanding_user_prompt(state)),
        ], require_sql=False)
        summary["understood_intent"] = understanding.intent
        summary["understanding_message"] = understanding.message
        summary["uncertainties"] = list(understanding.issues or [])
        summary["raw"] = understanding.raw
    except Exception as exc:
        AppLogUtil.warning(f"Dashboard manual chart understand_config fallback used: {exc}")
        summary["understanding_failed"] = True
        summary["understanding_error"] = str(exc)
    return {
        "config_summary": summary,
        "graph_trace": _append_trace(state, "understand_config"),
        "last_node": "understand_config",
    }


async def _async_node_diagnose_config(state: DashboardManualChartGraphState) -> dict[str, Any]:
    config = await get_default_config(state.get("skill_model_id"))
    llm = LLMFactory.create_llm(config).llm
    response = await _async_invoke_llm_json(llm, [
        SystemMessage(content=_dashboard_diagnosis_system_prompt()),
        HumanMessage(content=_dashboard_diagnosis_user_prompt(state)),
    ], require_sql=False)
    response.sql = ""
    if not response.intent:
        response.intent = str((state.get("config_summary") or {}).get("understood_intent") or "")
    return {
        "diagnosis": response,
        "response": response if response.success is False else state.get("response"),
        "graph_trace": _append_trace(state, "diagnose_config"),
        "last_node": "diagnose_config",
    }


def _route_after_diagnosis(state: DashboardManualChartGraphState) -> str:
    diagnosis = state.get("diagnosis")
    if diagnosis is None:
        return "finalize_response"
    if diagnosis.success is False:
        return "finalize_response"
    return "generate_sql"


async def _async_node_generate_sql(state: DashboardManualChartGraphState) -> dict[str, Any]:
    config = await get_default_config(state.get("skill_model_id"))
    llm = LLMFactory.create_llm(config).llm
    response = await _async_invoke_llm_json(llm, [
        SystemMessage(content=_dashboard_sql_system_prompt()),
        HumanMessage(content=_dashboard_sql_user_prompt(state)),
    ])
    diagnosis = state.get("diagnosis")
    if diagnosis:
        response.intent = response.intent or diagnosis.intent
    return {
        "response": response,
        "graph_trace": _append_trace(state, "generate_sql"),
        "last_node": "generate_sql",
    }


def _node_validate_sql(state: DashboardManualChartGraphState) -> dict[str, Any]:
    response = state.get("response") or DashboardAiSqlGenerateResponse(success=False)
    sql = (response.sql or "").strip()
    if not sql:
        response.success = False
        response.message = response.message or "Agent 未生成 SQL。"
        response.advice = response.advice or "按建议补全配置后再生成。"
    elif not re.match(r"^\s*(select|with)\b", sql, flags=re.IGNORECASE):
        response.success = False
        response.message = "SQL 不是只读查询。"
        response.advice = "只能生成 SELECT/WITH 查询，请重新生成。"
        response.issues = list(response.issues or []) + ["生成 SQL 不是只读查询。"]
    else:
        response.success = True
    return {
        "response": response,
        "graph_trace": _append_trace(state, "validate_sql"),
        "last_node": "validate_sql",
    }


def _node_finalize_response(state: DashboardManualChartGraphState) -> dict[str, Any]:
    response = state.get("response") or state.get("diagnosis") or DashboardAiSqlGenerateResponse(
        success=False,
        message="Agent 没有返回可用结果。",
        advice="请补充生成意图或检查配置后重试。",
    )
    return {
        "response": response,
        "graph_trace": _append_trace(state, "finalize_response"),
        "last_node": "finalize_response",
    }


def _build_manual_chart_graph():
    graph = StateGraph(DashboardManualChartGraphState)
    graph.add_node("collect_context", _node_collect_context)
    graph.add_node("understand_config", _async_node_understand_config)
    graph.add_node("diagnose_config", _async_node_diagnose_config)
    graph.add_node("generate_sql", _async_node_generate_sql)
    graph.add_node("validate_sql", _node_validate_sql)
    graph.add_node("finalize_response", _node_finalize_response)
    graph.set_entry_point("collect_context")
    graph.add_edge("collect_context", "understand_config")
    graph.add_edge("understand_config", "diagnose_config")
    graph.add_conditional_edges("diagnose_config", _route_after_diagnosis)
    graph.add_edge("generate_sql", "validate_sql")
    graph.add_edge("validate_sql", "finalize_response")
    graph.add_edge("finalize_response", END)
    return graph.compile()


MANUAL_CHART_GRAPH = _build_manual_chart_graph()


async def generate_dashboard_ai_sql(
        session: SessionDep,
        current_user: CurrentUser,
        request: DashboardAiSqlGenerateRequest,
) -> DashboardAiSqlGenerateResponse:
    """
    是什么：根据手动看板配置运行专用 Agent graph。
    谁调用：dashboard AI 生成 SQL 接口调用。
    做了什么：按 collect_context -> understand_config -> diagnose_config -> generate_sql -> validate_sql -> finalize_response 编排。
    """
    try:
        final_state = await MANUAL_CHART_GRAPH.ainvoke({
            "session": session,
            "current_user": current_user,
            "request": request,
            "graph_trace": [],
        })
    except Exception as exc:
        AppLogUtil.error(f"Dashboard manual chart graph failed: {exc}")
        raise HTTPException(status_code=500, detail=f"AI 生成 SQL 失败：{exc}") from exc

    trace = final_state.get("graph_trace") or []
    AppLogUtil.info(f"Dashboard manual chart graph trace: {trace}")
    response = final_state.get("response")
    if isinstance(response, DashboardAiSqlGenerateResponse):
        return response
    return DashboardAiSqlGenerateResponse(
        success=False,
        message="Agent 没有返回可用结果。",
        advice="请补充生成意图或检查配置后重试。",
    )
