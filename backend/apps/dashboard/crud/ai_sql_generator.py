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
import sqlglot
from fastapi import HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from sqlglot import exp

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
from apps.db.db import check_sql_read, get_sqlglot_dialect
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
RETENTION_COHORT_DAYS = 7
INTERVAL_LIMIT_MIN_SECONDS = 60
INTERVAL_LIMIT_MAX_SECONDS = 180 * 24 * 60 * 60


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
    sql_repair_attempts: int
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
    if isinstance(field, dict) and str(field.get("kind") or "") in {"tracking-event", "tracking-property"}:
        return str(field.get("eventName") or field.get("event_name") or "").strip()
    return ""


_FORMULA_OPERATORS = {"+", "-", "*", "/"}
_FORMULA_PRECEDENCE = {"+": 1, "-": 1, "*": 2, "/": 2}
_SUPPORTED_METRIC_AGGREGATIONS = {"count", "count_distinct", "sum", "avg", "max", "min"}
_SUPPORTED_DISTRIBUTION_PROPERTY_AGGREGATIONS = {
    "sum", "avg", "median", "max", "min", "count_distinct", "variance", "stddev",
    "percentile_99", "percentile_95", "percentile_90", "percentile_80", "percentile_75",
    "percentile_70", "percentile_60", "percentile_40", "percentile_30", "percentile_25",
    "percentile_20", "percentile_10", "percentile_05",
}
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


def _retention_simultaneous_metric(retention: dict[str, Any]) -> dict[str, Any]:
    simultaneous = retention.get("simultaneous") if isinstance(retention.get("simultaneous"), dict) else {}
    return {
        "field": simultaneous.get("event"),
        "metricField": (
            simultaneous.get("metricField")
            or simultaneous.get("metric_field")
            or simultaneous.get("metric")
        ),
        "aggregation": simultaneous.get("aggregation") or "count",
    }


def _distribution_simultaneous_metric(distribution: dict[str, Any]) -> dict[str, Any]:
    simultaneous = distribution.get("simultaneous") if isinstance(distribution.get("simultaneous"), dict) else {}
    return {
        "field": simultaneous.get("event"),
        "metricField": simultaneous.get("metricField") or simultaneous.get("metric_field"),
        "aggregation": simultaneous.get("aggregation") or "count",
    }


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


