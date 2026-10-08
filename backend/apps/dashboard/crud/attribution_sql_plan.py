"""Resolve attribution configuration exclusively against authorized metadata."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from sqlglot import exp, parse_one
from apps.dashboard.crud.analysis_event_time import EventTimePlan, build_event_time_plan
from apps.dashboard.crud.funnel_sql_plan import _EventResolver, _filter_issues, _is_field, FunnelConfigurationError
from apps.dashboard.crud.property_sql_plan import _Resolver, NUMERIC, TEXT, PropertyConfigurationError
from apps.dashboard.crud.interval_sql_plan import is_interval_order_type
from apps.dashboard.crud.attribution_rules import ATTRIBUTION_METRIC_COLUMNS
from apps.system.crud.tracking_event_schema import _event_names, _normalized_type


@dataclass(frozen=True)
class AttributionIssue:
    code: str
    path: str
    message: str

    def __str__(self):
        return f"{self.path}：{self.message}"


class AttributionConfigurationError(ValueError):
    def __init__(self, issues):
        self.issues = tuple(issues)
        super().__init__("；".join(map(str, self.issues)))


def fail(path, message):
    raise AttributionConfigurationError([AttributionIssue("ATTRIBUTION_INVALID_CONFIG", path, message)])


def _typed_json(expression, definition, dialect, path):
    if not definition.get('json_path'): return expression, definition
    if _normalized_type(definition.get('semantic_type')) == 'boolean':
        if dialect != 'postgres': fail(path, '当前引擎尚未验证 JSON 布尔属性能力。')
        return f'CAST({expression} AS BOOLEAN)', {**definition,'type':'boolean'}
    if dialect == 'mysql':
        tree = parse_one(expression,read=dialect)
        conditions = []
        for node in list(tree.walk()):
            raw = None
            if isinstance(node,exp.JSONExtractScalar):
                raw = exp.JSONExtract(this=node.this.copy(),expression=node.expression.copy())
            elif isinstance(node,exp.Anonymous) and node.name.upper() == 'JSON_UNQUOTE' and len(node.expressions) == 1 and isinstance(node.expressions[0],exp.JSONExtract):
                raw = node.expressions[0].copy()
            if raw is not None:
                kind = exp.Anonymous(this='JSON_TYPE',expressions=[raw])
                conditions.append(exp.or_(exp.Is(this=kind.copy(),expression=exp.Null()),exp.EQ(this=kind,expression=exp.Literal.string('NULL'))))
        if conditions:
            tree = exp.Case(ifs=[exp.If(this=exp.or_(*conditions),true=exp.Null())],default=tree)
        expression = tree.sql(dialect=dialect)
    return expression, definition


class _AttributionResolver(_Resolver):
    def field(self,value,path):
        return _typed_json(*super().field(value,path),self.dialect,path)


class _AttributionEventResolver(_EventResolver):
    def field(self,value,path):
        return _typed_json(*super().field(value,path),self.dialect,path)


@dataclass(frozen=True)
class AttributionEventPlan:
    name: str
    predicate: str
    groups: tuple[str, ...]
    related_target: str = ""
    related_touch: str = ""


@dataclass(frozen=True)
class AttributionSqlPlan:
    table: str
    dialect: str
    time: EventTimePlan
    range_field: str
    entity: str
    target: AttributionEventPlan
    touches: tuple[AttributionEventPlan, ...]
    metric: str
    aggregation: str
    method: str
    window_mode: str
    window_seconds: int
    include_direct: bool
    group_sides: tuple[str, ...]
    orders: tuple[str, ...]
    required_columns: tuple[str, ...]


def validate_attribution_input(raw):
    issues = []
    def add(path, message): issues.append(AttributionIssue("ATTRIBUTION_INVALID_CONFIG", path, message))
    if not isinstance(raw, dict) or not isinstance(raw.get("attribution"), dict):
        return [AttributionIssue("ATTRIBUTION_INVALID_CONFIG", "attribution", "归因配置必须为对象。")]
    a = raw["attribution"]
    if not _is_field(a.get("entityField")): add("attribution.entityField", "请选择分析主体字段。")
    if a.get("method") not in ("first", "last", "linear"): add("attribution.method", "归因方式必须是首次、末次或线性。")
    if type(a.get("includeDirect")) is not bool: add("attribution.includeDirect", "直接转化开关必须是布尔值。")
    window = a.get("window")
    if not isinstance(window, dict) or window.get("mode") not in ("same_day", "duration"):
        add("attribution.window", "请选择当天或时长窗口。")
    elif window["mode"] == "duration":
        factor = {"day":86400, "hour":3600, "minute":60}.get(window.get("unit")) if isinstance(window.get("unit"), str) else None
        if type(window.get("value")) is not int or not factor or not 60 <= window["value"] * factor <= 365 * 86400:
            add("attribution.window", "时长必须为整数，范围为 1 分钟至 365 天。")
    metric = a.get("targetMetric")
    if not isinstance(metric, dict) or metric.get("aggregation") not in ("count", "sum", "avg", "max", "min", "count_distinct"):
        add("attribution.targetMetric", "目标指标聚合无效。")
    else:
        if metric["aggregation"] != "count" and not _is_field(metric.get("metricField")):
            add("attribution.targetMetric.metricField", "非次数指标必须指定字段。")
        if a.get("method") == "linear" and metric["aggregation"] not in ("count", "sum"):
            add("attribution.targetMetric.aggregation", "线性归因仅支持次数和求和；均值、极值及去重数没有配置分摊口径，请选择首次/末次归因。")
    touches = a.get("events")
    if not isinstance(touches, list) or not 1 <= len(touches) <= 20:
        add("attribution.events", "请选择 1 至 20 个归因事件。")
        touches = []
    identities = []
    for path, event in [("attribution.targetEvent", a.get("targetEvent")), *[(f"attribution.events[{i}].event", v.get("event") if isinstance(v, dict) else None) for i,v in enumerate(touches)]]:
        if not isinstance(event, dict) or not all(isinstance(event.get(k), str) and event[k].strip() for k in ("eventTable", "eventNameField", "eventName")):
            add(path, "事件需要明确来源表、事件名字段和名称。")
        elif path != "attribution.targetEvent": identities.append(tuple(event[k] for k in ("eventTable", "eventNameField", "eventName")))
    if len(set(identities)) != len(identities): add("attribution.events", "归因事件不能重复。")
    for i, item in enumerate(touches):
        path = f"attribution.events[{i}]"
        if not isinstance(item, dict): continue
        rel = item.get("relatedProperty", {"enabled":False})
        if not isinstance(rel, dict) or type(rel.get("enabled")) is not bool:
            add(path + ".relatedProperty", "关联属性开关必须为布尔值。")
        elif rel["enabled"] and (not _is_field(rel.get("targetProperty")) or not _is_field(rel.get("touchProperty"))):
            add(path + ".relatedProperty", "启用关联属性时必须指定目标和触点属性。")
        issues.extend(AttributionIssue("ATTRIBUTION_INVALID_CONFIG", x.path, x.message) for x in _filter_issues(item.get("filters", {}), path + ".filters"))
    for key, value in (("filters", raw.get("filters", {})), ("attribution.targetEventFilters", a.get("targetEventFilters", {}))):
        issues.extend(AttributionIssue("ATTRIBUTION_INVALID_CONFIG", x.path, x.message) for x in _filter_issues(value, key))
    groups = raw.get("groups", [])
    if not isinstance(groups, list) or any(not _is_field(g) or g.get("attributionSide") not in (None, "", "target", "touch") for g in groups):
        add("groups", "分组必须是授权字段，归属只能是目标或触点。")
    if not isinstance(raw.get("time"), dict) or not _is_field(raw["time"].get("field")):
        add("time.field", "请选择明确的日期范围字段。")
    if isinstance(raw.get("chart"), dict) and raw["chart"].get("type", "table") != "table": add("chart.type", "归因分析仅输出归因表。")
    if any(raw.get(k) for k in ("formulaMetrics", "formula_metrics", "calculatedMetrics", "approximate")):
        add("attribution", "归因分析不支持附加公式或近似计算。")
    return issues


def build_attribution_plan(config, *, metadata_fields, allowed_fields_by_table, tracking_metadata,
                           table_filters, dialect, engine, business_timezone):
    issues = validate_attribution_input(config)
    if issues: raise AttributionConfigurationError(issues)
    if dialect not in {"postgres", "mysql"}: fail("datasource", "归因编译当前支持 PostgreSQL 和 MySQL。")
    # Non-native MySQL engines require their own verified time/window support.
    if any(n in engine.lower() for n in ("doris", "starrocks")):
        fail("datasource", "当前引擎尚未验证归因时间与窗口能力。")
    tracking = copy.deepcopy(tracking_metadata.model_dump() if hasattr(tracking_metadata, "model_dump") else tracking_metadata or {})
    if not tracking.get("enabled"): fail("metadata", "请启用当前工作空间事件字典。")
    def canonical(name):
        matches = [t for t in metadata_fields if t == name]
        if not matches: matches = [t for t in metadata_fields if t.split(".")[-1] == name]
        if len(matches) != 1: fail("metadata.table", "事件表不存在、未授权或表名存在歧义。")
        return matches[0]
    a = config["attribution"]
    table = canonical(a["targetEvent"]["eventTable"])
    def current(name): return name in {table, table.split(".")[-1]}
    tracking["default_event_table"] = canonical(tracking.get("default_event_table"))
    if tracking["default_event_table"] != table: fail("attribution.targetEvent", "事件必须属于当前工作空间事件表。")
    for role in tracking.get("field_role_mappings", []):
        if current(role.get("table")): role["table"] = table
    for item in tracking.get("fields", []):
        if current(item.get("table_name")) and item.get("field_role"):
            tracking.setdefault("field_role_mappings", []).append({"table":table,"field":item.get("field_name"),"role":item["field_role"]})
    time_config = copy.deepcopy(config["time"])
    if canonical(time_config["field"]["table"]) != table: fail("time.field", "日期字段必须属于事件表。")
    time_config["field"]["table"] = table
    sides = tuple("touch" if g.get("attributionSide") == "touch" else "target" for g in config.get("groups", []))
    try:
        physical = _AttributionResolver(metadata_fields, allowed_fields_by_table, dialect); physical.table = table
        entity, _ = physical.field(a["entityField"], "attribution.entityField")
        range_field, _ = physical.field(time_config['field'], 'time.field')
        time = build_event_time_plan(table=table, time_config=time_config, metadata_fields=metadata_fields,
            allowed_fields_by_table=allowed_fields_by_table, tracking_metadata=tracking, dialect=dialect, engine=engine,
            business_timezone=business_timezone, parameter_cte="attribution_parameter_bounds", fail=fail)
        # Avoid unverified connection-session requirements on the public execution path.
        if dialect == "mysql":
            if time.naive_timezones or time.mysql_utc or time.parameter_type == "timestamp":
                fail("metadata.event_time", "MySQL 归因需要明确编码的 epoch 秒/毫秒事件时间及自然日日期字段。")
            from dataclasses import replace
            time = replace(time, mysql_timezones=(business_timezone,))
        orders = []
        for role in ("event_sequence", "event_id"):
            names = {k for k,v in metadata_fields[table].items() if v.get("field_role") == role}
            names.update(m.get("field") for m in tracking.get("field_role_mappings", []) if m.get("table") == table and m.get("role") == role)
            if len(names) > 1: fail("metadata." + role, "同一稳定排序角色只能指定一个字段。")
            for name in sorted(names):
                expression, definition = physical.field({"table":table,"field":name}, "metadata." + role)
                if definition.get("json_path") or definition.get("expression") or not is_interval_order_type(definition.get("type", "")):
                    fail("metadata." + role, "稳定排序必须使用物理整数或文本字段。")
                if expression not in orders: orders.append(expression)
        if a["method"] in {"first", "last"} and not orders:
            fail("metadata.event_id", "首次/末次需要 event_id 或 event_sequence 稳定排序字段以处理同时间触点。")

        def resolver(event, path):
            name = event["eventName"]
            if canonical(event["eventTable"]) != table: fail(path, "当前归因编译要求同一事件表，不能猜测跨表角色映射。")
            mappings = [m for m in tracking.get("event_name_mappings", []) if name in _event_names(m)]
            if len(mappings) != 1: fail(path, "事件必须在当前工作空间字典中存在且定义唯一。")
            m = mappings[0]
            key = m.get("event_name_field") or tracking.get("default_event_name_field")
            if canonical(m.get("event_table") or m.get("table") or table) != table or event["eventNameField"] != key:
                fail(path, "事件来源与当前工作空间字典不一致。")
            properties = {}
            for prop in m.get("properties", []):
                pname = prop.get("property_name") or prop.get("field_name") or prop.get("name")
                if not pname or pname in properties: fail(path, "事件参数名称缺失或重复。")
                host = prop.get("source_field")
                semantic = _normalized_type(prop.get("property_type") or prop.get("semantic_type") or prop.get("type"))
                properties[pname] = {**prop, "semantic_type":semantic, "type": semantic if prop.get("json_path") else metadata_fields[table].get(host, {}).get("type", "")}
            r = _AttributionEventResolver(metadata_fields, allowed_fields_by_table, dialect, table, name, properties)
            return r, physical.field({"table":table,"field":key}, path + ".eventNameField")[0]

        def checked(r, value, path):
            if value.get("eventName") and value["eventName"] != r.event_name: fail(path, "属性不属于当前事件。")
            expression, definition = r.field(value, path)
            if definition.get("json_path"):
                kind = metadata_fields[table].get(definition.get("source_field"), {}).get("type", "")
                if not kind.startswith(("json", "text", "varchar", "char")): fail(path, "JSON 属性需要已授权的 JSON 或文本来源列。")
            return expression, definition

        target_resolver, key = resolver(a["targetEvent"], "attribution.targetEvent")
        metric = "1"
        aggregation = a["targetMetric"]["aggregation"]
        if aggregation != "count":
            metric, definition = checked(target_resolver, a["targetMetric"]["metricField"], "attribution.targetMetric.metricField")
            if aggregation in {"sum", "avg", "max", "min"} and not NUMERIC.match(definition.get("type", "")):
                fail("attribution.targetMetric.metricField", "所选聚合需要服务端元数据声明的数值字段。")
        def event_plan(r, event_key, event_filters, side):
            policies = []
            for t, filters in (table_filters or {}).items():
                if canonical(t) != table: continue
                errors = _filter_issues(filters, "workspace.required_filters")
                if errors: fail("workspace.required_filters", "；".join(map(str, errors)))
                policies.append(r.filters(filters, "workspace.required_filters"))
            conditions = [f"{event_key} = {exp.Literal.string(r.event_name).sql(dialect=dialect)}",
                f"{entity} IS NOT NULL", r.filters(config.get("filters", {}), "filters"), r.filters(event_filters, "event.filters"), *policies]
            groups = tuple(checked(r, g, f"groups[{i}]")[0] if sides[i] == side else "NULL" for i,g in enumerate(config.get("groups", [])))
            return AttributionEventPlan(r.event_name, " AND ".join(f"({v})" for v in conditions), groups)
        target = event_plan(target_resolver, key, a.get("targetEventFilters", {}), "target")
        touches = []
        from dataclasses import replace
        for i, item in enumerate(a["events"]):
            loc = f"attribution.events[{i}]"
            r, k = resolver(item["event"], loc + ".event")
            touch = event_plan(r, k, item.get("filters", {}), "touch")
            rel = item.get("relatedProperty", {})
            if rel.get("enabled"):
                left, ld = checked(target_resolver, rel["targetProperty"], loc + ".relatedProperty.targetProperty")
                right, rd = checked(r, rel["touchProperty"], loc + ".relatedProperty.touchProperty")
                def family(definition):
                    kind = str(definition.get("type") or "").lower()
                    if NUMERIC.match(kind): return "numeric"
                    if TEXT.match(kind): return "text"
                    if kind in {"boolean", "bool"}: return "boolean"
                    if kind == "date": return "date"
                    if kind.startswith(("timestamp", "datetime")): return kind
                    return None
                if not family(ld) or family(ld) != family(rd): fail(loc + ".relatedProperty", "目标和触点关联属性 SQL 类型不兼容。")
                touch = replace(touch, related_target=left, related_touch=right)
            touches.append(touch)
    except (PropertyConfigurationError, FunnelConfigurationError) as exc:
        raise AttributionConfigurationError([AttributionIssue("ATTRIBUTION_INVALID_CONFIG", i.path, i.message) for i in exc.issues]) from exc
    seconds = 0 if a["window"]["mode"] == "same_day" else a["window"]["value"] * {"day":86400,"hour":3600,"minute":60}[a["window"]["unit"]]
    columns = (*(f"group_{i+1}" for i in range(len(sides))), "attribution_event", "target_count", *ATTRIBUTION_METRIC_COLUMNS)
    return AttributionSqlPlan(table, dialect, time, range_field, entity, target, tuple(touches), metric, aggregation,
        a["method"], a["window"]["mode"], seconds, a["includeDirect"], sides, tuple(orders), columns)
