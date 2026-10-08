"""Resolve ranking configuration against authorized event metadata, without inference."""
from __future__ import annotations

import copy
from dataclasses import dataclass

from sqlglot import exp

from apps.dashboard.crud.dashboard_date_filter import dashboard_date_parameter_tokens
from apps.dashboard.crud.funnel_sql_plan import _EventResolver, _filter_issues, _is_field, FunnelConfigurationError
from apps.dashboard.crud.property_sql_plan import _Resolver, NUMERIC, PropertyConfigurationError
from apps.dashboard.crud.retention_sql_plan import _time_expression, RetentionConfigurationError
from apps.system.crud.tracking_event_schema import _event_names, _normalized_type

AGGREGATIONS = frozenset({"count", "count_distinct", "sum", "avg", "min", "max"})


@dataclass(frozen=True)
class RankingIssue:
    code: str
    path: str
    message: str

    def __str__(self):
        return f"{self.path}：{self.message}"


class RankingConfigurationError(ValueError):
    def __init__(self, issues):
        self.issues = tuple(issues)
        super().__init__("；".join(map(str, self.issues)))


def fail(path, message):
    raise RankingConfigurationError([RankingIssue("RANKING_INVALID_CONFIG", path, message)])


def _validate_definition(definition, metadata, table, path):
    if definition.get("json_path"):
        host = str(metadata[table].get(definition.get("source_field"), {}).get("type") or "").lower()
        if not host.startswith(("json", "text", "varchar", "char", "string")):
            fail(path, "JSON 属性需要已授权的 JSON 或文本来源列。")
    kind = str(definition.get("type") or "").lower()
    if not (NUMERIC.match(kind) or kind.startswith(("varchar", "char", "text", "string", "date", "timestamp", "bool"))):
        fail(path, "请选择具有明确标量类型的属性，不能直接使用 JSON 对象或数组。")


class _RankingResolver(_Resolver):
    def field(self, value, path):
        expression, definition = super().field(value, path)
        _validate_definition(definition, self.metadata, self.table, path)
        return expression, definition


class _RankingEventResolver(_EventResolver):
    def field(self, value, path):
        if isinstance(value, dict) and value.get("eventName") and value["eventName"] != self.event_name:
            fail(path, "属性必须属于当前配置事件。")
        expression, definition = super().field(value, path)
        _validate_definition(definition, self.metadata, self.table, path)
        return expression, definition


@dataclass(frozen=True)
class RankingMetricPlan:
    table: str
    entity: str
    predicate: str
    aggregation: str
    measure: str
    properties: tuple[str, ...] = ()


@dataclass(frozen=True)
class RankingSqlPlan:
    dialect: str
    metrics: tuple[RankingMetricPlan, ...]
    direction: str
    tie_handling: str
    parameter_type: str
    parameter_tokens: tuple[str, str]
    required_columns: tuple[str, ...]
    business_timezone: str
    mysql_timezones: tuple[str, ...] = ()


