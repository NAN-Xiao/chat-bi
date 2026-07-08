"""
脚本说明：这个脚本封装手动看板里的 AI SQL 生成能力。
"""
from __future__ import annotations

import inspect
import json
import re
import time
from asyncio import to_thread
from datetime import datetime
from typing import Any, TypedDict

import orjson
from fastapi import HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from apps.ai_model.model_factory import LLMFactory, get_default_config
from apps.chat.curd.custom_prompt import CustomPromptTargetScopeEnum
from apps.dashboard.models.dashboard_model import DashboardAiSqlGenerateRequest, DashboardAiSqlGenerateResponse
from apps.datasource.crud.sql_engine import BusinessSqlContext, BusinessSqlContextService
from apps.datasource.models.datasource import CoreDatasource
from apps.system.crud.tenant import TENANT_ADMIN_ROLES, normalize_tenant_role
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
    business_sql_context: BusinessSqlContext
    schema: str
    sql_dialect: str | None
    allowed_tables: list[str]
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
        "时间范围只是查询窗口，不是业务口径本身；不能因为未配置时间范围、时间范围较宽或时间范围与推荐窗口不同就让 success=false，除非用户意图明确要求某个时间窗口且当前配置与之冲突。\n"
        "事件指标自带事件名限定；不要因为没有额外事件筛选条件、未在 rules 里再限定 event，或没有把 event 写成单独筛选条件就让 success=false。\n"
        "一个分析指标可以有多个筛选条件或条件组；不要把多个筛选条件合并成一句含糊建议。涉及复合指标时，要同时说明“分析指标”和“计算指标”怎么配置。\n"
        "配置建议必须具体到界面动作，例如："
        "“时间范围：字段选「创建时间 orders.created_at」，粒度选「按天」，范围选「过去7天」”；"
        "“分析指标1：字段选「用户ID orders.user_id」，聚合选「去重数」，计算字段选「用户ID orders.user_id」，别名填「业务指标名」”；"
        "“分析指标1筛选条件：字段选「订单状态 orders.status」，条件选「等于」，最右侧值输入框手动填「业务口径里的状态值」”；"
        "“计算指标1：左侧选「指标A」，运算选「除以」，右侧选「指标B」，倍率填「1」，别名填「业务指标名」”；"
        "“分组项：添加「国家 users.country」”。"
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
        *,
        schema: str = "",
        sql_dialect: str | None = None,
        allowed_tables: list[str] | None = None,
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
        f"SQL 方言：{sql_dialect or datasource.type or datasource.type_name or 'unknown'}",
        "",
        "<business-sql-schema>",
        _trim_text(schema, 12000),
        "</business-sql-schema>",
        "",
        "<allowed-tables>",
        _safe_json(allowed_tables or []),
        "</allowed-tables>",
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
        "当前配置器可配置的控件：时间范围(time.field/time.grain/time.range)、分析指标(metrics: 字段/聚合/计算字段/别名/指标内筛选树)、公式指标(formulaMetrics/calculatedMetrics: token 化公式/小数/别名)、全局筛选、分组项(groups)。",
        "配置器规则：time.field + time.grain 会自动生成日期维度；groups 只表示额外维度，不包含时间维度也不是错误。",
        "公式指标规则：formulaMetrics[].tokens 是公式 token 列表；token.type=metric 时只能引用 metrics 中已有指标，并使用 metricAlias 对应的基础指标结果；token.type=atomicMetric 时表示公式内部直接插入的事件指标，结构与 metrics 单项类似，必须按它自己的 field/metric/aggregation/filters 生成基础聚合；token.type=operator 只能是 + - * /；token.type=paren 只能是 ( )；token.type=number 只能是数字常量。",
        "生成公式指标 SQL 时，必须先在内层/CTE 计算全部基础 metrics 和公式内 atomicMetric，再在外层 SELECT 中按 token 公式计算公式指标；除法必须使用 NULLIF(分母表达式, 0) 防止除零；小数位必须用 ROUND(公式表达式, decimalPlaces)；公式指标别名使用 alias。",
        "当 metrics.field.kind 为 tracking-event 时，它表示从“事件参数对照”中选择的业务事件；生成 SQL 时必须使用 metrics.field.eventTable 和 metrics.field.eventNameField（或 table/field）定位事件名字段，并添加“事件名字段 = metrics.field.eventName”的过滤条件。",
        "如果多个 tracking-event 指标来自同一张事件表、同一个事件名字段，但 eventName 不同，必须在 WHERE 中使用“事件名字段 IN (这些 eventName)”先收窄扫描范围，再在各指标表达式里用 CASE WHEN 区分每个事件；不要只在 COUNT/SUM CASE 里写事件条件而让 WHERE 扫全表。",
        "当指标内筛选 rules[].field.kind 为 tracking-property 时，它表示该业务事件下的事件参数；生成 SQL 时必须按 rules[].field.sourceField/jsonPath 或 field 在事件明细行中取值，再应用对应 operator/value。",
        "指标内筛选 rules 是可选配置；没有 rules 或 rules 为空时不是配置缺失，不要要求补筛选条件，不要生成空 WHERE/AND/CASE 条件；只有 rules 里存在有效字段、操作符和值时才应用该筛选。",
        "只允许使用 manual-dashboard-context 里的 selectedFields/metrics/formulaMetrics/calculatedMetrics/groups/filters 字段信息生成 SQL；不要编造未提供字段。",
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
            schema=state.get("schema", ""),
            sql_dialect=state.get("sql_dialect"),
            allowed_tables=state.get("allowed_tables") or [],
        ),
    ])


