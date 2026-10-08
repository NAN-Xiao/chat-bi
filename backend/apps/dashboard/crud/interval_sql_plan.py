"""Resolve interval configuration against authorized workspace metadata once."""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass

from sqlglot import exp, parse_one

from apps.dashboard.crud.event_sql_contract import _filter_expression
from apps.dashboard.crud.property_sql_plan import _Resolver, NUMERIC, TEXT, PropertyConfigurationError
from apps.system.crud.tracking_event_schema import _event_names, _normalized_type


@dataclass(frozen=True)
class IntervalIssue:
    code: str
    path: str
    message: str

    def __str__(self):
        return f"{self.path}：{self.message}"


class IntervalConfigurationError(ValueError):
    def __init__(self, issues):
        self.issues = tuple(issues)
        super().__init__("；".join(map(str, self.issues)))


def fail(path, message, code="INTERVAL_INVALID_CONFIG"):
    raise IntervalConfigurationError([IntervalIssue(code, path, message)])


def mapping(value):
    return value.model_dump() if hasattr(value, "model_dump") else dict(value or {})


def is_interval_order_type(value):
    kind = re.sub(r"\(\s*\d+\s*\)", "", str(value or "").lower()).strip()
    return bool(re.fullmatch(r"(?:tinyint|smallint|integer|int|bigint|int2|int4|int8)(?: unsigned)?", kind)
                or re.match(r"^(?:char|varchar|text|string|nvarchar|nchar)\b", kind))


@dataclass(frozen=True)
class IntervalTimePlan:
    instant: str
    raw_time: str
    date: str
    predicate: str
    bounds: str
    scaffold: str
    business_timezone: str
    naive_timezones: tuple[str, ...]
    mysql_utc: bool
    mysql_timezones: tuple[str, ...]
    parameter_type: str


@dataclass(frozen=True)
class IntervalSqlPlan:
    dialect: str
    engine: str
    table: str
    entity: str
    start: str
    end: str
    filters: str
    related_start: str | None
    related_end: str | None
    groups: tuple[str, ...]
    order_fields: tuple[str, ...]
    limit_seconds: int
    time: IntervalTimePlan

    @property
    def required_columns(self):
        return ("interval_date", *self.group_names, "entity_count", "interval_count",
                "max_interval_seconds", "p75_interval_seconds", "median_interval_seconds",
                "p25_interval_seconds", "min_interval_seconds", "avg_interval_seconds")

    @property
    def group_names(self):
        return tuple(f"group_{i + 1}" for i in range(len(self.groups)))


OPERATORS = {"eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "between", "not_between",
             "contains", "not_contains", "starts_with", "ends_with", "is_null", "is_not_null"}


def interval_filter_issues(value, path, child=False):
    """Validate optional root filters and required nested nodes consistently."""
    issues = []
    def add(path, message):
        issues.append(IntervalIssue("INTERVAL_INVALID_CONFIG", path, message))
    def field(value):
        return isinstance(value, dict) and bool(value.get("table")) and bool(value.get("field"))
    if not isinstance(value, dict):
        add(path, "筛选必须为结构化条件。")
        return issues
    if not value and not child:
        return issues
    key = "children" if value.get("type") == "group" else "rules"
    if key in value:
        children = value[key]
        if value.get("logic", "and") not in {"and", "or"} or not isinstance(children, list) or (child and not children):
            add(path, "筛选组合需要 AND/OR 和非空条件列表。")
        else:
            for i, item in enumerate(children):
                issues.extend(interval_filter_issues(item, f"{path}.{key}[{i}]", True))
    elif not field(value.get("field")) or value.get("operator") not in OPERATORS:
        add(path, "筛选字段或操作符无效。")
    elif value["operator"] not in {"is_null", "is_not_null"} and value.get("value") in (None, "", []):
        add(path + ".value", "筛选值不能为空。")
    return issues


