"""
脚本说明：这个脚本放聊天问数据和 Agent里较长或较复杂的处理流程，把一次任务分成可维护的步骤。
"""
from __future__ import annotations

import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, TypedDict

import orjson
import sqlglot
import sqlparse
from langgraph.graph import END, StateGraph
from sqlalchemy import text
from sqlglot import exp

from apps.chat.curd.chat import (
    end_log,
    format_json_data,
    get_chat_chart_data,
    rename_chat,
    save_analysis_answer,
    save_chart,
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
from apps.chat.task.sql_repair import (
    SQL_REPAIR_MAX_ATTEMPTS,
    SqlRepairContext,
    SqlRepairReason,
    classify_execute_sql_error,
    classify_prepare_sql_error,
    sanitize_sql_repair_error,
    sql_repair_fingerprint,
)
from apps.datasource.crud.permission_errors import (
    audit_permission_denied,
    looks_like_permission_scope_error,
)
from apps.datasource.crud.sql_engine import (
    get_ai_table_schema,
    user_data_unavailable_message,
    validate_user_query_sql_or_raise,
)
from apps.datasource.crud.sql_permission import normalize_identifier
from apps.datasource.models.datasource import CoreDatasource
from apps.db.db import check_connection, get_session, get_sqlglot_dialect
from common.core.config import settings
from common.error import AppDBConnectionError, DataUnavailableError
from common.utils.data_format import DataFormat
from common.utils.utils import AppLogUtil, extract_nested_json

WORKFLOW_KEY = "smart_qa"
RUN_ID_PREFIX = "smartqa"
LOG_PREFIX = "Smart Q&A LangGraph"
WORKFLOW_CONFIG = AssistantWorkflowConfig(WORKFLOW_KEY, RUN_ID_PREFIX, LOG_PREFIX)


def _sql_answer_message(full_sql_text: str) -> str | None:
    """
    是什么：从 SQL 生成结果里取出可展示给用户的普通提示。
    谁调用：Smart Q&A 生成 SQL 后需要提示部分数据缺失时调用。
    做了什么：只读取 success=true 的 message/warning，避免把失败原因当作成功提示重复展示。
    """
    json_str = extract_nested_json(full_sql_text)
    if not json_str:
        return None
    try:
        data = orjson.loads(json_str)
    except Exception:
        return None
    if not isinstance(data, dict) or not data.get("success"):
        return None
    message = data.get("message") or data.get("warning")
    if not isinstance(message, str):
        return None
    message = message.strip()
    return message or None


def _save_and_emit_plain_answer(
    *,
    service: Any,
    session: Any,
    message: str,
    in_chat: bool,
    stream: bool,
    json_result: dict[str, Any],
    finish: bool = False,
    notice: dict[str, Any] | None = None,
) -> None:
    """
    是什么：把业务提示保存为普通回答并发送给前端。
    谁调用：Smart Q&A 遇到部分数据缺失或数据不可用时调用。
    做了什么：复用 analysis 字段/analysis-result 事件，不把业务提示写成 record.error。
    """
    answer_payload = {
        "content": message,
        "reasoning_content": "",
    }
    if notice:
        answer_payload["notice"] = notice
    answer = orjson.dumps(answer_payload).decode()
    if hasattr(service, "save_analysis"):
        service.record = service.save_analysis(session=session, answer=answer)
    else:
        service.record = save_analysis_answer(
            session=session,
            record_id=service.record.id,
            answer=answer,
        )
    if in_chat:
        event_payload = {
            "content": message,
            "reasoning_content": "",
            "type": "analysis-result",
        }
        if notice:
            event_payload["notice"] = notice
        _emit(_sse(event_payload))
        if finish:
            _emit(_sse({"type": "finish"}))
    elif stream:
        _emit(f"> {message}\n")
    else:
        json_result["message"] = message
        if notice:
            json_result["notice"] = notice


def _has_result_rows(result: dict[str, Any] | None) -> bool:
    """
    是什么：判断 SQL 结果是否有可展示的数据行。
    谁调用：Smart Q&A 决定是否继续生成图表。
    做了什么：空结果仍会保存执行记录，但不会再生成空图表控件。
    """
    if not isinstance(result, dict):
        return False
    fields = result.get("fields")
    rows = result.get("data")
    return isinstance(fields, list) and len(fields) > 0 and isinstance(rows, list) and len(rows) > 0


def _empty_result_notice() -> dict[str, Any]:
    """
    是什么：生成空结果的业务提示标记。
    谁调用：SQL 正常执行但没有返回数据时调用。
    做了什么：把“没有数据”标为业务结果，而不是系统错误。
    """
    return {
        "notice_type": "data_scope_gap",
        "reason": "data_unavailable",
        "severity": "info",
    }


def _empty_result_feedback() -> str:
    """
    是什么：空结果时展示给用户的简短说明。
    谁调用：SQL 正常执行但没有可展示数据时调用。
    做了什么：避免前端出现空图表/空表，让用户明确知道查询范围内没有结果。
    """
    return "当前查询条件下没有可展示的数据，已保存本次执行记录。"


@dataclass
class _RequestedEventPredicate:
    table: str
    schema: str
    table_alias: str
    event_field: str
    event_values: set[str] = field(default_factory=set)
    select_alias: str | None = None
    select_output_columns: set[str] = field(default_factory=set)


@dataclass
class _EventResultCleanup:
    result: dict[str, Any]
    removed_fields: list[str] = field(default_factory=list)
    missing_events: list[str] = field(default_factory=list)


@dataclass
class _EventAvailability:
    predicate: _RequestedEventPredicate
    missing_values: set[str] = field(default_factory=set)
    existing_values: set[str] = field(default_factory=set)
    unknown_values: set[str] = field(default_factory=set)


@dataclass
class _MissingEventSqlRewrite:
    sql: str | None
    missing_events: list[str] = field(default_factory=list)
    unknown_events: list[str] = field(default_factory=list)
    removed_fields: list[str] = field(default_factory=list)
    removed_ctes: list[str] = field(default_factory=list)
    availability: list[_EventAvailability] = field(default_factory=list)
    changed: bool = False
    executable: bool = True


_EVENT_EXISTENCE_CACHE: dict[tuple[Any, str, str, str, str], tuple[float, bool]] = {}
_EVENT_EXISTENCE_CACHE_LOCK = Lock()


def _event_name_fields_for_service(service: Any) -> set[str]:
    """
    是什么：找出当前工作空间里表示“事件/埋点名”的字段名。
    谁调用：SQL 执行后校验事件值是否真实存在。
    做了什么：优先读工作空间打点配置；没有配置时用通用 event_name 兜底。
    """
    fields = {"event_name"}
    tracking_config = getattr(getattr(service, "chat_question", None), "tracking_config", "") or ""
    for pattern in [
        r"默认事件名字段\s*[:：]\s*`([^`]+)`",
        r"default_event_name_field[\"'\s:：]+([A-Za-z_][A-Za-z0-9_]*)",
    ]:
        for match in re.finditer(pattern, tracking_config, flags=re.IGNORECASE):
            field_name = normalize_identifier(match.group(1))
            if field_name:
                fields.add(field_name)
    for match in re.finditer(r"(?:field_role|role)[\"'\s:：]+event_name", tracking_config, flags=re.IGNORECASE):
        window = tracking_config[max(0, match.start() - 240): match.end() + 240]
        field_match = re.search(r"(?:field_name|field|字段)[\"'\s:：]+([A-Za-z_][A-Za-z0-9_]*)", window, flags=re.IGNORECASE)
        if field_match:
            field_name = normalize_identifier(field_match.group(1))
            if field_name:
                fields.add(field_name)
    return fields


def _sql_statements(sql: str, ds_type: str | None) -> list[exp.Expression]:
    """
    是什么：把原始 SQL 文本解析为 sqlglot 语法树语句列表。
    谁调用：所有需要分析或改写 SQL 的事件存在性相关函数调用。
    做了什么：根据数据源类型选择对应方言，调用 sqlglot.parse 解析并过滤掉空语句。
    """
    dialect = get_sqlglot_dialect(ds_type)
    return [stmt for stmt in sqlglot.parse(sql, dialect=dialect) if stmt is not None]


def _table_aliases_for_select(select_expr: exp.Select) -> dict[str, exp.Table]:
    """
    是什么：收集 SELECT 语句中 FROM 和 JOIN 子句的表别名映射。
    谁调用：_extract_requested_event_predicates、_aliases_for_final_sources 等 SQL 分析函数调用。
    做了什么：遍历 SELECT 的 from 和 joins，把表名及其别名映射回 exp.Table 节点，用于后续定位事件字段所属表。
    """
    sources = []
    from_expr = select_expr.args.get("from_")
    if from_expr and from_expr.this is not None:
        sources.append(from_expr.this)
    for join in select_expr.args.get("joins") or []:
        if join.this is not None:
            sources.append(join.this)

    aliases: dict[str, exp.Table] = {}
    for source in sources:
        if not isinstance(source, exp.Table):
            continue
        alias = normalize_identifier(source.alias_or_name or source.name)
        table_name = normalize_identifier(source.name)
        if alias:
            aliases[alias] = source
        if table_name:
            aliases[table_name] = source
    return aliases


def _literal_strings(expr_node: exp.Expression) -> set[str]:
    """
    是什么：从 sqlglot 表达式中提取所有字符串字面量。
    谁调用：_event_values_from_condition 在解析 WHERE 条件中的事件值时调用。
    做了什么：如果节点本身是字符串字面量则直接返回，否则递归查找子节点中的字符串字面量并去重返回。
    """
    values: set[str] = set()
    if isinstance(expr_node, exp.Literal) and expr_node.is_string:
        values.add(str(expr_node.this))
        return values
    for literal in expr_node.find_all(exp.Literal):
        if literal.is_string:
            values.add(str(literal.this))
    return values


def _event_values_from_condition(condition: exp.Expression, event_fields: set[str]) -> list[tuple[exp.Column, set[str]]]:
    """
    是什么：从 WHERE/HAVING 等条件表达式中提取与事件字段相关的字面量值。
    谁调用：_extract_requested_event_predicates 解析 SQL 谓词时调用。
    做了什么：遍历条件中的 EQ 和 In 表达式，当一侧是配置的事件名字段时，收集另一侧的字符串字面量，返回 (字段列, 事件值集合) 列表。
    """
    matches: list[tuple[exp.Column, set[str]]] = []

    for eq in condition.find_all(exp.EQ):
        left_column = eq.left if isinstance(eq.left, exp.Column) else None
        right_column = eq.right if isinstance(eq.right, exp.Column) else None
        if left_column is not None and normalize_identifier(left_column.name) in event_fields:
            values = _literal_strings(eq.right)
            if values:
                matches.append((left_column, values))
        elif right_column is not None and normalize_identifier(right_column.name) in event_fields:
            values = _literal_strings(eq.left)
            if values:
                matches.append((right_column, values))

    for in_expr in condition.find_all(exp.In):
        target = in_expr.this
        if not isinstance(target, exp.Column) or normalize_identifier(target.name) not in event_fields:
            continue
        values = set()
        expressions = in_expr.args.get("expressions") or []
        for item in expressions:
            values.update(_literal_strings(item))
        query = in_expr.args.get("query")
        if query is not None:
            values.update(_literal_strings(query))
        if values:
            matches.append((target, values))

    return matches


def _selected_output_columns(select_expr: exp.Select) -> set[str]:
    """
    是什么：获取 SELECT 语句输出列的别名集合。
    谁调用：_extract_requested_event_predicates 记录每个 SELECT 的输出列信息时调用。
    做了什么：遍历 SELECT 的表达式列表，使用 alias_or_name 归一化后收集非通配符列名。
    """
    columns: set[str] = set()
    for item in select_expr.expressions:
        alias = normalize_identifier(item.alias_or_name)
        if alias and alias != "*":
            columns.add(alias)
    return columns


def _extract_requested_event_predicates(sql: str, service: Any) -> list[_RequestedEventPredicate]:
    """
    是什么：从 SQL 中解析出所有涉及事件名字段的查询谓词。
    谁调用：_event_availability_for_sql 在检查事件存在性前调用。
    做了什么：解析 SQL 语句，对每个 SELECT 的 WHERE 条件分析事件字段，记录涉及的表、schema、别名、事件字段、事件值、所在 CTE 别名及输出列。
    """
    event_fields = _event_name_fields_for_service(service)
    if not event_fields:
        return []

    predicates: list[_RequestedEventPredicate] = []
    try:
        statements = _sql_statements(sql, getattr(getattr(service, "ds", None), "type", None))
    except Exception as exc:
        AppLogUtil.warning(f"Skip missing event post-check because SQL parsing failed: {exc}")
        return []

    for statement in statements:
        for select_expr in statement.find_all(exp.Select):
            where_expr = select_expr.args.get("where")
            if where_expr is None or where_expr.this is None:
                continue
            aliases = _table_aliases_for_select(select_expr)
            for column, values in _event_values_from_condition(where_expr.this, event_fields):
                table_ref = aliases.get(normalize_identifier(column.table))
                if table_ref is None and len(aliases) == 1:
                    table_ref = next(iter(aliases.values()))
                if table_ref is None:
                    continue
                table_name = normalize_identifier(table_ref.name)
                if not table_name:
                    continue
                predicates.append(_RequestedEventPredicate(
                    table=table_name,
                    schema=normalize_identifier(table_ref.db),
                    table_alias=normalize_identifier(table_ref.alias_or_name or table_ref.name),
                    event_field=normalize_identifier(column.name),
                    event_values=values,
                    select_alias=normalize_identifier(_nearest_cte_alias(select_expr)),
                    select_output_columns=_selected_output_columns(select_expr),
                ))

    return predicates


def _nearest_cte_alias(select_expr: exp.Select) -> str | None:
    """
    是什么：查找 SELECT 表达式所在最近的 CTE 名称。
    谁调用：_extract_requested_event_predicates 在定位事件谓词属于哪个 CTE 时调用。
    做了什么：沿 sqlglot 父节点向上遍历，遇到 exp.CTE 时返回其别名，无则返回 None。
    """
    parent = select_expr.parent
    while parent is not None:
        if isinstance(parent, exp.CTE):
            return parent.alias_or_name
        parent = parent.parent
    return None


def _quote_table_for_sql(table_name: str, schema_name: str | None, ds_type: str | None) -> str:
    """
    是什么：把表名和可选 schema 名转换为带引号的 SQL 表标识符字符串。
    谁调用：_event_values_exist_in_datasource 构造存在性探测 SQL 时调用。
    做了什么：使用 sqlglot 创建带引号的 Table 表达式并按数据源方言输出 SQL 文本。
    """
    table = exp.Table(this=exp.to_identifier(table_name, quoted=True))
    if schema_name:
        table.set("db", exp.to_identifier(schema_name, quoted=True))
    return table.sql(dialect=get_sqlglot_dialect(ds_type))


def _event_cache_datasource_key(ds: Any) -> Any:
    """
    是什么：为事件存在性缓存生成数据源级别的唯一键。
    谁调用：_event_cache_key 构造缓存键时调用。
    做了什么：优先返回数据源 id，否则返回由数据源类型、名称和对象 id 组成的元组。
    """
    return getattr(ds, "id", None) or (
        getattr(ds, "type", None),
        getattr(ds, "name", None),
        id(ds),
    )


def _event_cache_key(
        *,
        ds: Any,
        schema: str,
        table: str,
        event_field: str,
        event_value: str,
) -> tuple[Any, str, str, str, str]:
    """
    是什么：生成单个事件值存在性缓存的精确键。
    谁调用：_cached_event_existence 和 _store_event_existence_cache 读写缓存时调用。
    做了什么：组合数据源键、schema、表名、事件字段和事件值，并对标识符做归一化。
    """
    return (
        _event_cache_datasource_key(ds),
        normalize_identifier(schema),
        normalize_identifier(table),
        normalize_identifier(event_field),
        event_value,
    )


def _configured_event_values_for_service(service: Any) -> set[str]:
    """
    是什么：从工作空间打点配置中提取已声明的事件值。
    谁调用：事件存在性后置检查。
    做了什么：优先信任当前工作空间维护的事件字典，避免对已配置事件值再扫大事件表。
    """
    tracking_config = getattr(getattr(service, "chat_question", None), "tracking_config", "") or ""
    if not tracking_config:
        return set()
    configured: set[str] = set()

    for match in re.finditer(
            r"<Configured-Event-Names>(.*?)</Configured-Event-Names>",
            tracking_config,
            flags=re.IGNORECASE | re.DOTALL,
    ):
        try:
            values = orjson.loads(match.group(1))
        except orjson.JSONDecodeError:
            continue
        if isinstance(values, list):
            configured.update(str(value).strip() for value in values if str(value).strip())

    for match in re.finditer(
            r'"(?:events|event_names)"\s*:\s*\[(.*?)\]',
            tracking_config,
            flags=re.IGNORECASE | re.DOTALL,
    ):
        for value in re.findall(r'"([^"]+)"', match.group(1)):
            value = value.strip()
            if value:
                configured.add(value)
    for match in re.finditer(
            r'"(?:event_name|eventName)"\s*:\s*"([^"]+)"',
            tracking_config,
            flags=re.IGNORECASE,
    ):
        value = match.group(1).strip()
        if value:
            configured.add(value)
    return configured


def _cached_event_existence(
        *,
        ds: Any,
        schema: str,
        table: str,
        event_field: str,
        event_values: set[str],
) -> tuple[dict[str, bool], set[str]]:
    """
    是什么：从进程内缓存读取一批事件值的存在性结果。
    谁调用：_event_values_exist_in_datasource 在查库前尝试命中缓存时调用。
    做了什么：读取 SMART_QA_EVENT_EXISTENCE_CACHE_TTL_SECONDS 配置，在锁保护下过滤过期键，返回已缓存结果和待查值集合。
    """
    ttl = max(0, int(getattr(settings, "SMART_QA_EVENT_EXISTENCE_CACHE_TTL_SECONDS", 0) or 0))
    if ttl <= 0:
        return {}, set(event_values)
    now = time.monotonic()
    cached: dict[str, bool] = {}
    pending: set[str] = set()
    with _EVENT_EXISTENCE_CACHE_LOCK:
        for event_value in event_values:
            key = _event_cache_key(
                ds=ds,
                schema=schema,
                table=table,
                event_field=event_field,
                event_value=event_value,
            )
            item = _EVENT_EXISTENCE_CACHE.get(key)
            if item and item[0] > now:
                cached[event_value] = item[1]
            else:
                if item:
                    _EVENT_EXISTENCE_CACHE.pop(key, None)
                pending.add(event_value)
    return cached, pending


def _store_event_existence_cache(
        *,
        ds: Any,
        schema: str,
        table: str,
        event_field: str,
        values: dict[str, bool],
) -> None:
    """
    是什么：把事件值存在性结果写入进程内缓存。
    谁调用：_event_values_exist_in_datasource 查询数据库后将新结果缓存时调用。
    做了什么：在锁保护下按 TTL 设置缓存项，键由 _event_cache_key 生成。
    """
    ttl = max(0, int(getattr(settings, "SMART_QA_EVENT_EXISTENCE_CACHE_TTL_SECONDS", 0) or 0))
    if ttl <= 0 or not values:
        return
    expires_at = time.monotonic() + ttl
    with _EVENT_EXISTENCE_CACHE_LOCK:
        for event_value, exists in values.items():
            key = _event_cache_key(
                ds=ds,
                schema=schema,
                table=table,
                event_field=event_field,
                event_value=event_value,
            )
            _EVENT_EXISTENCE_CACHE[key] = (expires_at, bool(exists))


def _chunks(values: list[str], size: int):
    """
    是什么：把列表按指定大小切分为多个批次。
    谁调用：_event_values_exist_in_datasource 分批查询事件值存在性时调用。
    做了什么：使用生成器每次产出至多 size 个元素的子列表。
    """
    chunk_size = max(1, int(size or 1))
    for index in range(0, len(values), chunk_size):
        yield values[index:index + chunk_size]


def _event_values_exist_in_datasource(
        *,
        service: Any,
        table: str,
        schema: str,
        event_field: str,
        event_values: set[str],
) -> dict[str, bool | None]:
    """
    是什么：探测一组事件值在物理数据源表中是否存在。
    谁调用：_event_availability_for_sql 按组检查事件存在性时调用。
    做了什么：先读缓存，再分批对未命中缓存的值执行 SELECT DISTINCT 查询，把结果写回缓存，返回每个值的存在状态（True/False/None）。
    """
    ds = getattr(service, "ds", None)
    values = {str(value) for value in event_values if str(value).strip()}
    if ds is None or not values:
        return {value: None for value in values}

    configured_values = _configured_event_values_for_service(service)
    configured_hits = values.intersection(configured_values)
    result: dict[str, bool | None] = {value: True for value in configured_hits}
    values_to_probe = values.difference(configured_hits)
    if not values_to_probe:
        return result

    cached, pending = _cached_event_existence(
        ds=ds,
        schema=schema,
        table=table,
        event_field=event_field,
        event_values=values_to_probe,
    )
    result.update(cached)
    if not pending:
        return result

    ds_type = getattr(ds, "type", None)
    dialect = get_sqlglot_dialect(ds_type)
    table_sql = _quote_table_for_sql(table, schema, ds_type)
    field_sql = exp.column(event_field, quoted=True).sql(dialect=dialect)
    existing_values: set[str] = set()
    batch_size = max(1, int(getattr(settings, "SMART_QA_EVENT_EXISTENCE_BATCH_SIZE", 500) or 500))
    db_session = None
    try:
        db_session = get_session(ds, timeout=10)
        for batch in _chunks(sorted(pending), batch_size):
            params = {f"event_value_{index}": value for index, value in enumerate(batch)}
            placeholders = ", ".join(f":event_value_{index}" for index in range(len(batch)))
            sql = f"SELECT DISTINCT {field_sql} AS event_value FROM {table_sql} WHERE {field_sql} IN ({placeholders})"
            rows = db_session.execute(text(sql), params).all()
            for row in rows:
                try:
                    existing_values.add(str(row[0]))
                except Exception:
                    pass
    except Exception as exc:
        AppLogUtil.warning(
            "Skip missing event post-check batch: "
            f"{table}.{event_field} values={sorted(pending)} error={exc}"
        )
        for event_value in pending:
            result[event_value] = None
        return result
    finally:
        if db_session is not None:
            db_session.close()

    fresh = {event_value: event_value in existing_values for event_value in pending}
    _store_event_existence_cache(
        ds=ds,
        schema=schema,
        table=table,
        event_field=event_field,
        values=fresh,
    )
    result.update(fresh)
    return result


def _event_exists_in_datasource(
        *,
        service: Any,
        table: str,
        schema: str,
        event_field: str,
        event_value: str,
) -> bool | None:
    """
    是什么：探测单个事件值在物理数据源表中是否存在。
    谁调用：需要单点检查事件存在性的地方（目前主要为 _event_values_exist_in_datasource 的便捷封装）。
    做了什么：调用 _event_values_exist_in_datasource 并返回该单个值的存在状态。
    """
    return _event_values_exist_in_datasource(
        service=service,
        table=table,
        schema=schema,
        event_field=event_field,
        event_values={event_value},
    ).get(event_value)


def _event_availability_for_sql(service: Any, sql: str) -> list[_EventAvailability]:
    """
    是什么：对 SQL 中请求的所有事件值进行存在性校验并分类。
    谁调用：_rewrite_sql_for_missing_events、_cleanup_missing_event_result 等事件缺失处理逻辑调用。
    做了什么：提取事件谓词，按 (schema, table, event_field) 分组查库，根据 strict/unknown 策略把每个值标记为缺失、存在或未知。
    """
    predicates = _extract_requested_event_predicates(sql, service)
    if not predicates:
        return []

    grouped_values: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for predicate in predicates:
        grouped_values[(predicate.schema, predicate.table, predicate.event_field)].update(predicate.event_values)

    existence_by_group: dict[tuple[str, str, str], dict[str, bool | None]] = {}
    for (schema, table, event_field), event_values in grouped_values.items():
        existence_by_group[(schema, table, event_field)] = _event_values_exist_in_datasource(
            service=service,
            table=table,
            schema=schema,
            event_field=event_field,
            event_values=event_values,
        )

    unknown_policy = str(getattr(settings, "SMART_QA_EVENT_UNKNOWN_POLICY", "conservative") or "conservative").lower()
    strict_unknown = unknown_policy == "strict"
    availability: list[_EventAvailability] = []
    for predicate in predicates:
        item = _EventAvailability(predicate=predicate)
        for event_value in predicate.event_values:
            exists = existence_by_group.get(
                (predicate.schema, predicate.table, predicate.event_field),
                {},
            ).get(event_value)
            if exists is False:
                item.missing_values.add(event_value)
            elif exists is True:
                item.existing_values.add(event_value)
            elif strict_unknown:
                item.missing_values.add(event_value)
            else:
                item.unknown_values.add(event_value)
        availability.append(item)
    return availability


def _missing_requested_events_from_availability(items: list[_EventAvailability]) -> list[_RequestedEventPredicate]:
    """
    是什么：从事件可用性结果中筛选出缺失的事件谓词。
    谁调用：_cleanup_missing_event_result 判断需要清理哪些事件时调用。
    做了什么：遍历 _EventAvailability 列表，把 missing_values 非空的谓词重新构造为 _RequestedEventPredicate 返回。
    """
    missing: list[_RequestedEventPredicate] = []
    for item in items:
        if item.missing_values:
            predicate = item.predicate
            missing.append(_RequestedEventPredicate(
                table=predicate.table,
                schema=predicate.schema,
                table_alias=predicate.table_alias,
                event_field=predicate.event_field,
                event_values=item.missing_values,
                select_alias=predicate.select_alias,
                select_output_columns=predicate.select_output_columns,
            ))
    return missing


def _missing_requested_events(service: Any, sql: str) -> list[_RequestedEventPredicate]:
    """
    是什么：获取 SQL 中所有请求但数据源缺失的事件值。
    谁调用：_cleanup_missing_event_result 在 availability 参数为 None 时调用。
    做了什么：调用 _event_availability_for_sql 后再用 _missing_requested_events_from_availability 提取缺失事件。
    """
    return _missing_requested_events_from_availability(_event_availability_for_sql(service, sql))


def _unknown_events_from_availability(items: list[_EventAvailability]) -> list[str]:
    """
    是什么：收集事件存在性校验中无法确认的事件值。
    谁调用：_rewrite_sql_for_missing_events 生成 unknown_events 列表时调用。
    做了什么：从 _EventAvailability 列表中提取所有 unknown_values 并排序去重。
    """
    return sorted({
        value
        for item in items
        for value in item.unknown_values
    })


def _final_select(statement: exp.Expression) -> exp.Select | None:
    """
    是什么：从一条 SQL 语句中找出最终 SELECT 表达式。
    谁调用：_result_fields_for_missing_events 在定位最终输出 SELECT 时调用。
    做了什么：若语句本身是 SELECT 则直接返回，否则通过 find(exp.Select) 查找内部的 SELECT。
    """
    if isinstance(statement, exp.Select):
        return statement
    return statement.find(exp.Select)


def _aliases_for_final_sources(select_expr: exp.Select) -> dict[str, str]:
    """
    是什么：获取最终 SELECT 中所有表来源的别名到表名映射。
    谁调用：_result_fields_for_missing_events 和 _remove_missing_event_cte_branches 在识别列来源时调用。
    做了什么：调用 _table_aliases_for_select，把别名和表名都映射到归一化的表名。
    """
    aliases: dict[str, str] = {}
    for alias, table_expr in _table_aliases_for_select(select_expr).items():
        source_name = normalize_identifier(table_expr.name)
        if source_name:
            aliases[alias] = source_name
    return aliases


def _result_fields_for_missing_events(sql: str, service: Any, missing_events: list[_RequestedEventPredicate]) -> set[str]:
    """
    是什么：根据缺失事件谓词找出需要被移除的结果字段。
    谁调用：_rewrite_sql_for_missing_events 和 _cleanup_missing_event_result 在清理结果时调用。
    做了什么：解析 SQL，找出最终 SELECT 输出列中依赖缺失 CTE/表的字段，返回这些输出字段名集合。
    """
    if not missing_events:
        return set()
    try:
        statements = _sql_statements(sql, getattr(getattr(service, "ds", None), "type", None))
    except Exception:
        return set()

    missing_ctes: dict[str, set[str]] = {}
    for event in missing_events:
        if event.select_alias:
            missing_ctes.setdefault(normalize_identifier(event.select_alias), set()).update(event.select_output_columns)

    fields: set[str] = set()
    for statement in statements:
        select_expr = _final_select(statement)
        if select_expr is None:
            continue
        final_aliases = _aliases_for_final_sources(select_expr)
        only_final_source = next(iter(final_aliases.values()), None) if len(set(final_aliases.values())) == 1 else None
        for item in select_expr.expressions:
            output_name = item.alias_or_name
            if not output_name:
                continue
            for column in item.find_all(exp.Column):
                source_alias = normalize_identifier(column.table)
                source_name = final_aliases.get(source_alias) or (only_final_source if not source_alias else None)
                if not source_name:
                    continue
                output_columns = missing_ctes.get(source_name)
                if output_columns is None:
                    continue
                if not output_columns or normalize_identifier(column.name) in output_columns:
                    fields.add(output_name)
                    break
    return fields


def _prune_result_fields(result: dict[str, Any], fields_to_remove: set[str]) -> dict[str, Any]:
    """
    是什么：从 SQL 执行结果中删除指定的字段列。
    谁调用：_cleanup_missing_event_result 和 _execute_sql 在业务提示要求移除字段时调用。
    做了什么：重建 fields 和 data，过滤掉指定的列名，保持其他数据结构不变。
    """
    if not fields_to_remove:
        return result
    fields = [field for field in result.get("fields") or [] if field not in fields_to_remove]
    data = []
    for row in result.get("data") or []:
        if isinstance(row, dict):
            data.append({key: value for key, value in row.items() if key not in fields_to_remove})
        else:
            data.append(row)
    cleaned = dict(result)
    cleaned["fields"] = fields
    cleaned["data"] = data
    return cleaned


def _missing_event_feedback(missing_events: list[str], removed_fields: list[str]) -> str:
    """
    是什么：生成缺失埋点事件的用户提示文案。
    谁调用：_prepare_sql 和 _execute_sql 在检测到缺失事件时调用。
    做了什么：拼接缺失事件名称，如果有被移除的字段则补充说明已生成其余结果。
    """
    event_text = "、".join(missing_events)
    if removed_fields:
        return f"当前数据源缺少 {event_text} 埋点数据，已生成其余可支持的结果。"
    return f"当前数据源缺少 {event_text} 埋点数据。"


def _missing_event_notice(missing_events: list[str], removed_fields: list[str]) -> dict[str, Any]:
    """
    是什么：构造缺失埋点事件的业务提示数据结构。
    谁调用：_prepare_sql 和 _execute_sql 在需要返回 notice 时调用。
    做了什么：返回包含 notice_type、severity、reason、items 和 removed_fields 的字典。
    """
    return {
        "notice_type": "data_scope_gap",
        "severity": "warning",
        "reason": "missing_event",
        "items": missing_events,
        "removed_fields": removed_fields,
    }


def _unknown_event_feedback(unknown_events: list[str]) -> str:
    """
    是什么：生成无法确认事件存在性的用户提示文案。
    谁调用：_prepare_sql 在检测到未知事件时调用。
    做了什么：拼接未知事件名称，提示相关数值可能受数据源状态影响。
    """
    event_text = "、".join(unknown_events)
    return f"未能确认 {event_text} 埋点是否存在，相关数值可能受数据源状态影响。"


def _unknown_event_notice(unknown_events: list[str]) -> dict[str, Any]:
    """
    是什么：构造事件存在性未知的业务提示数据结构。
    谁调用：_prepare_sql 在需要返回未知事件 notice 时调用。
    做了什么：返回包含 notice_type、reason、unconfirmed_events 和 agent_guidance 的字典。
    """
    return {
        "notice_type": "data_scope_gap",
        "severity": "warning",
        "reason": "event_existence_unknown",
        "items": unknown_events,
        "unconfirmed_events": unknown_events,
        "agent_guidance": "部分埋点存在性未能确认，结论需提示这些指标可能不完整或为占位零值。",
    }


def _business_notice_rank(notice: dict[str, Any] | None) -> int:
    """
    是什么：评估业务提示的严重程度权重。
    谁调用：_merge_business_notice 在比较多个提示时调用。
    做了什么：根据 reason 返回缺失事件、存在性未知、数据不可用的优先级分数，未知 reason 返回 0。
    """
    reason = str((notice or {}).get("reason") or "")
    return {
        "missing_event": 30,
        "event_existence_unknown": 20,
        "data_unavailable": 10,
    }.get(reason, 0)


def _merge_business_notice(
        current: dict[str, Any] | None,
        candidate: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """
    是什么：合并两个业务提示，保留更严重的一个。
    谁调用：_prepare_sql 在组合缺失事件和未知事件提示时调用。
    做了什么：无候选返回当前，无当前返回候选，否则按 _business_notice_rank 比较并返回分数更高的提示。
    """
    if not candidate:
        return current
    if not current or _business_notice_rank(candidate) >= _business_notice_rank(current):
        return candidate
    return current


def _missing_event_predicates_from_availability(items: list[_EventAvailability]) -> list[_RequestedEventPredicate]:
    """
    是什么：从事件可用性结果中构造缺失事件的谓词列表。
    谁调用：_rewrite_sql_for_missing_events 在需要改写 SQL 前提取缺失谓词时调用。
    做了什么：遍历 availability，把 missing_values 非空的谓词复制为新的 _RequestedEventPredicate。
    """
    missing: list[_RequestedEventPredicate] = []
    for item in items:
        if not item.missing_values:
            continue
        predicate = item.predicate
        missing.append(_RequestedEventPredicate(
            table=predicate.table,
            schema=predicate.schema,
            table_alias=predicate.table_alias,
            event_field=predicate.event_field,
            event_values=set(item.missing_values),
            select_alias=predicate.select_alias,
            select_output_columns=set(predicate.select_output_columns),
        ))
    return missing


def _removable_missing_event_ctes(items: list[_EventAvailability]) -> set[str]:
    """
    是什么：判断哪些 CTE 分支因事件全部缺失而可以被整体移除。
    谁调用：_rewrite_sql_for_missing_events 在决定移除哪些 CTE 时调用。
    做了什么：按 CTE 别名分组，若某 CTE 下所有谓词都缺失事件且没有任何存在/未知事件，则该 CTE 可移除。
    """
    grouped: dict[str, dict[str, bool]] = {}
    for item in items:
        alias = normalize_identifier(item.predicate.select_alias)
        if not alias:
            continue
        state = grouped.setdefault(alias, {"missing": False, "supported": False})
        if item.missing_values:
            state["missing"] = True
        if item.existing_values or item.unknown_values or not item.missing_values:
            state["supported"] = True
    return {
        alias
        for alias, state in grouped.items()
        if state["missing"] and not state["supported"]
    }


def _expression_references_sources(
        expression: exp.Expression | None,
        *,
        source_aliases: set[str],
        final_aliases: dict[str, str],
        source_names: set[str],
) -> bool:
    """
    是什么：判断 sqlglot 表达式是否引用了指定的表别名或表名。
    谁调用：_remove_order_references 和 _remove_missing_event_cte_branches 在决定移除哪些子句时调用。
    做了什么：遍历表达式中的列，检查列的 table 是否在 source_aliases 中，或经 final_aliases 映射后落在 source_names 中。
    """
    if expression is None:
        return False
    for column in expression.find_all(exp.Column):
        alias = normalize_identifier(column.table)
        if alias in source_aliases:
            return True
        if final_aliases.get(alias) in source_names:
            return True
    return False


def _remove_order_references(
        select_expr: exp.Select,
        *,
        source_aliases: set[str],
        final_aliases: dict[str, str],
        source_names: set[str],
) -> None:
    """
    是什么：从 SELECT 中移除引用缺失 CTE/表的 ORDER BY 项。
    谁调用：_remove_missing_event_cte_branches 在改写 SQL 时调用。
    做了什么：过滤 order 表达式中引用被移除来源的项，若全部项都被移除则把整个 order 置空。
    """
    order_expr = select_expr.args.get("order")
    if not order_expr:
        return
    expressions = [
        item
        for item in order_expr.expressions
        if not _expression_references_sources(
            item,
            source_aliases=source_aliases,
            final_aliases=final_aliases,
            source_names=source_names,
        )
    ]
    if expressions:
        order_expr.set("expressions", expressions)
    else:
        select_expr.set("order", None)


def _remove_missing_event_cte_branches(
        statement: exp.Expression,
        *,
        missing_ctes: set[str],
        fields_to_remove: set[str],
) -> bool:
    """
    是什么：在语法树层面移除因事件缺失而无法提供数据的 CTE/Join 分支及关联字段。
    谁调用：_rewrite_sql_for_missing_events 对每条 SQL 语句进行改写时调用。
    做了什么：删除缺失 CTE，移除关联的 LEFT JOIN、输出列、WHERE/HAVING/GROUP/QUALIFY 引用，并清理 ORDER BY；若主表或关键子句受影响则放弃改写。
    """
    if not missing_ctes:
        return False
    select_expr = statement if isinstance(statement, exp.Select) else None
    if select_expr is None:
        return False

    with_expr = statement.args.get("with_")
    if with_expr:
        kept_ctes = [
            cte
            for cte in with_expr.expressions
            if normalize_identifier(cte.alias_or_name) not in missing_ctes
        ]
        if len(kept_ctes) != len(with_expr.expressions):
            if kept_ctes:
                with_expr.set("expressions", kept_ctes)
            else:
                statement.set("with_", None)

    final_aliases = _aliases_for_final_sources(select_expr)
    removed_aliases = {
        alias
        for alias, source_name in final_aliases.items()
        if source_name in missing_ctes
    }
    removed_aliases.update(missing_ctes)

    from_expr = select_expr.args.get("from_")
    if from_expr and isinstance(from_expr.this, exp.Table):
        if normalize_identifier(from_expr.this.name) in missing_ctes:
            return False

    kept_joins = []
    removed_join = False
    for join in select_expr.args.get("joins") or []:
        source = join.this
        if isinstance(source, exp.Table) and normalize_identifier(source.name) in missing_ctes:
            if str(join.args.get("side") or "").upper() != "LEFT":
                return False
            removed_join = True
            continue
        kept_joins.append(join)
    if removed_join:
        select_expr.set("joins", kept_joins)

    normalized_removed_fields = {normalize_identifier(field) for field in fields_to_remove}
    kept_expressions = []
    removed_expression = False
    for item in select_expr.expressions:
        output_name = normalize_identifier(item.alias_or_name)
        if output_name in normalized_removed_fields or _expression_references_sources(
            item,
            source_aliases=removed_aliases,
            final_aliases=final_aliases,
            source_names=missing_ctes,
        ):
            removed_expression = True
            continue
        kept_expressions.append(item)
    if not kept_expressions:
        return False
    if removed_expression:
        select_expr.set("expressions", kept_expressions)

    for key in ("where", "having", "qualify", "group"):
        if _expression_references_sources(
            select_expr.args.get(key),
            source_aliases=removed_aliases,
            final_aliases=final_aliases,
            source_names=missing_ctes,
        ):
            return False

    _remove_order_references(
        select_expr,
        source_aliases=removed_aliases,
        final_aliases=final_aliases,
        source_names=missing_ctes,
    )

    return removed_join or removed_expression


def _rewrite_sql_for_missing_events(service: Any, sql: str) -> _MissingEventSqlRewrite:
    """
    是什么：当 SQL 请求的事件部分缺失时尝试改写 SQL 以保留可展示结果。
    谁调用：_prepare_sql 在校验用户 SQL 后调用。
    做了什么：检查事件可用性，计算缺失/未知事件，若可安全移除整组 CTE 分支则生成改写后的 SQL；否则返回不可执行及原因。
    """
    availability = _event_availability_for_sql(service, sql)
    missing_events = sorted({
        value
        for item in availability
        for value in item.missing_values
    })
    unknown_events = _unknown_events_from_availability(availability)
    if not missing_events:
        return _MissingEventSqlRewrite(
            sql=sql,
            unknown_events=unknown_events,
            availability=availability,
            executable=True,
        )

    missing_predicates = _missing_event_predicates_from_availability(availability)
    fields_to_remove = _result_fields_for_missing_events(sql, service, missing_predicates)
    missing_ctes = _removable_missing_event_ctes(availability)
    if not missing_ctes:
        return _MissingEventSqlRewrite(
            sql=None,
            missing_events=missing_events,
            unknown_events=unknown_events,
            removed_fields=sorted(fields_to_remove),
            availability=availability,
            executable=False,
        )

    try:
        statements = _sql_statements(sql, getattr(getattr(service, "ds", None), "type", None))
    except Exception as exc:
        AppLogUtil.warning(f"Skip missing event SQL rewrite because SQL parsing failed: {exc}")
        return _MissingEventSqlRewrite(
            sql=None,
            missing_events=missing_events,
            unknown_events=unknown_events,
            removed_fields=sorted(fields_to_remove),
            availability=availability,
            executable=False,
        )

    rewritten_statements: list[exp.Expression] = []
    changed = False
    for statement in statements:
        rewritten = statement.copy()
        statement_changed = _remove_missing_event_cte_branches(
            rewritten,
            missing_ctes=missing_ctes,
            fields_to_remove=fields_to_remove,
        )
        if not statement_changed:
            return _MissingEventSqlRewrite(
                sql=None,
                missing_events=missing_events,
                unknown_events=unknown_events,
                removed_fields=sorted(fields_to_remove),
                removed_ctes=sorted(missing_ctes),
                availability=availability,
                executable=False,
            )
        changed = True
        rewritten_statements.append(rewritten)

    dialect = get_sqlglot_dialect(getattr(getattr(service, "ds", None), "type", None))
    rewritten_sql = ";\n".join(statement.sql(dialect=dialect) for statement in rewritten_statements)
    if not rewritten_sql.strip():
        return _MissingEventSqlRewrite(
            sql=None,
            missing_events=missing_events,
            unknown_events=unknown_events,
            removed_fields=sorted(fields_to_remove),
            removed_ctes=sorted(missing_ctes),
            availability=availability,
            executable=False,
        )
    for value in missing_events:
        if value in rewritten_sql:
            return _MissingEventSqlRewrite(
                sql=None,
                missing_events=missing_events,
                unknown_events=unknown_events,
                removed_fields=sorted(fields_to_remove),
                removed_ctes=sorted(missing_ctes),
                availability=availability,
                executable=False,
            )

    return _MissingEventSqlRewrite(
        sql=rewritten_sql,
        missing_events=missing_events,
        unknown_events=unknown_events,
        removed_fields=sorted(fields_to_remove),
        removed_ctes=sorted(missing_ctes),
        availability=availability,
        changed=changed,
        executable=True,
    )


def _cleanup_missing_event_result(
        service: Any,
        sql: str,
        result: dict[str, Any],
        availability: list[_EventAvailability] | None = None,
) -> _EventResultCleanup:
    """
    是什么：在 SQL 执行完成后根据缺失事件清理结果集。
    谁调用：_execute_sql 在执行 SQL 后调用。
    做了什么：识别缺失事件，从结果字段中移除依赖缺失事件的列，记录清理日志，返回清理后的结果和元信息。
    """
    missing_events = _missing_requested_events_from_availability(availability) if availability is not None else \
        _missing_requested_events(service, sql)
    if not missing_events:
        return _EventResultCleanup(result=result)

    event_values = sorted({value for event in missing_events for value in event.event_values})
    fields_to_remove = _result_fields_for_missing_events(sql, service, missing_events)
    fields_to_remove = {field for field in fields_to_remove if field in set(result.get("fields") or [])}
    cleaned_result = _prune_result_fields(result, fields_to_remove)
    removed_fields = [field for field in result.get("fields") or [] if field in fields_to_remove]
    AppLogUtil.info(
        "Smart Q&A missing event cleanup: "
        f"record_id={getattr(getattr(service, 'record', None), 'id', None)} "
        f"datasource_id={getattr(getattr(service, 'ds', None), 'id', None)} "
        f"missing_events={event_values} removed_fields={removed_fields}"
    )
    return _EventResultCleanup(
        result=cleaned_result,
        removed_fields=removed_fields,
        missing_events=event_values,
    )


class SmartQAGraphState(TypedDict, total=False):
    """
    类说明：SmartQAGraphState 把聊天问数据和 Agent相关的数据和行为放在一起，便于其他代码直接复用。
    """
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
    event_availability: list[_EventAvailability] | None
    business_notice: dict[str, Any] | None
    sql_repair_count: int
    sql_repair_pending: bool
    sql_repair_context: SqlRepairContext | None
    sql_repair_fingerprints: list[str]
    result: dict[str, Any]
    chart: dict[str, Any]
    saas_skill_handled: bool
    stop: bool


def _observe_node(node: str, handler):
    """
    是什么：为 Smart Q&A 图的某个节点包装观测与错误处理。
    谁调用：_build_graph 注册每个 LangGraph 节点时调用。
    做了什么：调用 assistant_workflow.observe_node，传入工作流配置、节点名和实际处理器，使节点执行具备统一的日志、追踪与异常格式化能力。
    """
    return observe_node(WORKFLOW_CONFIG, node, handler)


def _queue_sql_repair(
    state: SmartQAGraphState,
    *,
    error: BaseException,
    reason: SqlRepairReason,
    failed_sql: str,
) -> dict[str, Any]:
    """构造有限重试、可去重的 SQL 修复上下文。"""
    service = state["service"]
    context = SqlRepairContext(
        reason=reason,
        dialect=get_sqlglot_dialect(getattr(getattr(service, "ds", None), "type", None)),
        failed_sql=failed_sql,
        error_message=sanitize_sql_repair_error(error),
        violation=getattr(error, "violation", None),
        attempt=state.get("sql_repair_count", 0),
        max_attempts=SQL_REPAIR_MAX_ATTEMPTS,
    )
    fingerprint = sql_repair_fingerprint(context)
    fingerprints = list(state.get("sql_repair_fingerprints") or [])
    if context.attempt >= context.max_attempts or fingerprint in fingerprints:
        raise error
    return {
        "sql_repair_pending": True,
        "sql_repair_context": context,
        "sql_repair_fingerprints": [*fingerprints, fingerprint],
        "stop": False,
    }


def _repair_sql(state: SmartQAGraphState) -> dict[str, Any]:
    """调用统一修复接口生成完整 SQL，并交回准备节点重新校验。"""
    context = state.get("sql_repair_context")
    if context is None:
        raise RuntimeError("SQL repair context is missing")
    with _session_scope() as session:
        full_sql_text = _consume_generator_return(
            state["service"].regenerate_sql_after_error_streaming_reasoning(
                session,
                context,
                in_chat=state["in_chat"],
            ),
            _emit,
        )
    return {
        "full_sql_text": full_sql_text,
        "sql_repair_count": state.get("sql_repair_count", 0) + 1,
        "sql_repair_pending": False,
        "sql_repair_context": None,
        "stop": False,
    }


def _prepare_existing_context(state: SmartQAGraphState) -> dict[str, Any]:
    """
    是什么：加载 Smart Q&A 所需的上下文与自定义提示。
    谁调用：LangGraph 工作流的 prepare_context 节点调用。
    做了什么：在数据库会话中加载当前数据源的 Data Skill、生成 SQL 类型的自定义提示、保存 Agent 上下文快照、加载打点配置并初始化消息。
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
    是什么：向客户端发送当前对话记录的基础元数据事件。
    谁调用：LangGraph 工作流的 emit_record_metadata 节点调用。
    做了什么：调用 assistant_workflow.emit_record_metadata，在聊天场景下发送包含问题和重新生成 id 的元数据事件。
    """
    return _emit_workflow_record_metadata(
        state,
        include_question_in_chat=True,
        include_regenerate_id=True,
    )


def _ensure_datasource(state: SmartQAGraphState) -> dict[str, Any]:
    """
    是什么：确保 Smart Q&A 流程有合法且可连接的数据源。
    谁调用：LangGraph 工作流的 ensure_datasource 节点调用。
    做了什么：若当前无数据源则让服务自动选择并通过 SSE 通知前端；否则校验历史数据源；最后检查数据库连接，失败则抛出异常。
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
    是什么：调用 LLM 生成回答用户问题的 SQL。
    谁调用：LangGraph 工作流的 generate_sql 节点调用。
    做了什么：在数据库会话中流式调用 service.generate_sql_text_streaming_reasoning，消费并透传推理内容，返回完整的 SQL 生成文本。
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


def _execute_saas_skill(state: SmartQAGraphState) -> dict[str, Any]:
    """
    是什么：尝试命中并执行 Data Skill 中声明的可执行 SaaS Skill。
    谁调用：LangGraph 工作流的 execute_saas_skill 节点调用。
    做了什么：匹配用户问题对应的 SaaS Skill，执行 SQL/MCP 多源逻辑并合并结果；命中后根据 finish_step 决定直接结束或继续生成分析回答。
    """
    from apps.chat.task.saas_skill import (
        build_saas_skill_answer_messages,
        execute_saas_skill,
        find_matching_executable_saas_skill,
        serialize_saas_skill_messages,
        stream_saas_skill_answer_chunks,
    )

    service = state["service"]
    in_chat = state["in_chat"]
    stream = state["stream"]
    finish_step = state["finish_step"]
    json_result = state["json_result"]

    match = find_matching_executable_saas_skill(
        service.chat_question.data_skill,
        service.chat_question.question,
    )
    if match is None:
        return {"saas_skill_handled": False, "stop": False}

    with _session_scope() as session:
        service.current_logs[OperationEnum.EXECUTE_SQL] = start_log(
            session=session,
            operate=OperationEnum.EXECUTE_SQL,
            record_id=service.record.id,
            full_message={
                "saas_skill_id": match.definition.get("id"),
                "saas_skill_name": match.definition.get("name"),
                "parameters": match.params,
                "sources": [
                    {
                        "name": source.get("name") or source.get("id"),
                        "type": source.get("type"),
                    }
                    for source in match.definition.get("sources") or []
                    if isinstance(source, dict)
                ],
            },
            local_operation=True,
        )
        try:
            execution = execute_saas_skill(session, service, match)
        except Exception as execute_error:
            if not looks_like_permission_scope_error(str(execute_error)):
                raise
            audit_permission_denied(
                current_user=service.current_user,
                datasource_id=getattr(getattr(service, "ds", None), "id", None),
                record_id=getattr(getattr(service, "record", None), "id", None),
                operation="smart_qa.saas_skill_execute",
                reason=str(execute_error),
                fields=getattr(execute_error, "fields", None),
                json_paths=getattr(execute_error, "json_paths", None),
                rule_type=getattr(execute_error, "rule_type", None),
            )
            trigger_log_error(session, service.current_logs[OperationEnum.EXECUTE_SQL])
            failed_result = service.save_permission_denied_data(session=session)
            emit_permission_denied_response(
                in_chat=in_chat,
                stream=stream,
                json_result=json_result,
                sql=None,
                failed_result=failed_result,
                include_reason=True,
            )
            return {"json_result": json_result, "saas_skill_handled": True, "stop": True}

        service.current_logs[OperationEnum.EXECUTE_SQL] = end_log(
            session=session,
            log=service.current_logs[OperationEnum.EXECUTE_SQL],
            full_message={
                "saas_skill_id": match.definition.get("id"),
                "source_count": len(execution.sources),
                "row_count": len(execution.merged_result.get("data") or []),
                "fields": execution.merged_result.get("fields") or [],
            },
        )

        if execution.display_sql:
            service.save_checked_sql(session=session, sql=execution.display_sql)
            format_sql = sqlparse.format(execution.display_sql, reindent=True)
            if in_chat:
                _emit(_sse({"content": format_sql, "type": "sql"}))
            elif stream:
                _emit(f"```sql\n{format_sql}\n```\n\n")

        service.save_sql_data(session=session, data_obj=dict(execution.merged_result))
        save_chart(
            session=session,
            record_id=service.record.id,
            chart=orjson.dumps(execution.chart).decode(),
        )

        if in_chat:
            _emit(_sse({"content": "execute-success", "type": "sql-data"}))
            _emit(_sse({"content": orjson.dumps(execution.chart).decode(), "type": "chart"}))
        elif not stream:
            json_result["data"] = get_chat_chart_data(session, service.record.id)
            json_result["chart"] = execution.chart

    if finish_step.value <= ChatFinishStep.QUERY_DATA.value:
        if in_chat:
            _emit(_sse({"type": "finish"}))
        elif stream:
            column_list = [AxisObj(name=field, value=field) for field in execution.merged_result.get("fields") or []]
            _md_data, fields_list = DataFormat.convert_object_array_for_pandas(
                column_list,
                execution.merged_result.get("data") or [],
            )
            emit_markdown_table(
                _md_data,
                fields_list,
                empty_message="The SaaS Skill execution result is empty.",
            )
        else:
            _emit(json_result)
        return {
            "json_result": json_result,
            "result": execution.merged_result,
            "chart": execution.chart,
            "saas_skill_handled": True,
            "stop": True,
        }

    answer_messages = build_saas_skill_answer_messages(service, execution)
    token_usage: dict[str, Any] = {}
    full_answer = ""
    full_reasoning = ""

    with _session_scope() as session:
        service.current_logs[OperationEnum.ANALYSIS] = start_log(
            session=session,
            ai_modal_id=service.chat_question.ai_modal_id,
            ai_modal_name=service.chat_question.ai_modal_name,
            operate=OperationEnum.ANALYSIS,
            record_id=service.record.id,
            full_message=serialize_saas_skill_messages(answer_messages),
        )
        for chunk in stream_saas_skill_answer_chunks(service, answer_messages, token_usage):
            content = chunk.get("content") or ""
            reasoning_content = chunk.get("reasoning_content") or ""
            full_answer += content
            full_reasoning += reasoning_content
            if in_chat:
                _emit(_sse({
                    "content": content,
                    "reasoning_content": reasoning_content,
                    "type": "analysis-result",
                }))
            elif stream:
                _emit(content)

        service.current_logs[OperationEnum.ANALYSIS] = end_log(
            session=session,
            log=service.current_logs[OperationEnum.ANALYSIS],
            full_message=[
                *serialize_saas_skill_messages(answer_messages),
                {"type": "ai", "content": full_answer},
            ],
            reasoning_content=full_reasoning,
            token_usage=token_usage,
        )
        service.record = save_analysis_answer(
            session=session,
            record_id=service.record.id,
            answer=orjson.dumps({
                "content": full_answer,
                "reasoning_content": full_reasoning,
            }).decode(),
        )

    if not stream:
        json_result["analysis"] = full_answer
    if in_chat:
        _emit(_sse({"type": "finish"}))
    elif stream:
        _emit("\n\n")
        column_list = [AxisObj(name=field, value=field) for field in execution.merged_result.get("fields") or []]
        _md_data, fields_list = DataFormat.convert_object_array_for_pandas(
            column_list,
            execution.merged_result.get("data") or [],
        )
        emit_markdown_table(
            _md_data,
            fields_list,
            empty_message="The SaaS Skill execution result is empty.",
        )
    else:
        _emit(json_result)

    return {
        "json_result": json_result,
        "result": execution.merged_result,
        "chart": execution.chart,
        "saas_skill_handled": True,
        "stop": True,
    }


def _prepare_sql(state: SmartQAGraphState) -> dict[str, Any]:
    """
    是什么：校验、保存并准备最终用于执行的 SQL。
    谁调用：LangGraph 工作流的 prepare_sql 节点调用。
    做了什么：校验 SQL，处理 Data Skill 校验错误，提取图表类型，按需重命名聊天标题，处理动态数据源 SQL，校验用户表权限，检测缺失/未知事件并尝试改写，最后返回执行所需的 SQL 与元信息。
    """
    from apps.chat.task.llm import (
        APP_TEMP_SQL_TEXT_KEY,
        DataSkillSqlValidationError,
        _get_temp_sql_text,
        _remove_temp_sql_text,
        dynamic_ds_types,
        dynamic_subsql_prefix,
        looks_like_data_skill_schema_unavailable_error,
    )
    from common.error import SingleMessageError

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
        missing_event_message = None
        missing_event_notice = None
        unknown_event_message = None
        unknown_event_notice = None
        event_availability = None

        try:
            sql, tables = service.check_sql(session=session, res=full_sql_text, operate=sql_operate)
        except DataSkillSqlValidationError as semantic_error:
            if looks_like_data_skill_schema_unavailable_error(str(semantic_error)):
                message = user_data_unavailable_message(str(semantic_error))
                _save_and_emit_plain_answer(
                    service=service,
                    session=session,
                    message=message,
                    in_chat=in_chat,
                    stream=stream,
                    json_result=json_result,
                    finish=True,
                )
                if not in_chat and not stream:
                    json_result["success"] = False
                    json_result["message"] = message
                    _emit(json_result)
                return {"json_result": json_result, "stop": True}
            reason = classify_prepare_sql_error(semantic_error)
            if reason is not SqlRepairReason.DATA_SKILL_VALIDATION:
                raise
            return _queue_sql_repair(
                state,
                error=semantic_error,
                reason=reason,
                failed_sql=full_sql_text,
            )
        except SingleMessageError as response_error:
            reason = classify_prepare_sql_error(response_error)
            if reason is not SqlRepairReason.SQL_RESPONSE_FORMAT:
                raise
            return _queue_sql_repair(
                state,
                error=response_error,
                reason=reason,
                failed_sql=full_sql_text,
            )
        except Exception as parse_error:
            reason = classify_prepare_sql_error(parse_error)
            if reason is not SqlRepairReason.SQL_PARSE:
                raise
            return _queue_sql_repair(
                state,
                error=parse_error,
                reason=reason,
                failed_sql=full_sql_text,
            )

        chart_type = service.get_chart_type_from_sql_answer(full_sql_text)
        sql_answer_user_message = _sql_answer_message(full_sql_text)

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
                rewrite = _rewrite_sql_for_missing_events(service, checked_sql)
                event_availability = rewrite.availability
                if rewrite.missing_events:
                    supported_removed_fields = rewrite.removed_fields if rewrite.executable else []
                    missing_event_message = _missing_event_feedback(
                        rewrite.missing_events,
                        supported_removed_fields,
                    )
                    missing_event_notice = _missing_event_notice(
                        rewrite.missing_events,
                        supported_removed_fields,
                    )
                    if not rewrite.executable or not rewrite.sql:
                        _save_and_emit_plain_answer(
                            service=service,
                            session=session,
                            message=missing_event_message,
                            in_chat=in_chat,
                            stream=stream,
                            json_result=json_result,
                            finish=True,
                            notice=missing_event_notice,
                        )
                        if not in_chat and not stream:
                            json_result["success"] = False
                            json_result["message"] = missing_event_message
                            _emit(json_result)
                        return {
                            "json_result": json_result,
                            "business_notice": missing_event_notice,
                            "stop": True,
                        }
                    if rewrite.changed:
                        checked_sql, _actual_tables = validate_user_query_sql_or_raise(
                            session=session,
                            current_user=service.current_user,
                            datasource=service.ds,
                            sql=rewrite.sql,
                            allowed_tables=service.table_name_list,
                        )
                        tables = sorted(_actual_tables)
                        AppLogUtil.info(
                            "Smart Q&A missing event SQL rewrite: "
                            f"record_id={getattr(getattr(service, 'record', None), 'id', None)} "
                            f"datasource_id={getattr(getattr(service, 'ds', None), 'id', None)} "
                            f"missing_events={rewrite.missing_events} "
                            f"removed_ctes={rewrite.removed_ctes} "
                            f"removed_fields={rewrite.removed_fields}"
                        )
                        event_availability = None
                elif rewrite.unknown_events:
                    unknown_event_message = _unknown_event_feedback(rewrite.unknown_events)
                    unknown_event_notice = _unknown_event_notice(rewrite.unknown_events)
                sql = service.save_checked_sql(session=session, sql=checked_sql)
        except Exception as prepare_error:
            if isinstance(prepare_error, DataSkillSqlValidationError):
                if looks_like_data_skill_schema_unavailable_error(str(prepare_error)):
                    message = user_data_unavailable_message(str(prepare_error))
                    _save_and_emit_plain_answer(
                        service=service,
                        session=session,
                        message=message,
                        in_chat=in_chat,
                        stream=stream,
                        json_result=json_result,
                        finish=True,
                    )
                    if not in_chat and not stream:
                        json_result["success"] = False
                        json_result["message"] = message
                        _emit(json_result)
                    return {"json_result": json_result, "stop": True}
                reason = classify_prepare_sql_error(prepare_error)
                if reason is SqlRepairReason.DATA_SKILL_VALIDATION:
                    return _queue_sql_repair(
                        state,
                        error=prepare_error,
                        reason=reason,
                        failed_sql=sql,
                    )
                raise
            if not looks_like_permission_scope_error(str(prepare_error)):
                reason = classify_prepare_sql_error(prepare_error)
                if isinstance(prepare_error, SingleMessageError):
                    if reason is SqlRepairReason.SQL_RESPONSE_FORMAT:
                        return _queue_sql_repair(
                            state,
                            error=prepare_error,
                            reason=reason,
                            failed_sql=sql,
                        )
                elif reason is SqlRepairReason.SQL_PARSE:
                    return _queue_sql_repair(
                        state,
                        error=prepare_error,
                        reason=reason,
                        failed_sql=sql,
                    )
                raise
            audit_permission_denied(
                current_user=service.current_user,
                datasource_id=getattr(getattr(service, "ds", None), "id", None),
                record_id=getattr(getattr(service, "record", None), "id", None),
                operation="smart_qa.prepare_sql_permission",
                reason=str(prepare_error),
                tables=service.table_name_list,
                fields=getattr(prepare_error, "fields", None),
                json_paths=getattr(prepare_error, "json_paths", None),
                rule_type=getattr(prepare_error, "rule_type", None),
            )
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

    AppLogUtil.info("sql: " + sql)

    if not stream:
        json_result["sql"] = sql

    format_sql = sqlparse.format(sql, reindent=True)
    if in_chat:
        _emit(_sse({"content": format_sql, "type": "sql"}))
    elif stream:
        _emit(f"```sql\n{format_sql}\n```\n\n")

    if sql_answer_user_message:
        with _session_scope() as session:
            _save_and_emit_plain_answer(
                service=service,
                session=session,
                message=sql_answer_user_message,
                in_chat=in_chat,
                stream=stream,
                json_result=json_result,
            )

    if missing_event_message and missing_event_notice:
        with _session_scope() as session:
            _save_and_emit_plain_answer(
                service=service,
                session=session,
                message=missing_event_message,
                in_chat=in_chat,
                stream=stream,
                json_result=json_result,
                notice=missing_event_notice,
            )
    if unknown_event_message and unknown_event_notice:
        with _session_scope() as session:
            _save_and_emit_plain_answer(
                service=service,
                session=session,
                message=unknown_event_message,
                in_chat=in_chat,
                stream=stream,
                json_result=json_result,
                notice=unknown_event_notice,
            )

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
            "event_availability": event_availability,
            "business_notice": _merge_business_notice(missing_event_notice, unknown_event_notice),
            "stop": False,
        }


def _execute_sql(state: SmartQAGraphState) -> dict[str, Any]:
    """
    是什么：在数据源上执行 SQL 并处理结果与业务提示。
    谁调用：LangGraph 工作流的 execute_sql 节点调用。
    做了什么：记录执行日志，调用 service.execute_sql，处理数据不可用和权限异常，对结果做大数字与列名归一化，清理缺失事件列，保存数据，按需结束流程或继续生成图表。
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
    event_availability = state.get("event_availability")
    business_notice = state.get("business_notice")

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
        except DataUnavailableError as data_error:
            message = str(data_error)
            trigger_log_error(
                session,
                service.current_logs[OperationEnum.EXECUTE_SQL],
                full_message={
                    "sql": real_execute_sql,
                    "error_type": "data_unavailable",
                    "message": message,
                    "traceback": str(data_error.__cause__ or data_error),
                },
            )
            _save_and_emit_plain_answer(
                service=service,
                session=session,
                message=message,
                in_chat=in_chat,
                stream=stream,
                json_result=json_result,
                finish=True,
            )
            if not in_chat and not stream:
                json_result["success"] = False
                json_result["message"] = message
                _emit(json_result)
            return {"json_result": json_result, "stop": True}
        except Exception as execute_error:
            if looks_like_permission_scope_error(str(execute_error)):
                audit_permission_denied(
                    current_user=service.current_user,
                    datasource_id=getattr(getattr(service, "ds", None), "id", None),
                    record_id=getattr(getattr(service, "record", None), "id", None),
                    operation="smart_qa.execute_sql_permission",
                    reason=str(execute_error),
                    tables=execute_allowed_tables,
                    fields=getattr(execute_error, "fields", None),
                    json_paths=getattr(execute_error, "json_paths", None),
                    rule_type=getattr(execute_error, "rule_type", None),
                )
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

            reason = classify_execute_sql_error(execute_error)
            if reason is None:
                raise
            trigger_log_error(
                session,
                service.current_logs[OperationEnum.EXECUTE_SQL],
                full_message={
                    "sql": real_execute_sql,
                    "error_type": reason.value,
                    "message": sanitize_sql_repair_error(execute_error),
                    "repair_attempt": state.get("sql_repair_count", 0),
                },
            )
            return _queue_sql_repair(
                state,
                error=execute_error,
                reason=reason,
                failed_sql=sql,
            )

        data = DataFormat.convert_large_numbers_in_object_array(result.get("data"))
        data = DataFormat.normalize_qualified_sql_column_keys_in_object_array(data)
        result["data"] = data
        notice_removed_fields = set()
        if isinstance(business_notice, dict):
            notice_removed_fields = {
                str(field)
                for field in business_notice.get("removed_fields") or []
                if str(field).strip()
            }
        if notice_removed_fields:
            result = _prune_result_fields(result, notice_removed_fields)
        cleanup = _cleanup_missing_event_result(service, real_execute_sql, result, event_availability)
        result = cleanup.result
        execute_log_message: dict[str, Any] = {"sql": real_execute_sql, "count": len(result.get("data"))}
        if business_notice:
            execute_log_message["business_notice"] = business_notice
        stop_after_missing_event_notice = False
        if cleanup.missing_events:
            stop_after_missing_event_notice = not _has_result_rows(result)
            supported_removed_fields = [] if stop_after_missing_event_notice else cleanup.removed_fields
            message = _missing_event_feedback(cleanup.missing_events, supported_removed_fields)
            execute_log_message["business_notice"] = {
                "notice_type": "data_scope_gap",
                "reason": "missing_event",
                "missing_events": cleanup.missing_events,
                "removed_fields": supported_removed_fields,
            }
            _save_and_emit_plain_answer(
                service=service,
                session=session,
                message=message,
                in_chat=in_chat,
                stream=stream,
                json_result=json_result,
                notice=_missing_event_notice(cleanup.missing_events, supported_removed_fields),
            )

        empty_result_message = None
        empty_result_notice = None
        if not stop_after_missing_event_notice and not _has_result_rows(result):
            empty_result_message = _empty_result_feedback()
            empty_result_notice = _empty_result_notice()
            execute_log_message["business_notice"] = empty_result_notice

        service.current_logs[OperationEnum.EXECUTE_SQL] = end_log(
            session=session,
            log=service.current_logs[OperationEnum.EXECUTE_SQL],
            full_message=execute_log_message,
        )

        service.save_sql_data(session=session, data_obj=result)
        if in_chat:
            _emit(_sse({"content": "execute-success", "type": "sql-data"}))
        if not stream:
            json_result["data"] = get_chat_chart_data(session, service.record.id)

        if stop_after_missing_event_notice:
            if in_chat:
                _emit(_sse({"type": "finish"}))
            elif not stream:
                json_result["success"] = False
                json_result["message"] = message
                _emit(json_result)
            return {"json_result": json_result, "result": result, "stop": True}

        if empty_result_message and empty_result_notice:
            _save_and_emit_plain_answer(
                service=service,
                session=session,
                message=empty_result_message,
                in_chat=in_chat,
                stream=stream,
                json_result=json_result,
                finish=True,
                notice=empty_result_notice,
            )
            if not in_chat and not stream:
                json_result["success"] = True
                json_result["message"] = empty_result_message
                _emit(json_result)
            return {"json_result": json_result, "result": result, "stop": True}

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
    是什么：根据 SQL 执行结果生成图表配置。
    谁调用：LangGraph 工作流的 generate_chart 节点调用。
    做了什么：获取相关表 schema，流式调用 LLM 生成图表配置并校验保存，按 in_chat/stream/普通模式把图表或数据发送给前端。
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
        elif getattr(service, "business_sql_context", None) is not None:
            used_tables_schema = service.business_sql_context.schema
            _used_tables = service.business_sql_context.allowed_tables
        elif hasattr(service, "load_business_sql_context"):
            context = service.load_business_sql_context(
                session,
                embedding=False,
            )
            used_tables_schema = context.schema if context else ""
            _used_tables = context.allowed_tables if context else []
        else:
            used_tables_schema, _used_tables = get_ai_table_schema(
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
    是什么：决定 SQL 准备完成后是否继续执行 SQL。
    谁调用：LangGraph 条件边，在 prepare_sql 节点后调用。
    做了什么：若状态中存在 stop 标志则返回 END，待修复时进入 repair_sql，否则进入 execute_sql。
    """
    if state.get("stop"):
        return END
    if state.get("sql_repair_pending"):
        return "repair_sql"
    return "execute_sql"


def _should_continue_after_saas_skill(state: SmartQAGraphState) -> str:
    """
    是什么：决定 SaaS Skill 执行完成后是否继续常规 SQL 流程。
    谁调用：LangGraph 条件边，在 execute_saas_skill 节点后调用。
    做了什么：若状态中存在 stop 标志（表示已处理完成）则返回 END，否则进入 generate_sql 节点。
    """
    return END if state.get("stop") else "generate_sql"


def _should_continue_after_execute(state: SmartQAGraphState) -> str:
    """
    是什么：决定 SQL 执行完成后是否继续生成图表。
    谁调用：LangGraph 条件边，在 execute_sql 节点后调用。
    做了什么：若状态中存在 stop 标志则返回 END，待修复时进入 repair_sql，否则进入 generate_chart 节点。
    """
    if state.get("stop"):
        return END
    if state.get("sql_repair_pending"):
        return "repair_sql"
    return "generate_chart"


def _build_graph():
    """
    是什么：构建并编译 Smart Q&A 的 LangGraph 状态机。
    谁调用：模块导入时调用，结果缓存到 SMART_QA_GRAPH。
    做了什么：添加 prepare_context、emit_record_metadata、ensure_datasource、execute_saas_skill、generate_sql、prepare_sql、execute_sql、generate_chart 节点及条件边，并编译图。
    """
    graph = StateGraph(SmartQAGraphState)

    # 节点 1：加载 Smart Q&A 所需的上下文、Data Skill、自定义提示和打点配置。
    graph.add_node("prepare_context", _observe_node("prepare_context", _prepare_existing_context))

    # 节点 2：向前端发送当前对话记录的基础元数据（问题、重新生成 id 等）。
    graph.add_node("emit_record_metadata", _observe_node("emit_record_metadata", _emit_record_metadata))

    # 节点 3：确保当前流程有合法且可连接的数据源；未指定时自动选择并通知前端。
    graph.add_node("ensure_datasource", _observe_node("ensure_datasource", _ensure_datasource))

    # 节点 4：尝试命中并执行 Data Skill 中声明的可执行 SaaS Skill；命中后可能直接结束流程。
    graph.add_node("execute_saas_skill", _observe_node("execute_saas_skill", _execute_saas_skill))

    # 节点 5：根据用户问题、表结构和上下文生成 SQL 文本。
    graph.add_node("generate_sql", _observe_node("generate_sql", _generate_sql))

    # 节点 6：校验并保存生成的 SQL，处理权限、缺失事件、动态数据源等分支逻辑。
    graph.add_node("prepare_sql", _observe_node("prepare_sql", _prepare_sql))

    # 节点 7：根据结构化错误上下文修复 SQL，并返回准备节点重新校验。
    graph.add_node("repair_sql", _observe_node("repair_sql", _repair_sql))

    # 节点 8：执行 SQL 并获取结果；处理数据不可用、权限拒绝、空结果等情况。
    graph.add_node("execute_sql", _observe_node("execute_sql", _execute_sql))

    # 节点 9：根据 SQL 结果生成图表配置，并向前端发送图表或图片。
    graph.add_node("generate_chart", _observe_node("generate_chart", _generate_chart))

    # 流程起点：从准备上下文开始。
    graph.set_entry_point("prepare_context")

    # 顺序边：准备上下文 → 发送元数据 → 确保数据源 → 尝试 SaaS Skill。
    graph.add_edge("prepare_context", "emit_record_metadata")
    graph.add_edge("emit_record_metadata", "ensure_datasource")
    graph.add_edge("ensure_datasource", "execute_saas_skill")

    # 条件边：SaaS Skill 命中并处理完成后直接结束；否则进入常规 SQL 生成。
    graph.add_conditional_edges("execute_saas_skill", _should_continue_after_saas_skill)

    # 顺序边：生成 SQL → 准备/校验 SQL。
    graph.add_edge("generate_sql", "prepare_sql")

    # 条件边：prepare_sql 根据 finish_step 或业务异常决定停止还是继续执行 SQL。
    graph.add_conditional_edges("prepare_sql", _should_continue_after_sql)

    # 修复后的 SQL 必须回到 prepare_sql，重新经过格式、语义、权限和范围校验。
    graph.add_edge("repair_sql", "prepare_sql")

    # 条件边：execute_sql 根据 finish_step 或业务异常决定停止还是继续生成图表。
    graph.add_conditional_edges("execute_sql", _should_continue_after_execute)

    # 终点边：图表生成完成后结束整个工作流。
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
    是什么：Smart Q&A 工作流的入口函数。
    谁调用：外部 Smart Q&A 服务启动一次问答流程时调用。
    做了什么：构造初始状态，调用 run_assistant_workflow 执行编译好的图，并透传执行过程中的事件/结果生成器。
    """
    json_result: dict[str, Any] = {"success": True}
    initial_state: SmartQAGraphState = {
        "service": service,
        "in_chat": in_chat,
        "stream": stream,
        "finish_step": finish_step,
        "return_img": return_img,
        "json_result": json_result,
        "sql_repair_count": 0,
        "sql_repair_pending": False,
        "sql_repair_context": None,
        "sql_repair_fingerprints": [],
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
