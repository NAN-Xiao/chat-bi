"""
脚本说明：这个脚本把 Data Skill 中声明的可执行 SaaS Skill 转成 Smart Q&A 可调用的多源分析能力。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import orjson
from langchain_core.messages import BaseMessage, HumanMessage
from sqlmodel import Session

from apps.chat.models.chat_model import SystemPromptMessage
from apps.external_mcp.crud import (
    get_bound_external_mcp_id_for_tenant,
    preview_external_mcp_tool,
)
from apps.system.schemas.access_context import require_current_tenant_id
from common.error import SingleMessageError
from common.utils.data_format import DataFormat
from common.utils.utils import AppLogUtil


SAAS_SKILL_COMMENT_RE = re.compile(r"<!--\s*saas-skill\s*:(.*?)-->", re.IGNORECASE | re.DOTALL)
SAAS_SKILL_FENCE_RE = re.compile(r"```(?:saas-skill|json\s+saas-skill)\s*(.*?)```", re.IGNORECASE | re.DOTALL)
PLACEHOLDER_RE = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_.-]*)\s*}}")


@dataclass(frozen=True)
class ExecutableSaasSkillMatch:
    """
    类说明：ExecutableSaasSkillMatch 表示一次用户问题命中的可执行 SaaS Skill。
    """
    definition: dict[str, Any]
    params: dict[str, Any]
    score: int


@dataclass(frozen=True)
class SaasSkillSourceResult:
    """
    类说明：SaasSkillSourceResult 表示可执行 SaaS Skill 的单个数据来源结果。
    """
    name: str
    source_type: str
    fields: list[str]
    data: list[dict[str, Any]]
    spec: dict[str, Any]
    sql: str | None = None
    raw: Any = None
    meta: dict[str, Any] | None = None


@dataclass(frozen=True)
class SaasSkillExecutionResult:
    """
    类说明：SaasSkillExecutionResult 表示可执行 SaaS Skill 执行后的合并结果。
    """
    match: ExecutableSaasSkillMatch
    sources: list[SaasSkillSourceResult]
    merged_result: dict[str, Any]
    chart: dict[str, Any]
    display_sql: str | None


def _json_default(value: Any) -> Any:
    """
    是什么：_json_default 是一个可以复用的小步骤，负责把特殊对象转成 JSON 能表达的值。
    """
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _safe_json_loads(text: str) -> Any:
    """
    是什么：_safe_json_loads 解析 Skill 声明块中的 JSON。
    """
    return orjson.loads((text or "").strip())


def _iter_skill_payloads(payload: Any) -> list[dict[str, Any]]:
    """
    是什么：_iter_skill_payloads 把不同 JSON 形态统一成 Skill 定义列表。
    """
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get("skills"), list):
        return [item for item in payload["skills"] if isinstance(item, dict)]
    if isinstance(payload.get("saas_skills"), list):
        return [item for item in payload["saas_skills"] if isinstance(item, dict)]
    return [payload]


def _is_executable_skill(definition: dict[str, Any]) -> bool:
    """
    是什么：_is_executable_skill 判断一个 Skill 声明是否具备可执行数据来源。
    """
    if definition.get("enabled") is False:
        return False
    sources = definition.get("sources")
    if not isinstance(sources, list) or not sources:
        return False
    return any(str(source.get("type") or "").strip().lower() in {"sql", "mcp", "external_mcp"} for source in sources if isinstance(source, dict))


def parse_executable_saas_skills(data_skill_text: str | None) -> list[dict[str, Any]]:
    """
    是什么：parse_executable_saas_skills 从 Data Skill 文本中提取可执行 SaaS Skill 声明。
    """
    if not data_skill_text:
        return []

    blocks = [match.group(1) for match in SAAS_SKILL_COMMENT_RE.finditer(data_skill_text)]
    blocks.extend(match.group(1) for match in SAAS_SKILL_FENCE_RE.finditer(data_skill_text))

    definitions: list[dict[str, Any]] = []
    for index, block in enumerate(blocks):
        try:
            payload = _safe_json_loads(block)
        except Exception as exc:
            AppLogUtil.warning(f"Skip invalid saas-skill block at index {index}: {exc}")
            continue
        for definition in _iter_skill_payloads(payload):
            if not _is_executable_skill(definition):
                continue
            item = dict(definition)
            item.setdefault("id", f"embedded_saas_skill_{index}_{len(definitions)}")
            definitions.append(item)
    return definitions


def _normalize_text(value: Any) -> str:
    """
    是什么：_normalize_text 把匹配用文本归一化。
    """
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def _word_terms(text: str) -> set[str]:
    """
    是什么：_word_terms 提取中英文关键词，供 Skill 匹配使用。
    """
    normalized = str(text or "").lower()
    terms = {item for item in re.findall(r"[a-zA-Z][a-zA-Z0-9_]{1,}", normalized)}
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", normalized):
        run = re.sub(r"[年月日号天这的了和与及在后前近最近过去]", "", run)
        if len(run) < 2:
            continue
        max_len = min(6, len(run))
        for size in range(2, max_len + 1):
            for start in range(0, len(run) - size + 1):
                terms.add(run[start:start + size])
    return {term for term in terms if len(term) >= 2}


def _flatten_match_terms(definition: dict[str, Any]) -> list[str]:
    """
    是什么：_flatten_match_terms 把 Skill 的 intent/keywords 等触发信息拉平成字符串列表。
    """
    terms: list[str] = []
    for key in ("intent", "intents", "keywords", "triggers", "questions"):
        value = definition.get(key)
        if isinstance(value, str):
            terms.append(value)
        elif isinstance(value, list):
            terms.extend(str(item) for item in value if item not in (None, ""))
    match = definition.get("match")
    if isinstance(match, dict):
        for key in ("keywords_any", "keywords_all", "phrases", "examples"):
            value = match.get(key)
            if isinstance(value, str):
                terms.append(value)
            elif isinstance(value, list):
                terms.extend(str(item) for item in value if item not in (None, ""))
    for key in ("name", "description"):
        if definition.get(key):
            terms.append(str(definition[key]))
    return [term for term in terms if term.strip()]


def _phrase_score(question: str, phrase: str) -> int:
    """
    是什么：_phrase_score 计算一个触发短语和用户问题的相关性。
    """
    q = _normalize_text(question)
    p = _normalize_text(phrase)
    if len(p) < 2 or not q:
        return 0
    if p in q:
        return 18 + min(len(p), 16)
    if q in p and len(q) >= 4:
        return 12

    phrase_terms = _word_terms(phrase)
    if not phrase_terms:
        return 0
    question_terms = _word_terms(question)
    hits = phrase_terms.intersection(question_terms)
    if not hits:
        return 0
    return len(hits) * 4


def _required_terms_match(question: str, definition: dict[str, Any]) -> bool:
    """
    是什么：_required_terms_match 处理 Skill 显式声明的 all/any 匹配规则。
    """
    match = definition.get("match")
    if not isinstance(match, dict):
        return True
    q = _normalize_text(question)
    all_terms = match.get("keywords_all") or match.get("all")
    if isinstance(all_terms, str):
        all_terms = [all_terms]
    if isinstance(all_terms, list):
        for term in all_terms:
            if _normalize_text(term) not in q:
                return False
    any_terms = match.get("keywords_any") or match.get("any")
    if isinstance(any_terms, str):
        any_terms = [any_terms]
    if isinstance(any_terms, list) and any_terms:
        return any(_normalize_text(term) in q for term in any_terms)
    return True


def _map_param_scalar(value: Any, spec: dict[str, Any]) -> Any:
    """
    是什么：_map_param_scalar 按 Skill 声明中的 value_map 归一化枚举值。
    """
    value_map = spec.get("value_map")
    if not isinstance(value_map, dict) or value in (None, ""):
        return value
    raw_text = str(value).strip()
    for key, mapped in value_map.items():
        if str(key).strip().lower() == raw_text.lower():
            return mapped
    return value


def _coerce_number_bounds(value: int | float, spec: dict[str, Any]) -> int | float:
    """
    是什么：_coerce_number_bounds 按 Skill 参数声明限制数值范围。
    """
    minimum = spec.get("min", spec.get("minimum"))
    maximum = spec.get("max", spec.get("maximum"))
    try:
        if minimum not in (None, ""):
            value = max(value, float(minimum))
        if maximum not in (None, ""):
            value = min(value, float(maximum))
    except (TypeError, ValueError):
        return value
    return value


def _coerce_list_value(value: Any, spec: dict[str, Any]) -> list[Any]:
    """
    是什么：_coerce_list_value 把参数值整理成列表，适配 MCP 数组参数。
    """
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, (tuple, set)):
        raw_items = list(value)
    else:
        raw_items = [
            item
            for item in re.split(r"[,，、/\s]+", str(value or ""))
            if item.strip()
        ]
    items = [_map_param_scalar(item, spec) for item in raw_items]
    if spec.get("unique", True):
        result: list[Any] = []
        seen: set[str] = set()
        for item in items:
            key = str(item)
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result
    return items


def _coerce_param_value(value: Any, spec: dict[str, Any]) -> Any:
    """
    是什么：_coerce_param_value 按参数声明转换用户问题中抽取到的值。
    """
    param_type = str(spec.get("type") or "").lower()
    if param_type in {"int", "integer", "number"}:
        try:
            number = float(value)
            bounded = _coerce_number_bounds(number, spec)
            return int(bounded) if float(bounded).is_integer() else bounded
        except (TypeError, ValueError):
            return value
    if param_type in {"bool", "boolean"}:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "y", "是", "开启"}
    if param_type in {"array", "list", "string[]", "str[]"}:
        return _coerce_list_value(value, spec)
    return _map_param_scalar(value, spec)


def _extract_param_by_pattern(question: str, spec: dict[str, Any]) -> Any:
    """
    是什么：_extract_param_by_pattern 用参数自定义正则从问题里抽取值。
    """
    patterns = spec.get("patterns") or []
    if isinstance(patterns, str):
        patterns = [patterns]
    for pattern in patterns:
        try:
            match = re.search(pattern, question or "", re.IGNORECASE)
        except re.error:
            continue
        if not match:
            continue
        group_value = match.groupdict().get("value")
        if group_value is None and match.groups():
            group_value = match.group(1)
        if group_value is not None:
            return group_value
    return None


def _extract_builtin_param(question: str, name: str) -> Any:
    """
    是什么：_extract_builtin_param 对常见时间窗口参数提供内置抽取。
    """
    normalized_name = str(name or "").lower()
    if normalized_name in {"days", "day", "recent_days", "window_days", "date_window_days"}:
        match = re.search(r"(?:最近|近|过去|last)\s*(\d+)\s*(?:天|日|days?)", question or "", re.IGNORECASE)
        if match:
            return match.group(1)
    if normalized_name in {"hours", "hour", "recent_hours", "window_hours"}:
        match = re.search(r"(?:最近|近|过去|last)\s*(\d+)\s*(?:小时|hours?)", question or "", re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def resolve_saas_skill_params(definition: dict[str, Any], question: str | None) -> dict[str, Any]:
    """
    是什么：resolve_saas_skill_params 把用户问题中的时间窗等参数解析成 Skill 执行参数。
    """
    params: dict[str, Any] = {}
    declarations = definition.get("parameters") or {}
    if not isinstance(declarations, dict):
        return params

    for name, raw_spec in declarations.items():
        spec = raw_spec if isinstance(raw_spec, dict) else {"default": raw_spec}
        value = spec.get("default")
        extracted = _extract_param_by_pattern(question or "", spec)
        if extracted is None:
            extracted = _extract_builtin_param(question or "", str(name))
        if extracted is not None:
            value = extracted
        if value in (None, "") and spec.get("required"):
            raise SingleMessageError(f"SaaS Skill 参数 {name} 缺少取值")
        if value is not None:
            params[str(name)] = _coerce_param_value(value, spec)
    if "days" in params:
        try:
            days = max(1, int(params["days"]))
            end_date = date.today()
            start_date = end_date - timedelta(days=days - 1)
            params.setdefault("start_date", start_date.isoformat())
            params.setdefault("end_date", end_date.isoformat())
        except (TypeError, ValueError):
            pass
    return params


def find_matching_executable_saas_skill(data_skill_text: str | None, question: str | None) -> ExecutableSaasSkillMatch | None:
    """
    是什么：find_matching_executable_saas_skill 找出最适合当前问题的可执行 SaaS Skill。
    """
    definitions = parse_executable_saas_skills(data_skill_text)
    if not definitions:
        return None

    scored: list[tuple[int, int, dict[str, Any]]] = []
    for index, definition in enumerate(definitions):
        if not _required_terms_match(question or "", definition):
            continue
        terms = _flatten_match_terms(definition)
        if not terms:
            continue
        score = sum(_phrase_score(question or "", term) for term in terms)
        threshold = int(definition.get("match_threshold") or 8)
        if score >= threshold:
            scored.append((score, index, definition))

    if not scored:
        return None
    score, _index, definition = sorted(scored, key=lambda item: (-item[0], item[1]))[0]
    return ExecutableSaasSkillMatch(
        definition=definition,
        params=resolve_saas_skill_params(definition, question),
        score=score,
    )


def _resolve_placeholder_value(params: dict[str, Any], key: str) -> Any:
    """
    是什么：_resolve_placeholder_value 从参数字典中读取点号路径。
    """
    current: Any = params
    for part in key.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def render_template_value(value: Any, params: dict[str, Any]) -> Any:
    """
    是什么：render_template_value 递归渲染 Skill 声明中的 {{param}} 模板。
    """
    if isinstance(value, dict):
        return {key: render_template_value(item, params) for key, item in value.items()}
    if isinstance(value, list):
        return [render_template_value(item, params) for item in value]
    if not isinstance(value, str):
        return value

    stripped = value.strip()
    exact = PLACEHOLDER_RE.fullmatch(stripped)
    if exact:
        return _resolve_placeholder_value(params, exact.group(1))

    def replace(match: re.Match[str]) -> str:
        resolved = _resolve_placeholder_value(params, match.group(1))
        return "" if resolved is None else str(resolved)

    return PLACEHOLDER_RE.sub(replace, value)


def _source_name(source: dict[str, Any], index: int) -> str:
    """
    是什么：_source_name 返回稳定的数据来源名称。
    """
    name = str(source.get("name") or source.get("id") or "").strip()
    return name or f"source_{index + 1}"


def _normalize_rows(
    fields: list[str] | None,
    rows: list[dict[str, Any]] | None,
    field_map: dict[str, Any] | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    """
    是什么：_normalize_rows 整理执行结果字段和行数据。
    """
    normalized_rows = DataFormat.convert_large_numbers_in_object_array(rows or [])
    normalized_rows = DataFormat.normalize_qualified_sql_column_keys_in_object_array(normalized_rows)
    rename_map = {str(key): str(value) for key, value in (field_map or {}).items() if value not in (None, "")}
    if rename_map:
        normalized_rows = [
            {rename_map.get(str(key), str(key)): value for key, value in row.items()}
            for row in normalized_rows
        ]
        fields = [rename_map.get(str(field), str(field)) for field in fields or []]
    normalized_fields = list(fields or [])
    if not normalized_fields and normalized_rows:
        normalized_fields = list(normalized_rows[0].keys())
    for row in normalized_rows:
        for key in row.keys():
            if key not in normalized_fields:
                normalized_fields.append(key)
    return normalized_fields, normalized_rows


def _execute_sql_source(
    session: Session,
    service: Any,
    source: dict[str, Any],
    index: int,
) -> SaasSkillSourceResult:
    """
    是什么：_execute_sql_source 执行 Skill 声明中的 SQL 数据来源。
    """
    sql = str(source.get("sql_template") or source.get("query") or source.get("sql") or "").strip()
    if not sql and isinstance(source.get("sql_template_lines"), list):
        sql = "\n".join(str(line) for line in source["sql_template_lines"]).strip()
    if not sql:
        raise SingleMessageError("SaaS Skill SQL source is missing sql_template")
    result = service.execute_sql(
        session=session,
        sql=sql,
        scope_sql=sql,
        scope_allowed_tables=getattr(service, "table_name_list", None),
    )
    fields, rows = _normalize_rows(result.get("fields"), result.get("data"), source.get("field_map"))
    return SaasSkillSourceResult(
        name=_source_name(source, index),
        source_type="sql",
        fields=fields,
        data=rows,
        spec=source,
        sql=sql,
        raw=result,
    )


def _external_mcp_server_id(session: Session, service: Any, source: dict[str, Any]) -> int:
    """
    是什么：_external_mcp_server_id 解析 MCP 数据来源应该调用的外部 MCP 服务。
    """
    configured = source.get("external_mcp_server_id") or source.get("server_id") or source.get("mcp_server_id")
    if configured not in (None, ""):
        return int(configured)
    tenant_id = require_current_tenant_id(service.current_user)
    bound_server_id = get_bound_external_mcp_id_for_tenant(session, tenant_id)
    if bound_server_id is None:
        raise SingleMessageError("当前工作空间未绑定第三方 MCP 数据源，无法执行 SaaS Skill 的 MCP 来源")
    return int(bound_server_id)


def _execute_mcp_source(
    session: Session,
    service: Any,
    source: dict[str, Any],
    index: int,
) -> SaasSkillSourceResult:
    """
    是什么：_execute_mcp_source 执行 Skill 声明中的外部 MCP 数据来源。
    """
    tool = str(source.get("tool") or "").strip()
    if not tool:
        raise SingleMessageError("SaaS Skill MCP source is missing tool")
    arguments = source.get("arguments_template")
    if arguments is None:
        arguments = source.get("arguments") or {}
    if not isinstance(arguments, dict):
        raise SingleMessageError("SaaS Skill MCP source arguments must be an object")

    preview = preview_external_mcp_tool(
        session,
        service.current_user,
        external_mcp_server_id=_external_mcp_server_id(session, service, source),
        tool=tool,
        arguments=arguments,
        result_path=source.get("result_path"),
        key_field=source.get("key_field"),
        value_field=source.get("value_field"),
        tenant_id=source.get("tenant_id") or require_current_tenant_id(service.current_user),
        dashboard_id=source.get("dashboard_id"),
    )
    fields, rows = _normalize_rows(preview.get("fields"), preview.get("data"), source.get("field_map"))
    return SaasSkillSourceResult(
        name=_source_name(source, index),
        source_type="external_mcp",
        fields=fields,
        data=rows,
        spec=source,
        raw=preview.get("raw"),
        meta=preview.get("mcp"),
    )


def execute_saas_skill_sources(
    session: Session,
    service: Any,
    match: ExecutableSaasSkillMatch,
) -> list[SaasSkillSourceResult]:
    """
    是什么：execute_saas_skill_sources 依次执行 SaaS Skill 声明的 SQL/MCP 数据来源。
    """
    source_results: list[SaasSkillSourceResult] = []
    for index, raw_source in enumerate(match.definition.get("sources") or []):
        if not isinstance(raw_source, dict):
            continue
        source = render_template_value(raw_source, match.params)
        source_type = str(source.get("type") or "").strip().lower()
        if source_type == "sql":
            source_results.append(_execute_sql_source(session, service, source, index))
        elif source_type in {"mcp", "external_mcp"}:
            source_results.append(_execute_mcp_source(session, service, source, index))
    if not source_results:
        raise SingleMessageError("SaaS Skill 没有可执行的数据来源")
    return source_results


def _row_join_key(row: dict[str, Any], join_fields: list[str]) -> tuple[Any, ...]:
    """
    是什么：_row_join_key 生成跨来源合并用的行 key。
    """
    return tuple(str(row.get(field) or "") for field in join_fields)


def _field_output_name(
    source: SaasSkillSourceResult,
    field: str,
    collisions: set[str],
) -> str:
    """
    是什么：_field_output_name 处理不同来源字段同名冲突。
    """
    aliases = source.spec.get("field_aliases") or {}
    if isinstance(aliases, dict) and aliases.get(field):
        return str(aliases[field])
    if field in collisions:
        return f"{source.name}.{field}"
    return field


def _merge_without_join(sources: list[SaasSkillSourceResult]) -> dict[str, Any]:
    """
    是什么：_merge_without_join 没有 join key 时把多来源数据纵向拼接。
    """
    fields = ["source"]
    rows: list[dict[str, Any]] = []
    for source in sources:
        for field in source.fields:
            if field not in fields:
                fields.append(field)
        for row in source.data:
            rows.append({"source": source.name, **row})
    return {"status": "success", "fields": fields, "data": rows}


def merge_saas_skill_sources(
    sources: list[SaasSkillSourceResult],
    merge: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    是什么：merge_saas_skill_sources 按 Skill 声明把 SQL/MCP 结果合并为一张证据表。
    """
    merge = merge if isinstance(merge, dict) else {}
    join_fields = merge.get("join_fields") or merge.get("keys") or merge.get("on") or []
    if isinstance(join_fields, str):
        join_fields = [join_fields]
    join_fields = [str(field) for field in join_fields if str(field).strip()]
    if not join_fields:
        return _merge_without_join(sources)

    non_key_field_sources: dict[str, set[str]] = {}
    for source in sources:
        for field in source.fields:
            if field not in join_fields:
                non_key_field_sources.setdefault(field, set()).add(source.name)
    collisions = {field for field, owners in non_key_field_sources.items() if len(owners) > 1}

    rows_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    order: list[tuple[Any, ...]] = []
    output_fields = list(join_fields)
    for source in sources:
        for row in source.data:
            key = _row_join_key(row, join_fields)
            if key not in rows_by_key:
                rows_by_key[key] = {field: row.get(field) for field in join_fields}
                order.append(key)
            target = rows_by_key[key]
            for field in source.fields:
                if field in join_fields:
                    continue
                output_field = _field_output_name(source, field, collisions)
                if output_field not in output_fields:
                    output_fields.append(output_field)
                target[output_field] = row.get(field)

    mode = str(merge.get("mode") or "outer").lower()
    if mode == "inner":
        required_keys = [
            {_row_join_key(row, join_fields) for row in source.data}
            for source in sources
        ]
        common_keys = set.intersection(*required_keys) if required_keys else set()
        order = [key for key in order if key in common_keys]

    return {
        "status": "success",
        "fields": output_fields,
        "data": [rows_by_key[key] for key in order],
    }


