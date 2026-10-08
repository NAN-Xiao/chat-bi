"""Resolve retention configuration against authorized workspace metadata, without inference."""
from __future__ import annotations

import copy
from dataclasses import dataclass

from sqlglot import exp

from apps.dashboard.crud.dashboard_date_filter import dashboard_date_parameter_tokens
from apps.dashboard.crud.property_sql_plan import (
    _Resolver, _local_timestamp, NUMERIC, PropertyConfigurationError,
)
from apps.system.crud.tracking_event_schema import _normalized_type, _event_names


@dataclass(frozen=True)
class RetentionIssue:
    code: str
    path: str
    message: str

    def __str__(self):
        return f"{self.path}：{self.message}"


class RetentionConfigurationError(ValueError):
    def __init__(self, issues):
        self.issues = tuple(issues)
        super().__init__("；".join(map(str, self.issues)))


def fail(path, message):
    raise RetentionConfigurationError([RetentionIssue("RETENTION_INVALID_CONFIG", path, message)])


@dataclass(frozen=True)
class RetentionEventPlan:
    table: str
    entity: str
    date: str
    predicate: str
    related: str = ""
    metric: str = ""


@dataclass(frozen=True)
class RetentionSqlPlan:
    dialect: str
    initial: RetentionEventPlan
    returning: RetentionEventPlan
    simultaneous: RetentionEventPlan | None
    aggregation: str
    related_enabled: bool
    related_as_group: bool
    end_expression: str
    end_inclusive: bool
    required_columns: tuple[str, ...]
    window_days: int = 7


def validate_retention_input(raw):
    issues = []

    def add(path, message):
        issues.append(RetentionIssue("RETENTION_INVALID_CONFIG", path, message))

    def filters(value, path):
        if not isinstance(value, dict):
            add(path, "筛选必须为结构化条件。")
            return
        if not value:
            return
        key = "children" if value.get("type") == "group" else "rules"
        if key in value:
            if value.get("logic", "and") not in {"and", "or"} or not isinstance(value[key], list):
                add(path, "筛选需要 AND/OR 和有效条件列表。")
                return
            for i, child in enumerate(value[key]):
                if not child:
                    add(f"{path}.{key}[{i}]", "筛选条件不能为空。")
                filters(child, f"{path}.{key}[{i}]")
        elif not isinstance(value.get("field"), dict) or value.get("operator") not in {
            "eq", "ne", "gt", "lt", "between", "contains", "is_null", "is_not_null"
        }:
            add(path, "筛选字段或操作符无效。")
        elif value["operator"] not in {"is_null", "is_not_null"} and value.get("value") in (None, ""):
            add(path + ".value", "筛选值不能为空。")

    r = raw.get("retention")
    if not isinstance(r, dict):
        return [RetentionIssue("RETENTION_INVALID_CONFIG", "retention", "留存配置必须为对象。")]
    for key in ("entityField", "initialEvent", "returnEvent"):
        if not isinstance(r.get(key), dict) or not r[key]:
            add("retention." + key, "请选择有效字段或事件。")
    time = raw.get("time")
    if not isinstance(time, dict) or not isinstance(time.get("field"), dict):
        add("time.field", "请选择时间字段。")
    elif time.get("grain") not in (None, "", "day"):
        add("time.grain", "留存模型按自然日计算，请选择日粒度。")
    for key in ("simultaneous", "relatedProperty"):
        option = r.get(key, {})
        if not isinstance(option, dict):
            add("retention." + key, "配置必须为对象。")
            continue
        for toggle in ("enabled", "asGroup"):
            if toggle in option and not isinstance(option[toggle], bool):
                add(f"retention.{key}.{toggle}", "开关必须为布尔值。")
    sim = r.get("simultaneous")
    if isinstance(sim, dict) and sim.get("enabled") is True:
        if sim.get("aggregation") not in {"count", "count_distinct", "sum", "avg", "min", "max"}:
            add("retention.simultaneous.aggregation", "请选择支持的聚合方式。")
        if not isinstance(sim.get("event"), dict):
            add("retention.simultaneous.event", "请选择同时展示事件。")
        if sim.get("aggregation") != "count" and not isinstance(sim.get("metricField"), dict):
            add("retention.simultaneous.metricField", "请选择聚合属性。")
    for key in ("initialEventFilters", "returnEventFilters"):
        filters(r.get(key, {}), "retention." + key)
    filters(raw.get("filters", {}), "filters")
    if raw.get("groups"):
        add("groups", "留存分组请使用关联属性的作为分组配置。")
    return issues