def _field_type_family(field: Any) -> str:
    type_text = _field_reference_text(field)
    if not type_text.strip():
        return ""
    if _text_has_numeric_type_hint(type_text):
        return "numeric"
    if any(keyword in type_text for keyword in ("date", "time", "timestamp", "datetime", "日期", "时间")):
        return "temporal"
    if any(keyword in type_text for keyword in ("bool", "boolean", "布尔")):
        return "boolean"
    if any(keyword in type_text for keyword in ("char", "string", "text", "varchar", "enum", "文本", "字符串")):
        return "text"
    return " ".join(type_text.split())


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
    analysis_model = str(context.get("analysisModel") or context.get("analysis_model") or "event").strip().lower()
    if analysis_model not in {"event", "retention", "funnel", "distribution", "interval", "path"}:
        analysis_model = "event"
    retention = dict(context.get("retention") or {}) if isinstance(context.get("retention"), dict) else {}
    funnel = dict(context.get("funnel") or {}) if isinstance(context.get("funnel"), dict) else {}
    distribution = dict(context.get("distribution") or {}) if isinstance(context.get("distribution"), dict) else {}
    interval = dict(context.get("interval") or {}) if isinstance(context.get("interval"), dict) else {}
    path = dict(context.get("path") or {}) if isinstance(context.get("path"), dict) else {}
    return {
        "analysis_model": analysis_model,
        "retention": retention,
        "funnel": funnel,
        "distribution": distribution,
        "interval": interval,
        "path": path,
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
        issues.extend(_json_subfield_mapping_issues(field, label))
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
    retention = normalized_config.get("retention") if isinstance(normalized_config.get("retention"), dict) else {}
    simultaneous = retention.get("simultaneous") if isinstance(retention.get("simultaneous"), dict) else {}
    simultaneous_metric = _retention_simultaneous_metric(retention)
    related_property = retention.get("relatedProperty") if isinstance(retention.get("relatedProperty"), dict) else {}
    retention_fields = [
        retention.get("entityField") or retention.get("entity_field"),
        retention.get("initialEvent") or retention.get("initial_event"),
        retention.get("returnEvent") or retention.get("return_event"),
        simultaneous.get("event"),
        _metric_measure_field(simultaneous_metric),
        related_property.get("initialProperty") or related_property.get("initial_property"),
        related_property.get("returnProperty") or related_property.get("return_property"),
        related_property.get("simultaneousProperty") or related_property.get("simultaneous_property"),
    ]
    for field in retention_fields:
        table_name = _field_table_name(field)
        if table_name:
            tables.add(table_name)
    for filter_config in (
        retention.get("initialEventFilters") or retention.get("initial_event_filters"),
        retention.get("returnEventFilters") or retention.get("return_event_filters"),
    ):
        for field in _iter_filter_rule_fields(filter_config):
            table_name = _field_table_name(field)
            if table_name:
                tables.add(table_name)
    funnel = normalized_config.get("funnel") if isinstance(normalized_config.get("funnel"), dict) else {}
    funnel_fields = [funnel.get("entityField") or funnel.get("entity_field")]
    for step in _list_dict_items(funnel.get("steps")):
        funnel_fields.extend([
            step.get("event"),
            step.get("relatedProperty") or step.get("related_property"),
        ])
        for field in _iter_filter_rule_fields(step.get("filters")):
            funnel_fields.append(field)
    for field in funnel_fields:
        table_name = _field_table_name(field)
        if table_name:
            tables.add(table_name)
    distribution = normalized_config.get("distribution") if isinstance(normalized_config.get("distribution"), dict) else {}
    distribution_metric = distribution.get("metric") if isinstance(distribution.get("metric"), dict) else {}
    distribution_simultaneous = (
        distribution.get("simultaneous") if isinstance(distribution.get("simultaneous"), dict) else {}
    )
    distribution_fields = [
        distribution.get("entityField") or distribution.get("entity_field"),
        distribution.get("event"),
        distribution_metric.get("field"),
        distribution_simultaneous.get("event"),
        _metric_measure_field(_distribution_simultaneous_metric(distribution)),
    ]
    distribution_fields.extend(_iter_filter_rule_fields(
        distribution.get("eventFilters") or distribution.get("event_filters")
    ))
    for field in distribution_fields:
        table_name = _field_table_name(field)
        if table_name:
            tables.add(table_name)
    interval = normalized_config.get("interval") if isinstance(normalized_config.get("interval"), dict) else {}
    interval_related = interval.get("relatedProperty") if isinstance(interval.get("relatedProperty"), dict) else {}
    interval_fields = [
        interval.get("entityField") or interval.get("entity_field"),
        interval.get("startEvent") or interval.get("start_event"),
        interval.get("endEvent") or interval.get("end_event"),
        interval_related.get("startProperty") or interval_related.get("start_property"),
        interval_related.get("endProperty") or interval_related.get("end_property"),
    ]
    for filter_config in (
        interval.get("startEventFilters") or interval.get("start_event_filters"),
        interval.get("endEventFilters") or interval.get("end_event_filters"),
    ):
        interval_fields.extend(_iter_filter_rule_fields(filter_config))
    for field in interval_fields:
        table_name = _field_table_name(field)
        if table_name:
            tables.add(table_name)
    path = normalized_config.get("path") if isinstance(normalized_config.get("path"), dict) else {}
    path_fields: list[Any] = [path.get("initialEvent") or path.get("initial_event")]
    for event_item in _list_dict_items(path.get("events")):
        path_fields.append(event_item.get("event"))
        path_fields.extend(event_item.get("splitProperties") or event_item.get("split_properties") or [])
    for field in path_fields:
        table_name = _field_table_name(field)
        if table_name:
            tables.add(table_name)
    return tables


def _uses_dashboard_date_parameters(chart_type: Any, time_config: dict[str, Any]) -> bool:
    return (
        _field_table_name(time_config.get("field")) != ""
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

    analysis_model = str(normalized_config.get("analysis_model") or "event")
    metrics = _list_dict_items(normalized_config.get("metrics"))
    formula_metrics = _list_dict_items(normalized_config.get("formula_metrics"))
    if analysis_model == "event" and not metrics and not formula_metrics:
        issues.append("至少需要配置一个分析指标或公式指标。")

    if analysis_model == "retention":
        retention = normalized_config.get("retention") if isinstance(normalized_config.get("retention"), dict) else {}
        entity_field = retention.get("entityField") or retention.get("entity_field")
        initial_event = retention.get("initialEvent") or retention.get("initial_event")
        return_event = retention.get("returnEvent") or retention.get("return_event")
        if not _field_has_resolvable_reference(entity_field):
            issues.append("留存分析请先选择分析主体。")
        if not _field_has_resolvable_reference(initial_event):
            issues.append("留存分析请先选择初始事件。")
        if not _field_has_resolvable_reference(return_event):
            issues.append("留存分析请先选择回访事件。")
        if not _field_has_resolvable_reference(time_config.get("field")):
            issues.append("留存分析请先选择时间字段。")
        if str((normalized_config.get("chart") or {}).get("type") or request.chart_type) != "table":
            issues.append("留存分析只能使用留存表结果。")
        simultaneous = retention.get("simultaneous") if isinstance(retention.get("simultaneous"), dict) else {}
        simultaneous_enabled = simultaneous.get("enabled") is True
        simultaneous_event = simultaneous.get("event")
        if simultaneous_enabled and not _field_has_resolvable_reference(simultaneous_event):
            issues.append("使用同时展示时请选择参与事件。")
        if simultaneous_enabled and _field_has_resolvable_reference(simultaneous_event):
            simultaneous_metric = _retention_simultaneous_metric(retention)
            issues.extend(_validate_metric_item(
                simultaneous_metric,
                "同时展示指标",
                require_aggregation=True,
            ))
            issues.extend(_metric_permission_issues(
                simultaneous_metric,
                "同时展示指标",
                allowed_tables,
                allowed_fields_by_table,
            ))

        related_property = retention.get("relatedProperty") if isinstance(retention.get("relatedProperty"), dict) else {}
        related_enabled = related_property.get("enabled") is True
        initial_property = related_property.get("initialProperty") or related_property.get("initial_property")
        return_property = related_property.get("returnProperty") or related_property.get("return_property")
        simultaneous_property = related_property.get("simultaneousProperty") or related_property.get("simultaneous_property")
        if related_enabled and not _field_has_resolvable_reference(initial_property):
            issues.append("使用关联属性时请选择初始事件属性。")
        if related_enabled and not _field_has_resolvable_reference(return_property):
            issues.append("使用关联属性时请选择回访事件属性。")
        if related_enabled and simultaneous_enabled and not _field_has_resolvable_reference(simultaneous_property):
            issues.append("使用关联属性和同时展示时请选择同时展示事件属性。")

        for field, label in (
            (entity_field, "分析主体"),
            (initial_event, "初始事件"),
            (return_event, "回访事件"),
            (simultaneous_event if simultaneous_enabled else None, "同时展示事件"),
            (initial_property if related_enabled else None, "初始事件关联属性"),
            (return_property if related_enabled else None, "回访事件关联属性"),
            (simultaneous_property if related_enabled and simultaneous_enabled else None, "同时展示关联属性"),
        ):
            if field:
                issues.extend(_tracking_event_metadata_issues(field, label))
                issues.extend(_json_subfield_mapping_issues(field, label))
                issues.extend(_field_table_permission_issues(field, label, allowed_tables))
                issues.extend(_field_schema_permission_issues(field, label, allowed_fields_by_table))
        for property_field, event_field, label in (
            (initial_property, initial_event, "初始事件关联属性"),
            (return_property, return_event, "回访事件关联属性"),
            (simultaneous_property, simultaneous_event, "同时展示关联属性"),
        ):
            property_event_name = _tracking_event_name_from_field(property_field)
            expected_event_name = _tracking_event_name_from_field(event_field)
            if related_enabled and property_event_name and expected_event_name and property_event_name != expected_event_name:
                issues.append(f"{label}不属于当前选择的事件。")
        for filter_config, event_field, label in (
            (
                retention.get("initialEventFilters") or retention.get("initial_event_filters"),
                initial_event,
                "初始事件筛选",
            ),
            (
                retention.get("returnEventFilters") or retention.get("return_event_filters"),
                return_event,
                "回访事件筛选",
            ),
        ):
            expected_event_name = _tracking_event_name_from_field(event_field)
            for index, filter_field in enumerate(_iter_filter_rule_fields(filter_config)):
                filter_label = f"{label}{index + 1}"
                issues.extend(_json_subfield_mapping_issues(filter_field, filter_label))
                issues.extend(_field_table_permission_issues(filter_field, filter_label, allowed_tables))
                issues.extend(_field_schema_permission_issues(filter_field, filter_label, allowed_fields_by_table))
                filter_event_name = _tracking_event_name_from_field(filter_field)
                if filter_event_name and expected_event_name and filter_event_name != expected_event_name:
                    issues.append(f"{filter_label}不属于当前选择的事件。")

    if analysis_model == "funnel":
        funnel = normalized_config.get("funnel") if isinstance(normalized_config.get("funnel"), dict) else {}
        entity_field = funnel.get("entityField") or funnel.get("entity_field")
        steps = _list_dict_items(funnel.get("steps"))
        related_enabled = funnel.get("relatedPropertyEnabled") is True or funnel.get("related_property_enabled") is True
        window_days = funnel.get("windowDays")
        if window_days is None:
            window_days = funnel.get("window_days")
        if window_days is None:
            window_days = 1
        if not _field_has_resolvable_reference(entity_field):
            issues.append("漏斗分析请先选择分析主体。")
        else:
            issues.extend(_json_subfield_mapping_issues(entity_field, "漏斗分析主体"))
            issues.extend(_field_table_permission_issues(entity_field, "漏斗分析主体", allowed_tables))
            issues.extend(_field_schema_permission_issues(entity_field, "漏斗分析主体", allowed_fields_by_table))
        if not _field_has_resolvable_reference(time_config.get("field")):
            issues.append("漏斗分析请先选择时间字段。")
        if len(steps) < 2:
            issues.append("漏斗分析至少需要配置两个步骤。")
        if len(steps) > 10:
            issues.append("漏斗分析最多支持十个步骤。")
        if str((normalized_config.get("chart") or {}).get("type") or request.chart_type) != "funnel":
            issues.append("漏斗分析只能使用漏斗图结果。")
        try:
            normalized_window_days = int(window_days)
        except (TypeError, ValueError):
            normalized_window_days = 0
        if normalized_window_days < 1 or normalized_window_days > 365:
            issues.append("漏斗分析窗口期必须是 1 到 365 天。")
        for index, step in enumerate(steps):
            label = f"漏斗步骤{index + 1}"
            event = step.get("event")
            related_property = step.get("relatedProperty") or step.get("related_property")
            if not _field_has_resolvable_reference(event):
                issues.append(f"{label}请先选择事件。")
            if related_enabled and not _field_has_resolvable_reference(related_property):
                issues.append(f"使用关联属性时请选择{label}关联属性。")
            for field, field_label in (
                (event, f"{label}事件"),
                (related_property if related_enabled else None, f"{label}关联属性"),
            ):
                if not field:
                    continue
                issues.extend(_tracking_event_metadata_issues(field, field_label))
                issues.extend(_json_subfield_mapping_issues(field, field_label))
                issues.extend(_field_table_permission_issues(field, field_label, allowed_tables))
                issues.extend(_field_schema_permission_issues(field, field_label, allowed_fields_by_table))
            event_name = _tracking_event_name_from_field(event)
            property_event_name = _tracking_event_name_from_field(related_property)
            if related_enabled and event_name and property_event_name and event_name != property_event_name:
                issues.append(f"{label}关联属性不属于当前选择的事件。")
            for filter_index, filter_field in enumerate(_iter_filter_rule_fields(step.get("filters"))):
                filter_label = f"{label}筛选{filter_index + 1}"
                issues.extend(_json_subfield_mapping_issues(filter_field, filter_label))
                issues.extend(_field_table_permission_issues(filter_field, filter_label, allowed_tables))
                issues.extend(_field_schema_permission_issues(filter_field, filter_label, allowed_fields_by_table))
                filter_event_name = _tracking_event_name_from_field(filter_field)
                if filter_event_name and event_name and filter_event_name != event_name:
                    issues.append(f"{filter_label}不属于当前选择的事件。")

    if analysis_model == "distribution":
        distribution = normalized_config.get("distribution") if isinstance(normalized_config.get("distribution"), dict) else {}
        entity_field = distribution.get("entityField") or distribution.get("entity_field")
        event = distribution.get("event")
        metric = distribution.get("metric") if isinstance(distribution.get("metric"), dict) else {}
        metric_kind = str(metric.get("kind") or "count").strip().lower()
        metric_field = metric.get("field")
        metric_aggregation = str(metric.get("aggregation") or "sum").strip().lower()
        interval = distribution.get("interval") if isinstance(distribution.get("interval"), dict) else {}
        interval_mode = str(interval.get("mode") or "auto").strip().lower()
        custom_bounds = interval.get("customBounds") or interval.get("custom_bounds") or []
        simultaneous = distribution.get("simultaneous") if isinstance(distribution.get("simultaneous"), dict) else {}
        simultaneous_enabled = simultaneous.get("enabled") is True
        simultaneous_event = simultaneous.get("event")

        if not _field_has_resolvable_reference(entity_field):
            issues.append("分布分析请先选择分析主体。")
        if not _field_has_resolvable_reference(event):
            issues.append("分布分析请先选择参与事件。")
        if not _field_has_resolvable_reference(time_config.get("field")):
            issues.append("分布分析请先选择时间字段。")
        if metric_kind not in {"count", "days", "hours", "property"}:
            issues.append("分布分析使用了不支持的指标类型。")
        if metric_kind == "property":
            if not _field_has_resolvable_reference(metric_field):
                issues.append("分布分析选择事件属性指标时，请先选择事件属性。")
            if metric_aggregation not in _SUPPORTED_DISTRIBUTION_PROPERTY_AGGREGATIONS:
                issues.append(f"分布分析使用了不支持的事件属性聚合方式：{metric_aggregation}。")
            if metric_aggregation not in {"count_distinct"} and metric_field and _field_is_known_non_numeric(metric_field):
                issues.append("分布分析当前事件属性聚合要求数值字段。")
        if interval_mode not in {"auto", "discrete", "custom"}:
            issues.append("分布分析使用了不支持的区间模式。")
        if interval_mode == "custom":
            try:
                normalized_bounds = [float(value) for value in custom_bounds]
            except (TypeError, ValueError):
                normalized_bounds = []
            if (
                len(normalized_bounds) < 2
                or len(normalized_bounds) > 20
                or any(value <= normalized_bounds[index - 1] for index, value in enumerate(normalized_bounds) if index)
            ):
                issues.append("分布分析自定义区间需要 2 到 20 个严格递增的数字边界。")
        if str((normalized_config.get("chart") or {}).get("type") or request.chart_type) != "table":
            issues.append("分布分析当前只能使用分布表结果。")
        if simultaneous_enabled:
            simultaneous_metric = _distribution_simultaneous_metric(distribution)
            if not _field_has_resolvable_reference(simultaneous_event):
                issues.append("分布分析使用同时展示时请选择参与事件。")
            else:
                issues.extend(_validate_metric_item(
                    simultaneous_metric,
                    "分布分析同时展示指标",
                    require_aggregation=True,
                ))
                issues.extend(_metric_permission_issues(
                    simultaneous_metric,
                    "分布分析同时展示指标",
                    allowed_tables,
                    allowed_fields_by_table,
                ))

        for field, label in (
            (entity_field, "分布分析主体"),
            (event, "分布分析参与事件"),
            (metric_field if metric_kind == "property" else None, "分布分析事件属性"),
            (simultaneous_event if simultaneous_enabled else None, "分布分析同时展示事件"),
        ):
            if not field:
                continue
            issues.extend(_tracking_event_metadata_issues(field, label))
            issues.extend(_json_subfield_mapping_issues(field, label))
            issues.extend(_field_table_permission_issues(field, label, allowed_tables))
            issues.extend(_field_schema_permission_issues(field, label, allowed_fields_by_table))
        event_name = _tracking_event_name_from_field(event)
        metric_event_name = _tracking_event_name_from_field(metric_field)
        if metric_kind == "property" and metric_event_name and event_name and metric_event_name != event_name:
            issues.append("分布分析事件属性不属于当前参与事件。")
        for index, filter_field in enumerate(_iter_filter_rule_fields(
            distribution.get("eventFilters") or distribution.get("event_filters")
        )):
            label = f"分布分析参与事件筛选{index + 1}"
            issues.extend(_json_subfield_mapping_issues(filter_field, label))
            issues.extend(_field_table_permission_issues(filter_field, label, allowed_tables))
            issues.extend(_field_schema_permission_issues(filter_field, label, allowed_fields_by_table))
            filter_event_name = _tracking_event_name_from_field(filter_field)
            if filter_event_name and event_name and filter_event_name != event_name:
                issues.append(f"{label}不属于当前参与事件。")

    if analysis_model == "interval":
        interval = normalized_config.get("interval") if isinstance(normalized_config.get("interval"), dict) else {}
        entity_field = interval.get("entityField") or interval.get("entity_field")
        start_event = interval.get("startEvent") or interval.get("start_event")
        end_event = interval.get("endEvent") or interval.get("end_event")
        related_property = interval.get("relatedProperty") if isinstance(interval.get("relatedProperty"), dict) else {}
        related_enabled = related_property.get("enabled") is True
        start_property = related_property.get("startProperty") or related_property.get("start_property")
        end_property = related_property.get("endProperty") or related_property.get("end_property")
        limit_seconds = interval.get("limitSeconds")
        if limit_seconds is None:
            limit_seconds = interval.get("limit_seconds")

        if not _field_has_resolvable_reference(entity_field):
            issues.append("间隔分析请先选择分析主体。")
        if not _field_has_resolvable_reference(start_event):
            issues.append("间隔分析请先选择起点事件。")
        if not _field_has_resolvable_reference(end_event):
            issues.append("间隔分析请先选择终点事件。")
        if not _field_has_resolvable_reference(time_config.get("field")):
            issues.append("间隔分析请先选择时间字段。")
        if str((normalized_config.get("chart") or {}).get("type") or request.chart_type) != "table":
            issues.append("间隔分析当前只能使用间隔表结果。")
        try:
            normalized_limit_seconds = int(limit_seconds)
        except (TypeError, ValueError):
            normalized_limit_seconds = 0
        if normalized_limit_seconds < INTERVAL_LIMIT_MIN_SECONDS or normalized_limit_seconds > INTERVAL_LIMIT_MAX_SECONDS:
            issues.append("间隔分析上限必须是 1 分钟到 180 天。")

        if related_enabled and not _field_has_resolvable_reference(start_property):
            issues.append("使用关联属性时请选择起点事件属性。")
        if related_enabled and not _field_has_resolvable_reference(end_property):
            issues.append("使用关联属性时请选择终点事件属性。")
        start_type_family = _field_type_family(start_property)
        end_type_family = _field_type_family(end_property)
        if related_enabled and start_type_family and end_type_family and start_type_family != end_type_family:
            issues.append("起点事件属性和终点事件属性的类型必须一致。")

        for field, label in (
            (entity_field, "间隔分析主体"),
            (start_event, "间隔分析起点事件"),
            (end_event, "间隔分析终点事件"),
            (start_property if related_enabled else None, "间隔分析起点事件属性"),
            (end_property if related_enabled else None, "间隔分析终点事件属性"),
        ):
            if not field:
                continue
            issues.extend(_tracking_event_metadata_issues(field, label))
            issues.extend(_json_subfield_mapping_issues(field, label))
            issues.extend(_field_table_permission_issues(field, label, allowed_tables))
            issues.extend(_field_schema_permission_issues(field, label, allowed_fields_by_table))

        for property_field, event_field, label in (
            (start_property, start_event, "起点事件关联属性"),
            (end_property, end_event, "终点事件关联属性"),
        ):
            property_event_name = _tracking_event_name_from_field(property_field)
            expected_event_name = _tracking_event_name_from_field(event_field)
            if related_enabled and property_event_name and expected_event_name and property_event_name != expected_event_name:
                issues.append(f"{label}不属于当前选择的事件。")

        for filter_config, event_field, label in (
            (
                interval.get("startEventFilters") or interval.get("start_event_filters"),
                start_event,
                "起点事件筛选",
            ),
            (
                interval.get("endEventFilters") or interval.get("end_event_filters"),
                end_event,
                "终点事件筛选",
            ),
        ):
            expected_event_name = _tracking_event_name_from_field(event_field)
            for index, filter_field in enumerate(_iter_filter_rule_fields(filter_config)):
                filter_label = f"{label}{index + 1}"
                issues.extend(_json_subfield_mapping_issues(filter_field, filter_label))
                issues.extend(_field_table_permission_issues(filter_field, filter_label, allowed_tables))
                issues.extend(_field_schema_permission_issues(filter_field, filter_label, allowed_fields_by_table))
                filter_event_name = _tracking_event_name_from_field(filter_field)
                if filter_event_name and expected_event_name and filter_event_name != expected_event_name:
                    issues.append(f"{filter_label}不属于当前选择的事件。")

    if analysis_model == "path":
        path = normalized_config.get("path") if isinstance(normalized_config.get("path"), dict) else {}
        events = _list_dict_items(path.get("events"))
        selected_events = [item for item in events if _field_has_resolvable_reference(item.get("event"))]
        initial_event = path.get("initialEvent") or path.get("initial_event")
        initial_name = _tracking_event_name_from_field(initial_event)
        if not selected_events:
            issues.append("路径分析至少需要一个参与分析事件。")
        if len(events) > 30:
            issues.append("路径分析最多支持 30 个参与分析事件。")
        if not _field_has_resolvable_reference(initial_event):
            issues.append("路径分析请先选择初始事件。")
        elif initial_name and initial_name not in {
            _tracking_event_name_from_field(item.get("event")) for item in selected_events
        }:
            issues.append("路径分析初始事件必须来自参与分析的事件。")
        if not _field_has_resolvable_reference(time_config.get("field")):
            issues.append("路径分析请先选择时间字段。")
        if str((normalized_config.get("chart") or {}).get("type") or request.chart_type) != "sankey":
            issues.append("路径分析只能使用桑基图结果。")
        session_gap = path.get("sessionGapSeconds")
        if session_gap is None:
            session_gap = path.get("session_gap_seconds")
        try:
            normalized_session_gap = int(session_gap)
        except (TypeError, ValueError):
            normalized_session_gap = 0
        if normalized_session_gap < 1 or normalized_session_gap > 24 * 60 * 60:
            issues.append("路径分析会话间隔必须是 1 秒到 24 小时。")

        for index, event_item in enumerate(events):
            event = event_item.get("event")
            label = f"路径参与事件{index + 1}"
            if not _field_has_resolvable_reference(event):
                issues.append(f"{label}请先选择事件。")
            elif isinstance(event, dict) and str(event.get("kind") or "") != "tracking-event":
                issues.append(f"{label}必须是事件，而不是普通字段。")
            if event:
                issues.extend(_tracking_event_metadata_issues(event, label))
                issues.extend(_json_subfield_mapping_issues(event, label))
                issues.extend(_field_table_permission_issues(event, label, allowed_tables))
                issues.extend(_field_schema_permission_issues(event, label, allowed_fields_by_table))
            event_name = _tracking_event_name_from_field(event)
            split_properties = event_item.get("splitProperties") or event_item.get("split_properties") or []
            for split_index, property_field in enumerate(split_properties):
                property_label = f"{label}拆分属性{split_index + 1}"
                if not _field_has_resolvable_reference(property_field):
                    issues.append(f"{property_label}缺少字段。")
                    continue
                if isinstance(property_field, dict) and str(property_field.get("kind") or "") != "tracking-property":
                    issues.append(f"{property_label}必须是当前事件属性。")
                issues.extend(_json_subfield_mapping_issues(property_field, property_label))
                issues.extend(_field_table_permission_issues(property_field, property_label, allowed_tables))
                issues.extend(_field_schema_permission_issues(property_field, property_label, allowed_fields_by_table))
                property_event_name = _tracking_event_name_from_field(property_field)
                if property_event_name and event_name and property_event_name != event_name:
                    issues.append(f"{property_label}不属于当前参与事件。")
            if list(_iter_filter_rule_fields(event_item.get("filters") or event_item.get("eventFilters") or event_item.get("event_filters"))):
                issues.append(f"{label}不支持事件筛选条件。")

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
        analysis_model=analysis_model if analysis_model in {"retention", "funnel", "distribution", "interval", "path"} else "event",
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
    analysis_model = str(normalized_config.get("analysis_model") or "event")
    retention = normalized_config.get("retention") if isinstance(normalized_config.get("retention"), dict) else {}
    interval = normalized_config.get("interval") if isinstance(normalized_config.get("interval"), dict) else {}
    result_contract: dict[str, Any] = {}
    if analysis_model == "retention":
        simultaneous = retention.get("simultaneous") if isinstance(retention.get("simultaneous"), dict) else {}
        related_property = retention.get("relatedProperty") if isinstance(retention.get("relatedProperty"), dict) else {}
        required_columns = ["cohort_date", "cohort_size"]
        required_columns.extend(f"day_{day}" for day in range(RETENTION_COHORT_DAYS + 1))
        if simultaneous.get("enabled") is True:
            required_columns.append("simultaneous_value")
        if related_property.get("enabled") is True and related_property.get("asGroup") is True:
            required_columns.append("related_property")
        result_contract = {
            "type": "cohort_table",
            "window_days": RETENTION_COHORT_DAYS,
            "required_columns": required_columns,
            "day_value": "retention_rate",
            "final_grain": [
                "cohort_date",
                *(["related_property"] if "related_property" in required_columns else []),
            ],
        }
    elif analysis_model == "distribution":
        distribution = normalized_config.get("distribution") if isinstance(normalized_config.get("distribution"), dict) else {}
        simultaneous = distribution.get("simultaneous") if isinstance(distribution.get("simultaneous"), dict) else {}
        required_columns = [
            "distribution_date",
            "total_entities",
            "interval_order",
            "interval_label",
            "entity_count",
            "entity_rate",
        ]
        if simultaneous.get("enabled") is True:
            required_columns.append("simultaneous_value")
        result_contract = {
            "type": "distribution_table",
            "required_columns": required_columns,
            "final_grain": [
                "distribution_date",
                *[f"group_{index + 1}" for index, _ in enumerate(normalized_config.get("groups") or [])],
                "interval_order",
                "interval_label",
            ],
            "interval_mode": str((distribution.get("interval") or {}).get("mode") or "auto"),
        }
    elif analysis_model == "interval":
        result_contract = {
            "type": "interval_table",
            "required_columns": [
                "interval_date",
                "entity_count",
                "interval_count",
                "max_interval_seconds",
                "p75_interval_seconds",
                "median_interval_seconds",
                "p25_interval_seconds",
                "min_interval_seconds",
                "avg_interval_seconds",
            ],
            "duration_unit": "seconds",
            "limit_seconds": int(interval.get("limitSeconds") or interval.get("limit_seconds") or 3600),
            "final_grain": [
                "interval_date",
                *[f"group_{index + 1}" for index, _ in enumerate(normalized_config.get("groups") or [])],
            ],
        }
    elif analysis_model == "path":
        result_contract = {
            "type": "path_sankey",
            "required_columns": ["path_source", "path_target", "path_value", "path_step"],
            "source_field": "path_source",
            "target_field": "path_target",
            "value_field": "path_value",
            "step_field": "path_step",
            "session_count_field": "session_count",
            "final_grain": ["path_step", "path_source", "path_target"],
        }
    return {
        "analysis_model": analysis_model,
        "retention": retention,
        "funnel": normalized_config.get("funnel") or {},
        "distribution": normalized_config.get("distribution") or {},
        "interval": interval,
        "path": normalized_config.get("path") or {},
        "result_contract": result_contract,
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


def _dashboard_sql_dialect_text(sql_dialect: str | None, datasource: CoreDatasource | None) -> str:
    return " ".join([
        str(sql_dialect or ""),
        str(getattr(datasource, "type", "") or ""),
        str(getattr(datasource, "type_name", "") or ""),
    ]).lower()


def _dashboard_sql_dialect_rules(sql_dialect: str | None, datasource: CoreDatasource | None) -> list[str]:
    dialect_text = _dashboard_sql_dialect_text(sql_dialect, datasource)
    if "mysql" in dialect_text or "mariadb" in dialect_text:
        return [
            "MySQL/MariaDB 方言约束：不能使用 FULL OUTER JOIN；MySQL 不支持该语法。",
            "如果需要合并两个按日期/维度聚合的结果集，优先用一个 key_set CTE 通过 UNION/UNION ALL 去重收集日期或维度键，再分别 LEFT JOIN 各聚合结果；也可以在同一事实表中用 SUM/COUNT(DISTINCT CASE WHEN ...) 做条件聚合。",
        ]
    return []


def _retention_date_generation_rules(
        parameter_type: str,
        sql_dialect: str | None,
        datasource: CoreDatasource | None,
) -> list[str]:
    """为留存查询提供与日期编码和 SQL 方言匹配的强制生成规则。"""
    if parameter_type not in {"yyyymmdd_number", "yyyymmdd_text"}:
        return []
    rules = [
        "留存日期运算规则（强制）：当前时间字段和看板日期参数是 YYYYMMDD 编码键，不是 DATE，也不是自某个纪元起的天数。",
        "原始时间字段的范围过滤必须直接使用 YYYYMMDD 看板参数，避免在过滤列上套日期函数；进入 cohort、behavior、日期窗口或日差计算前，必须另行解析为真实 DATE。",
        "禁止使用 FROM_DAYS 解析 YYYYMMDD，禁止让 YYYYMMDD 数值或文本直接参与 INTERVAL 运算。",
    ]
    dialect_text = _dashboard_sql_dialect_text(sql_dialect, datasource)
    if any(name in dialect_text for name in ("mysql", "mariadb", "starrocks", "doris")):
        rules.extend([
            "MySQL/MariaDB/StarRocks/Doris：YYYYMMDD 转 DATE 必须使用 STR_TO_DATE(CAST(<yyyymmdd_expr> AS CHAR), '%Y%m%d')。",
            "cohort 和 behavior 层必须输出转换后的 DATE；窗口上界使用 DATE_ADD(<cohort_date>, INTERVAL <window_days> DAY)。",
            "日差必须使用 DATEDIFF(<behavior_date>, <cohort_date>)，参数顺序表示回访日期减去初始日期，不得反向。",
        ])
    elif any(name in dialect_text for name in ("postgres", "redshift", "kingbase")):
        rules.extend([
            "PostgreSQL/Redshift/Kingbase：YYYYMMDD 转 DATE 必须使用 TO_DATE(CAST(<yyyymmdd_expr> AS TEXT), 'YYYYMMDD')。",
            "cohort 和 behavior 层必须输出转换后的 DATE，再使用当前方言的日期区间和日期相减语法计算窗口与日差。",
        ])
    else:
        rules.append("必须使用当前 SQL 方言明确支持的 YYYYMMDD 解析函数得到 DATE 后再计算留存窗口和日差，不得猜测日期函数。")
    return rules


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
            ["当前图表不包含可变时间范围，不生成看板日期参数或日期控件；若其为明确固定语义指标，必须保留原有时间含义。"]
            if not uses_date_parameters
            else ["看板日期参数类型缺失，不能生成 SQL。"]
        )
    )
    analysis_model = str(context.get("analysisModel") or context.get("analysis_model") or "event").strip().lower()
    retention = context.get("retention") if isinstance(context.get("retention"), dict) else {}
    retention_rules: list[str] = []
    if analysis_model == "retention":
        simultaneous = retention.get("simultaneous") if isinstance(retention.get("simultaneous"), dict) else {}
        related_property = retention.get("relatedProperty") if isinstance(retention.get("relatedProperty"), dict) else {}
        retention_rules = [
            "当前 analysisModel=retention，必须严格按 retention.entityField、initialEvent 和 returnEvent 生成 cohort 留存查询。",
            "初始事件定义分母 cohort，回访事件定义后续行为；两个事件都必须使用各自字段对象中的 eventTable、eventNameField 和 eventName，不得猜测事件名。",
            "initialEventAlias 和 returnEventAlias 只表示用户设置的展示名称，不得替换 SQL 事件条件中的 eventName。",
            "initialEventFilters 和 returnEventFilters 与指标内筛选使用相同的 logic/rules 结构；必须分别应用于初始事件明细和回访事件明细，不得互换或合并到全局筛选。",
            f"基础结果使用固定 Cohort 宽表，范围为第 0 日到第 {RETENTION_COHORT_DAYS} 日的留存比例：第一列 cohort_date，第二列 cohort_size，后续列为 day_0 到 day_{RETENTION_COHORT_DAYS}。",
            "retention.simultaneous.enabled=true 时，额外按 simultaneous.event、simultaneous.aggregation 和 simultaneous.metricField 计算回访用户参与该事件的统计值，并以 simultaneous_value 输出。",
            "同时展示聚合规则与事件分析指标一致：count=事件明细总次数；count_distinct=COUNT(DISTINCT metricField)；sum/avg/max/min 分别对 metricField 使用 SUM/AVG/MAX/MIN。禁止改用其他字段或默认字段。",
            "retention.relatedProperty.enabled=true 时，初始事件、回访事件以及已启用的同时展示事件必须按各自配置的关联属性值相等进行关联，不得改用同名字段猜测。",
            "retention.relatedProperty.asGroup=true 时，结果必须额外输出 related_property 分组列。",
            f"当前同时展示配置：{_safe_json(simultaneous)}。",
            f"当前关联属性配置：{_safe_json(related_property)}。",
            "最终返回 chart_type 必须为 table。",
        ]
        retention_rules.extend(_retention_date_generation_rules(
            parameter_type,
            sql_dialect,
            datasource,
        ))
    funnel = context.get("funnel") if isinstance(context.get("funnel"), dict) else {}
    funnel_rules: list[str] = []
    if analysis_model == "funnel":
        steps = _list_dict_items(funnel.get("steps"))
        funnel_rules = [
            "当前 analysisModel=funnel，必须严格按 funnel.entityField、funnel.steps 的顺序生成用户漏斗查询。",
            "每个 steps[i].event 都必须使用字段对象中的 eventTable、eventNameField 和 eventName 定位事件，不得猜测事件名或用步骤序号替代事件条件。",
            "漏斗按同一分析主体去重计数：步骤 1 是样本基数，后续步骤必须在前一步完成后发生，并且整个步骤链的时间差不超过 funnel.windowDays 天。",
            "每个步骤的 filters.rules 只应用于该步骤事件明细；全局 filters 仍按全局配置应用，不得把步骤筛选互换或合并。",
            "funnel.relatedPropertyEnabled=true 时，必须使用每个步骤 relatedProperty 指定的属性值与前一步相等进行关联，不得根据字段名猜测关联属性。",
            "最终结果必须是一行一个漏斗步骤，并固定输出 step_order、step_name、step_count、step_rate、step_conversion_rate、step_dropoff_rate 六列；step_rate 以第一步为分母，step_conversion_rate 以相邻上一步为分母。",
            "step_order 必须按 steps 配置顺序为 1、2、3...，不能按用户数据量重新排序；step_name 使用步骤 alias（没有 alias 时使用事件展示名称）。",
            f"当前配置的漏斗步骤数量：{len(steps)}，窗口期：{funnel.get('windowDays') or funnel.get('window_days') or 1} 天。",
            "最终返回 chart_type 必须为 funnel。",
        ]
    distribution = context.get("distribution") if isinstance(context.get("distribution"), dict) else {}
    distribution_rules: list[str] = []
    if analysis_model == "distribution":
        metric = distribution.get("metric") if isinstance(distribution.get("metric"), dict) else {}
        interval = distribution.get("interval") if isinstance(distribution.get("interval"), dict) else {}
        simultaneous = distribution.get("simultaneous") if isinstance(distribution.get("simultaneous"), dict) else {}
        distribution_rules = [
            "当前 analysisModel=distribution，只能使用 distribution 配置生成分布查询；不得读取或套用事件、留存、漏斗模型的指标语义。",
            "先按 distribution.entityField 和 distribution.event 筛选参与过事件的分析主体，再按日期粒度及分组项对每个主体计算一个 distribution_value。未参与该事件的主体不进入任何区间。",
            "distribution.metric.kind=count 时 distribution_value 是主体当期事件次数；days 时是主体发生事件的去重自然日数；hours 时是主体发生事件的去重小时数；property 时必须按 metric.field 和 metric.aggregation 聚合。",
            "property 的 percentile_XX 表示对应百分位数，median 表示中位数，variance/stddev 表示方差/标准差；必须使用当前 SQL 方言支持的函数，不能降级成平均值或其他聚合。",
            "distribution.eventFilters 只应用于参与事件明细；全局筛选和分组项继续使用公共配置，不得互换筛选范围。",
            "distribution.interval.mode=discrete 时每个 distribution_value 单独成区间；mode=custom 时严格按 customBounds 生成小于首边界、相邻边界和大于等于末边界的完整互斥区间；mode=auto 时按数据最小最大值：差值小于 12 使用离散值，否则划分 12 个等宽区间。",
            "最终结果按日期、分组和区间输出固定长表列 distribution_date、interval_order、interval_label、entity_count、entity_rate；entity_rate 是当前日期及分组内区间主体数占参与事件主体总数的比例。",
            "distribution.simultaneous.enabled=true 时，在区间主体集合上按 simultaneous.event、aggregation、metricField 计算事件分析指标并输出 simultaneous_value；不得把它用于划分主区间。",
            f"当前分布指标配置：{_safe_json(metric)}。",
            f"当前分布区间配置：{_safe_json(interval)}。",
            f"当前同时展示配置：{_safe_json(simultaneous)}。",
            "最终返回 chart_type 必须为 table。",
        ]
    path = context.get("path") if isinstance(context.get("path"), dict) else {}
    path_rules: list[str] = []
    if analysis_model == "path":
        path_events = _list_dict_items(path.get("events"))
        path_rules = [
            "当前 analysisModel=path，只能使用 path 配置生成路径查询；不得读取或套用留存、漏斗、分布、间隔模型的指标语义。",
            "路径分析以同一分析主体的会话为基础，从 path.initialEvent 开始向后寻找后续节点；相邻事件时间间隔超过 sessionGapSeconds 时必须结束当前会话。",
            "参与分析事件最多 30 个，事件本身不支持事件筛选；每个事件的 splitProperties 是该事件节点身份的一部分，同一事件不同属性值必须作为不同节点。",
            "必须按同一主体和事件时间排序，先切分会话，再从初始事件开始为相邻节点生成 source/target 边；不要把路径分析实现成漏斗步骤计数，也不要按固定步骤直接聚合事件次数。",
            "最多展示 10 个路径步骤；每一步按节点流量聚合，但最终边结果必须固定输出 path_source、path_target、path_value、path_step，并可额外输出 session_count。path_value 是边的会话数。",
            f"当前路径参与事件数量：{len(path_events)}；初始事件：{_safe_json(path.get('initialEvent') or path.get('initial_event'))}；会话间隔：{path.get('sessionGapSeconds') or path.get('session_gap_seconds') or 1800} 秒。",
            "最终返回 chart_type 必须为 sankey。",
        ]
    interval = context.get("interval") if isinstance(context.get("interval"), dict) else {}
    interval_rules: list[str] = []
    if analysis_model == "interval":
        related_property = interval.get("relatedProperty") if isinstance(interval.get("relatedProperty"), dict) else {}
        interval_rules = [
            "当前 analysisModel=interval，只能使用 interval 配置生成间隔查询；不得读取或套用事件、留存、漏斗、分布模型的指标语义。",
            "同一分析主体的起点事件和终点事件必须按事件时间顺序配对，最终持续时间统一计算为秒。",
            "起点事件与终点事件不同时采用最短间隔原则：连续出现多个起点时只保留最后一个起点，每个起点只匹配其后第一个有效终点；例如 A1,A2,B1,B2 只生成 A2-B1，A1,B1,A2,B2 生成两条间隔。",
            "起点事件与终点事件相同时，按同一主体相邻两条有效事件配对，N 条事件生成 N-1 条间隔；禁止把一条事件与自身配对。",
            "startEventFilters 和 endEventFilters 只应用于各自事件明细；全局筛选和分组项继续使用公共配置，不得交换或合并筛选范围。",
            "interval.relatedProperty.enabled=true 时，起点和终点分别使用配置属性关联，属性值必须相等且两端 NULL 值事件必须剔除；不得按字段名猜测其他关联属性。",
            "仅保留大于等于 0 且小于等于 interval.limitSeconds 的间隔，超过上限的数据在聚合前剔除。",
            "最终结果按起点事件日期和分组统计，并固定输出 interval_date、entity_count、interval_count、max_interval_seconds、p75_interval_seconds、median_interval_seconds、p25_interval_seconds、min_interval_seconds、avg_interval_seconds。",
            "entity_count 是产生有效间隔的主体去重数，interval_count 是有效配对数；所有时长统计列必须保持数值秒，不得在 SQL 中拼接中文时长文本。",
            "分位数必须使用当前 SQL 方言支持的确定性百分位函数，不得用平均值或最大最小值替代。",
            f"当前关联属性配置：{_safe_json(related_property)}。",
            f"当前间隔上限：{interval.get('limitSeconds') or interval.get('limit_seconds') or 3600} 秒。",
            "最终返回 chart_type 必须为 table。",
        ]
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
        "筛选属性范围：指标内筛选可使用当前事件的 tracking-property 事件属性，或字段对象明确提供的 event.userinfo JSON 用户属性。",
        "全局筛选只允许使用 context.filters 中提供的 event.userinfo JSON 子字段；必须使用字段对象的 expression，不得把用户属性改为 user 表或其他表的同名字段。",
        "字段对象包含 sourceField、jsonPath 和 expression 时，JSON 子字段必须使用 expression；不得自行改写 JSON 宿主列或路径。",
        "指标内筛选 rules 是可选配置；没有 rules 或 rules 为空时不是配置缺失，不要要求补筛选条件，不要生成空 WHERE/AND/CASE 条件；只有 rules 里存在有效字段、操作符和值时才应用该筛选。",
         "只允许使用 manual-dashboard-context 里的 selectedFields/metrics/formulaMetrics/calculatedMetrics/groups/filters/retention/funnel/distribution/interval/path 字段信息生成 SQL；不要编造未提供字段。",
        *retention_rules,
        *funnel_rules,
        *distribution_rules,
        *interval_rules,
        *path_rules,
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


def _sqlglot_statements_for_generation_validation(sql: str, sql_dialect: str | None) -> list[exp.Expression]:
    source_sql = re.sub(r"\{\{dashboard_[a-z0-9_]+\}\}", "20260101", str(sql or ""), flags=re.IGNORECASE)
    try:
        dialect = get_sqlglot_dialect(str(sql_dialect or ""))
        return [statement for statement in sqlglot.parse(source_sql, read=dialect) if statement is not None]
    except sqlglot.errors.ParseError:
        return []


def _expression_mentions_column(expression: exp.Expression | None, fragment: str) -> bool:
    if expression is None:
        return False
    return any(
        isinstance(node, exp.Column) and fragment in str(node.name or "").lower()
        for node in expression.walk()
    )


def _retention_date_operation_issues(
        sql: str,
        normalized_config: dict[str, Any],
        *,
        sql_dialect: str | None = None,
        datasource: CoreDatasource | None = None,
) -> list[str]:
    time_config = normalized_config.get("time") if isinstance(normalized_config.get("time"), dict) else {}
    parameter_type = str(time_config.get("date_parameter_type") or "").strip()
    if parameter_type not in {"yyyymmdd_number", "yyyymmdd_text"}:
        return []

    issues: list[str] = []
    if re.search(r"\bfrom_days\s*\(", str(sql or ""), flags=re.IGNORECASE):
        issues.append("留存 SQL 不能使用 FROM_DAYS 解析 YYYYMMDD；必须先按当前方言转换为 DATE。")

    dialect_text = _dashboard_sql_dialect_text(sql_dialect, datasource)
    if not any(name in dialect_text for name in ("mysql", "mariadb", "starrocks", "doris")):
        return _unique_text_items(issues)

    statements = _sqlglot_statements_for_generation_validation(sql, sql_dialect)
    nodes = [node for statement in statements for node in statement.walk()]
    if not any(isinstance(node, exp.StrToDate) for node in nodes):
        issues.append("留存 SQL 未将 YYYYMMDD 通过 STR_TO_DATE 转换为 DATE。")
    if not any(isinstance(node, exp.DateAdd) for node in nodes):
        issues.append("留存 SQL 未使用 DATE_ADD 计算回访窗口上界。")
    if any(
        isinstance(node, (exp.Add, exp.Sub))
        and isinstance(node.args.get("expression"), exp.Interval)
        for node in nodes
    ):
        issues.append("留存 SQL 不能让字段直接加减 INTERVAL；必须对转换后的 DATE 使用 DATE_ADD。")

    date_diffs = [node for node in nodes if isinstance(node, exp.DateDiff)]
    if not date_diffs:
        issues.append("留存 SQL 未使用 DATEDIFF 计算回访日期与初始日期的日差。")
    elif any(
        _expression_mentions_column(node.args.get("this"), "cohort")
        and _expression_mentions_column(node.args.get("expression"), "behavior")
        for node in date_diffs
    ):
        issues.append("留存 SQL 的 DATEDIFF 参数顺序错误；必须使用回访日期减去初始日期。")
    return _unique_text_items(issues)


def _retention_simultaneous_aggregation_issues(
        sql: str,
        retention: dict[str, Any],
        *,
        sql_dialect: str | None = None,
) -> list[str]:
    simultaneous = retention.get("simultaneous") if isinstance(retention.get("simultaneous"), dict) else {}
    if simultaneous.get("enabled") is not True:
        return []
    aggregation = _aggregation_value(_retention_simultaneous_metric(retention))
    if aggregation not in _SUPPORTED_METRIC_AGGREGATIONS:
        return []
    statements = _sqlglot_statements_for_generation_validation(sql, sql_dialect)
    aliases = [
        node
        for statement in statements
        for node in statement.find_all(exp.Alias)
        if _normalized_identifier(node.alias) == "simultaneous_value"
    ]
    if not aliases:
        return []

    aggregate_type_by_name: dict[str, type[exp.Expression]] = {
        "sum": exp.Sum,
        "avg": exp.Avg,
        "max": exp.Max,
        "min": exp.Min,
    }

    def matches(alias: exp.Alias) -> bool:
        aggregate_nodes = list(alias.this.walk())
        if aggregation == "count_distinct":
            return any(
                isinstance(node, exp.Count) and isinstance(node.this, exp.Distinct)
                for node in aggregate_nodes
            )
        if aggregation == "count":
            return any(
                isinstance(node, exp.Count) and not isinstance(node.this, exp.Distinct)
                for node in aggregate_nodes
            )
        expected_type = aggregate_type_by_name.get(aggregation)
        return expected_type is not None and any(isinstance(node, expected_type) for node in aggregate_nodes)

    if any(matches(alias) for alias in aliases):
        return []
    aggregation_labels = {
        "count": "COUNT",
        "count_distinct": "COUNT(DISTINCT ...)",
        "sum": "SUM",
        "avg": "AVG",
        "max": "MAX",
        "min": "MIN",
    }
    return [
        "留存 SQL 的 simultaneous_value 未按同时展示配置使用 "
        f"{aggregation_labels[aggregation]} 聚合。"
    ]


def _retention_sql_result_issues(
        sql: str,
        normalized_config: dict[str, Any],
        *,
        sql_dialect: str | None = None,
        datasource: CoreDatasource | None = None,
) -> list[str]:
    if str(normalized_config.get("analysis_model") or "event") != "retention":
        return []
    retention = normalized_config.get("retention") if isinstance(normalized_config.get("retention"), dict) else {}
    required_aliases = ["cohort_date", "cohort_size"]
    required_aliases.extend(f"day_{day}" for day in range(RETENTION_COHORT_DAYS + 1))
    simultaneous = retention.get("simultaneous") if isinstance(retention.get("simultaneous"), dict) else {}
    related_property = retention.get("relatedProperty") if isinstance(retention.get("relatedProperty"), dict) else {}
    if simultaneous.get("enabled") is True:
        required_aliases.append("simultaneous_value")
    if related_property.get("enabled") is True and related_property.get("asGroup") is True:
        required_aliases.append("related_property")
    normalized_sql = str(sql or "").lower()
    missing = [alias for alias in required_aliases if not re.search(rf"\b{re.escape(alias)}\b", normalized_sql)]
    issues = _retention_date_operation_issues(
        sql,
        normalized_config,
        sql_dialect=sql_dialect,
        datasource=datasource,
    )
    issues.extend(_retention_simultaneous_aggregation_issues(
        sql,
        retention,
        sql_dialect=sql_dialect,
    ))
    if missing:
        issues.append(f"留存 SQL 缺少固定结果列：{'、'.join(missing)}。")
    return _unique_text_items(issues)


def _funnel_sql_result_issues(
        sql: str,
        normalized_config: dict[str, Any],
) -> list[str]:
    if str(normalized_config.get("analysis_model") or "event") != "funnel":
        return []
    required_aliases = [
        "step_order",
        "step_name",
        "step_count",
        "step_rate",
        "step_conversion_rate",
        "step_dropoff_rate",
    ]
    normalized_sql = str(sql or "").lower()
    missing = [alias for alias in required_aliases if not re.search(rf"\b{re.escape(alias)}\b", normalized_sql)]
    return [f"漏斗 SQL 缺少固定结果列：{'、'.join(missing)}。"] if missing else []


def _distribution_sql_result_issues(
        sql: str,
        normalized_config: dict[str, Any],
) -> list[str]:
    if str(normalized_config.get("analysis_model") or "event") != "distribution":
        return []
    distribution = normalized_config.get("distribution") if isinstance(normalized_config.get("distribution"), dict) else {}
    simultaneous = distribution.get("simultaneous") if isinstance(distribution.get("simultaneous"), dict) else {}
    required_aliases = [
        "distribution_date",
        "total_entities",
        "interval_order",
        "interval_label",
        "entity_count",
        "entity_rate",
    ]
    if simultaneous.get("enabled") is True:
        required_aliases.append("simultaneous_value")
    normalized_sql = str(sql or "").lower()
    missing = [alias for alias in required_aliases if not re.search(rf"\b{re.escape(alias)}\b", normalized_sql)]
    issues = [f"分布 SQL 缺少固定结果列：{'、'.join(missing)}。"] if missing else []
    if not re.search(r"\bcount\s*\(\s*distinct\b", normalized_sql):
        issues.append("分布 SQL 必须按分析主体去重统计 entity_count。")
    if not re.search(r"\bnullif\s*\(", normalized_sql):
        issues.append("分布 SQL 的 entity_rate 必须使用 NULLIF 保护分母。")
    return _unique_text_items(issues)


def _interval_sql_result_issues(
        sql: str,
        normalized_config: dict[str, Any],
) -> list[str]:
    if str(normalized_config.get("analysis_model") or "event") != "interval":
        return []
    required_aliases = [
        "interval_date",
        "entity_count",
        "interval_count",
        "max_interval_seconds",
        "p75_interval_seconds",
        "median_interval_seconds",
        "p25_interval_seconds",
        "min_interval_seconds",
        "avg_interval_seconds",
    ]
    normalized_sql = str(sql or "").lower()
    missing = [alias for alias in required_aliases if not re.search(rf"\b{re.escape(alias)}\b", normalized_sql)]
    issues = [f"间隔 SQL 缺少固定结果列：{'、'.join(missing)}。"] if missing else []
    if not re.search(r"\bcount\s*\(\s*distinct\b", normalized_sql):
        issues.append("间隔 SQL 必须按分析主体去重统计 entity_count。")
    if not re.search(r"\bcount\s*\(", normalized_sql):
        issues.append("间隔 SQL 必须统计有效配对数 interval_count。")
    for function_name, label in (("max", "最大值"), ("min", "最小值"), ("avg", "平均值")):
        if not re.search(rf"\b{function_name}\s*\(", normalized_sql):
            issues.append(f"间隔 SQL 缺少{label}聚合。")
    if not re.search(r"\b(?:percentile|percentile_cont|quantile|quantile_cont|median)\s*\(", normalized_sql):
        issues.append("间隔 SQL 必须使用当前方言支持的分位数函数计算四分位数。")
    return _unique_text_items(issues)


def _path_sql_result_issues(
        sql: str,
        normalized_config: dict[str, Any],
) -> list[str]:
    if str(normalized_config.get("analysis_model") or "event") != "path":
        return []
    required_aliases = ["path_source", "path_target", "path_value", "path_step"]
    normalized_sql = str(sql or "").lower()
    missing = [alias for alias in required_aliases if not re.search(rf"\b{re.escape(alias)}\b", normalized_sql)]
    issues = [f"路径 SQL 缺少固定结果列：{'、'.join(missing)}。"] if missing else []
    if not re.search(r"\bcount\s*\(", normalized_sql):
        issues.append("路径 SQL 必须统计相邻路径边的会话数。")
    if not re.search(r"\b(?:lag|lead)\s*\(", normalized_sql):
        issues.append("路径 SQL 必须按会话内事件时间生成相邻节点。")
    if not re.search(r"\bsession(?:_|\b)|\bsession_gap\b|\b(?:datediff|timestampdiff|date_diff|extract)\b", normalized_sql):
        issues.append("路径 SQL 必须应用会话间隔规则。")
    return _unique_text_items(issues)


def _dashboard_sql_system_prompt(analysis_model: str = "event") -> str:
    common_prompt = (
        "你是 BI 手动看板 SQL 生成节点。确定性配置校验已经通过，你只负责根据当前配置、公式 IR 和 SQL plan 生成只读 SELECT SQL。\n"
        "必须使用配置里的时间字段、时间粒度、指标、筛选、分组、计算指标；time.field + time.grain 要生成日期维度；groups 只生成额外维度。不要编造未提供字段。\n"
        "请求中的 chart_type 非空时，返回的 chart_type 必须保持一致，不得改成其他图表类型。"
        "仅当请求中的 chart_type 为 donut，或用户明确要求环形图、圆环图、donut chart 时才允许返回 donut。\n"
        "当用户问题或当前配置涉及复杂分析，例如留存、转化、活跃、复购、漏斗、cohort 分析、分组比率、时间窗口对比时，优先使用 CTE 分层结构。"
        "CTE 只是组织结构范式，所有表名、字段名、事件名、日期表达式、过滤条件、分子分母和成熟窗口必须来自当前配置、business-sql-schema、data-skill 或用户明确规则；不得照抄占位符，也不得编造未提供字段。\n"
        "时间边界层规则：\n"
        "- bounds CTE 必须只返回一行时间边界，供后续 CTE 通过 JOIN 或 CROSS JOIN 引用。\n"
        "- 聚合函数和窗口函数不得出现在同一查询层的 WHERE 条件中。\n"
        "- 当结束日期来自 MAX(date_field) 时，必须先在独立 CTE 中计算最大日期，再在下一层 bounds CTE 中计算开始日期。\n"
        "- 禁止生成 WHERE date_field >= <包含 MAX(date_field) 的表达式>。\n"
        "- 仅当当前图表配置要求可变时间范围时，日期边界必须使用当前配置提供的看板日期参数占位符，不能使用数据库当前日期函数。\n"
        "- 具体日期格式和分区字段类型必须服从当前 SQL 方言与配置的日期参数类型。\n"
    )
    if str(analysis_model or "event") == "retention":
        structure_prompt = (
            "当前 SQL plan 的 analysis_model=retention，必须使用留存专用 Cohort 宽表结构；禁止把最终结果生成为按 period_offset 展开的长表。\n"
            "留存 SQL 结构范式：\n"
            "WITH bounds AS (...仅一行时间边界...),\n"
            "cohort AS (\n"
            "    SELECT DISTINCT <entity_id> AS entity_id, <parsed_cohort_date> AS cohort_date\n"
            "    FROM <configured_initial_event_table>\n"
            "    WHERE <configured_date_filter> AND <configured_initial_event_filter>\n"
            "),\n"
            "behavior AS (\n"
            "    SELECT DISTINCT <entity_id> AS entity_id, <parsed_behavior_date> AS behavior_date\n"
            "    FROM <configured_return_event_table>\n"
            "    WHERE <configured_return_event_filter>\n"
            "),\n"
            "matched AS (\n"
            "    SELECT c.entity_id, c.cohort_date, b.behavior_date,\n"
            "           <dialect_date_diff>(b.behavior_date, c.cohort_date) AS period_offset\n"
            "    FROM cohort c LEFT JOIN behavior b ON <configured_entity_and_window_join>\n"
            ")\n"
            "SELECT cohort_date,\n"
            "       COUNT(DISTINCT entity_id) AS cohort_size,\n"
            "       ROUND(COUNT(DISTINCT CASE WHEN period_offset = 0 THEN entity_id END) * 100.0 / NULLIF(COUNT(DISTINCT entity_id), 0), 2) AS day_0,\n"
            "       ...按同一条件聚合规则继续输出 day_1 到 day_7...\n"
            "FROM matched\n"
            "GROUP BY cohort_date\n"
            "ORDER BY cohort_date。\n"
            "最终 SELECT 必须逐项输出 sql-plan.result_contract.required_columns，列名、顺序和最终粒度必须完全一致。"
            "period_offset 只能作为中间计算字段，不能出现在基础 Cohort 最终结果中。\n"
            "day_0 到 day_7 都表示对应周期回访人数占 cohort_size 的比例；不得输出长表 matched_rate 代替这些固定列。\n"
        )
    elif str(analysis_model or "event") == "interval":
        structure_prompt = (
            "当前 SQL plan 的 analysis_model=interval，必须使用间隔分析专用的事件排序、配对、上限过滤和统计结构。\n"
            "间隔 SQL 结构范式：\n"
            "WITH scoped_events AS (...仅保留起点/终点事件、主体、事件时间、分组、关联属性和各自筛选...),\n"
            "ordered_events AS (...按主体、分组和关联属性分区，并按事件时间稳定排序...),\n"
            "paired AS (...按 interval 配对规则生成 start_time 与 end_time，禁止笛卡尔积产生重复配对...),\n"
            "valid_intervals AS (\n"
            "    SELECT <start_date> AS interval_date, entity_id, <groups>,\n"
            "           <dialect_timestamp_diff_seconds>(start_time, end_time) AS interval_seconds\n"
            "    FROM paired\n"
            "    WHERE end_time >= start_time\n"
            "      AND <dialect_timestamp_diff_seconds>(start_time, end_time) <= <configured_limit_seconds>\n"
            ")\n"
            "SELECT interval_date,\n"
            "       COUNT(DISTINCT entity_id) AS entity_count,\n"
            "       COUNT(*) AS interval_count,\n"
            "       MAX(interval_seconds) AS max_interval_seconds,\n"
            "       <p75_function>(interval_seconds) AS p75_interval_seconds,\n"
            "       <median_function>(interval_seconds) AS median_interval_seconds,\n"
            "       <p25_function>(interval_seconds) AS p25_interval_seconds,\n"
            "       MIN(interval_seconds) AS min_interval_seconds,\n"
            "       AVG(interval_seconds) AS avg_interval_seconds\n"
            "FROM valid_intervals\n"
            "GROUP BY interval_date, <groups>\n"
            "ORDER BY interval_date, <groups>。\n"
            "最终 SELECT 必须逐项输出 sql-plan.result_contract.required_columns；所有时长列必须为数值秒。\n"
            "不同事件必须实现最后起点到首个后续终点的最短配对；相同事件必须使用相邻行配对，不能复用不同事件算法导致遗漏或重复。\n"
        )
    elif str(analysis_model or "event") == "distribution":
        structure_prompt = (
            "当前 SQL plan 的 analysis_model=distribution，必须使用分布分析专用的按主体聚合、区间划分、区间统计三层结构。\n"
            "分布 SQL 结构范式：\n"
            "WITH base_events AS (...仅保留配置事件、日期、主体、分组和配置属性...),\n"
            "entity_values AS (\n"
            "    SELECT <distribution_date> AS distribution_date, <entity_id> AS entity_id, <groups>,\n"
            "           <configured_per_entity_aggregation> AS distribution_value\n"
            "    FROM base_events\n"
            "    GROUP BY distribution_date, entity_id, <groups>\n"
            "),\n"
            "bucketed AS (...按 distribution.interval 生成互斥且完整的 interval_order 与 interval_label...),\n"
            "totals AS (...按 distribution_date 与 groups 统计参与事件的主体总数...)\n"
            "SELECT distribution_date, total_entities, interval_order, interval_label,\n"
            "       COUNT(DISTINCT entity_id) AS entity_count,\n"
            "       ROUND(COUNT(DISTINCT entity_id) * 100.0 / NULLIF(total_entities, 0), 2) AS entity_rate\n"
            "       <启用时输出 simultaneous_value>\n"
            "FROM bucketed ...\n"
            "GROUP BY distribution_date, <groups>, interval_order, interval_label, total_entities\n"
            "ORDER BY distribution_date, <groups>, interval_order。\n"
            "最终 SELECT 必须逐项输出 sql-plan.result_contract.required_columns；interval_order 只负责稳定排序，interval_label 是展示文本。\n"
            "主体必须先聚合再分桶，禁止直接按事件明细行分桶；entity_rate 分母只包含当期参与配置事件的主体。\n"
        )
    elif str(analysis_model or "event") == "path":
        structure_prompt = (
            "当前 SQL plan 的 analysis_model=path，必须使用路径分析专用的会话切分、节点排序和相邻边聚合结构；禁止把路径分析改写为漏斗或普通事件计数。\n"
            "路径 SQL 结构范式：\n"
            "WITH scoped_events AS (...按 path.events 只保留配置事件，输出 entity_id、event_time、event_name、拆分属性和分组...),\n"
            "ordered_events AS (...按 entity_id 和配置分组排序，并用会话间隔识别会话边界...),\n"
            "sessionized AS (...为每条事件生成 session_id，并保留每个会话的事件顺序...),\n"
            "path_nodes AS (...从 path.initialEvent 开始向后取最多 10 个步骤；事件拆分属性参与节点身份...),\n"
            "edges AS (...使用 LAG/LEAD 在同一会话内生成相邻 path_source/path_target，过滤跨会话边...),\n"
            "SELECT path_source, path_target, COUNT(*) AS path_value, path_step\n"
            "FROM edges\n"
            "GROUP BY path_step, path_source, path_target\n"
            "ORDER BY path_step, path_value DESC。\n"
            "最终 SELECT 必须逐项输出 sql-plan.result_contract.required_columns；path_value 是边的会话流量，必须应用 sessionGapSeconds。\n"
        )
    else:
        structure_prompt = (
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
        )
    return (
        common_prompt
        + structure_prompt
        + "只能输出单个 JSON 对象："
        '{"success":true,"sql":"SELECT ...","tables":["..."],"chart_type":"table|line|bar|column|grouped_column|pie|donut|area|metric|scatter|heatmap|funnel|sankey|treemap","brief":"图表标题","intent":"一句话用户意图","message":"","advice":"","issues":[],"suggestions":[]}。'
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
        raise HTTPException(status_code=400, detail="看板未配置数据源，请重新选择数据源")

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
    analysis_model = str((state.get("normalized_config") or {}).get("analysis_model") or "event")
    response = await _async_invoke_llm_json(llm, [
        SystemMessage(content=_dashboard_sql_system_prompt(analysis_model)),
        HumanMessage(content=_dashboard_sql_user_prompt(state)),
    ], node="generate_sql")
    response.analysis_model = analysis_model if analysis_model in {"retention", "funnel", "distribution", "interval", "path"} else "event"
    validation = state.get("validation_result")
    if validation:
        response.intent = response.intent or validation.intent
    return {
        "response": response,
        "graph_trace": _append_trace(state, "generate_sql"),
        "last_node": "generate_sql",
    }


def _dashboard_sql_repair_user_prompt(state: DashboardManualChartGraphState) -> str:
    response = state.get("response") or DashboardAiSqlGenerateResponse(success=False)
    return "\n".join([
        _dashboard_sql_user_prompt(state),
        "",
        "<failed-sql>",
        _trim_text(response.sql, 30000),
        "</failed-sql>",
        "",
        "<sql-validation-issues>",
        _safe_json(list(response.issues or [])),
        "</sql-validation-issues>",
        "",
        "上一版 SQL 未通过留存协议校验。请根据 sql-plan.result_contract 和上述具体错误完整重写 SQL。",
        "不得删除日期、权限、事件、筛选、关联属性或同时展示约束，不得通过改列名掩盖错误。",
    ])


async def _async_node_repair_retention_sql(state: DashboardManualChartGraphState) -> dict[str, Any]:
    llm = await _create_dashboard_ai_sql_llm(state.get("skill_model_id"))
    response = await _async_invoke_llm_json(llm, [
        SystemMessage(content=(
            _dashboard_sql_system_prompt("retention")
            + "\n你正在修复一条未通过留存 SQL 协议校验的查询。必须完整重写 SQL，并逐项消除校验错误；不能放宽或绕过校验。"
        )),
        HumanMessage(content=_dashboard_sql_repair_user_prompt(state)),
    ], node="repair_retention_sql")
    response.analysis_model = "retention"
    return {
        "response": response,
        "sql_repair_attempts": int(state.get("sql_repair_attempts") or 0) + 1,
        "graph_trace": _append_trace(state, "repair_retention_sql"),
        "last_node": "repair_retention_sql",
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
    elif retention_issues := _retention_sql_result_issues(
        sql,
        state.get("normalized_config") or {},
        sql_dialect=state.get("sql_dialect"),
        datasource=state.get("datasource"),
    ):
        response.success = False
        response.message = "生成 SQL 未满足留存分析生成要求。"
        response.advice = "请按当前日期类型、SQL 方言和留存周期重新生成 Cohort 查询。"
        response.issues = _unique_text_items(list(response.issues or []) + retention_issues)
    elif funnel_issues := _funnel_sql_result_issues(
        sql,
        state.get("normalized_config") or {},
    ):
        response.success = False
        response.message = "生成 SQL 未满足漏斗分析生成要求。"
        response.advice = "请按当前漏斗步骤顺序和固定结果列重新生成漏斗查询。"
        response.issues = _unique_text_items(list(response.issues or []) + funnel_issues)
    elif distribution_issues := _distribution_sql_result_issues(
        sql,
        state.get("normalized_config") or {},
    ):
        response.success = False
        response.message = "生成 SQL 未满足分布分析生成要求。"
        response.advice = "请按主体聚合、区间划分和固定结果列重新生成分布查询。"
        response.issues = _unique_text_items(list(response.issues or []) + distribution_issues)
    elif interval_issues := _interval_sql_result_issues(
        sql,
        state.get("normalized_config") or {},
    ):
        response.success = False
        response.message = "生成 SQL 未满足间隔分析生成要求。"
        response.advice = "请按事件配对、间隔上限和固定统计列重新生成间隔查询。"
        response.issues = _unique_text_items(list(response.issues or []) + interval_issues)
    elif path_issues := _path_sql_result_issues(
        sql,
        state.get("normalized_config") or {},
    ):
        response.success = False
        response.message = "生成 SQL 未满足路径分析生成要求。"
        response.advice = "请按会话间隔、初始事件和相邻节点边重新生成路径查询。"
        response.issues = _unique_text_items(list(response.issues or []) + path_issues)
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


def _route_after_sql_validate(state: DashboardManualChartGraphState) -> str:
    response = state.get("response")
    analysis_model = str((state.get("normalized_config") or {}).get("analysis_model") or "event")
    if (
        analysis_model == "retention"
        and response is not None
        and response.success is False
        and bool(str(response.sql or "").strip())
        and bool(response.issues)
        and int(state.get("sql_repair_attempts") or 0) < 1
    ):
        return "repair_retention_sql"
    return "explain_advice"


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
    normalized_config = state.get("normalized_config") or {}
    analysis_model = str(normalized_config.get("analysis_model") or "event")
    response.analysis_model = analysis_model if analysis_model in {"retention", "funnel", "distribution", "interval", "path"} else "event"
    if response.analysis_model == "retention":
        retention = normalized_config.get("retention") if isinstance(normalized_config.get("retention"), dict) else {}
        simultaneous = retention.get("simultaneous") if isinstance(retention.get("simultaneous"), dict) else {}
        related_property = retention.get("relatedProperty") if isinstance(retention.get("relatedProperty"), dict) else {}
        response.chart_type = "table"
        response.result_config = {
            "type": "cohort_table",
            "initial_event_alias": str(retention.get("initialEventAlias") or retention.get("initial_event_alias") or "").strip(),
            "return_event_alias": str(retention.get("returnEventAlias") or retention.get("return_event_alias") or "").strip(),
            "simultaneous_enabled": simultaneous.get("enabled") is True,
            "related_property_enabled": related_property.get("enabled") is True,
            "related_property_as_group": related_property.get("asGroup") is True,
        }
    elif response.analysis_model == "funnel":
        response.chart_type = "funnel"
        response.result_config = {
            "type": "funnel",
            "step_field": "step_name",
            "value_field": "step_count",
            "order_field": "step_order",
            "rate_fields": ["step_rate", "step_conversion_rate", "step_dropoff_rate"],
        }
    elif response.analysis_model == "distribution":
        distribution = normalized_config.get("distribution") if isinstance(normalized_config.get("distribution"), dict) else {}
        simultaneous = distribution.get("simultaneous") if isinstance(distribution.get("simultaneous"), dict) else {}
        response.chart_type = "table"
        response.result_config = {
            "type": "distribution_table",
            "date_field": "distribution_date",
            "total_entities_field": "total_entities",
            "interval_order_field": "interval_order",
            "interval_field": "interval_label",
            "entity_count_field": "entity_count",
            "entity_rate_field": "entity_rate",
            "simultaneous_value_field": "simultaneous_value" if simultaneous.get("enabled") is True else "",
        }
    elif response.analysis_model == "interval":
        interval = normalized_config.get("interval") if isinstance(normalized_config.get("interval"), dict) else {}
        response.chart_type = "table"
        response.result_config = {
            "type": "interval_table",
            "date_field": "interval_date",
            "entity_count_field": "entity_count",
            "interval_count_field": "interval_count",
            "max_field": "max_interval_seconds",
            "p75_field": "p75_interval_seconds",
            "median_field": "median_interval_seconds",
            "p25_field": "p25_interval_seconds",
            "min_field": "min_interval_seconds",
            "avg_field": "avg_interval_seconds",
            "duration_unit": "seconds",
            "limit_seconds": int(interval.get("limitSeconds") or interval.get("limit_seconds") or 3600),
        }
    elif response.analysis_model == "path":
        response.chart_type = "sankey"
        response.result_config = {
            "type": "path_sankey",
            "source_field": "path_source",
            "target_field": "path_target",
            "value_field": "path_value",
            "step_field": "path_step",
            "session_count_field": "session_count",
            "max_steps": 10,
        }
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
    graph.add_node(
        "repair_retention_sql",
        _timed_node("repair_retention_sql", _async_node_repair_retention_sql),
    )
    graph.add_node("explain_advice", _timed_node("explain_advice", _node_explain_advice))
    graph.add_node("finalize_response", _timed_node("finalize_response", _node_finalize_response))
    graph.set_entry_point("collect_context")
    graph.add_edge("collect_context", "normalize_manual_config")
    graph.add_edge("normalize_manual_config", "build_formula_ir")
    graph.add_edge("build_formula_ir", "deterministic_validate")
    graph.add_conditional_edges("deterministic_validate", _route_after_deterministic_validate)
    graph.add_edge("build_sql_plan", "generate_sql")
    graph.add_edge("generate_sql", "validate_sql")
    graph.add_conditional_edges("validate_sql", _route_after_sql_validate)
    graph.add_edge("repair_retention_sql", "validate_sql")
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