def validate_interval_input(raw):
    issues = []
    def add(path, message):
        issues.append(IntervalIssue("INTERVAL_INVALID_CONFIG", path, message))
    def field(value):
        return isinstance(value, dict) and bool(value.get("table")) and bool(value.get("field"))
    def filters(value, path):
        issues.extend(interval_filter_issues(value, path))
    interval = raw.get("interval")
    if not isinstance(interval, dict):
        return [IntervalIssue("INTERVAL_INVALID_CONFIG", "interval", "间隔配置必须为对象。")]
    if not field(interval.get("entityField")): add("interval.entityField", "请选择分析主体。")
    for side in ("start", "end"):
        event = interval.get(side + "Event")
        if not isinstance(event, dict) or not all(isinstance(event.get(k), str) and event[k].strip() for k in ("eventTable", "eventNameField", "eventName")):
            add("interval." + side + "Event", "请选择配置完整的事件。")
        filters(interval.get(side + "EventFilters", {}), "interval." + side + "EventFilters")
    limit = interval.get("limitSeconds")
    if type(limit) is not int or not 60 <= limit <= 15552000:
        add("interval.limitSeconds", "间隔上限必须为 60 至 15552000 的整数秒。")
    related = interval.get("relatedProperty", {})
    if not isinstance(related, dict) or ("enabled" in related and type(related["enabled"]) is not bool):
        add("interval.relatedProperty", "关联开关必须为布尔值。")
    elif related.get("enabled"):
        for key in ("startProperty", "endProperty"):
            if not field(related.get(key)): add("interval.relatedProperty." + key, "请选择关联字段。")
    time = raw.get("time")
    if not isinstance(time, dict) or not field(time.get("field")):
        add("time.field", "请选择日期过滤字段。")
    elif time.get("grain") not in (None, "", "day"):
        add("time.grain", "间隔模型按日统计。")
    groups = raw.get("groups", [])
    if not isinstance(groups, list) or not all(field(g) for g in groups): add("groups", "分组必须是字段列表。")
    filters(raw.get("filters", {}), "filters")
    return issues