def _time_expression(resolver, value, parameter_type, path):
    column, definition = resolver.field(value, path)
    kind = str(definition.get("type") or "").lower()
    dialect = resolver.dialect
    tokens = dashboard_date_parameter_tokens(parameter_type)
    if not tokens:
        fail(path, "日期参数类型无效。")
    start, end = tokens
    end_expression = end
    if parameter_type in {"yyyymmdd_number", "yyyymmdd_text"}:
        if parameter_type == "yyyymmdd_number" and not NUMERIC.match(kind):
            fail(path, "数值日期参数需要数值日期字段。")
        if parameter_type == "yyyymmdd_text" and not kind.startswith(("varchar", "char", "text", "string")):
            fail(path, "文本日期参数需要文本日期字段。")
        def parsed(item):
            return (f"TO_DATE(CAST({item} AS TEXT), 'YYYYMMDD')" if dialect == "postgres"
                    else f"STR_TO_DATE(CAST({item} AS CHAR), '%Y%m%d')")
        date, end_expression = parsed(column), parsed(end)
    elif parameter_type == "date" and kind == "date":
        date = column
    elif parameter_type == "timestamp" and NUMERIC.match(kind):
        from common.core.config import settings
        encoding = (definition.get("extra_properties") or {}).get("encoding")
        if encoding not in {"epoch_seconds", "epoch_milliseconds"}:
            fail(path, "数值时间字段必须声明 epoch_seconds 或 epoch_milliseconds。")
        factor = 1000 if encoding == "epoch_milliseconds" else 1
        zone = exp.Literal.string(settings.DASHBOARD_BUSINESS_TIMEZONE).sql(dialect=dialect)
        if dialect == "postgres":
            date = f"CAST(TO_TIMESTAMP({column} / {factor}.0) AT TIME ZONE {zone} AS DATE)"
            start, end = (f"(EXTRACT(EPOCH FROM ({token} AT TIME ZONE {zone})) * {factor})" for token in tokens)
        else:
            epoch = "CAST('1970-01-01 00:00:00' AS DATETIME)"
            date = f"CAST(CONVERT_TZ(TIMESTAMPADD(SECOND, {column} / {factor}.0, {epoch}), '+00:00', {zone}) AS DATE)"
            start, end = (f"(TIMESTAMPDIFF(SECOND, {epoch}, CONVERT_TZ({token}, {zone}, '+00:00')) * {factor})" for token in tokens)
    elif parameter_type == "timestamp" and kind.startswith(("timestamp", "datetime")):
        parsed = _local_timestamp(column, definition, dialect, path)
        date = f"CAST({parsed} AS DATE)"
        if kind == "timestamptz" or "with time zone" in kind:
            from common.core.config import settings
            zone = exp.Literal.string(settings.DASHBOARD_BUSINESS_TIMEZONE).sql(dialect=dialect)
            start, end = (f"({token} AT TIME ZONE {zone})" for token in tokens)
    else:
        fail(path, "时间字段类型与日期参数不匹配，请配置明确的时间编码。")
    predicate = f"{column} >= {start} AND {column} {'<' if parameter_type == 'timestamp' else '<='} {end}"
    return date, predicate, end_expression