def build_saas_skill_chart(
    match: ExecutableSaasSkillMatch,
    merged_result: dict[str, Any],
) -> dict[str, Any]:
    """
    是什么：build_saas_skill_chart 生成 Smart Q&A 可展示的图表配置。
    """
    configured_chart = match.definition.get("chart")
    if isinstance(configured_chart, dict):
        chart = render_template_value(configured_chart, match.params)
        chart.setdefault("type", "table")
        chart.setdefault("title", match.definition.get("name") or "SaaS Skill 分析")
        return chart

    fields = merged_result.get("fields") or []
    return {
        "type": "table",
        "title": match.definition.get("name") or match.definition.get("id") or "SaaS Skill 分析",
        "columns": [{"name": field, "value": field} for field in fields],
    }


def execute_saas_skill(
    session: Session,
    service: Any,
    match: ExecutableSaasSkillMatch,
) -> SaasSkillExecutionResult:
    """
    是什么：execute_saas_skill 执行并合并一个可执行 SaaS Skill。
    """
    sources = execute_saas_skill_sources(session, service, match)
    merged_result = merge_saas_skill_sources(sources, match.definition.get("merge"))
    chart = build_saas_skill_chart(match, merged_result)
    display_sqls = [source.sql for source in sources if source.sql]
    return SaasSkillExecutionResult(
        match=match,
        sources=sources,
        merged_result=merged_result,
        chart=chart,
        display_sql="\n\n".join(display_sqls) if display_sqls else None,
    )


