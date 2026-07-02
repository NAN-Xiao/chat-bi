"""
脚本说明：这个脚本放聊天问数据和 Agent里较长或较复杂的处理流程，把一次任务分成可维护的步骤。
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, TypedDict

import orjson
import sqlglot
import sqlparse
from sqlglot import exp
from sqlalchemy import text
from langgraph.graph import END, StateGraph

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
from apps.datasource.crud.datasource import get_table_schema
from apps.datasource.crud.permission_errors import (
    looks_like_permission_scope_error,
)
from apps.datasource.crud.query_executor import validate_user_query_sql_or_raise
from apps.datasource.crud.sql_permission import normalize_identifier
from apps.datasource.models.datasource import CoreDatasource
from apps.db.db import check_connection, get_session, get_sqlglot_dialect
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
    removed_fields: list[str] = field(default_factory=list)
    removed_ctes: list[str] = field(default_factory=list)
    changed: bool = False
    executable: bool = True


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
    dialect = get_sqlglot_dialect(ds_type)
    return [stmt for stmt in sqlglot.parse(sql, dialect=dialect) if stmt is not None]


def _table_aliases_for_select(select_expr: exp.Select) -> dict[str, exp.Table]:
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
    values: set[str] = set()
    if isinstance(expr_node, exp.Literal) and expr_node.is_string:
        values.add(str(expr_node.this))
        return values
    for literal in expr_node.find_all(exp.Literal):
        if literal.is_string:
            values.add(str(literal.this))
    return values


def _event_values_from_condition(condition: exp.Expression, event_fields: set[str]) -> list[tuple[exp.Column, set[str]]]:
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
    columns: set[str] = set()
    for item in select_expr.expressions:
        alias = normalize_identifier(item.alias_or_name)
        if alias and alias != "*":
            columns.add(alias)
    return columns


def _extract_requested_event_predicates(sql: str, service: Any) -> list[_RequestedEventPredicate]:
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
    parent = select_expr.parent
    while parent is not None:
        if isinstance(parent, exp.CTE):
            return parent.alias_or_name
        parent = parent.parent
    return None


def _quote_table_for_sql(table_name: str, schema_name: str | None, ds_type: str | None) -> str:
    table = exp.Table(this=exp.to_identifier(table_name, quoted=True))
    if schema_name:
        table.set("db", exp.to_identifier(schema_name, quoted=True))
    return table.sql(dialect=get_sqlglot_dialect(ds_type))


def _event_exists_in_datasource(
        *,
        service: Any,
        table: str,
        schema: str,
        event_field: str,
        event_value: str,
) -> bool | None:
    ds = getattr(service, "ds", None)
    if ds is None:
        return None

    ds_type = getattr(ds, "type", None)
    table_expr = exp.Table(this=exp.to_identifier(table, quoted=True))
    if schema:
        table_expr.set("db", exp.to_identifier(schema, quoted=True))
    sql = exp.select(exp.Literal.number(1)).from_(table_expr).where(
        exp.EQ(
            this=exp.column(event_field, quoted=True),
            expression=exp.Var(this=":event_value"),
        )
    ).limit(1).sql(
        dialect=get_sqlglot_dialect(ds_type),
    )
    try:
        db_session = get_session(ds, timeout=10)
        try:
            row = db_session.execute(text(sql), {"event_value": event_value}).first()
            return row is not None
        finally:
            db_session.close()
    except Exception as exc:
        AppLogUtil.warning(
            f"Skip missing event post-check for {table}.{event_field}={event_value}: {exc}"
        )
        return None


def _event_availability_for_sql(service: Any, sql: str) -> list[_EventAvailability]:
    predicates = _extract_requested_event_predicates(sql, service)
    if not predicates:
        return []

    availability: list[_EventAvailability] = []
    existence_cache: dict[tuple[str, str, str, str], bool | None] = {}
    for predicate in predicates:
        item = _EventAvailability(predicate=predicate)
        for event_value in predicate.event_values:
            cache_key = (predicate.schema, predicate.table, predicate.event_field, event_value)
            if cache_key not in existence_cache:
                existence_cache[cache_key] = _event_exists_in_datasource(
                    service=service,
                    table=predicate.table,
                    schema=predicate.schema,
                    event_field=predicate.event_field,
                    event_value=event_value,
                )
            exists = existence_cache[cache_key]
            if exists is False:
                item.missing_values.add(event_value)
            elif exists is True:
                item.existing_values.add(event_value)
            else:
                item.unknown_values.add(event_value)
        availability.append(item)
    return availability


def _missing_requested_events(service: Any, sql: str) -> list[_RequestedEventPredicate]:
    missing: list[_RequestedEventPredicate] = []
    for item in _event_availability_for_sql(service, sql):
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


def _final_select(statement: exp.Expression) -> exp.Select | None:
    if isinstance(statement, exp.Select):
        return statement
    return statement.find(exp.Select)


def _aliases_for_final_sources(select_expr: exp.Select) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for alias, table_expr in _table_aliases_for_select(select_expr).items():
        source_name = normalize_identifier(table_expr.name)
        if source_name:
            aliases[alias] = source_name
    return aliases


def _result_fields_for_missing_events(sql: str, service: Any, missing_events: list[_RequestedEventPredicate]) -> set[str]:
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
    event_text = "、".join(missing_events)
    if removed_fields:
        return f"当前数据源缺少 {event_text} 埋点数据，已生成其余可支持的结果。"
    return f"当前数据源缺少 {event_text} 埋点数据。"


def _missing_event_notice(missing_events: list[str], removed_fields: list[str]) -> dict[str, Any]:
    return {
        "notice_type": "data_scope_gap",
        "severity": "warning",
        "reason": "missing_event",
        "items": missing_events,
        "removed_fields": removed_fields,
    }


def _missing_event_predicates_from_availability(items: list[_EventAvailability]) -> list[_RequestedEventPredicate]:
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
    availability = _event_availability_for_sql(service, sql)
    missing_events = sorted({
        value
        for item in availability
        for value in item.missing_values
    })
    if not missing_events:
        return _MissingEventSqlRewrite(sql=sql, executable=True)

    missing_predicates = _missing_event_predicates_from_availability(availability)
    fields_to_remove = _result_fields_for_missing_events(sql, service, missing_predicates)
    missing_ctes = _removable_missing_event_ctes(availability)
    if not missing_ctes:
        return _MissingEventSqlRewrite(
            sql=None,
            missing_events=missing_events,
            removed_fields=sorted(fields_to_remove),
            executable=False,
        )

    try:
        statements = _sql_statements(sql, getattr(getattr(service, "ds", None), "type", None))
    except Exception as exc:
        AppLogUtil.warning(f"Skip missing event SQL rewrite because SQL parsing failed: {exc}")
        return _MissingEventSqlRewrite(
            sql=None,
            missing_events=missing_events,
            removed_fields=sorted(fields_to_remove),
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
                removed_fields=sorted(fields_to_remove),
                removed_ctes=sorted(missing_ctes),
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
            removed_fields=sorted(fields_to_remove),
            removed_ctes=sorted(missing_ctes),
            executable=False,
        )
    for value in missing_events:
        if value in rewritten_sql:
            return _MissingEventSqlRewrite(
                sql=None,
                missing_events=missing_events,
                removed_fields=sorted(fields_to_remove),
                removed_ctes=sorted(missing_ctes),
                executable=False,
            )

    return _MissingEventSqlRewrite(
        sql=rewritten_sql,
        missing_events=missing_events,
        removed_fields=sorted(fields_to_remove),
        removed_ctes=sorted(missing_ctes),
        changed=changed,
        executable=True,
    )


def _cleanup_missing_event_result(service: Any, sql: str, result: dict[str, Any]) -> _EventResultCleanup:
    missing_events = _missing_requested_events(service, sql)
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
    business_notice: dict[str, Any] | None
    result: dict[str, Any]
    chart: dict[str, Any]
    saas_skill_handled: bool
    stop: bool


def _observe_node(node: str, handler):
    """
    是什么：_observe_node 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return observe_node(WORKFLOW_CONFIG, node, handler)