def build_retention_plan(config, *, metadata_fields, allowed_fields_by_table, dialect, tracking_metadata=None, table_filters=None):
    issues = validate_retention_input(config)
    if issues:
        raise RetentionConfigurationError(issues)
    if dialect not in {"postgres", "mysql", "starrocks", "doris"}:
        fail("datasource", f"当前方言 {dialect} 未提供留存编译能力。")
    tracking = tracking_metadata.model_dump() if hasattr(tracking_metadata, "model_dump") else (tracking_metadata or {})
    retention, time = config["retention"], config["time"]
    related = retention.get("relatedProperty", {})
    simultaneous = retention.get("simultaneous", {})
    parameter_type = time.get("date_parameter_type") or time.get("dateParameterType")

    def canonical_table(name):
        if name in metadata_fields:
            return name
        matches = [t for t in metadata_fields if t.split(".")[-1] == name]
        if len(matches) != 1:
            fail("metadata.table", "事件表不存在、无权限或短表名不唯一。")
        return matches[0]

    def resolve_event(event, path, filter_config, related_key, metric=None):
        table, name, event_field = event.get("eventTable"), event.get("eventName"), event.get("eventNameField")
        if not all(isinstance(v, str) and v.strip() for v in (table, name, event_field)):
            fail(path, "事件必须配置实际表、事件名字段和事件名称。")
        table = canonical_table(table)
        metadata = copy.deepcopy(metadata_fields)
        # Event JSON properties are resolved only within their configured event.
        mappings = [m for m in tracking.get("event_name_mappings", []) if isinstance(m, dict)
                    and name in _event_names(m)]
        if tracking.get("enabled") and not mappings:
            fail(path, "事件已不在当前工作空间事件字典中。")
        for mapping in mappings:
            configured_table = mapping.get("event_table") or mapping.get("table") or tracking.get("default_event_table")
            configured_key = mapping.get("event_name_field") or tracking.get("default_event_name_field")
            if table != canonical_table(configured_table) or event_field != configured_key:
                fail(path, "事件来源与当前工作空间事件字典不一致。")
        for mapping in mappings:
            for prop in mapping.get("properties", []):
                key = prop.get("property_name") or prop.get("field_name") or prop.get("name")
                host, json_path = prop.get("source_field"), prop.get("json_path")
                if key and host in metadata.get(table, {}) and json_path:
                    kind = _normalized_type(prop.get("property_type") or prop.get("semantic_type") or prop.get("field_type") or prop.get("type"))
                    metadata[table][key] = {**prop, "source_field": host, "json_path": json_path,
                                          "semantic_type": kind, "type": kind}
        resolver = _Resolver(metadata, allowed_fields_by_table, dialect)
        resolver.table = table

        def mapped_field(value, role, field_path):
            if canonical_table(value.get("table")) == table:
                return value
            # Cross-table mappings must be explicit and unique, not same-name guesses.
            if role is None:
                origin = metadata.get(canonical_table(value.get("table")), {}).get(value.get("field"), {})
                roles = {origin.get("field_role")}
                roles |= {m.get("role") for m in tracking.get("field_role_mappings", [])
                          if isinstance(m, dict) and m.get("table") == value.get("table") and m.get("field") == value.get("field")}
                roles.discard(None)
                roles.discard("")
                if len(roles) != 1:
                    fail(field_path, "跨表主体需要明确且唯一的字段角色。")
                role = next(iter(roles))
            candidates = {m.get("field") for m in tracking.get("field_role_mappings", [])
                          if isinstance(m, dict) and m.get("table") == table and m.get("role") == role}
            candidates |= {m.get("field_name") for m in tracking.get("fields", [])
                           if isinstance(m, dict) and m.get("table_name") == table and m.get("field_role") == role}
            candidates |= {name for name, definition in metadata.get(table, {}).items() if definition.get("field_role") == role}
            candidates.discard(None)
            if len(candidates) != 1:
                fail(field_path, f"跨表事件需要唯一的 {role} 字段映射。")
            return {"table": table, "field": next(iter(candidates))}

        event_column, _ = resolver.field({"table": table, "field": event_field}, path)
        entity, _ = resolver.field(mapped_field(retention["entityField"], None, path + ".entityField"), path + ".entityField")
        date, time_predicate, end_expression = _time_expression(resolver, mapped_field(time["field"], "event_time", path + ".time"), parameter_type, path + ".time")
        related_expression = ""
        if related.get("enabled"):
            related_expression, _ = resolver.field(related.get(related_key), "retention.relatedProperty." + related_key)
        metric_expression = ""
        if metric is not None:
            metric_expression, definition = resolver.field(metric, "retention.simultaneous.metricField")
            if simultaneous["aggregation"] in {"sum", "avg"} and not NUMERIC.match(str(definition.get("type") or "")):
                fail("retention.simultaneous.metricField", "SUM/AVG 需要数值属性。")
        predicate = " AND ".join(f"({v})" for v in (
            f"{event_column} = {exp.Literal.string(name).sql(dialect=dialect)}",
            time_predicate, f"{entity} IS NOT NULL", resolver.filters(config.get("filters", {}), "filters"),
            resolver.filters(filter_config, path + ".filters"),
            *(resolver.filters(policy, "workspace.required_filters") for policy_table, policy in (table_filters or {}).items()
              if canonical_table(policy_table) == table),
        ))
        return RetentionEventPlan(resolver.table, entity, date, predicate, related_expression, metric_expression), end_expression

    try:
        initial, end = resolve_event(retention["initialEvent"], "retention.initialEvent", retention.get("initialEventFilters", {}), "initialProperty")
        returning, _ = resolve_event(retention["returnEvent"], "retention.returnEvent", retention.get("returnEventFilters", {}), "returnProperty")
        sim = None
        if simultaneous.get("enabled"):
            sim, _ = resolve_event(simultaneous["event"], "retention.simultaneous.event", {}, "simultaneousProperty",
                                   simultaneous.get("metricField") if simultaneous["aggregation"] != "count" else None)
    except PropertyConfigurationError as exc:
        raise RetentionConfigurationError([RetentionIssue("RETENTION_INVALID_CONFIG", i.path, i.message.replace("属性分析仅支持同一个授权源表", "事件字段必须属于当前事件表")) for i in exc.issues]) from exc
    columns = ("cohort_date", "cohort_size", *(f"day_{d}" for d in range(8)))
    if sim: columns += ("simultaneous_value",)
    as_group = related.get("enabled") is True and related.get("asGroup") is True
    if as_group: columns += ("related_property",)
    return RetentionSqlPlan(dialect, initial, returning, sim, simultaneous.get("aggregation", "count"),
                            related.get("enabled") is True, as_group, end, parameter_type != "timestamp", columns)