def validate_ranking_input(raw):
    issues = []

    def add(path, message):
        issues.append(RankingIssue("RANKING_INVALID_CONFIG", path, message))

    if not isinstance(raw, dict) or not isinstance(raw.get("ranking"), dict):
        return [RankingIssue("RANKING_INVALID_CONFIG", "ranking", "排行榜配置必须为对象。")]
    ranking = raw["ranking"]
    if not _is_field(ranking.get("entityField")):
        add("ranking.entityField", "请选择明确的排行主体。")
    if ranking.get("tieHandling") not in ("default", "skip", "dense"):
        add("ranking.tieHandling", "并列名次规则无效。")
    additional = ranking.get("simultaneousMetrics", [])
    if not isinstance(additional, list):
        add("ranking.simultaneousMetrics", "同时展示指标必须为列表。")
        additional = []
    for index, metric in enumerate([ranking.get("metric"), *additional]):
        path = "ranking.metric" if index == 0 else f"ranking.simultaneousMetrics[{index - 1}]"
        if not isinstance(metric, dict):
            add(path, "指标必须为有效对象。")
            continue
        event = metric.get("event")
        if not isinstance(event, dict) or not all(isinstance(event.get(k), str) and event[k].strip()
                for k in ("eventTable", "eventNameField", "eventName")):
            add(path + ".event", "请选择明确的事件来源表、事件名字段和事件。")
        if not isinstance(metric.get("aggregation"), str) or metric["aggregation"] not in AGGREGATIONS:
            add(path + ".aggregation", "指标聚合方式无效。")
        elif metric["aggregation"] != "count" and not _is_field(metric.get("metricField")):
            add(path + ".metricField", "请选择指标计算字段。")
        if index == 0 and metric.get("direction") not in ("asc", "desc"):
            add(path + ".direction", "排序方向无效。")
    properties = ranking.get("simultaneousProperties", [])
    if not isinstance(properties, list) or any(not _is_field(p) for p in properties):
        add("ranking.simultaneousProperties", "同时展示属性必须为明确的属性列表。")
    time = raw.get("time")
    if not isinstance(time, dict) or not _is_field(time.get("field")):
        add("time.field", "请选择明确的日期范围字段。")
    elif (time.get("date_parameter_type") or time.get("dateParameterType")) not in ("date", "timestamp", "yyyymmdd_number", "yyyymmdd_text"):
        add("time.dateParameterType", "日期参数类型无效。")
    if raw.get("groups"):
        add("groups", "排行榜固定一行一个主体，不支持额外分组。")
    if any(raw.get(k) for k in ("formulaMetrics", "formula_metrics", "calculatedMetrics")):
        add("formulaMetrics", "排行榜不支持额外公式指标。")
    if raw.get("approximate") not in (None, False):
        add("approximate", "排行榜使用精确聚合。")
    if isinstance(raw.get("chart"), dict) and raw["chart"].get("type") not in (None, "table"):
        add("chart.type", "排行榜只能输出排行榜表。")
    issues.extend(RankingIssue("RANKING_INVALID_CONFIG", i.path, i.message) for i in _filter_issues(raw.get("filters", {}), "filters"))
    return issues


