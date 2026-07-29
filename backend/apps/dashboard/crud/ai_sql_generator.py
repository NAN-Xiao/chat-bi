"""
脚本说明：这个脚本封装手动看板里的 AI SQL 生成能力。
"""
from __future__ import annotations

import copy
import inspect
import json
import re
import time
from asyncio import to_thread
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

import orjson
from fastapi import HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from apps.ai_model.model_factory import LLMFactory, get_default_config
from apps.chat.curd.custom_prompt import CustomPromptTargetScopeEnum
from apps.dashboard.crud.dashboard_date_filter import (
    dashboard_date_parameter_tokens,
    validate_dashboard_date_parameter_sql,
)
from apps.dashboard.models.dashboard_model import (
    DashboardAiSqlGenerateRequest,
    DashboardAiSqlGenerateResponse,
)
from apps.datasource.crud.sql_engine import (
    BusinessSqlContext,
    BusinessSqlContextService,
)
from apps.datasource.models.datasource import CoreDatasource
from apps.db.db import check_sql_read
from apps.system.crud.tenant import TENANT_ADMIN_ROLES, normalize_tenant_role
from apps.system.crud.tracking_config import get_tracking_config
from apps.system.crud.tracking_expression import compile_tracking_json_expression
from apps.system.crud.user import (
    is_platform_admin,
    is_platform_workspace_delegate,
    is_system_admin,
)
from apps.system.schemas.access_context import require_current_tenant_id
from common.core.deps import CurrentUser, SessionDep
from common.sql_json_paths import extract_sql_json_field_pairs, normalize_json_path
from common.utils.utils import AppLogUtil, extract_nested_json

DASHBOARD_AI_SQL_LLM_OUTPUT_FILE = (
    Path(__file__).resolve().parents[4] / "logs" / "dashboard_ai_sql_llm_outputs.jsonl"
)
_DATABASE_CURRENT_DATE_PATTERN = re.compile(
    r"\b(?:curdate\s*\(|current_date\b|now\s*\(|current_timestamp\b|localtime\b|localtimestamp\b|getdate\s*\(|getutcdate\s*\()",
    flags=re.IGNORECASE,
)


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
    allowed_fields_by_table: dict[str, set[str]]
    data_skill: str
    tracking_config: str
    event_scope: dict[str, Any]
    skill_model_id: int | None
    normalized_config: dict[str, Any]
    formula_ir: dict[str, Any]
    json_subfield_requirements: list[dict[str, str]]
    validation_result: DashboardAiSqlGenerateResponse
    sql_plan: dict[str, Any]
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


def _write_llm_output_debug_file(node: str, full_text: str, require_sql: bool) -> None:
    """
    是什么：把手动看板生成 SQL 过程中的 LLM 原始输出追加到本地调试文件。
    """
    try:
        output_file = Path(DASHBOARD_AI_SQL_LLM_OUTPUT_FILE)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "created_at": datetime.now().isoformat(timespec="milliseconds"),
            "node": node,
            "require_sql": require_sql,
            "output": full_text or "",
        }
        with output_file.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False, default=_json_default) + "\n")
    except Exception as exc:
        AppLogUtil.warning(f"Dashboard manual chart LLM output debug file write failed: {exc}")


async def _create_dashboard_ai_sql_llm(skill_model_id: int | None = None) -> Any:
    """
    是什么：创建手动看板 AI SQL 生成专用 LLM，并关闭模型思考输出。
    """
    config = await get_default_config(skill_model_id)
    additional_params = dict(config.additional_params or {})
    extra_body = dict(additional_params.get("extra_body") or {})
    extra_body["enable_thinking"] = False
    additional_params["extra_body"] = extra_body
    config = config.model_copy(update={"additional_params": additional_params})
    return LLMFactory.create_llm(config).llm


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
    warnings = payload.get("warnings") if isinstance(payload.get("warnings"), list) else []
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
        warnings=[str(item) for item in warnings if str(item or "").strip()],
        suggestions=[str(item) for item in suggestions if str(item or "").strip()],
        raw=text or "",
    )


def _tracking_event_name_from_field(field: Any) -> str:
    if isinstance(field, str):
        parts = field.split(":")
        if len(parts) >= 3 and parts[0] == "tracking-event":
            return parts[-1].strip()
        return ""
    if isinstance(field, dict) and str(field.get("kind") or "") == "tracking-event":
        return str(field.get("eventName") or field.get("event_name") or "").strip()
    return ""


_FORMULA_OPERATORS = {"+", "-", "*", "/"}
_FORMULA_PRECEDENCE = {"+": 1, "-": 1, "*": 2, "/": 2}
_SUPPORTED_METRIC_AGGREGATIONS = {"count", "count_distinct", "sum", "avg", "max", "min"}
_NUMERIC_TYPE_KEYWORDS = (
    "int", "float", "double", "decimal", "number", "numeric", "real",
    "数值", "数字", "整数", "小数",
)
_NON_NUMERIC_TYPE_KEYWORDS = (
    "char", "text", "string", "date", "time", "bool", "json",
    "文本", "字符串", "字符", "日期", "时间", "布尔", "对象", "数组",
)


