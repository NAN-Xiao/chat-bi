"""Resolve distribution inputs against authorized workspace metadata, without AI."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlglot import exp

from apps.dashboard.crud.funnel_sql_plan import _EventResolver, _filter_issues, _is_field, FunnelConfigurationError
from apps.dashboard.crud.property_sql_plan import _Resolver, NUMERIC, PropertyConfigurationError
from apps.dashboard.crud.retention_sql_plan import _time_expression, RetentionConfigurationError
from apps.system.crud.tracking_event_schema import _event_names, _normalized_type


PROPERTY_AGGREGATIONS = frozenset({"sum", "avg", "median", "max", "min", "count_distinct", "variance", "stddev",
    *[f"percentile_{p:02}" for p in (99, 95, 90, 80, 75, 70, 60, 40, 30, 25, 20, 10, 5)]})
SIMULTANEOUS_AGGREGATIONS = frozenset({"count", "count_distinct", "sum", "avg", "min", "max"})


@dataclass(frozen=True)
class DistributionIssue:
    code: str
    path: str
    message: str

    def __str__(self):
        return f"{self.path}：{self.message}"


class DistributionConfigurationError(ValueError):
    def __init__(self, issues):
        self.issues = tuple(issues)
        super().__init__("；".join(map(str, self.issues)))


def fail(path, message):
    raise DistributionConfigurationError([DistributionIssue("DISTRIBUTION_INVALID_CONFIG", path, message)])


@dataclass(frozen=True)
class DistributionSourcePlan:
    table: str
    entity_expression: str
    date_expression: str
    event_time_expression: str
    group_expressions: tuple[str, ...]
    value_expression: str
    predicate: str
    source_columns: tuple[str, ...]


@dataclass(frozen=True)
class DistributionSqlPlan:
    dialect: str
    engine: str
    main_source: DistributionSourcePlan
    simultaneous_source: DistributionSourcePlan | None
    metric_kind: str
    aggregation: str
    simultaneous_aggregation: str
    interval_mode: str
    custom_bounds: tuple[Decimal, ...]
    group_names: tuple[str, ...]
    required_columns: tuple[str, ...]
    contract_version: int = 1  # Server version, never a required client field.


def validate_distribution_input(raw: dict) -> list[DistributionIssue]:
    issues = []

    def add(path, message):
        issues.append(DistributionIssue("DISTRIBUTION_INVALID_CONFIG", path, message))

    def filters(value, path):
        issues.extend(DistributionIssue("DISTRIBUTION_INVALID_CONFIG", i.path, i.message)
                      for i in _filter_issues(value, path))

    def event(value, path):
        if not isinstance(value, dict) or not all(isinstance(value.get(k), str) and value[k].strip()
                for k in ("eventTable", "eventNameField", "eventName")):
            add(path, "请选择明确的事件来源表、事件名字段和事件。")

    if not isinstance(raw, dict) or not isinstance(raw.get("distribution"), dict):
        return [DistributionIssue("DISTRIBUTION_INVALID_CONFIG", "distribution", "分布配置必须为对象。")]
    d = raw["distribution"]
    if any(k in d for k in ("entity_field", "event_filters")):
        add("distribution", "请使用当前 entityField、eventFilters 配置字段。")
    if not _is_field(d.get("entityField")):
        add("distribution.entityField", "请选择明确的主体字段。")
    event(d.get("event"), "distribution.event")
    filters(d.get("eventFilters", {}), "distribution.eventFilters")
    filters(raw.get("filters", {}), "filters")
    time = raw.get("time")
    if not isinstance(time, dict) or not _is_field(time.get("field")):
        add("time.field", "请选择明确的日期范围字段。")
    elif time.get("grain", "day") != "day":
        add("time.grain", "当前分布编译只支持日粒度。")
    if isinstance(time, dict):
        parameter = time.get("date_parameter_type") or time.get("dateParameterType")
        if parameter not in ("date", "yyyymmdd_number", "yyyymmdd_text", "timestamp"):
            add("time.dateParameterType", "请选择有效的日期参数类型。")
    groups = raw.get("groups", [])
    if not isinstance(groups, list):
        add("groups", "分组必须是字段列表。")
    else:
        for n, g in enumerate(groups):
            if not _is_field(g):
                add(f"groups[{n}]", "请选择明确的分组字段。")
    chart = raw.get("chart", {})
    if not isinstance(chart, dict) or chart.get("type", "table") != "table":
        add("chart.type", "分布分析只支持分布表。")
    if any(raw.get(k) for k in ("calculatedMetrics", "formulaMetrics", "formula_metrics")):
        add("calculatedMetrics", "分布编译不支持公式指标。")
    if raw.get("approximate") not in (None, False):
        add("approximate", "分布编译不支持近似计算。")
    metric = d.get("metric")
    if not isinstance(metric, dict) or metric.get("kind") not in ("count", "days", "hours", "property"):
        add("distribution.metric.kind", "请选择有效的分布指标类型。")
    elif metric["kind"] == "property":
        if not _is_field(metric.get("field")):
            add("distribution.metric.field", "请选择事件属性。")
        if not isinstance(metric.get("aggregation"), str) or metric["aggregation"] not in PROPERTY_AGGREGATIONS:
            add("distribution.metric.aggregation", "事件属性聚合方式无效。")
    interval = d.get("interval")
    if not isinstance(interval, dict) or interval.get("mode") not in ("auto", "discrete", "custom"):
        add("distribution.interval.mode", "请选择有效的区间模式。")
    elif interval["mode"] == "custom":
        bounds = interval.get("customBounds")
        try:
            if not isinstance(bounds, list) or not 2 <= len(bounds) <= 20:
                raise ValueError()
            if any(type(v) not in (int, float, Decimal) for v in bounds):
                raise ValueError()
            numbers = [Decimal(str(v)) for v in bounds]
            if any(not n.is_finite() for n in numbers) or any(a >= b for a, b in zip(numbers, numbers[1:])):
                raise ValueError()
        except (InvalidOperation, ValueError):
            add("distribution.interval.customBounds", "需要 2 到 20 个有限、严格递增的数值边界。")
    sim = d.get("simultaneous", {})
    if not isinstance(sim, dict) or ("enabled" in sim and not isinstance(sim["enabled"], bool)):
        add("distribution.simultaneous.enabled", "同时展示开关必须为布尔值。")
    elif sim.get("enabled") is True:
        event(sim.get("event"), "distribution.simultaneous.event")
        if not isinstance(sim.get("aggregation"), str) or sim["aggregation"] not in SIMULTANEOUS_AGGREGATIONS:
            add("distribution.simultaneous.aggregation", "同时展示聚合方式无效。")
        elif sim["aggregation"] != "count" and not _is_field(sim.get("metricField")):
            add("distribution.simultaneous.metricField", "请选择同时展示的计算属性。")
    return issues


def _business_event_time(resolver, definitions, tracking, table, dialect, kind):
    """Business calendar values require explicit roles and encodings, not names."""
    from common.core.config import settings
    zone_name = settings.DASHBOARD_BUSINESS_TIMEZONE
    try:
        ZoneInfo(zone_name)
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        fail("metadata.timezone", "业务时区配置无效。")
    def current(name):
        return name in (table, table.split(".")[-1])
    candidates = {n for n, d in definitions.items() if d.get("field_role") == "event_time"}
    candidates.update(m.get("field") for m in tracking.get("field_role_mappings", [])
        if isinstance(m, dict) and current(m.get("table")) and m.get("role") == "event_time")
    candidates.update(m.get("field_name") for m in tracking.get("fields", [])
        if isinstance(m, dict) and current(m.get("table_name")) and m.get("field_role") == "event_time")
    if tracking.get("default_event_time_field"):
        candidates.add(tracking["default_event_time_field"])
    if len(candidates) != 1 or next(iter(candidates)) not in definitions:
        fail("metadata.event_time", "天数/小时数需要唯一且已授权的事件时间字段。")
    column, definition = resolver.field({"table": table, "field": next(iter(candidates))}, "metadata.event_time")
    _validate_time_metadata(definition, dialect, "metadata.event_time")
    data_type = str(definition.get("type") or "").lower()
    extra = definition.get("extra_properties") or {}
    zone = exp.Literal.string(zone_name).sql(dialect=dialect)
    if NUMERIC.match(data_type):
        if extra.get("encoding") not in ("epoch_seconds", "epoch_milliseconds"):
            fail("metadata.event_time", "数值事件时间需要明确的秒/毫秒编码。")
        seconds = f"({column} / 1000.0)" if extra["encoding"] == "epoch_milliseconds" else column
        local = (f"(TO_TIMESTAMP({seconds}) AT TIME ZONE {zone})" if dialect == "postgres" else
                 f"CONVERT_TZ(TIMESTAMPADD(SECOND, FLOOR({seconds}), CAST('1970-01-01 00:00:00' AS DATETIME)), '+00:00', {zone})")
    elif data_type == "date" and kind == "days" and extra.get("date_semantics") == "business_date":
        local = column
    elif data_type.startswith(("timestamp", "datetime")):
        aware = data_type == "timestamptz" or "with time zone" in data_type
        if aware:
            if dialect != "postgres":
                fail("metadata.event_time", "当前方言不支持此带时区时间字段。")
            local = f"({column} AT TIME ZONE {zone})"
        else:
            if extra.get("timezone") != zone_name:
                fail("metadata.event_time", "无时区时间字段需要声明与业务时区一致的 timezone。")
            local = column
    else:
        fail("metadata.event_time", "小时数需要实际时间戳，日期分区不能替代事件时间。")
    if kind == "days":
        return f"CAST({local} AS DATE)"
    return (f"DATE_TRUNC('hour', {local})" if dialect == "postgres" else f"DATE_FORMAT({local}, '%Y-%m-%d %H:00:00')")


def _validate_time_metadata(definition, dialect, path, parameter=None):
    data_type = str(definition.get("type") or "").lower()
    encoding = (definition.get("extra_properties") or {}).get("encoding")
    if parameter in {"yyyymmdd_number", "yyyymmdd_text"}:
        # Workspace calendar metadata also uses the format spelling yyyyMMdd.
        # Compare the same calendar encoding independent of format-token case;
        # unrelated encodings (for example epoch_seconds) remain invalid.
        calendar_encoding = encoding.lower() if isinstance(encoding, str) else encoding
        if calendar_encoding not in (None, "yyyymmdd"):
            fail(path, "日期参数与字段声明的 encoding 不一致。")
    if data_type.startswith(("timestamp", "datetime")):
        if encoding not in (None, "datetime", "timestamp", "timestamptz"):
            fail(path, "时间戳字段与声明的 encoding 不一致。")
        if dialect != "postgres" and data_type.startswith("timestamp"):
            # Native MySQL TIMESTAMP is rendered in the connection time zone.
            # This compiler cannot enforce that execution-session setting.
            fail(path, "当前分布编译尚未提供 TIMESTAMP 会话时区执行契约，请配置明确时区的 DATETIME 或 epoch 字段。")


def build_distribution_plan(config: dict, *, metadata_fields: dict, allowed_fields_by_table: dict,
                            tracking_metadata: Any, table_filters: dict, dialect: str, engine: str) -> DistributionSqlPlan:
    issues = validate_distribution_input(config)
    if issues:
        raise DistributionConfigurationError(issues)
    if dialect not in {"postgres", "mysql", "starrocks", "doris"}:
        fail("datasource", f"当前方言 {dialect} 未提供分布编译能力。")
    tracking = tracking_metadata.model_dump() if hasattr(tracking_metadata, "model_dump") else (tracking_metadata or {})
    if not tracking.get("enabled") or not tracking.get("default_event_table"):
        fail("metadata", "请启用工作空间事件字典并配置默认事件表。")

    def canonical(name):
        matches = [t for t in metadata_fields if t == name]
        if not matches:
            matches = [t for t in metadata_fields if t.split(".")[-1] == name]
        if len(matches) != 1:
            fail("metadata.table", "事件表不存在、未授权或表名存在歧义。")
        return matches[0]

    table = canonical(tracking["default_event_table"])
    definitions = metadata_fields[table]
    d, time = config["distribution"], config["time"]
    metric, interval, sim = d["metric"], d["interval"], d.get("simultaneous", {})

    def source(event, path, measure, aggregation, event_filters, time_kind=None):
        if canonical(event["eventTable"]) != table:
            fail(path, "分布事件必须属于当前工作空间默认事件表。")
        name = event["eventName"]
        mappings = [m for m in tracking.get("event_name_mappings", []) if isinstance(m, dict) and name in _event_names(m)]
        if len(mappings) != 1:
            fail(path, "事件不存在或事件字典定义不唯一。")
        mapping = mappings[0]
        if canonical(mapping.get("event_table") or mapping.get("table") or tracking["default_event_table"]) != table or (
            mapping.get("event_name_field") or tracking.get("default_event_name_field")) != event["eventNameField"]:
            fail(path, "事件来源与工作空间字典不一致。")
        properties = {}
        for prop in mapping.get("properties", []):
            key = prop.get("property_name") or prop.get("field_name") or prop.get("name")
            if key and prop.get("source_field") in definitions and prop.get("json_path"):
                if key in properties:
                    fail(path, "同一事件内参数名称重复。")
                kind = _normalized_type(prop.get("property_type") or prop.get("semantic_type") or prop.get("field_type") or prop.get("type"))
                properties[key] = {**prop, "semantic_type": kind, "type": kind}
        resolver = _EventResolver(metadata_fields, allowed_fields_by_table, dialect, table, name, properties)
        physical = _Resolver(metadata_fields, allowed_fields_by_table, dialect)
        physical.table = table
        entity, _ = resolver.field(d["entityField"], "distribution.entityField")
        event_column, _ = physical.field({"table": table, "field": event["eventNameField"]}, path)
        parameter = time.get("date_parameter_type") or time.get("dateParameterType")
        _, date_definition = physical.field(time["field"], "time.field")
        _validate_time_metadata(date_definition, dialect, "time.field", parameter)
        date, time_predicate, _ = _time_expression(physical, time["field"], parameter, "time.field")
        groups = tuple(resolver.field(g, f"groups[{i}]")[0] for i, g in enumerate(config.get("groups", [])))
        value = ""
        if measure is not None:
            value, definition = resolver.field(measure, path + ".metricField")
            if aggregation not in {"count_distinct", "min", "max"} or path == "distribution.event":
                if aggregation != "count_distinct" and not NUMERIC.match(str(definition.get("type") or "")):
                    fail(path + ".metricField", "当前聚合需要数值属性。")
        event_time = _business_event_time(physical, definitions, tracking, table, dialect, time_kind) if time_kind else ""
        predicates = [f"{event_column} = {exp.Literal.string(name).sql(dialect=dialect)}", time_predicate,
                      f"{entity} IS NOT NULL", resolver.filters(config.get("filters", {}), "filters"),
                      resolver.filters(event_filters, path + ".eventFilters")]
        for policy_table, policy in table_filters.items():
            if canonical(policy_table) != table:
                fail("workspace.required_filters", "强制筛选指向当前事件表之外的来源。")
            errors = _filter_issues(policy, "workspace.required_filters")
            if errors:
                raise DistributionConfigurationError([DistributionIssue("DISTRIBUTION_INVALID_CONFIG", i.path, i.message) for i in errors])
            predicates.append(physical.filters(policy, "workspace.required_filters"))
        return DistributionSourcePlan(table, entity, date, event_time, groups, value,
            " AND ".join(f"({p})" for p in predicates), tuple(sorted(resolver.columns | physical.columns)))

    try:
        main = source(d["event"], "distribution.event", metric.get("field") if metric["kind"] == "property" else None,
                      metric.get("aggregation", "sum"), d.get("eventFilters", {}), metric["kind"] if metric["kind"] in {"days", "hours"} else None)
        simultaneous = source(sim["event"], "distribution.simultaneous.event", sim.get("metricField") if sim["aggregation"] != "count" else None,
                              sim["aggregation"], {}) if sim.get("enabled") is True else None
    except (PropertyConfigurationError, RetentionConfigurationError, FunnelConfigurationError) as exc:
        raise DistributionConfigurationError([DistributionIssue("DISTRIBUTION_INVALID_CONFIG", i.path,
            i.message.replace("属性分析仅支持同一个授权源表", "分布字段必须属于当前默认事件表")) for i in exc.issues]) from exc
    group_names = tuple(f"group_{n + 1}" for n in range(len(main.group_expressions)))
    columns = ("distribution_date", *group_names, "total_entities", "interval_order", "interval_label", "entity_count", "entity_rate")
    if simultaneous:
        columns += ("simultaneous_value",)
    return DistributionSqlPlan(dialect, engine, main, simultaneous, metric["kind"], metric.get("aggregation", "sum"),
        sim.get("aggregation", "count"), interval["mode"], tuple(Decimal(str(b)) for b in interval["customBounds"]) if interval["mode"] == "custom" else (),
        group_names, columns)