def build_ranking_plan(config, *, metadata_fields, allowed_fields_by_table, dialect, tracking_metadata=None, table_filters=None):
    issues = validate_ranking_input(config)
    if issues:
        raise RankingConfigurationError(issues)
    if dialect not in {"postgres", "mysql", "starrocks", "doris"}:
        fail("datasource", f"当前方言 {dialect} 未提供排行榜编译能力。")
    from common.core.config import settings
    tracking = tracking_metadata.model_dump() if hasattr(tracking_metadata, "model_dump") else (tracking_metadata or {})
    ranking, time = config["ranking"], config["time"]
    parameter = time.get("date_parameter_type") or time.get("dateParameterType")
    tokens = tuple(dashboard_date_parameter_tokens(parameter))

    def canonical(name):
        matches = [t for t in metadata_fields if t == name]
        if not matches:
            matches = [t for t in metadata_fields if t.split(".")[-1] == name]
        if len(matches) != 1:
            fail("metadata.table", "表不存在、未授权或短表名存在歧义。")
        return matches[0]

    table = canonical(ranking["metric"]["event"]["eventTable"])
    mysql_timezones = set()

    def resolve(metric, index):
        path = "ranking.metric" if index == 0 else f"ranking.simultaneousMetrics[{index - 1}]"
        event = metric["event"]
        if canonical(event["eventTable"]) != table:
            fail(path, "当前排行榜需使用同一授权事件表，不能猜测跨表关联。")
        name, key = event["eventName"], event["eventNameField"]
        mappings = [m for m in tracking.get("event_name_mappings", []) if isinstance(m, dict) and name in _event_names(m)]
        if tracking.get("enabled") and len(mappings) != 1:
            fail(path, "事件必须在当前工作空间字典中存在且定义唯一。")
        properties = {}
        for mapping in mappings:
            if canonical(mapping.get("event_table") or mapping.get("table") or tracking.get("default_event_table")) != table or (
                    mapping.get("event_name_field") or tracking.get("default_event_name_field")) != key:
                fail(path, "事件来源与工作空间字典不一致。")
            for prop in mapping.get("properties", []):
                pname = prop.get("property_name") or prop.get("field_name") or prop.get("name")
                if not pname:
                    continue
                if pname in properties:
                    fail(path, "同一事件的参数名称重复。")
                kind = _normalized_type(prop.get("property_type") or prop.get("semantic_type") or prop.get("field_type") or prop.get("type"))
                physical_type = metadata_fields[table].get(prop.get("source_field"), {}).get("type", "")
                properties[pname] = {**prop, "type": kind if prop.get("json_path") else physical_type, "semantic_type": kind}
        base = _RankingResolver(copy.deepcopy(metadata_fields), allowed_fields_by_table, dialect)
        base.table = table
        resolver = _RankingEventResolver(metadata_fields, allowed_fields_by_table, dialect, table, name, properties)
        entity, _ = base.field(ranking["entityField"], "ranking.entityField")
        event_column, _ = base.field({"table": table, "field": key}, path + ".eventNameField")
        _, time_definition = base.field(time["field"], "time.field")
        kind = str(time_definition.get("type") or "").lower()
        encoding = (time_definition.get("extra_properties") or {}).get("encoding")
        if parameter.startswith("yyyymmdd") and encoding is not None and str(encoding).lower() != "yyyymmdd":
            fail("time.field", "日期参数与字段时间编码不一致。")
        if parameter == "timestamp" and kind.startswith(("timestamp", "datetime")):
            if encoding not in (None, "timestamp", "datetime", "timestamptz"):
                fail("time.field", "时间戳字段与声明的编码不一致。")
            # Without a connection timezone contract, MySQL TIMESTAMP comparisons are ambiguous.
            if dialect != "postgres" and kind.startswith("timestamp"):
                fail("time.field", "当前排行榜请使用明确业务时区的 DATETIME 或 epoch 时间字段。")
            if "with time zone" not in kind and kind != "timestamptz" and (time_definition.get("extra_properties") or {}).get("timezone") != settings.DASHBOARD_BUSINESS_TIMEZONE:
                fail("time.field", "无时区时间字段必须声明与业务时区一致的 timezone。")
        if parameter == "timestamp" and NUMERIC.match(kind) and dialect != "postgres":
            mysql_timezones.add(settings.DASHBOARD_BUSINESS_TIMEZONE)
        _, time_predicate, _ = _time_expression(base, time["field"], parameter, "time.field")
        for token, bound in zip(tokens, ("range_start", "range_end")):
            time_predicate = time_predicate.replace(token, f"(SELECT {bound} FROM ranking_parameter_bounds)")
        policies = []
        for policy_table, condition in (table_filters or {}).items():
            if canonical(policy_table) == table:
                errors = _filter_issues(condition, "workspace.required_filters")
                if errors:
                    fail("workspace.required_filters", "；".join(map(str, errors)))
                policies.append(base.filters(condition, "workspace.required_filters"))
        predicate = " AND ".join(f"({p})" for p in (
            f"{event_column} = {exp.Literal.string(name).sql(dialect=dialect)}", time_predicate,
            f"{entity} IS NOT NULL", base.filters(config.get("filters", {}), "filters"), *policies))
        measure = ""
        if metric["aggregation"] != "count":
            measure, definition = resolver.field(metric["metricField"], path + ".metricField")
            if metric["aggregation"] in {"sum", "avg"} and not NUMERIC.match(str(definition.get("type") or "").lower()):
                fail(path + ".metricField", "SUM/AVG 必须选择服务端元数据声明的数值属性。")
            if metric["aggregation"] in {"min", "max"} and str(definition.get("type") or "").lower().startswith("bool"):
                fail(path + ".metricField", "MIN/MAX 不支持布尔属性。")
        props = tuple(resolver.field(p, f"ranking.simultaneousProperties[{i}]")[0]
                      for i, p in enumerate(ranking.get("simultaneousProperties", []))) if index == 0 else ()
        return RankingMetricPlan(table, entity, predicate, metric["aggregation"], measure, props)

    try:
        metrics = tuple(resolve(m, i) for i, m in enumerate([ranking["metric"], *ranking.get("simultaneousMetrics", [])]))
    except (PropertyConfigurationError, FunnelConfigurationError, RetentionConfigurationError) as exc:
        raise RankingConfigurationError([RankingIssue("RANKING_INVALID_CONFIG", i.path,
            i.message.replace("属性分析仅支持同一个授权源表", "字段必须属于当前授权事件表")) for i in exc.issues]) from exc
    columns = ("rank", "ranking_entity", "ranking_value", *(f"simultaneous_metric_{i}" for i in range(1, len(metrics))),
               *(f"ranking_property_{i + 1}" for i in range(len(metrics[0].properties))))
    return RankingSqlPlan(dialect, metrics, ranking["metric"]["direction"], ranking["tieHandling"], parameter, tokens,
                          columns, settings.DASHBOARD_BUSINESS_TIMEZONE, tuple(sorted(mysql_timezones)))