def _truncate_text(value: Any, limit: int = 240) -> Any:
    """
    是什么：_truncate_text 控制给模型的证据体积。
    """
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + "..."
    return value


def _sample_rows(rows: list[dict[str, Any]], limit: int = 80) -> list[dict[str, Any]]:
    """
    是什么：_sample_rows 截取证据样例行。
    """
    sampled: list[dict[str, Any]] = []
    for row in rows[:limit]:
        sampled.append({key: _truncate_text(value) for key, value in row.items()})
    return sampled


def _answer_contract(definition: dict[str, Any]) -> Any:
    """
    是什么：_answer_contract 读取 Skill 声明中的回答约束。
    """
    analysis = definition.get("analysis")
    if isinstance(analysis, dict):
        return analysis.get("answer_contract") or analysis.get("sections") or analysis.get("instructions")
    return analysis


def build_saas_skill_answer_messages(
    service: Any,
    execution: SaasSkillExecutionResult,
) -> list[BaseMessage]:
    """
    是什么：build_saas_skill_answer_messages 构造基于多源证据的最终回答提示词。
    """
    match = execution.match
    definition = match.definition
    source_evidence = []
    for source in execution.sources:
        source_evidence.append({
            "name": source.name,
            "type": source.source_type,
            "fields": source.fields,
            "row_count": len(source.data),
            "sample_rows": _sample_rows(source.data),
            "meta": source.meta or {},
        })
    evidence = {
        "skill": {
            "id": definition.get("id"),
            "name": definition.get("name"),
            "description": definition.get("description"),
        },
        "question": service.chat_question.question,
        "parameters": match.params,
        "sources": source_evidence,
        "merged": {
            "fields": execution.merged_result.get("fields") or [],
            "row_count": len(execution.merged_result.get("data") or []),
            "sample_rows": _sample_rows(execution.merged_result.get("data") or [], limit=120),
        },
        "answer_contract": _answer_contract(definition),
    }
    system = (
        f"你是{getattr(service.chat_question, 'shuzhi_name', '星通数智')}的数据分析助手。"
        "现在你要基于一个已授权的 SaaS Skill 的执行结果回答用户问题。"
        "只能使用给出的 SQL/MCP 证据、字段名、行数据和 Skill 回答约束，不要编造未提供的数值、日期、来源或业务口径。"
        "如果证据不足以确认原因，要明确说明证据不足，并给出下一步需要补充的数据。"
        f"请使用{getattr(service.chat_question, 'lang', '简体中文')}回答。"
    )
    human = (
        "用户问题：\n"
        f"{service.chat_question.question}\n\n"
        "SaaS Skill 执行证据(JSON)：\n"
        f"{orjson.dumps(evidence, default=_json_default).decode()}\n\n"
        "请输出结构化但自然的分析结论，优先覆盖 answer_contract 中要求的部分；"
        "需要把 SQL 指标和 MCP/外部信号放在同一时间线或同一维度下对照解释。"
    )
    return [SystemPromptMessage(content=system), HumanMessage(content=human)]


def serialize_saas_skill_messages(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    """
    是什么：serialize_saas_skill_messages 把回答提示词转成日志可存的结构。
    """
    serialized: list[dict[str, Any]] = []
    for message in messages:
        serialized.append({
            "type": getattr(message, "type", message.__class__.__name__),
            "content": getattr(message, "content", ""),
        })
    return serialized


def stream_saas_skill_answer_chunks(
    service: Any,
    messages: list[BaseMessage],
    token_usage: dict[str, Any],
):
    """
    是什么：stream_saas_skill_answer_chunks 调用当前问答模型生成 SaaS Skill 分析答案。
    """
    from apps.chat.task.llm import process_stream

    yield from process_stream(service.llm.stream(messages), token_usage)