def _dashboard_sql_system_prompt() -> str:
    return (
        "你是 BI 手动看板 SQL 生成节点。诊断节点已经通过，你只负责根据当前配置生成只读 SELECT SQL。\n"
        "必须使用配置里的时间字段、时间粒度、指标、筛选、分组、计算指标；time.field + time.grain 要生成日期维度；groups 只生成额外维度。不要编造未提供字段。\n"
        "当用户问题或当前配置涉及复杂分析，例如留存、转化、活跃、复购、漏斗、cohort 分析、分组比率、时间窗口对比时，优先使用 CTE 分层结构。"
        "CTE 只是组织结构范式，所有表名、字段名、事件名、日期表达式、过滤条件、分子分母和成熟窗口必须来自当前配置、business-sql-schema、data-skill 或用户明确规则；不得照抄占位符，也不得编造未提供字段。\n"
        "推荐 SQL 结构范式：\n"
        "WITH bounds AS (\n"
        "    -- 1. 时间边界层：统一管理查询窗口和数据成熟窗口\n"
        "    SELECT\n"
        "        CAST(<start_date> AS DATE) AS start_dt,\n"
        "        CAST(<end_date> AS DATE) AS end_dt,\n"
        "        CAST(<data_end_date> AS DATE) AS data_end_dt\n"
        "),\n"
        "cohort AS (\n"
        "    -- 2. 分母人群层：定义本次分析的基准对象\n"
        "    SELECT\n"
        "        <entity_id> AS entity_id,\n"
        "        <cohort_date_expr> AS cohort_dt,\n"
        "        <dimension_1> AS dimension_1,\n"
        "        <dimension_2> AS dimension_2\n"
        "    FROM <cohort_source_table> s\n"
        "    JOIN bounds b\n"
        "      ON <cohort_date_expr> BETWEEN b.start_dt AND b.end_dt\n"
        "    WHERE\n"
        "        <entity_id> IS NOT NULL\n"
        "        AND <cohort_filter_conditions>\n"
        "    GROUP BY\n"
        "        <entity_id>,\n"
        "        <cohort_date_expr>,\n"
        "        <dimension_1>,\n"
        "        <dimension_2>\n"
        "),\n"
        "behavior AS (\n"
        "    -- 3. 行为事实层：定义用于计算分子或后续状态的行为\n"
        "    SELECT\n"
        "        <entity_id> AS entity_id,\n"
        "        <behavior_date_expr> AS behavior_dt,\n"
        "        <behavior_type_or_value> AS behavior_value\n"
        "    FROM <behavior_source_table> a\n"
        "    JOIN bounds b\n"
        "      ON <behavior_date_expr> BETWEEN b.start_dt AND b.data_end_dt\n"
        "    WHERE\n"
        "        <entity_id> IS NOT NULL\n"
        "        AND <behavior_filter_conditions>\n"
        "    GROUP BY\n"
        "        <entity_id>,\n"
        "        <behavior_date_expr>,\n"
        "        <behavior_type_or_value>\n"
        "),\n"
        "matched AS (\n"
        "    -- 4. 关联判断层：把分母对象与后续行为按业务规则关联\n"
        "    SELECT\n"
        "        c.entity_id,\n"
        "        c.cohort_dt,\n"
        "        c.dimension_1,\n"
        "        c.dimension_2,\n"
        "        b.behavior_dt,\n"
        "        <date_diff_expr>(c.cohort_dt, b.behavior_dt) AS period_offset,\n"
        "        CASE\n"
        "            WHEN b.entity_id IS NOT NULL THEN 1\n"
        "            ELSE 0\n"
        "        END AS is_matched\n"
        "    FROM cohort c\n"
        "    LEFT JOIN behavior b\n"
        "      ON c.entity_id = b.entity_id\n"
        "     AND b.behavior_dt >= c.cohort_dt\n"
        "     AND b.behavior_dt <= <mature_window_expr>\n"
        "),\n"
        "aggregated AS (\n"
        "    -- 5. 指标聚合层：统一计算分母、分子和比率\n"
        "    SELECT\n"
        "        cohort_dt,\n"
        "        dimension_1,\n"
        "        dimension_2,\n"
        "        period_offset,\n"
        "        COUNT(DISTINCT entity_id) AS base_count,\n"
        "        COUNT(DISTINCT CASE WHEN is_matched = 1 THEN entity_id END) AS matched_count,\n"
        "        ROUND(\n"
        "            COUNT(DISTINCT CASE WHEN is_matched = 1 THEN entity_id END) * 100.0\n"
        "            / NULLIF(COUNT(DISTINCT entity_id), 0),\n"
        "            2\n"
        "        ) AS matched_rate\n"
        "    FROM matched\n"
        "    GROUP BY\n"
        "        cohort_dt,\n"
        "        dimension_1,\n"
        "        dimension_2,\n"
        "        period_offset\n"
        ")\n"
        "SELECT\n"
        "    cohort_dt,\n"
        "    dimension_1,\n"
        "    dimension_2,\n"
        "    period_offset,\n"
        "    base_count,\n"
        "    matched_count,\n"
        "    matched_rate\n"
        "FROM aggregated\n"
        "ORDER BY\n"
        "    cohort_dt,\n"
        "    dimension_1,\n"
        "    dimension_2,\n"
        "    period_offset\n"
        "LIMIT <limit_size>;\n"
        "只能输出单个 JSON 对象："
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
            schema=state.get("schema", ""),
            sql_dialect=state.get("sql_dialect"),
            allowed_tables=state.get("allowed_tables") or [],
        ),
    ])


