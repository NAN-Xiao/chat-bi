"""Resolve daily revenue cohorts from explicit configuration and authorized metadata."""
from __future__ import annotations

import copy
from dataclasses import dataclass

from sqlglot import exp

from apps.dashboard.crud.funnel_sql_plan import _EventResolver, _filter_issues, _is_field, FunnelConfigurationError
from apps.dashboard.crud.property_sql_plan import _Resolver, NUMERIC, PropertyConfigurationError
from apps.dashboard.crud.retention_sql_plan import _time_expression, RetentionConfigurationError
from apps.system.crud.tracking_event_schema import _event_names, _normalized_type


METHODS = frozenset({"count", "entity_count", "per_entity_count", "period_cumulative_count",
                     "period_average_count", "period_cumulative_entity_count", "period_average_entity_count",
                     "property_sum", "property_avg"})


@dataclass(frozen=True)
class RevenueIssue:
    code: str
    path: str
    message: str

    def __str__(self):
        return f"{self.path}：{self.message}"


class RevenueConfigurationError(ValueError):
    def __init__(self, issues):
        self.issues = tuple(issues)
        super().__init__("；".join(map(str, self.issues)))


def fail(path, message):
    raise RevenueConfigurationError([RevenueIssue("REVENUE_INVALID_CONFIG", path, message)])


def _validate_json_source(definition, metadata, table, path):
    if definition.get("json_path"):
        host_type = str(metadata[table].get(definition.get("source_field"), {}).get("type") or "").lower()
        if not host_type.startswith(("json", "text", "varchar", "char", "string")):
            fail(path, "JSON 属性必须有明确、已授权的 JSON 或文本来源列。")


class _RevenueResolver(_Resolver):
    """All selected roles obey the same trusted JSON source contract."""
    def field(self, value, path):
        expression, definition = super().field(value, path)
        _validate_json_source(definition, self.metadata, self.table, path)
        return expression, definition


@dataclass(frozen=True)
class RevenueEventPlan:
    table: str
    entity: str
    date: str
    predicate: str
    groups: tuple[str, ...] = ()
    metric: str = ""
    cost: str = ""


@dataclass(frozen=True)
class RevenueSqlPlan:
    dialect: str
    initial: RevenueEventPlan
    payment: RevenueEventPlan
    metric_event: RevenueEventPlan
    cost_event: RevenueEventPlan | None
    cost_method: str | None
    method: str
    observation_days: int
    end_expression: str
    end_inclusive: bool
    required_columns: tuple[str, ...]


