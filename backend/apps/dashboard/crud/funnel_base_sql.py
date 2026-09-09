"""Build the normalized source query used by the deterministic funnel executor."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
_OPERATORS = {
    "eq": "=", "=": "=", "neq": "<>", "!=": "<>", "gt": ">", ">": ">",
    "gte": ">=", ">=": ">=", "lt": "<", "<": "<", "lte": "<=", "<=": "<=",
}


@dataclass(frozen=True)
class FunnelBaseSqlPlan:
    sql: str
    tables: list[str]
    steps: list[dict[str, Any]]
    entity_alias: str = "entity_id"
    event_alias: str = "event_name"
    time_alias: str = "event_time"
    group_fields: tuple[str, ...] = ()
    related_field: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "sql": self.sql,
            "tables": self.tables,
            "steps": self.steps,
            "entity_field": self.entity_alias,
            "event_field": self.event_alias,
            "time_field": self.time_alias,
            "group_fields": list(self.group_fields),
            "related_field": self.related_field,
        }


def _quote(name: str) -> str:
    text = str(name or "").strip().strip("`")
    if not _IDENTIFIER.fullmatch(text):
        raise ValueError(f"字段或表名不合法：{name}")
    return f"`{text}`"


def _split_reference(value: Any, default_table: str | None = None) -> tuple[str, str]:
    text = str(value or "").strip()
    if text.startswith(("tracking-event:", "tracking-property:")):
        parts = text.split(":", 3)
        if len(parts) < 3 or "." not in parts[1]:
            raise ValueError(f"字段配置无效：{text}")
        table, field = parts[1].split(".", 1)
        return table, field
    if "." in text:
        return tuple(text.split(".", 1))  # type: ignore[return-value]
    if not default_table:
        raise ValueError(f"字段缺少所属表：{text}")
    return default_table, text


def _field_reference(field: Any, default_table: str | None = None) -> tuple[str, str]:
    if isinstance(field, dict):
        if str(field.get("kind") or "") == "tracking-event":
            table = str(field.get("eventTable") or field.get("event_table") or field.get("table") or "").strip()
            name_field = str(field.get("eventNameField") or field.get("event_name_field") or field.get("field") or "").strip()
            if table and name_field:
                return table, name_field
        value = field.get("value") or field.get("field") or field.get("sourceField") or field.get("source_field")
        return _split_reference(value, default_table)
    return _split_reference(field, default_table)


def _field_expression(field: Any, alias: str, default_table: str) -> str:
    if isinstance(field, dict) and str(field.get("expression") or "").strip():
        table = str(field.get("table") or field.get("eventTable") or default_table).strip()
        if table != default_table:
            raise ValueError("字段表达式必须来自漏斗事件表")
        expression = str(field["expression"]).strip()
        return re.sub(rf"`?{re.escape(table)}`?\.", f"{alias}.", expression)
    _, column = _field_reference(field, default_table)
    return f"{alias}.{_quote(column)}"


def _event_spec(value: Any) -> tuple[str, str, str]:
    if isinstance(value, dict):
        table, field = _field_reference(value)
        event_name = str(value.get("eventName") or value.get("event_name") or "").strip()
        if not event_name:
            raise ValueError("漏斗步骤缺少事件名")
        return table, field, event_name
    text = str(value or "").strip()
    if text.startswith("tracking-event:"):
        parts = text.split(":", 3)
        if len(parts) == 3 and "." in parts[1] and parts[2].strip():
            table, field = parts[1].split(".", 1)
            return table, field, parts[2].strip()
        if len(parts) == 4 and "." in parts[1] and parts[3].strip():
            table, field = parts[1].split(".", 1)
            return table, field, parts[3].strip()
    raise ValueError(f"漏斗步骤事件配置无效：{text}")


def _literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    text = str(value).replace("'", "''")
    return f"'{text}'"


def _filter_sql(rule: dict[str, Any], alias: str, default_table: str) -> str:
    field = rule.get("field")
    table, column = _field_reference(field, default_table)
    if table != default_table:
        raise ValueError("筛选字段必须来自漏斗事件表")
    column_sql = _field_expression(field, alias, default_table)
    operator = str(rule.get("operator") or rule.get("op") or "eq").strip().lower()
    if operator in {"is_null", "null"}:
        return f"{column_sql} IS NULL"
    if operator in {"is_not_null", "not_null"}:
        return f"{column_sql} IS NOT NULL"
    if operator in {"in", "not_in"}:
        values = rule.get("value") if isinstance(rule.get("value"), list) else [rule.get("value")]
        if not values:
            raise ValueError("IN 筛选值不能为空")
        expression = ", ".join(_literal(item) for item in values)
        return f"{column_sql} {'NOT ' if operator == 'not_in' else ''}IN ({expression})"
    sql_operator = _OPERATORS.get(operator)
    if sql_operator is None:
        raise ValueError(f"不支持的漏斗筛选操作符：{operator}")
    return f"{column_sql} {sql_operator} {_literal(rule.get('value'))}"


def _rules_sql(filters: Any, alias: str, default_table: str) -> str | None:
    if not isinstance(filters, dict):
        return None
    rules = filters.get("rules") if isinstance(filters.get("rules"), list) else []
    parts: list[str] = []
    def visit(node: Any) -> str | None:
        if not isinstance(node, dict):
            return None
        if node.get("type") == "group":
            children = [visit(child) for child in node.get("children", [])]
            children = [child for child in children if child]
            if not children:
                return None
            logic = " OR " if str(node.get("logic") or "and").lower() == "or" else " AND "
            return "(" + logic.join(children) + ")"
        if node.get("type") not in {None, "rule"}:
            return None
        return _filter_sql(node, alias, default_table)

    for rule in rules:
        result = visit(rule)
        if result:
            parts.append(result)
    if not parts:
        return None
    logic = " OR " if str(filters.get("logic") or "and").lower() == "or" else " AND "
    return "(" + logic.join(parts) + ")"


def build_funnel_base_sql(context: dict[str, Any]) -> FunnelBaseSqlPlan:
    funnel = context.get("funnel") if isinstance(context.get("funnel"), dict) else {}
    raw_steps = funnel.get("steps") if isinstance(funnel.get("steps"), list) else []
    if not raw_steps:
        raise ValueError("漏斗至少需要一个步骤")
    parsed_steps: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_steps):
        if not isinstance(raw, dict):
            raise ValueError("漏斗步骤配置无效")
        table, event_field, event_name = _event_spec(raw.get("event"))
        parsed_steps.append({
            "order": index + 1,
            "event_name": event_name,
            "event_table": table,
            "event_field": event_field,
            "alias": str(raw.get("alias") or event_name).strip(),
            "filters": raw.get("filters") if isinstance(raw.get("filters"), dict) else {},
        })
    tables = sorted({step["event_table"] for step in parsed_steps})
    if len(tables) != 1:
        raise ValueError("当前漏斗基础查询要求所有步骤来自同一事件表")
    table = tables[0]
    time_config = context.get("time") if isinstance(context.get("time"), dict) else {}
    _, date_field = _field_reference(time_config.get("field") or "dt", table)
    funnel_time_field = funnel.get("eventTimeField") or funnel.get("event_time_field") or f"{table}.time"
    _, event_time_field = _field_reference(funnel_time_field, table)
    _, entity_field = _field_reference(funnel.get("entityField") or f"{table}.uid", table)
    event_field = parsed_steps[0]["event_field"]
    for step in parsed_steps:
        if step["event_field"] != event_field:
            raise ValueError("漏斗步骤必须使用同一个事件名称字段")

    select_items = [
        f"e.{_quote(entity_field)} AS entity_id",
        f"e.{_quote(event_field)} AS event_name",
        f"e.{_quote(event_time_field)} AS event_time",
        f"e.{_quote(date_field)} AS event_date_key",
    ]
    group_fields: list[str] = []
    for index, field in enumerate(context.get("groups") if isinstance(context.get("groups"), list) else []):
        expression = _field_expression(field, "e", table)
        alias = f"group_{index + 1}"
        select_items.append(f"{expression} AS {_quote(alias)}")
        group_fields.append(alias)
    related_field = None
    if funnel.get("relatedPropertyEnabled") is True and funnel.get("relatedProperty"):
        related_field = "related_value"
        select_items.append(f"{_field_expression(funnel.get('relatedProperty'), 'e', table)} AS related_value")

    predicates = [
        f"e.{_quote(date_field)} >= b.start_dt",
        f"e.{_quote(date_field)} <= b.end_dt",
        "e." + _quote(event_field) + " IN (" + ", ".join(_literal(step["event_name"]) for step in parsed_steps) + ")",
    ]
    filters = context.get("filters")
    global_filter = _rules_sql(filters, "e", table) if isinstance(filters, dict) else None
    if global_filter:
        predicates.append(global_filter)
    step_filter_parts: list[str] = []
    has_step_filters = False
    for step in parsed_steps:
        condition = _rules_sql(step.get("filters"), "e", table)
        if condition:
            has_step_filters = True
        event_condition = f"e.{_quote(event_field)} = {_literal(step['event_name'])}"
        step_filter_parts.append(f"({event_condition}{f' AND {condition}' if condition else ''})")
    if has_step_filters:
        predicates.append("(" + " OR ".join(step_filter_parts) + ")")
    sql = "WITH bounds AS (\n  SELECT CAST({{dashboard_start_yyyymmdd}} AS SIGNED) AS start_dt,\n         CAST({{dashboard_end_yyyymmdd}} AS SIGNED) AS end_dt\n)\nSELECT\n  " + ",\n  ".join(select_items) + f"\nFROM {_quote(table)} e\nCROSS JOIN bounds b\nWHERE " + "\n  AND ".join(predicates) + "\n"
    return FunnelBaseSqlPlan(sql, tables, parsed_steps, group_fields=tuple(group_fields), related_field=related_field)


def normalize_funnel_builder_context(builder: dict[str, Any]) -> dict[str, Any]:
    """Normalize the compact persisted builder shape to the generation context shape."""
    if not isinstance(builder, dict):
        return {}
    if isinstance(builder.get("funnel"), dict) and isinstance(builder.get("time"), dict):
        return builder
    funnel = dict(builder.get("funnel") or {})
    return {
        "time": {"field": builder.get("timeField") or "dt"},
        "funnel": funnel,
        "filters": {
            "logic": builder.get("globalFilterLogic") or "and",
            "rules": builder.get("globalFilters") or [],
        },
        "groups": builder.get("groups") or [],
    }