def _unique_text_items(items: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _list_dict_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _formula_metric_items_from_context(context: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for key in ("formulaMetrics", "calculatedMetrics"):
        for item in _list_dict_items(context.get(key)):
            item_id = str(item.get("id") or "").strip()
            fingerprint = item_id or _safe_json(item.get("tokens") or [])
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            items.append(item)
    return items


def _metric_item_id(metric: dict[str, Any], index: int) -> str:
    return str(metric.get("id") or metric.get("alias") or metric.get("label") or f"metric_{index + 1}").strip()


def _formula_item_id(formula: dict[str, Any], index: int) -> str:
    return str(formula.get("id") or formula.get("alias") or f"formula_{index + 1}").strip()


def _field_table_name(field: Any) -> str:
    if isinstance(field, dict):
        if str(field.get("kind") or "") == "tracking-event":
            return str(field.get("eventTable") or field.get("event_table") or field.get("table") or "").strip()
        return str(field.get("table") or "").strip()
    text = str(field or "").strip()
    if text.startswith("tracking-event:") or text.startswith("tracking-property:"):
        parts = text.split(":")
        if len(parts) >= 2:
            table_field = parts[1]
            return table_field.split(".", 1)[0].strip()
    if "." in text:
        return text.split(".", 1)[0].strip()
    return ""


def _field_reference_text(field: Any) -> str:
    if isinstance(field, dict):
        return " ".join([
            str(field.get("category") or ""),
            str(field.get("type") or ""),
            str(field.get("fieldType") or ""),
            str(field.get("field_type") or ""),
            str(field.get("propertyType") or ""),
            str(field.get("property_type") or ""),
            str(field.get("semanticType") or ""),
            str(field.get("semantic_type") or ""),
        ]).lower()
    return str(field or "").lower()


def _text_has_numeric_type_hint(text: str) -> bool:
    return any(keyword in text for keyword in _NUMERIC_TYPE_KEYWORDS)


def _text_has_non_numeric_type_hint(text: str) -> bool:
    return any(keyword in text for keyword in _NON_NUMERIC_TYPE_KEYWORDS)


def _field_has_resolvable_reference(field: Any) -> bool:
    if isinstance(field, str):
        return bool(field.strip())
    if not isinstance(field, dict):
        return False
    if str(field.get("kind") or "") == "tracking-event":
        return bool(
            (field.get("eventTable") or field.get("event_table") or field.get("table"))
            and (field.get("eventNameField") or field.get("event_name_field") or field.get("field"))
            and (field.get("eventName") or field.get("event_name"))
        )
    return any(
        str(field.get(key) or "").strip()
        for key in ("field", "sourceField", "source_field", "expression", "value")
    )


def _tracking_event_metadata_issues(field: Any, label: str) -> list[str]:
    issues: list[str] = []
    if isinstance(field, str):
        if not field.startswith("tracking-event:"):
            return []
        parts = field.split(":")
        if len(parts) < 3 or not parts[-1].strip():
            issues.append(f"{label} 缺少事件名。")
        if len(parts) < 2 or "." not in parts[1]:
            issues.append(f"{label} 缺少事件表或事件名字段。")
        return issues
    if not isinstance(field, dict) or str(field.get("kind") or "") != "tracking-event":
        return []
    if not str(field.get("eventTable") or field.get("event_table") or field.get("table") or "").strip():
        issues.append(f"{label} 缺少事件表。")
    if not str(field.get("eventNameField") or field.get("event_name_field") or field.get("field") or "").strip():
        issues.append(f"{label} 缺少事件名字段。")
    if not str(field.get("eventName") or field.get("event_name") or "").strip():
        issues.append(f"{label} 缺少事件名。")
    return issues


def _json_subfield_mapping_issues(field: Any, label: str) -> list[str]:
    if not isinstance(field, dict):
        return []
    source_field = str(field.get("sourceField") or field.get("source_field") or "").strip()
    json_path = str(field.get("jsonPath") or field.get("json_path") or "").strip()
    is_json_subfield = bool(
        field.get("isJsonSubfield") is True
        or field.get("is_json_subfield") is True
        or (source_field and json_path)
    )
    if not is_json_subfield:
        return []
    missing = [
        key
        for key, value in (
            ("sourceField", field.get("sourceField") or field.get("source_field")),
            ("jsonPath", field.get("jsonPath") or field.get("json_path")),
            ("expression", field.get("expression")),
        )
        if not str(value or "").strip()
    ]
    if not missing:
        return []
    return [f"{label} 的 JSON 字段映射不完整，缺少：{'、'.join(missing)}。请重新选择字段。"]


def _compile_json_subfield_field(field: Any, datasource_type: str | None) -> Any:
    if not isinstance(field, dict):
        return field
    source_field = str(field.get("sourceField") or field.get("source_field") or "").strip()
    json_path = str(field.get("jsonPath") or field.get("json_path") or "").strip()
    if not source_field or not json_path or not datasource_type:
        return field
    compiled = copy.deepcopy(field)
    expression = compile_tracking_json_expression(
        _field_table_name(compiled),
        source_field,
        json_path,
        str(compiled.get("semanticType") or compiled.get("semantic_type") or compiled.get("category") or ""),
        datasource_type,
    )
    compiled["sourceField"] = source_field
    compiled["jsonPath"] = json_path
    compiled["isJsonSubfield"] = True
    compiled["expression"] = expression
    return compiled


def _compile_json_subfield_fields(value: Any, datasource_type: str | None) -> Any:
    if isinstance(value, list):
        return [_compile_json_subfield_fields(item, datasource_type) for item in value]
    if not isinstance(value, dict):
        return value
    compiled = _compile_json_subfield_field(value, datasource_type)
    return {
        key: _compile_json_subfield_fields(item, datasource_type)
        for key, item in compiled.items()
    }


def _normalized_json_path(value: Any, *, postgres: bool = False) -> str:
    return normalize_json_path(value, postgres=postgres)


def _sql_json_field_pairs(sql: str, dialect: str) -> tuple[set[tuple[str, str]], list[str]]:
    return extract_sql_json_field_pairs(sql, dialect)


def _json_subfield_requirements(*values: Any) -> list[dict[str, str]]:
    requirements: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return
        source_field = str(value.get("sourceField") or value.get("source_field") or "").strip()
        json_path = _normalized_json_path(value.get("jsonPath") or value.get("json_path"))
        is_json_subfield = bool(
            value.get("isJsonSubfield") is True
            or value.get("is_json_subfield") is True
            or (source_field and json_path)
        )
        if is_json_subfield and source_field and json_path:
            key = (source_field, json_path)
            if key not in seen:
                seen.add(key)
                requirements.append({
                    "label": str(value.get("displayName") or value.get("label") or value.get("field") or "JSON 字段"),
                    "source_field": source_field,
                    "json_path": json_path,
                })
        for item in value.values():
            visit(item)

    for value in values:
        visit(value)
    return requirements


def _json_subfield_sql_issues(
        sql: str,
        requirements: list[dict[str, str]],
        *,
        dialect: str,
) -> list[str]:
    if not requirements:
        return []
    actual_pairs, parse_issues = _sql_json_field_pairs(sql, dialect)
    if parse_issues:
        return parse_issues
    expected_pairs = {
        (str(item.get("source_field") or "").strip(), _normalized_json_path(item.get("json_path")))
        for item in requirements
    }
    issues: list[str] = []
    for item in requirements:
        expected = (str(item.get("source_field") or "").strip(), _normalized_json_path(item.get("json_path")))
        if expected not in actual_pairs:
            issues.append(
                f"{item.get('label') or 'JSON 字段'}：JSON 字段 "
                f"{expected[0]} + {expected[1]} 未出现在生成 SQL 中。"
            )
    for source_field, json_path in sorted(actual_pairs - expected_pairs):
        issues.append(f"生成 SQL 使用了未配置的 JSON 列或路径：{source_field} + {json_path}。")
    return _unique_text_items(issues)


def _metric_measure_field(metric: dict[str, Any]) -> Any:
    return metric.get("metricField") or metric.get("metric") or metric.get("measureField")


def _aggregation_value(metric: dict[str, Any]) -> str:
    return str(metric.get("aggregation") or "count").strip().lower()


def _field_is_known_non_numeric(field: Any) -> bool:
    if not isinstance(field, dict):
        return False
    category = str(field.get("category") or "").strip().lower()
    if category:
        if _text_has_numeric_type_hint(category) or category in {"measure"}:
            return False
        if _text_has_non_numeric_type_hint(category):
            return True
    type_text = _field_reference_text(field)
    if not type_text.strip():
        return False
    if _text_has_numeric_type_hint(type_text):
        return False
    return _text_has_non_numeric_type_hint(type_text)


def _validate_metric_item(
        metric: dict[str, Any],
        label: str,
        *,
        require_aggregation: bool = False,
        require_metric_field_for_count: bool = False,
) -> list[str]:
    issues: list[str] = []
    raw_aggregation = str(metric.get("aggregation") or "").strip().lower()
    aggregation = raw_aggregation or "count"
    field = metric.get("field")
    metric_field = _metric_measure_field(metric)
    if require_aggregation and not raw_aggregation:
        issues.append(f"{label} 缺少聚合方式。")
    if aggregation not in _SUPPORTED_METRIC_AGGREGATIONS:
        issues.append(f"{label} 使用了不支持的聚合方式：{aggregation}。")
    if not field:
        issues.append(f"{label} 缺少事件字段或分析字段。")
    elif not _field_has_resolvable_reference(field):
        issues.append(f"{label} 的分析字段配置不完整。")
    issues.extend(_tracking_event_metadata_issues(field, label))
    issues.extend(_json_subfield_mapping_issues(field, label))
    should_require_metric_field = aggregation != "count" or require_metric_field_for_count
    if should_require_metric_field and not metric_field:
        issues.append(f"{label} 缺少计算字段。")
    elif should_require_metric_field and not _field_has_resolvable_reference(metric_field):
        issues.append(f"{label} 的计算字段配置不完整。")
    issues.extend(_json_subfield_mapping_issues(metric_field, label))
    for filter_field in _iter_filter_rule_fields(metric.get("filters")):
        issues.extend(_json_subfield_mapping_issues(filter_field, f"{label} 的筛选字段"))
    if aggregation in {"sum", "avg"} and metric_field and _field_is_known_non_numeric(metric_field):
        field_name = str(
            metric_field.get("displayName")
            or metric_field.get("label")
            or metric_field.get("field")
            or metric_field.get("value")
            or metric_field.get("sourceField")
            or metric_field.get("source_field")
            or "当前字段"
        ).strip()
        issues.append(f"{label} 使用 {aggregation} 聚合，但计算字段“{field_name}”不是数值字段。")
    return issues


def _metric_base_ir(
        metric: dict[str, Any],
        *,
        metric_id: str,
        source: str,
) -> dict[str, Any]:
    field = metric.get("field")
    metric_field = _metric_measure_field(metric)
    return {
        "id": metric_id,
        "source": source,
        "event": _tracking_event_name_from_field(field),
        "table": _field_table_name(field) or _field_table_name(metric_field),
        "field": field,
        "metric_field": metric_field,
        "aggregation": _aggregation_value(metric),
        "alias": str(metric.get("alias") or metric.get("label") or metric_id).strip(),
        "label": str(metric.get("label") or metric.get("alias") or metric_id).strip(),
        "filters": metric.get("filters") or [],
    }


def _normalize_manual_config(
        request: DashboardAiSqlGenerateRequest,
        *,
        datasource_type: str | None = None,
) -> dict[str, Any]:
    """
    是什么：把前端手动配置归一化成后端稳定结构，供公式 IR 和确定性校验使用。
    """
    context = _compile_json_subfield_fields(copy.deepcopy(dict(request.context or {})), datasource_type)
    metrics = _list_dict_items(context.get("metrics"))
    formula_metrics = _formula_metric_items_from_context(context)
    time_config = dict(context.get("time") or {}) if isinstance(context.get("time"), dict) else {}
    time_config["date_parameter_type"] = str(
        time_config.get("dateParameterType") or time_config.get("date_parameter_type") or ""
    ).strip()
    time_config["date_expression"] = time_config.get("dateExpression") or time_config.get("date_expression")
    return {
        "chart": context.get("chart") if isinstance(context.get("chart"), dict) else {
            "title": request.title,
            "type": request.chart_type,
        },
        "datasource": context.get("datasource") if isinstance(context.get("datasource"), dict) else {},
        "time": time_config,
        "metrics": metrics,
        "formula_metrics": formula_metrics,
        "groups": _list_dict_items(context.get("groups")),
        "filters": context.get("filters") if isinstance(context.get("filters"), dict) else {},
        "selected_fields": _list_dict_items(context.get("selectedFields")),
        "approximate": context.get("approximate") is True,
        "raw_context": context,
    }


def _formula_token_kind(token: dict[str, Any] | None) -> str:
    if not token:
        return "unknown"
    token_type = token.get("type")
    if token_type in {"metric", "atomicMetric", "number"}:
        return "operand"
    if token_type == "operator":
        return "operator"
    if token_type == "paren" and token.get("value") == "(":
        return "leftParen"
    if token_type == "paren" and token.get("value") == ")":
        return "rightParen"
    return "unknown"


def _is_valid_formula_number(value: Any) -> bool:
    return bool(re.match(r"^(?:\d+(?:\.\d*)?|\.\d+)$", str(value or "").strip()))


def _formula_number_is_zero(value: Any) -> bool:
    try:
        return float(str(value).strip()) == 0
    except Exception:
        return False


def _expression_is_zero_number(expression: dict[str, Any]) -> bool:
    return expression.get("type") == "number" and _formula_number_is_zero(expression.get("value"))


def _expression_has_divide_by_zero(expression: dict[str, Any] | None) -> bool:
    if not isinstance(expression, dict):
        return False
    if expression.get("type") == "binary":
        if expression.get("operator") == "/" and _expression_is_zero_number(expression.get("right") or {}):
            return True
        return (
            _expression_has_divide_by_zero(expression.get("left"))
            or _expression_has_divide_by_zero(expression.get("right"))
        )
    return False


def _apply_formula_operator(values: list[dict[str, Any]], operators: list[str], issues: list[str]) -> None:
    if not operators:
        issues.append("公式运算符缺失。")
        return
    operator = operators.pop()
    if len(values) < 2:
        issues.append("运算符前后缺少指标或数字。")
        return
    right = values.pop()
    left = values.pop()
    values.append({
        "type": "binary",
        "operator": operator,
        "left": left,
        "right": right,
    })


def _parse_formula_expression(
        formula: dict[str, Any],
        *,
        formula_index: int,
        metric_by_id: dict[str, dict[str, Any]],
        formula_metric_ids: set[str],
) -> dict[str, Any]:
    tokens = formula.get("tokens") if isinstance(formula.get("tokens"), list) else []
    formula_id = _formula_item_id(formula, formula_index)
    alias = str(formula.get("alias") or formula_id or f"公式指标{formula_index + 1}").strip()
    issues: list[str] = []
    base_metric_by_id: dict[str, dict[str, Any]] = {}

    if not tokens:
        issues.append("公式不能为空。")

    balance = 0
    previous_kind = "unknown"
    previous_token: dict[str, Any] | None = None
    normalized_tokens: list[dict[str, Any]] = []

    for token in tokens:
        if not isinstance(token, dict):
            issues.append("公式包含无法识别的 token。")
            continue
        token_type = token.get("type")
        current_kind = _formula_token_kind(token)
        if current_kind == "unknown":
            issues.append("公式包含当前版本不支持的 token。")
            continue

        if token_type == "metric":
            metric_id = str(token.get("metricId") or "").strip()
            if metric_id in formula_metric_ids:
                issues.append("第一版暂不支持公式引用另一个公式指标。")
            elif metric_id not in metric_by_id:
                issues.append("公式引用的分析指标不存在。")
        elif token_type == "atomicMetric":
            metric = token.get("metric") if isinstance(token.get("metric"), dict) else {}
            label = str(metric.get("label") or metric.get("alias") or f"{alias} 内事件指标").strip()
            issues.extend(_validate_metric_item(
                metric,
                label,
                require_aggregation=True,
                require_metric_field_for_count=True,
            ))
        elif token_type == "number" and not _is_valid_formula_number(token.get("value")):
            issues.append("数字格式不正确。")
        elif token_type == "operator" and str(token.get("value") or "") not in _FORMULA_OPERATORS:
            issues.append("公式包含当前版本不支持的运算符。")

        if current_kind == "leftParen":
            if previous_kind in {"operand", "rightParen"}:
                issues.append("括号前缺少运算符。")
            balance += 1
        elif current_kind == "rightParen":
            if balance <= 0:
                issues.append("括号不配对。")
            if previous_kind in {"operator", "leftParen", "unknown"}:
                issues.append("右括号前缺少指标或数字。")
            balance -= 1
        elif current_kind == "operator":
            if previous_kind in {"unknown", "operator", "leftParen"}:
                issues.append("运算符前缺少指标或数字。")
        elif current_kind == "operand":
            if previous_kind in {"operand", "rightParen"}:
                issues.append("两个指标或数字之间缺少运算符。")

        normalized_tokens.append(token)
        previous_kind = current_kind
        previous_token = token

    if balance != 0:
        issues.append("括号不配对。")
    if previous_kind == "operator":
        operator = previous_token.get("value") if isinstance(previous_token, dict) else ""
        issues.append("除号后缺少指标或数字。" if operator == "/" else "运算符后缺少指标或数字。")
    if previous_kind == "leftParen":
        issues.append("左括号后缺少指标或数字。")

    if issues:
        return {
            "id": formula_id,
            "alias": alias,
            "decimal_places": formula.get("decimalPlaces"),
            "expression": None,
            "base_metrics": [],
            "issues": _unique_text_items(issues),
        }

    values: list[dict[str, Any]] = []
    operators: list[str] = []
    parse_issues: list[str] = []

    for index, token in enumerate(normalized_tokens):
        token_type = token.get("type")
        if token_type == "number":
            values.append({"type": "number", "value": str(token.get("value") or "").strip()})
            continue
        if token_type == "metric":
            metric_id = str(token.get("metricId") or "").strip()
            metric = metric_by_id[metric_id]
            base_metric = _metric_base_ir(metric, metric_id=metric_id, source="metric")
            base_metric_by_id[metric_id] = base_metric
            values.append({"type": "metric_ref", "id": metric_id})
            continue
        if token_type == "atomicMetric":
            metric = token.get("metric") if isinstance(token.get("metric"), dict) else {}
            metric_id = str(metric.get("id") or f"{formula_id}__atomic_{index + 1}").strip()
            base_metric = _metric_base_ir(metric, metric_id=metric_id, source="atomicMetric")
            base_metric_by_id[metric_id] = base_metric
            values.append({"type": "metric_ref", "id": metric_id})
            continue
        if token_type == "operator":
            operator = str(token.get("value") or "")
            while (
                operators
                and operators[-1] != "("
                and _FORMULA_PRECEDENCE[operators[-1]] >= _FORMULA_PRECEDENCE[operator]
            ):
                _apply_formula_operator(values, operators, parse_issues)
            operators.append(operator)
            continue
        if token_type == "paren" and token.get("value") == "(":
            operators.append("(")
            continue
        if token_type == "paren" and token.get("value") == ")":
            while operators and operators[-1] != "(":
                _apply_formula_operator(values, operators, parse_issues)
            if operators and operators[-1] == "(":
                operators.pop()

    while operators:
        if operators[-1] == "(":
            parse_issues.append("括号不配对。")
            operators.pop()
            continue
        _apply_formula_operator(values, operators, parse_issues)

    expression = values[0] if len(values) == 1 and not parse_issues else None
    if expression is None:
        parse_issues.append("公式无法解析为单个表达式。")
    if _expression_has_divide_by_zero(expression):
        parse_issues.append("公式明确除以常量 0。")

    return {
        "id": formula_id,
        "alias": alias,
        "decimal_places": formula.get("decimalPlaces"),
        "expression": expression,
        "base_metrics": list(base_metric_by_id.values()),
        "issues": _unique_text_items(parse_issues),
    }


def _build_formula_ir(normalized_config: dict[str, Any]) -> dict[str, Any]:
    """
    是什么：把公式指标 token 解析为可校验的表达式树。
    """
    metrics = _list_dict_items(normalized_config.get("metrics"))
    formula_metrics = _list_dict_items(normalized_config.get("formula_metrics"))
    metric_by_id = {
        _metric_item_id(metric, index): metric
        for index, metric in enumerate(metrics)
        if _metric_item_id(metric, index)
    }
    formula_metric_ids = {
        _formula_item_id(formula, index)
        for index, formula in enumerate(formula_metrics)
        if _formula_item_id(formula, index)
    }
    formulas: list[dict[str, Any]] = []
    issues: list[str] = []
    warnings: list[str] = []
    base_metric_by_id: dict[str, dict[str, Any]] = {}

    for index, formula in enumerate(formula_metrics):
        formula_ir = _parse_formula_expression(
            formula,
            formula_index=index,
            metric_by_id=metric_by_id,
            formula_metric_ids=formula_metric_ids,
        )
        formulas.append(formula_ir)
        for issue in formula_ir.get("issues") or []:
            issues.append(f"{formula_ir['alias']} 的公式语法错误：{issue}")
        events = {
            str(metric.get("event") or "").strip()
            for metric in formula_ir.get("base_metrics") or []
            if str(metric.get("event") or "").strip()
        }
        if len(events) > 1:
            warnings.append(f"{formula_ir['alias']} 的公式分子分母来自不同事件，系统会先分别聚合再相除。")
        for base_metric in formula_ir.get("base_metrics") or []:
            metric_id = str(base_metric.get("id") or "").strip()
            if metric_id:
                base_metric_by_id[metric_id] = base_metric

    return {
        "formulas": formulas,
        "base_metrics": list(base_metric_by_id.values()),
        "issues": _unique_text_items(issues),
        "warnings": _unique_text_items(warnings),
    }


def _normalized_table_candidates(table_name: str) -> set[str]:
    normalized = str(table_name or "").strip().strip('"`[]').lower()
    if not normalized:
        return set()
    candidates = {normalized}
    if "." in normalized:
        candidates.add(normalized.split(".")[-1])
    return candidates


def _normalized_identifier(value: Any) -> str:
    return str(value or "").strip().strip('"`[]').lower()


def _schema_table_lookup_keys(table_name: str) -> set[str]:
    candidates = _normalized_table_candidates(table_name)
    for candidate in list(candidates):
        if "." in candidate:
            candidates.add(candidate.split(".")[-1])
    return {item for item in candidates if item}


def _schema_field_candidates(field: Any) -> set[str]:
    candidates: set[str] = set()
    if isinstance(field, dict):
        field_name = str(field.get("field") or field.get("field_name") or "").strip()
        source_field = str(field.get("sourceField") or field.get("source_field") or "").strip()
        value = str(field.get("value") or "").strip()
        if str(field.get("kind") or "") == "tracking-event":
            field_name = str(field.get("eventNameField") or field.get("event_name_field") or field_name).strip()
        for item in (field_name, source_field):
            if item:
                candidates.add(_normalized_identifier(item))
        table_name = _field_table_name(field)
        if value:
            normalized_value = _normalized_identifier(value)
            candidates.add(normalized_value)
            for table_key in _schema_table_lookup_keys(table_name):
                prefix = f"{table_key}."
                if normalized_value.startswith(prefix):
                    candidates.add(normalized_value[len(prefix):])
        if field_name and (field.get("isJsonSubfield") or field.get("jsonPath") or field.get("expression")):
            candidates.add(_normalized_identifier(field_name.split(".", 1)[0]))
        return {item for item in candidates if item}

    text = str(field or "").strip()
    if not text:
        return set()
    if text.startswith("tracking-event:"):
        parts = text.split(":")
        if len(parts) >= 2 and "." in parts[1]:
            candidates.add(_normalized_identifier(parts[1].split(".", 1)[1]))
        return {item for item in candidates if item}
    if text.startswith("tracking-property:"):
        parts = text.split(":")
        if len(parts) >= 4:
            candidates.add(_normalized_identifier(parts[3]))
            candidates.add(_normalized_identifier(parts[3].split(".", 1)[0]))
        return {item for item in candidates if item}
    normalized = _normalized_identifier(text)
    candidates.add(normalized)
    if "." in normalized:
        candidates.add(normalized.split(".", 1)[1])
    return {item for item in candidates if item}


def _allowed_fields_by_table_from_schema(schema: str) -> dict[str, set[str]]:
    """
    是什么：从 AI schema 文本里提取当前用户可见字段，供手动配置确定性校验使用。
    """
    result: dict[str, set[str]] = {}
    current_table = ""
    for line in str(schema or "").splitlines():
        table_match = re.match(r"\s*#\s*Table:\s*(.+?)\s*$", line)
        if table_match:
            current_table = table_match.group(1).split(",", 1)[0].strip()
            for table_key in _schema_table_lookup_keys(current_table):
                result.setdefault(table_key, set())
            continue
        if not current_table:
            continue
        field_names = [
            _normalized_identifier(match.group(1))
            for match in re.finditer(r"\(([^():,\[\]]+?)\s*:", line)
        ]
        if not field_names:
            continue
        for table_key in _schema_table_lookup_keys(current_table):
            result.setdefault(table_key, set()).update(field_names)
    return {table: fields for table, fields in result.items() if fields}


def _canonical_table_name(table_name: str) -> str:
    normalized = str(table_name or "").strip().strip('"`[]').lower()
    if "." in normalized:
        return normalized.split(".")[-1]
    return normalized


def _allowed_table_name_set(allowed_tables: list[str] | None) -> set[str]:
    allowed: set[str] = set()
    for table_name in allowed_tables or []:
        allowed.update(_normalized_table_candidates(table_name))
    return allowed


def _table_is_allowed(table_name: str, allowed_tables: list[str] | None) -> bool:
    allowed = _allowed_table_name_set(allowed_tables)
    if not allowed:
        return True
    return bool(_normalized_table_candidates(table_name) & allowed)


def _dashboard_event_scope(
        config: Any,
        *,
        datasource_id: int | str | None,
        allowed_tables: list[str] | None = None,
) -> dict[str, Any]:
    """根据服务端工作空间配置确定手动图表事件模式的唯一表范围。"""
    default_event_table = str(getattr(config, "default_event_table", None) or "").strip()
    has_persisted_config = bool(getattr(config, "id", None) or default_event_table)
    if config is None or not has_persisted_config or getattr(config, "enabled", True) is False:
        return {
            "mode": "general",
            "status": "general",
            "default_event_table": "",
            "table_list": None,
            "issues": [],
        }

    configured_datasource_id = getattr(config, "datasource_id", None)
    if (
        configured_datasource_id is not None
        and datasource_id is not None
        and str(configured_datasource_id) != str(datasource_id)
    ):
        return {
            "mode": "event",
            "status": "datasource-mismatch",
            "default_event_table": default_event_table,
            "table_list": [],
            "issues": ["当前埋点配置与图表数据源不一致，事件配置不可用。"],
        }
    if not default_event_table:
        return {
            "mode": "event",
            "status": "missing-default-table",
            "default_event_table": "",
            "table_list": [],
            "issues": ["当前工作空间未配置默认事件表，事件配置不可用。"],
        }
    if allowed_tables is not None and not _table_is_allowed(default_event_table, allowed_tables):
        return {
            "mode": "event",
            "status": "table-unavailable",
            "default_event_table": default_event_table,
            "table_list": [],
            "issues": [f"默认事件表 {default_event_table} 不存在或不可访问，事件配置不可用。"],
        }
    return {
        "mode": "event",
        "status": "active",
        "default_event_table": default_event_table,
        "table_list": [default_event_table],
        "issues": [],
    }


def _field_table_permission_issues(field: Any, label: str, allowed_tables: list[str] | None) -> list[str]:
    table_name = _field_table_name(field)
    if not table_name or _table_is_allowed(table_name, allowed_tables):
        return []
    return [f"{label} 使用了无权限的数据表：{table_name}。"]


def _field_schema_permission_issues(
        field: Any,
        label: str,
        allowed_fields_by_table: dict[str, set[str]] | None,
) -> list[str]:
    table_name = _field_table_name(field)
    if not table_name or not allowed_fields_by_table:
        return []
    allowed_fields: set[str] = set()
    for table_key in _schema_table_lookup_keys(table_name):
        allowed_fields.update(allowed_fields_by_table.get(table_key) or set())
    if not allowed_fields:
        return []
    field_candidates = _schema_field_candidates(field)
    if not field_candidates or field_candidates & allowed_fields:
        return []
    field_text = str(
        (field.get("field") or field.get("value") or field.get("sourceField"))
        if isinstance(field, dict)
        else field
    ).strip()
    return [f"{label} 使用了字段不存在或无权限的字段：{table_name}.{field_text}。"]


def _metric_permission_issues(
        metric: dict[str, Any],
        label: str,
        allowed_tables: list[str] | None,
        allowed_fields_by_table: dict[str, set[str]] | None = None,
) -> list[str]:
    issues: list[str] = []
    issues.extend(_field_table_permission_issues(metric.get("field"), label, allowed_tables))
    issues.extend(_field_schema_permission_issues(metric.get("field"), label, allowed_fields_by_table))
    metric_field = _metric_measure_field(metric)
    if metric_field:
        issues.extend(_field_table_permission_issues(metric_field, label, allowed_tables))
        issues.extend(_field_schema_permission_issues(metric_field, label, allowed_fields_by_table))
    return _unique_text_items(issues)


def _configured_field_permission_issues(
        normalized_config: dict[str, Any],
        *,
        allowed_tables: list[str] | None,
        allowed_fields_by_table: dict[str, set[str]] | None,
) -> list[str]:
    issues: list[str] = []
    time_config = normalized_config.get("time") if isinstance(normalized_config.get("time"), dict) else {}
    time_field = time_config.get("field")
    if time_field:
        issues.extend(_field_table_permission_issues(time_field, "时间字段", allowed_tables))
        issues.extend(_field_schema_permission_issues(time_field, "时间字段", allowed_fields_by_table))
    for index, group in enumerate(_list_dict_items(normalized_config.get("groups"))):
        label = f"分组项{index + 1}"
        issues.extend(_field_table_permission_issues(group, label, allowed_tables))
        issues.extend(_field_schema_permission_issues(group, label, allowed_fields_by_table))
    for index, field in enumerate(_iter_filter_rule_fields(normalized_config.get("filters"))):
        label = f"全局筛选{index + 1}"
        issues.extend(_field_table_permission_issues(field, label, allowed_tables))
        issues.extend(_field_schema_permission_issues(field, label, allowed_fields_by_table))
    return _unique_text_items(issues)


def _iter_filter_rule_fields(value: Any):
    if isinstance(value, list):
        for item in value:
            yield from _iter_filter_rule_fields(item)
        return
    if not isinstance(value, dict):
        return
    if value.get("field") is not None:
        yield value.get("field")
    for key in ("rules", "children"):
        child_value = value.get(key)
        if isinstance(child_value, list):
            yield from _iter_filter_rule_fields(child_value)


def _metric_effective_table(metric: dict[str, Any]) -> str:
    return _field_table_name(metric.get("field")) or _field_table_name(_metric_measure_field(metric))


def _config_reference_table_names(normalized_config: dict[str, Any], formula_ir: dict[str, Any]) -> set[str]:
    tables: set[str] = set()
    time_config = normalized_config.get("time") if isinstance(normalized_config.get("time"), dict) else {}
    table_name = _field_table_name(time_config.get("field"))
    if table_name:
        tables.add(table_name)
    for metric in _list_dict_items(normalized_config.get("metrics")):
        table_name = _metric_effective_table(metric)
        if table_name:
            tables.add(table_name)
    for group in _list_dict_items(normalized_config.get("groups")):
        table_name = _field_table_name(group)
        if table_name:
            tables.add(table_name)
    filters = normalized_config.get("filters")
    for field in _iter_filter_rule_fields(filters):
        table_name = _field_table_name(field)
        if table_name:
            tables.add(table_name)
    for base_metric in _list_dict_items(formula_ir.get("base_metrics")):
        table_name = str(base_metric.get("table") or "").strip()
        if table_name:
            tables.add(table_name)
    return tables


def _uses_dashboard_date_parameters(chart_type: Any, time_config: dict[str, Any]) -> bool:
    return (
        str(chart_type or "").strip().lower() != "metric"
        and _field_table_name(time_config.get("field")) != ""
    )


def _deterministic_validate_manual_config(
        request: DashboardAiSqlGenerateRequest,
        normalized_config: dict[str, Any],
        formula_ir: dict[str, Any],
        *,
        allowed_tables: list[str] | None = None,
        allowed_fields_by_table: dict[str, set[str]] | None = None,
        event_scope_issues: list[str] | None = None,
) -> DashboardAiSqlGenerateResponse:
    """
    是什么：由代码层判断当前配置能否进入 SQL 生成，LLM 不能覆盖这个结果。
    """
    issues: list[str] = list(event_scope_issues or [])
    warnings: list[str] = list(formula_ir.get("warnings") or [])
    suggestions: list[str] = []

    if not request.datasource:
        issues.append("没有数据源，无法生成 SQL。")

    time_config = normalized_config.get("time") if isinstance(normalized_config.get("time"), dict) else {}
    chart_config = normalized_config.get("chart") if isinstance(normalized_config.get("chart"), dict) else {}
    if _uses_dashboard_date_parameters(chart_config.get("type"), time_config):
        parameter_type = str(time_config.get("date_parameter_type") or "").strip()
        if dashboard_date_parameter_tokens(parameter_type) is None:
            issues.append("生成 SQL 前请先选择日期参数类型。")
        if not isinstance(time_config.get("date_expression"), dict):
            issues.append("生成 SQL 前请选择有效日期表达式。")

    metrics = _list_dict_items(normalized_config.get("metrics"))
    formula_metrics = _list_dict_items(normalized_config.get("formula_metrics"))
    if not metrics and not formula_metrics:
        issues.append("至少需要配置一个分析指标或公式指标。")

    for index, metric in enumerate(metrics):
        label = str(metric.get("alias") or metric.get("label") or f"分析指标{index + 1}").strip()
        issues.extend(_validate_metric_item(metric, label))
        issues.extend(_metric_permission_issues(metric, label, allowed_tables, allowed_fields_by_table))

    issues.extend(str(item) for item in formula_ir.get("issues") or [])
    for base_metric in _list_dict_items(formula_ir.get("base_metrics")):
        label = str(base_metric.get("label") or base_metric.get("alias") or base_metric.get("id") or "公式内基础指标")
        for field_key in ("field", "metric_field"):
            field = base_metric.get(field_key)
            if field:
                issues.extend(_field_table_permission_issues(field, label, allowed_tables))
                issues.extend(_field_schema_permission_issues(field, label, allowed_fields_by_table))
    issues.extend(_configured_field_permission_issues(
        normalized_config,
        allowed_tables=allowed_tables,
        allowed_fields_by_table=allowed_fields_by_table,
    ))
    reference_tables = _config_reference_table_names(normalized_config, formula_ir)
    if len({_canonical_table_name(table) for table in reference_tables if table}) > 1:
        table_text = "、".join(sorted(reference_tables))
        issues.append(f"当前配置涉及跨表计算（{table_text}），但没有明确关联规则。")
    issues = _unique_text_items(issues)
    warnings = _unique_text_items(warnings)
    success = not issues
    return DashboardAiSqlGenerateResponse(
        success=success,
        sql="",
        intent=(request.intent or "").strip(),
        message="配置可以生成 SQL。" if success else issues[0],
        advice="" if success else "请先修正阻断问题，再生成 SQL。",
        issues=issues,
        warnings=warnings,
        suggestions=_unique_text_items(suggestions),
    )


def _build_sql_plan(normalized_config: dict[str, Any], formula_ir: dict[str, Any]) -> dict[str, Any]:
    """
    是什么：把已通过校验的手动配置整理成 SQL 生成计划，作为 LLM SQL 节点的结构化上下文。
    """
    time_config = normalized_config.get("time") if isinstance(normalized_config.get("time"), dict) else {}
    parameter_type = str(time_config.get("date_parameter_type") or "").strip()
    parameter_tokens = dashboard_date_parameter_tokens(parameter_type)
    uses_date_parameters = _uses_dashboard_date_parameters(
        (normalized_config.get("chart") or {}).get("type"),
        time_config,
    )
    return {
        "time": time_config,
        "date_parameters": {
            "enabled": uses_date_parameters,
            "type": parameter_type if uses_date_parameters else "",
            "start_token": parameter_tokens[0] if uses_date_parameters and parameter_tokens else "",
            "end_token": parameter_tokens[1] if uses_date_parameters and parameter_tokens else "",
        },
        "groups": normalized_config.get("groups") or [],
        "filters": normalized_config.get("filters") or {},
        "metrics": normalized_config.get("metrics") or [],
        "formula_metrics": [
            {
                "id": formula.get("id"),
                "alias": formula.get("alias"),
                "decimal_places": formula.get("decimal_places"),
                "expression": formula.get("expression"),
                "base_metric_ids": [
                    base_metric.get("id")
                    for base_metric in formula.get("base_metrics") or []
                    if base_metric.get("id")
                ],
            }
            for formula in formula_ir.get("formulas") or []
        ],
        "base_aggregations": formula_ir.get("base_metrics") or [],
        "generation_rules": [
            "先计算 metrics 和公式内 atomicMetric 对应的基础聚合。",
            "再在外层 SELECT 根据公式 IR 计算公式指标。",
            "除法必须使用 NULLIF(分母表达式, 0)。",
            "decimal_places 有值时使用 ROUND 包裹公式表达式。",
        ],
    }


def _trim_text(value: Any, limit: int = 12000) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[:limit] + "\n...（已截断）"


def _dashboard_sql_dialect_rules(sql_dialect: str | None, datasource: CoreDatasource) -> list[str]:
    dialect_text = " ".join([
        str(sql_dialect or ""),
        str(getattr(datasource, "type", "") or ""),
        str(getattr(datasource, "type_name", "") or ""),
    ]).lower()
    if "mysql" in dialect_text or "mariadb" in dialect_text:
        return [
            "MySQL/MariaDB 方言约束：不能使用 FULL OUTER JOIN；MySQL 不支持该语法。",
            "如果需要合并两个按日期/维度聚合的结果集，优先用一个 key_set CTE 通过 UNION/UNION ALL 去重收集日期或维度键，再分别 LEFT JOIN 各聚合结果；也可以在同一事实表中用 SUM/COUNT(DISTINCT CASE WHEN ...) 做条件聚合。",
        ]
    return []


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
    time_config = context.get("time") if isinstance(context.get("time"), dict) else {}
    parameter_type = str(
        time_config.get("dateParameterType") or time_config.get("date_parameter_type") or ""
    ).strip()
    parameter_tokens = dashboard_date_parameter_tokens(parameter_type)
    chart_config = context.get("chart") if isinstance(context.get("chart"), dict) else {}
    uses_date_parameters = _uses_dashboard_date_parameters(
        chart_config.get("type") or request.chart_type,
        time_config,
    )
    date_parameter_rules = (
        [
            "看板日期参数规则：SQL 必须使用且只能使用以下一对日期占位符："
            f"{parameter_tokens[0]} 和 {parameter_tokens[1]}。",
            "禁止使用数据库当前日期函数，包括 CURDATE、CURRENT_DATE、NOW、CURRENT_TIMESTAMP、LOCALTIME、LOCALTIMESTAMP、GETDATE 和 GETUTCDATE。",
        ]
        if uses_date_parameters and parameter_tokens
        else (
            ["当前图表不包含可变时间范围，不生成看板日期参数或日期控件；若其为固定语义指标，必须保留原有时间含义。"]
            if not uses_date_parameters
            else ["看板日期参数类型缺失，不能生成 SQL。"]
        )
    )
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
        "字段对象包含 sourceField、jsonPath 和 expression 时，JSON 子字段必须使用 expression；不得自行改写 JSON 宿主列或路径。",
        "指标内筛选 rules 是可选配置；没有 rules 或 rules 为空时不是配置缺失，不要要求补筛选条件，不要生成空 WHERE/AND/CASE 条件；只有 rules 里存在有效字段、操作符和值时才应用该筛选。",
        "只允许使用 manual-dashboard-context 里的 selectedFields/metrics/formulaMetrics/calculatedMetrics/groups/filters 字段信息生成 SQL；不要编造未提供字段。",
        *date_parameter_rules,
        *_dashboard_sql_dialect_rules(sql_dialect, datasource),
    ])