def _prepare_existing_context(state: SmartQAGraphState) -> dict[str, Any]:
    """
    是什么：_prepare_existing_context 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
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
    是什么：_emit_record_metadata 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent处理过程中的消息或结果一段段传出去。
    """
    return _emit_workflow_record_metadata(
        state,
        include_question_in_chat=True,
        include_regenerate_id=True,
    )


def _ensure_datasource(state: SmartQAGraphState) -> dict[str, Any]:
    """
    是什么：_ensure_datasource 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：检查聊天问数据和 Agent里的数据、权限或配置是否合法，不对就及时拦住。
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
    是什么：_generate_sql 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：根据已有信息生成聊天问数据和 Agent的结果，比如答案、SQL、图表或建议。
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
    是什么：_execute_saas_skill 让 Data Skill 中声明的 SQL/MCP 多源能力可以直接服务 Smart Q&A。
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
    是什么：_prepare_sql 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    from apps.chat.task.llm import (
        APP_TEMP_SQL_TEXT_KEY,
        DataSkillSqlValidationError,
        _get_temp_sql_text,
        _remove_temp_sql_text,
        dynamic_ds_types,
        dynamic_subsql_prefix,
        looks_like_data_skill_schema_unavailable_error,
        user_data_unavailable_message,
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
            try:
                sql, tables = service.check_sql(session=session, res=full_sql_text, operate=sql_operate)
            except (DataSkillSqlValidationError, SingleMessageError) as regenerated_error:
                if not looks_like_data_skill_schema_unavailable_error(str(regenerated_error)):
                    raise
                message = user_data_unavailable_message(str(regenerated_error))
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
                rewrite = _rewrite_sql_for_missing_events(service, checked_sql)
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
            "business_notice": missing_event_notice,
            "stop": False,
        }


def _execute_sql(state: SmartQAGraphState) -> dict[str, Any]:
    """
    是什么：_execute_sql 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent的主要流程跑起来，一步步调用需要的处理。
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
        cleanup = _cleanup_missing_event_result(service, real_execute_sql, result)
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
    是什么：_generate_chart 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：根据已有信息生成聊天问数据和 Agent的结果，比如答案、SQL、图表或建议。
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
    是什么：_should_continue_after_sql 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return END if state.get("stop") else "execute_sql"