def build_interval_plan(config, *, time_plan, metadata_fields, allowed_fields_by_table,
                        dialect, engine, tracking_metadata, table_filters):
    issues = validate_interval_input(config)
    if issues: raise IntervalConfigurationError(issues)
    if dialect not in {"postgres", "mysql", "starrocks", "doris"}:
        fail("datasource", "当前数据源不支持确定性间隔编译。")
    t, interval = mapping(tracking_metadata), config["interval"]
    if not t.get("enabled"): fail("metadata", "请启用当前工作空间事件元数据。")
    table = interval["startEvent"]["eventTable"]
    if table != interval["endEvent"]["eventTable"] or table not in metadata_fields or not allowed_fields_by_table.get(table):
        fail("interval.endEvent", "起终事件必须来自同一授权事件表。")
    metadata = copy.deepcopy(metadata_fields)
    base = _Resolver(metadata, allowed_fields_by_table, dialect)
    base.table = table

    def resolve(resolver, value, path):
        if not isinstance(value, dict) or value.get("table") != table:
            fail(path, "字段必须属于当前授权事件表。")
        try:
            return resolver.field(value, path)
        except PropertyConfigurationError as exc:
            fail(path, str(exc))

    def filters(resolver, value, path):
        issues = interval_filter_issues(value, path)
        if issues:
            raise IntervalConfigurationError(issues)
        root_key = "children" if value.get("type") == "group" else "rules"
        # An empty optional root means the user has not selected a restriction.
        # Nested empty groups remain invalid, and are rejected above.
        if not value or (root_key in value and not value[root_key]):
            return "TRUE"
        node = copy.deepcopy(value)
        def visit(item, at):
            key = "children" if item.get("type") == "group" else "rules"
            if key in item:
                for i, child in enumerate(item[key]): visit(child, f"{at}.{key}[{i}]")
            else:
                expression, definition = resolve(resolver, item["field"], at + ".field")
                item["field"] = {"expression": expression, "type": definition.get("type")}
        visit(node, path)
        return _filter_expression(node, dialect).sql(dialect=dialect)

    def event(side):
        value = interval[side + "Event"]
        name, key = value["eventName"], value["eventNameField"]
        entries = [m for m in t.get("event_name_mappings", []) if isinstance(m, dict) and name in _event_names(m)]
        if not entries: fail("interval." + side + "Event", "事件不在当前工作空间事件字典中。")
        event_meta = copy.deepcopy(metadata)
        for m in entries:
            if (m.get("event_table") or m.get("table") or t.get("default_event_table")) != table or (m.get("event_name_field") or t.get("default_event_name_field")) != key:
                fail("interval." + side + "Event", "事件来源与工作空间元数据不一致。")
            for p in m.get("properties", []):
                n = p.get("property_name") or p.get("field_name") or p.get("name")
                host = p.get("source_field")
                if n and host in metadata[table] and p.get("json_path"):
                    kind = _normalized_type(p.get("property_type") or p.get("semantic_type") or p.get("type"))
                    event_meta[table][n] = {**p, "type": kind, "semantic_type": kind}
        r = _Resolver(event_meta, allowed_fields_by_table, dialect); r.table = table
        column, _ = resolve(r, {"table": table, "field": key}, "interval." + side + "Event")
        predicate = f"({column} = {exp.Literal.string(name).sql(dialect=dialect)}) AND ({filters(r, interval.get(side + 'EventFilters', {}), 'interval.' + side + 'EventFilters')})"
        return predicate, r

    start, sr = event("start"); end, er = event("end")
    if interval["startEvent"]["eventNameField"] != interval["endEvent"]["eventNameField"]:
        fail("interval.endEvent", "起终事件必须使用同一事件标识字段。")
    entity, _ = resolve(base, interval["entityField"], "interval.entityField")
    resolve(base, config["time"]["field"], "time.field")
    for column in parse_one(time_plan.raw_time, read=dialect).find_all(exp.Column):
        resolve(base, {"table": table, "field": column.name}, "metadata.event_time")
    related = interval.get("relatedProperty", {})
    a = b = None
    if related.get("enabled"):
        a, ad = resolve(sr, related["startProperty"], "interval.relatedProperty.startProperty")
        b, bd = resolve(er, related["endProperty"], "interval.relatedProperty.endProperty")
        family = lambda d: "number" if NUMERIC.match(d.get("type", "")) else "text" if TEXT.match(d.get("type", "")) else d.get("type")
        if family(ad) != family(bd): fail("interval.relatedProperty", "两端关联属性类型必须一致。")
        if interval["startEvent"]["eventName"] == interval["endEvent"]["eventName"] and a != b:
            fail("interval.relatedProperty", "同事件相邻配对需要同一关联属性。")
    # Keep the established metadata contract: event time is the primary key;
    # explicitly declared event_id/event_sequence roles provide tie breakers.
    # The query guard, rather than a new mandatory UI setting, rejects actual
    # ambiguous rows when the configured keys do not establish a total order.
    order_names = {name for name, definition in metadata[table].items()
                   if definition.get("field_role") in {"event_id", "event_sequence"}}
    for item in t.get("field_role_mappings", []):
        if isinstance(item, dict) and item.get("table") == table and item.get("role") in {"event_id", "event_sequence"}:
            if not isinstance(item.get("field"), str) or not item["field"]:
                fail("metadata.field_role_mappings", "事件排序字段角色缺少字段名。")
            order_names.add(item["field"])
    orders = []
    for name in sorted(order_names):
        expression, definition = resolve(base, {"table": table, "field": name}, "metadata.field_role_mappings")
        kind = definition.get("type", "").lower()
        if definition.get("json_path") or definition.get("expression") or not is_interval_order_type(kind):
            fail("metadata.field_role_mappings", "排序键仅支持物理整数或文本字段。")
        orders.append(expression)
    global_filter = filters(base, config.get("filters", {}), "filters")
    mandatory = filters(base, table_filters.get(table, {}), "metadata.table_filters")
    return IntervalSqlPlan(dialect, engine.lower(), table, entity, start, end, f"({mandatory}) AND ({global_filter})",
                           a, b, tuple(resolve(base, g, f"groups[{i}]")[0] for i, g in enumerate(config.get("groups", []))),
                           tuple(orders), interval["limitSeconds"], time_plan)