def _append_trace(state: DashboardManualChartGraphState, node: str, status: str = "ok") -> list[dict[str, Any]]:
    trace = list(state.get("graph_trace") or [])
    trace.append({"node": node, "status": status})
    return trace


def _graph_node_log_context(state: DashboardManualChartGraphState) -> dict[str, Any]:
    request = state.get("request")
    current_user = state.get("current_user")
    return {
        "datasource_id": getattr(request, "datasource", None),
        "tenant_id": state.get("tenant_id") or getattr(current_user, "tenant_id", None),
        "user_id": getattr(current_user, "id", None),
    }


def _log_graph_node_timing(
        *,
        node: str,
        status: str,
        elapsed_ms: int,
        state: DashboardManualChartGraphState,
        error: Exception | None = None,
) -> None:
    context = _graph_node_log_context(state)
    message = (
        f"Dashboard manual chart graph node {'failed' if error else 'finished'}: "
        f"node={node}, "
        f"status={status}, "
        f"elapsed_ms={elapsed_ms}, "
        f"datasource_id={context['datasource_id']}, "
        f"tenant_id={context['tenant_id']}, "
        f"user_id={context['user_id']}"
    )
    if error is not None:
        message += f", error={error}"
        AppLogUtil.warning(message)
        return
    AppLogUtil.info(message)