def _dashboard_date_sql_issues(sql: str, time_config: dict[str, Any]) -> list[str]:
    parameter_type = str(time_config.get("date_parameter_type") or "").strip()
    token_error = validate_dashboard_date_parameter_sql(sql, parameter_type)
    issues: list[str] = []
    if token_error:
        issues.append("生成 SQL 未使用当前图表日期参数，请重新生成。")
    if _DATABASE_CURRENT_DATE_PATTERN.search(sql):
        issues.append("生成 SQL 使用了数据库当前日期函数，请改用看板日期参数。")
    return _unique_text_items(issues)


def _dashboard_sql_system_prompt() -> str:
    return (
        "你是 BI 手动看板 SQL 生成节点。确定性配置校验已经通过，你只负责根据当前配置、公式 IR 和 SQL plan 生成只读 SELECT SQL。\n"
        "必须使用配置里的时间字段、时间粒度、指标、筛选、分组、计算指标；time.field + time.grain 要生成日期维度；groups 只生成额外维度。不要编造未提供字段。\n"
        "当用户问题或当前配置涉及复杂分析，例如留存、转化、活跃、复购、漏斗、cohort 分析、分组比率、时间窗口对比时，优先使用 CTE 分层结构。"
        "CTE 只是组织结构范式，所有表名、字段名、事件名、日期表达式、过滤条件、分子分母和成熟窗口必须来自当前配置、business-sql-schema、data-skill 或用户明确规则；不得照抄占位符，也不得编造未提供字段。\n"
        "时间边界层规则：\n"
        "- bounds CTE 必须只返回一行时间边界，供后续 CTE 通过 JOIN 或 CROSS JOIN 引用。\n"
        "- 聚合函数和窗口函数不得出现在同一查询层的 WHERE 条件中。\n"
        "- 当结束日期来自 MAX(date_field) 时，必须先在独立 CTE 中计算最大日期，再在下一层 bounds CTE 中计算开始日期。\n"
        "- 禁止生成 WHERE date_field >= <包含 MAX(date_field) 的表达式>。\n"
        "- 仅当当前图表配置要求可变时间范围时，日期边界必须使用当前配置提供的看板日期参数占位符，不能使用数据库当前日期函数。\n"
        "- 具体日期格式和分区字段类型必须服从当前 SQL 方言与配置的日期参数类型。\n"
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
    validation = state.get("validation_result")
    return "\n".join([
        "确定性校验已通过，请生成 SQL。",
        "",
        "<deterministic-validation>",
        _safe_json(validation.model_dump() if validation else {}),
        "</deterministic-validation>",
        "",
        "<formula-ir>",
        _safe_json(state.get("formula_ir") or {}),
        "</formula-ir>",
        "",
        "<sql-plan>",
        _safe_json(state.get("sql_plan") or {}),
        "</sql-plan>",
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


def _invoke_llm_json(
    llm: Any,
    messages: list[Any],
    require_sql: bool = True,
    node: str | None = None,
) -> DashboardAiSqlGenerateResponse:
    result = llm.invoke(messages)
    full_text = _text_chunk_content(getattr(result, "content", result))
    AppLogUtil.info(f"Dashboard manual chart graph raw node result: {full_text}")
    if node:
        _write_llm_output_debug_file(node=node, full_text=full_text, require_sql=require_sql)
    return _response_from_model_text(full_text, require_sql=require_sql)


async def _async_invoke_llm_json(
    llm: Any,
    messages: list[Any],
    require_sql: bool = True,
    node: str | None = None,
) -> DashboardAiSqlGenerateResponse:
    if hasattr(llm, "ainvoke"):
        result = await llm.ainvoke(messages)
        full_text = _text_chunk_content(getattr(result, "content", result))
    elif hasattr(llm, "invoke"):
        return await to_thread(_invoke_llm_json, llm, messages, require_sql, node)
    else:
        raise AttributeError("LLM does not support non-streaming invoke")
    AppLogUtil.info(f"Dashboard manual chart graph raw node result: {full_text}")
    if node:
        _write_llm_output_debug_file(node=node, full_text=full_text, require_sql=require_sql)
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
    workspace_tracking_config = get_tracking_config(
        session,
        tenant_id,
        int(request.datasource),
        include_legacy=False,
    )
    event_scope = _dashboard_event_scope(
        workspace_tracking_config,
        datasource_id=int(request.datasource),
    )
    business_context = BusinessSqlContextService.build(
        session=session,
        current_user=current_user,
        tenant_id=tenant_id,
        datasource_id=int(request.datasource),
        question=question_text,
        target_scope=CustomPromptTargetScopeEnum.SMART_QA,
        data_skill_id=request.data_skill_id,
        embedding=False,
        table_list=event_scope["table_list"],
        can_manage_all=is_system_admin(current_user),
        can_manage_public=_can_manage_tenant_prompt_runtime(current_user),
        can_manage_platform_public=_can_manage_platform_prompt_runtime(current_user),
    )
    if event_scope["status"] == "active":
        event_scope = _dashboard_event_scope(
            workspace_tracking_config,
            datasource_id=int(request.datasource),
            allowed_tables=business_context.allowed_tables,
        )
    return {
        "datasource": business_context.datasource,
        "tenant_id": tenant_id,
        "business_sql_context": business_context,
        "schema": business_context.schema,
        "sql_dialect": business_context.sql_dialect,
        "allowed_tables": business_context.allowed_tables,
        "allowed_fields_by_table": _allowed_fields_by_table_from_schema(business_context.schema),
        "data_skill": business_context.data_skill,
        "tracking_config": business_context.tracking_config,
        "event_scope": event_scope,
        "skill_model_id": business_context.skill_model_id,
        "graph_trace": _append_trace(state, "collect_context"),
        "last_node": "collect_context",
    }


def _node_normalize_manual_config(state: DashboardManualChartGraphState) -> dict[str, Any]:
    datasource = state.get("datasource")
    normalized_config = _normalize_manual_config(
        state["request"],
        datasource_type=getattr(datasource, "type", None) or getattr(datasource, "type_name", None),
    )
    return {
        "normalized_config": normalized_config,
        "graph_trace": _append_trace(state, "normalize_manual_config"),
        "last_node": "normalize_manual_config",
    }


def _node_build_formula_ir(state: DashboardManualChartGraphState) -> dict[str, Any]:
    normalized_config = state.get("normalized_config") or {}
    formula_ir = _build_formula_ir(normalized_config)
    return {
        "formula_ir": formula_ir,
        "json_subfield_requirements": _json_subfield_requirements(normalized_config, formula_ir),
        "graph_trace": _append_trace(state, "build_formula_ir"),
        "last_node": "build_formula_ir",
    }


def _node_deterministic_validate(state: DashboardManualChartGraphState) -> dict[str, Any]:
    event_scope = state.get("event_scope") or {}
    validation = _deterministic_validate_manual_config(
        state["request"],
        state.get("normalized_config") or {},
        state.get("formula_ir") or {},
        allowed_tables=state.get("allowed_tables") or [],
        allowed_fields_by_table=state.get("allowed_fields_by_table") or {},
        event_scope_issues=list(event_scope.get("issues") or []),
    )
    return {
        "validation_result": validation,
        "response": validation if validation.success is False else state.get("response"),
        "graph_trace": _append_trace(state, "deterministic_validate"),
        "last_node": "deterministic_validate",
    }


def _route_after_deterministic_validate(state: DashboardManualChartGraphState) -> str:
    validation = state.get("validation_result")
    if validation is None:
        return "finalize_response"
    if validation.success is False:
        return "finalize_response"
    return "build_sql_plan"


def _node_build_sql_plan(state: DashboardManualChartGraphState) -> dict[str, Any]:
    sql_plan = _build_sql_plan(state.get("normalized_config") or {}, state.get("formula_ir") or {})
    return {
        "sql_plan": sql_plan,
        "graph_trace": _append_trace(state, "build_sql_plan"),
        "last_node": "build_sql_plan",
    }


async def _async_node_generate_sql(state: DashboardManualChartGraphState) -> dict[str, Any]:
    llm = await _create_dashboard_ai_sql_llm(state.get("skill_model_id"))
    response = await _async_invoke_llm_json(llm, [
        SystemMessage(content=_dashboard_sql_system_prompt()),
        HumanMessage(content=_dashboard_sql_user_prompt(state)),
    ], node="generate_sql")
    validation = state.get("validation_result")
    if validation:
        response.intent = response.intent or validation.intent
    return {
        "response": response,
        "graph_trace": _append_trace(state, "generate_sql"),
        "last_node": "generate_sql",
    }


def _node_validate_sql(state: DashboardManualChartGraphState) -> dict[str, Any]:
    response = state.get("response") or DashboardAiSqlGenerateResponse(success=False)
    sql = (response.sql or "").strip()

    def _mark_sql_valid() -> None:
        response.success = True
        if response.issues:
            response.suggestions = _unique_text_items(list(response.suggestions or []) + list(response.issues or []))
            response.issues = []

    if not sql:
        response.success = False
        response.message = response.message or "Agent 未生成 SQL。"
        response.advice = response.advice or "按建议补全配置后再生成。"
    elif not re.match(r"^\s*(select|with)\b", sql, flags=re.IGNORECASE):
        response.success = False
        response.message = "SQL 不是只读查询。"
        response.advice = "只能生成 SELECT/WITH 查询，请重新生成。"
        response.issues = list(response.issues or []) + ["生成 SQL 不是只读 SELECT/WITH 查询。"]
    elif isinstance(state.get("normalized_config"), dict) and _uses_dashboard_date_parameters(
        response.chart_type
        or ((state["normalized_config"].get("chart") or {}).get("type")),
        state["normalized_config"].get("time")
        if isinstance(state["normalized_config"].get("time"), dict)
        else {},
    ) and (
        date_issues := _dashboard_date_sql_issues(
            sql,
            state["normalized_config"].get("time")
            if isinstance(state["normalized_config"].get("time"), dict)
            else {},
        )
    ):
        response.success = False
        response.message = "生成 SQL 未满足看板日期参数要求。"
        response.advice = "请使用当前图表配置的起止日期参数重新生成。"
        response.issues = _unique_text_items(list(response.issues or []) + date_issues)
    elif json_issues := _json_subfield_sql_issues(
        sql,
        state.get("json_subfield_requirements") or [],
        dialect=state.get("sql_dialect") or "",
    ):
        response.success = False
        response.message = "生成 SQL 的 JSON 字段映射与当前配置不一致。"
        response.advice = "请重新选择事件参数后生成 SQL。"
        response.issues = _unique_text_items(list(response.issues or []) + json_issues)
    elif state.get("datasource") is not None:
        try:
            is_read, reason = check_sql_read(sql, state["datasource"])
        except Exception as exc:
            is_read, reason = False, str(exc)
        if not is_read:
            response.success = False
            response.message = "SQL 不是只读查询。"
            response.advice = "只能生成单条 SELECT/WITH 查询，请重新生成。"
            response.issues = _unique_text_items(
                list(response.issues or []) + [f"生成 SQL 不是只读查询：{reason or '未通过只读校验'}。"]
            )
        else:
            _mark_sql_valid()
    else:
        _mark_sql_valid()
    return {
        "response": response,
        "graph_trace": _append_trace(state, "validate_sql"),
        "last_node": "validate_sql",
    }


def _node_explain_advice(state: DashboardManualChartGraphState) -> dict[str, Any]:
    response = state.get("response") or DashboardAiSqlGenerateResponse(success=False)
    validation = state.get("validation_result")
    if validation:
        updated = response.model_copy(deep=True)
        if validation.intent and not updated.intent:
            updated.intent = validation.intent
        updated.warnings = _unique_text_items(list(updated.warnings or []) + list(validation.warnings or []))
        updated.suggestions = _unique_text_items(list(updated.suggestions or []) + list(validation.suggestions or []))
        response = updated
    return {
        "response": response,
        "graph_trace": _append_trace(state, "explain_advice"),
        "last_node": "explain_advice",
    }


def _node_finalize_response(state: DashboardManualChartGraphState) -> dict[str, Any]:
    response = state.get("response") or state.get("validation_result") or DashboardAiSqlGenerateResponse(
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
    graph.add_node("normalize_manual_config", _timed_node("normalize_manual_config", _node_normalize_manual_config))
    graph.add_node("build_formula_ir", _timed_node("build_formula_ir", _node_build_formula_ir))
    graph.add_node("deterministic_validate", _timed_node("deterministic_validate", _node_deterministic_validate))
    graph.add_node("build_sql_plan", _timed_node("build_sql_plan", _node_build_sql_plan))
    graph.add_node("generate_sql", _timed_node("generate_sql", _async_node_generate_sql))
    graph.add_node("validate_sql", _timed_node("validate_sql", _node_validate_sql))
    graph.add_node("explain_advice", _timed_node("explain_advice", _node_explain_advice))
    graph.add_node("finalize_response", _timed_node("finalize_response", _node_finalize_response))
    graph.set_entry_point("collect_context")
    graph.add_edge("collect_context", "normalize_manual_config")
    graph.add_edge("normalize_manual_config", "build_formula_ir")
    graph.add_edge("build_formula_ir", "deterministic_validate")
    graph.add_conditional_edges("deterministic_validate", _route_after_deterministic_validate)
    graph.add_edge("build_sql_plan", "generate_sql")
    graph.add_edge("generate_sql", "validate_sql")
    graph.add_edge("validate_sql", "explain_advice")
    graph.add_edge("explain_advice", "finalize_response")
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
    做了什么：按 collect_context -> normalize_manual_config -> build_formula_ir -> deterministic_validate -> build_sql_plan -> generate_sql -> validate_sql -> explain_advice -> finalize_response 编排。
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