def _should_continue_after_saas_skill(state: SmartQAGraphState) -> str:
    """
    是什么：_should_continue_after_saas_skill 决定可执行 SaaS Skill 命中后是否跳过常规 SQL 流程。
    """
    return END if state.get("stop") else "generate_sql"


def _should_continue_after_execute(state: SmartQAGraphState) -> str:
    """
    是什么：_should_continue_after_execute 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return END if state.get("stop") else "generate_chart"


def _build_graph():
    """
    是什么：_build_graph 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：创建或保存聊天问数据和 Agent需要的东西，让后续流程能继续往下走。
    """
    graph = StateGraph(SmartQAGraphState)
    graph.add_node("prepare_context", _observe_node("prepare_context", _prepare_existing_context))
    graph.add_node("emit_record_metadata", _observe_node("emit_record_metadata", _emit_record_metadata))
    graph.add_node("ensure_datasource", _observe_node("ensure_datasource", _ensure_datasource))
    graph.add_node("execute_saas_skill", _observe_node("execute_saas_skill", _execute_saas_skill))
    graph.add_node("generate_sql", _observe_node("generate_sql", _generate_sql))
    graph.add_node("prepare_sql", _observe_node("prepare_sql", _prepare_sql))
    graph.add_node("execute_sql", _observe_node("execute_sql", _execute_sql))
    graph.add_node("generate_chart", _observe_node("generate_chart", _generate_chart))

    graph.set_entry_point("prepare_context")
    graph.add_edge("prepare_context", "emit_record_metadata")
    graph.add_edge("emit_record_metadata", "ensure_datasource")
    graph.add_edge("ensure_datasource", "execute_saas_skill")
    graph.add_conditional_edges("execute_saas_skill", _should_continue_after_saas_skill)
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
    是什么：run_smart_qa_graph 是一个可以复用的小步骤，负责聊天问数据和 Agent相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把聊天问数据和 Agent的主要流程跑起来，一步步调用需要的处理。
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