def validate_revenue_input(raw):
    issues = []

    def add(path, message):
        issues.append(RevenueIssue("REVENUE_INVALID_CONFIG", path, message))

    if not isinstance(raw, dict) or not isinstance(raw.get("revenue"), dict):
        return [RevenueIssue("REVENUE_INVALID_CONFIG", "revenue", "收入配置必须为对象。")]
    revenue = raw["revenue"]
    if any(k in revenue for k in ("entity_field", "initial_event", "payment_event", "observation_days", "costEnabled", "costField", "cost_field")):
        add("revenue", "请使用 entityField、initialEvent、paymentEvent、metricEvent、observationDays 和 cost 配置。")
    if not _is_field(revenue.get("entityField")):
        add("revenue.entityField", "请选择明确的分析主体字段。")
    def validate_event(event, path):
        if not isinstance(event, dict) or not all(isinstance(event.get(k), str) and event[k].strip()
                                                   for k in ("eventTable", "eventNameField", "eventName")):
            add(path, "请选择明确的事件来源表、事件名字段和事件名称。")
    for key in ("initialEvent", "paymentEvent", "metricEvent"):
        validate_event(revenue.get(key), "revenue." + key)
    days = revenue.get("observationDays")
    if type(days) is not int or not 1 <= days <= 365:
        add("revenue.observationDays", "观察时长必须是 1 到 365 的整数天数。")
    metric = revenue.get("metric")
    if not isinstance(metric, dict) or not isinstance(metric.get("method"), str) or metric["method"] not in METHODS:
        add("revenue.metric.method", "请选择支持的收入口径。")
    elif metric["method"] in {"property_sum", "property_avg"} and not _is_field(metric.get("field")):
        add("revenue.metric.field", "属性求和或均值必须选择数值属性。")
    cost = revenue.get("cost", {})
    if not isinstance(cost, dict) or ("enabled" in cost and type(cost["enabled"]) is not bool):
        add("revenue.cost.enabled", "成本开关必须为布尔值。")
    elif cost.get("enabled") is True:
        validate_event(cost.get("event"), "revenue.cost.event")
        if not isinstance(cost.get("method"), str) or cost["method"] not in METHODS:
            add("revenue.cost.method", "请选择支持的成本计算方式。")
        elif cost["method"] in {"property_sum", "property_avg"} and not _is_field(cost.get("field")):
            add("revenue.cost.field", "启用成本时必须选择成本事件的金额属性。")
    time = raw.get("time")
    if not isinstance(time, dict) or not _is_field(time.get("field")):
        add("time.field", "请选择明确的日期或时间字段。")
    elif time.get("grain") not in (None, "", "day"):
        add("time.grain", "收入模型按自然日计算，请选择日粒度。")
    if isinstance(raw.get("chart"), dict) and raw["chart"].get("type") not in (None, "table"):
        add("chart.type", "收入模型只能输出收入表。")
    groups = raw.get("groups", [])
    if not isinstance(groups, list) or any(not _is_field(g) for g in groups):
        add("groups", "分组必须为明确的授权属性列表。")
    issues.extend(RevenueIssue("REVENUE_INVALID_CONFIG", i.path, i.message)
                  for i in _filter_issues(raw.get("filters", {}), "filters"))
    if any(raw.get(k) for k in ("formulaMetrics", "calculatedMetrics", "formula_metrics")):
        add("formulaMetrics", "收入模型不支持额外公式指标。")
    if raw.get("approximate") not in (None, False):
        add("approximate", "收入模型使用精确主体计数。")
    return issues