async def _timed_graph_node(node: str, handler: Any, state: DashboardManualChartGraphState) -> dict[str, Any]:
    started_at = time.perf_counter()
    try:
        result = handler(state)
        if inspect.isawaitable(result):
            result = await result
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        _log_graph_node_timing(
            node=node,
            status="ok",
            elapsed_ms=elapsed_ms,
            state=state,
        )
        return result
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        _log_graph_node_timing(
            node=node,
            status="error",
            elapsed_ms=elapsed_ms,
            state=state,
            error=exc,
        )
        raise


def _timed_graph_node_sync(node: str, handler: Any, state: DashboardManualChartGraphState) -> dict[str, Any]:
    started_at = time.perf_counter()
    try:
        result = handler(state)
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        _log_graph_node_timing(
            node=node,
            status="ok",
            elapsed_ms=elapsed_ms,
            state=state,
        )
        return result
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        _log_graph_node_timing(
            node=node,
            status="error",
            elapsed_ms=elapsed_ms,
            state=state,
            error=exc,
        )
        raise


def _timed_node(node: str, handler: Any):
    if inspect.iscoroutinefunction(handler):
        async def _async_wrapped(state: DashboardManualChartGraphState) -> dict[str, Any]:
            return await _timed_graph_node(node, handler, state)

        return _async_wrapped

    def _wrapped(state: DashboardManualChartGraphState) -> dict[str, Any]:
        return _timed_graph_node_sync(node, handler, state)

    return _wrapped


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

    tenant_id = require_current_tenant_id(current_user)
    seed_datasource = session.get(CoreDatasource, int(request.datasource))
    if seed_datasource is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    question_text = _dashboard_config_prompt(request, seed_datasource, "", "")
    business_context = BusinessSqlContextService.build(
        session=session,
        current_user=current_user,
        tenant_id=tenant_id,
        datasource_id=int(request.datasource),
        question=question_text,
        target_scope=CustomPromptTargetScopeEnum.SMART_QA,
        data_skill_id=request.data_skill_id,
        embedding=False,
        can_manage_all=is_system_admin(current_user),
        can_manage_public=_can_manage_tenant_prompt_runtime(current_user),
        can_manage_platform_public=_can_manage_platform_prompt_runtime(current_user),
    )
    return {
        "datasource": business_context.datasource,
        "tenant_id": tenant_id,
        "business_sql_context": business_context,
        "schema": business_context.schema,
        "sql_dialect": business_context.sql_dialect,
        "allowed_tables": business_context.allowed_tables,
        "data_skill": business_context.data_skill,
        "tracking_config": business_context.tracking_config,
        "skill_model_id": business_context.skill_model_id,
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
    graph.add_node("collect_context", _timed_node("collect_context", _node_collect_context))
    graph.add_node("understand_config", _timed_node("understand_config", _async_node_understand_config))
    graph.add_node("diagnose_config", _timed_node("diagnose_config", _async_node_diagnose_config))
    graph.add_node("generate_sql", _timed_node("generate_sql", _async_node_generate_sql))
    graph.add_node("validate_sql", _timed_node("validate_sql", _node_validate_sql))
    graph.add_node("finalize_response", _timed_node("finalize_response", _node_finalize_response))
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