def build_revenue_plan(config, *, metadata_fields, allowed_fields_by_table, dialect,
                       tracking_metadata=None, table_filters=None):
    issues = validate_revenue_input(config)
    if issues:
        raise RevenueConfigurationError(issues)
    if dialect not in {"postgres", "mysql", "starrocks", "doris"}:
        fail("datasource", f"当前方言 {dialect} 未提供收入编译能力。")
    tracking = tracking_metadata.model_dump() if hasattr(tracking_metadata, "model_dump") else (tracking_metadata or {})
    revenue, time = config["revenue"], config["time"]

    def canonical(name):
        matches = [t for t in metadata_fields if t == name]
        if not matches:
            matches = [t for t in metadata_fields if t.split(".")[-1] == name]
        if len(matches) != 1:
            fail("metadata.table", "表不存在、未授权或短表名存在歧义。")
        return matches[0]

    table = canonical(revenue["initialEvent"]["eventTable"])
    for key in ("paymentEvent", "metricEvent"):
        if canonical(revenue[key]["eventTable"]) != table:
            fail("revenue." + key, "当前收入配置需使用同一授权事件表；不能猜测跨表关联。")

    def resolve(event, path, role="initial"):
        if canonical(event["eventTable"]) != table:
            fail(path, "当前收入配置需使用同一授权事件表；不能猜测跨表关联。")
        name, key = event["eventName"], event["eventNameField"]
        mappings = [m for m in tracking.get("event_name_mappings", []) if isinstance(m, dict) and name in _event_names(m)]
        if tracking.get("enabled") and len(mappings) != 1:
            fail(path, "事件必须在当前工作空间字典中存在且定义唯一。")
        properties = {}
        for mapping in mappings:
            mapped_table = mapping.get("event_table") or mapping.get("table") or tracking.get("default_event_table")
            mapped_key = mapping.get("event_name_field") or tracking.get("default_event_name_field")
            if canonical(mapped_table) != table or mapped_key != key:
                fail(path, "事件来源与工作空间事件字典不一致。")
            for prop in mapping.get("properties", []):
                pname = prop.get("property_name") or prop.get("field_name") or prop.get("name")
                if not pname:
                    continue
                if pname in properties:
                    fail(path, "事件参数存在重复定义。")
                host = prop.get("source_field")
                kind = _normalized_type(prop.get("property_type") or prop.get("semantic_type") or prop.get("field_type") or prop.get("type"))
                # A dictionary label cannot turn a physical text column into
                # a numeric SQL value. Only JSON extraction uses its value type.
                physical_type = metadata_fields[table].get(host, {}).get("type", "")
                properties[pname] = {**prop, "type": kind if prop.get("json_path") else physical_type,
                                     "semantic_type": kind}
        base = _RevenueResolver(copy.deepcopy(metadata_fields), allowed_fields_by_table, dialect)
        base.table = table
        event_column, _ = base.field({"table": table, "field": key}, path + ".eventNameField")
        entity, _ = base.field(revenue["entityField"], "revenue.entityField")
        parameter_type = time.get("date_parameter_type") or time.get("dateParameterType")
        date, time_predicate, end = _time_expression(base, time["field"], parameter_type, "time.field")
        groups = tuple(base.field(g, f"groups[{i}]")[0] for i, g in enumerate(config.get("groups", []))) if role == "initial" else ()
        policy = []
        for policy_table, condition in (table_filters or {}).items():
            if canonical(policy_table) == table:
                errors = _filter_issues(condition, "workspace.required_filters")
                if errors:
                    fail("workspace.required_filters", "；".join(map(str, errors)))
                policy.append(base.filters(condition, "workspace.required_filters"))
        predicate = " AND ".join(f"({p})" for p in (
            f"{event_column} = {exp.Literal.string(name).sql(dialect=dialect)}", time_predicate,
            f"{entity} IS NOT NULL", base.filters(config.get("filters", {}), "filters"), *policy))
        resolver = _EventResolver(metadata_fields, allowed_fields_by_table, dialect, table, name, properties)

        def numeric(value, field_path):
            if value.get("eventName") and value["eventName"] != name:
                fail(field_path, "属性必须属于该配置项选择的事件。")
            expression, definition = resolver.field(value, field_path)
            # Validate the resolved mapping, including virtual references that
            # omit client kind and workspace-defined JSON attributes.
            _validate_json_source(definition, metadata_fields, table, field_path)
            if not NUMERIC.match(str(definition.get("type") or "").lower()):
                fail(field_path, "必须选择服务端元数据声明的数值属性。")
            return expression

        metric = numeric(revenue["metric"]["field"], "revenue.metric.field") if role == "metric" and revenue["metric"]["method"] in {"property_sum", "property_avg"} else ""
        cost_config = revenue.get("cost", {})
        cost = numeric(cost_config["field"], "revenue.cost.field") if role == "cost" and cost_config["method"] in {"property_sum", "property_avg"} else ""
        return RevenueEventPlan(table, entity, date, predicate, groups, metric, cost), end

    try:
        initial, end = resolve(revenue["initialEvent"], "revenue.initialEvent")
        payment, _ = resolve(revenue["paymentEvent"], "revenue.paymentEvent", "payment")
        metric_event, _ = resolve(revenue["metricEvent"], "revenue.metricEvent", "metric")
        cost_event = resolve(revenue["cost"]["event"], "revenue.cost.event", "cost")[0] if revenue.get("cost", {}).get("enabled") is True else None
    except (PropertyConfigurationError, FunnelConfigurationError, RetentionConfigurationError) as exc:
        raise RevenueConfigurationError([RevenueIssue("REVENUE_INVALID_CONFIG", i.path,
            i.message.replace("属性分析仅支持同一个授权源表", "字段必须属于当前授权事件表")) for i in exc.issues]) from exc
    columns = ("cohort_date", "cohort_size", *(f"day_{d}" for d in range(revenue["observationDays"] + 1)))
    if cost_event:
        columns += ("cost_value",)
    columns += tuple(f"group_{i + 1}" for i in range(len(initial.groups)))
    return RevenueSqlPlan(dialect, initial, payment, metric_event, cost_event,
                          revenue["cost"]["method"] if cost_event else None, revenue["metric"]["method"], revenue["observationDays"],
                          end, (time.get("date_parameter_type") or time.get("dateParameterType")) != "timestamp", columns)
