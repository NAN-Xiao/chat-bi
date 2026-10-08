"""Resolve funnel configuration exclusively against authorized workspace metadata."""
from __future__ import annotations

from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlglot import exp

from apps.dashboard.crud.property_sql_plan import _Resolver, NUMERIC, OPERATORS, PropertyConfigurationError
from apps.dashboard.crud.retention_sql_plan import _time_expression, RetentionConfigurationError
from apps.system.crud.tracking_event_schema import _event_names, _normalized_type


@dataclass(frozen=True)
class FunnelIssue:
    code: str
    path: str
    message: str

    def __str__(self):
        return f"{self.path}：{self.message}"


class FunnelConfigurationError(ValueError):
    def __init__(self, issues):
        self.issues = tuple(issues)
        super().__init__("；".join(map(str, self.issues)))


def fail(path, message):
    raise FunnelConfigurationError([FunnelIssue("FUNNEL_INVALID_CONFIG", path, message)])


@dataclass(frozen=True)
class FunnelStepPlan:
    order: int
    label: str
    table: str
    entity: str
    time: str  # exact UTC elapsed seconds, not integer-truncated
    time_day: str  # business-local calendar date
    time_encoding: str
    related: str
    predicate: str


@dataclass(frozen=True)
class FunnelSqlPlan:
    dialect: str
    engine: str
    steps: tuple[FunnelStepPlan, ...]
    window_mode: str
    window_seconds: int
    timezone: str
    related_enabled: bool
    required_columns: tuple[str, ...] = (
        "step_order", "step_name", "step_count", "step_rate", "step_conversion_rate", "step_dropoff_rate",
    )


def funnel_window(funnel):
    """Only the documented day-only legacy shape may migrate, never a present invalid window."""
    if "window" in funnel:
        return funnel["window"]
    for key in ("windowDays", "window_days"):
        if key in funnel:
            return {"mode": "duration", "value": funnel[key], "unit": "day"}
    return None


def _filter_issues(value, path, *, nested=False, depth=0):
    def issue(message):
        return [FunnelIssue("FUNNEL_INVALID_CONFIG", path, message)]
    if not isinstance(value, dict) or depth > 20:
        return issue("筛选必须为有效的结构化条件，嵌套不能超过 20 层。")
    if not value and not nested:
        return []
    key = "children" if value.get("type") == "group" else "rules"
    if key in value:
        children = value[key]
        if value.get("logic", "and") not in ("and", "or") or not isinstance(children, list) or (nested and not children):
            return issue("筛选组需要 AND/OR 和有效条件列表。")
        return [i for n, child in enumerate(children)
                for i in _filter_issues(child, f"{path}.{key}[{n}]", nested=True, depth=depth + 1)]
    if value.get("type") == "group" or not _is_field(value.get("field")):
        return issue("筛选条件缺少有效字段或子条件。")
    op = value.get("operator")
    if not isinstance(op, str) or op not in OPERATORS:
        return issue("筛选操作符无效。")
    if op not in {"is_null", "is_not_null"} and value.get("value") in (None, ""):
        return issue("筛选值不能为空。")
    return []


def _is_field(value):
    return isinstance(value, dict) and all(isinstance(value.get(k), str) and value[k].strip() for k in ("table", "field"))


class _EventResolver(_Resolver):
    """Physical columns and event-local parameters have separate identities."""
    def __init__(self, metadata, allowed, dialect, table, event_name, properties):
        super().__init__(metadata, allowed, dialect)
        self.table, self.event_name, self.properties = table, event_name, properties

    def field(self, value, path):
        if not isinstance(value, dict):
            return super().field(value, path)
        name = value.get("propertyName") or value.get("field")
        is_parameter = value.get("kind") == "tracking-property"
        # Minimal server/config references can resolve a unique virtual name,
        # but a physical name is never shadowed by an event parameter.
        if not is_parameter and value.get("field") in self.metadata[self.table]:
            return super().field(value, path)
        if name not in self.properties:
            if is_parameter:
                fail(path, "所选事件参数不属于当前事件字典。")
            return super().field(value, path)
        if value.get("eventName") and value["eventName"] != self.event_name:
            fail(path, "事件参数只能用于其明确配置的事件。")
        metadata = {**self.metadata, self.table: {**self.metadata[self.table], value.get("field"): self.properties[name]}}
        resolver = _Resolver(metadata, self.allowed, self.dialect)
        resolver.table = self.table
        return resolver.field(value, path)


def validate_funnel_input(raw: dict) -> list[FunnelIssue]:
    issues = []
    def add(path, message):
        issues.append(FunnelIssue("FUNNEL_INVALID_CONFIG", path, message))
    if not isinstance(raw, dict) or not isinstance(raw.get("funnel"), dict):
        return [FunnelIssue("FUNNEL_INVALID_CONFIG", "funnel", "漏斗配置必须为对象。")]
    f = raw["funnel"]
    # Undocumented aliases must not be silently discarded by normalization.
    if any(k in f for k in ("entity_field", "related_property", "related_property_enabled")):
        add("funnel", "请使用 entityField、relatedProperty、relatedPropertyEnabled 配置字段。")
    if not _is_field(f.get("entityField")):
        add("funnel.entityField", "请选择明确的分析主体字段。")
    if not isinstance(raw.get("time"), dict) or not _is_field(raw["time"].get("field")):
        add("time.field", "请选择看板范围字段。")
    if "relatedPropertyEnabled" in f and not isinstance(f["relatedPropertyEnabled"], bool):
        add("funnel.relatedPropertyEnabled", "关联属性开关必须为布尔值。")
    window = funnel_window(f)
    if not isinstance(window, dict) or window.get("mode") not in ("same_day", "duration"):
        add("funnel.window", "请选择有效的当天或时长窗口。")
    elif window["mode"] == "duration":
        value, unit = window.get("value"), window.get("unit")
        factor = {"day": 86400, "hour": 3600, "minute": 60}.get(unit) if isinstance(unit, str) else None
        if type(value) is not int or factor is None or not 1 <= value * factor <= 365 * 86400:
            add("funnel.window", "时长必须为正整数，单位为天/小时/分钟，且不超过 365 天。")
    steps = f.get("steps")
    if not isinstance(steps, list) or not 2 <= len(steps) <= 10:
        add("funnel.steps", "漏斗必须配置 2 至 10 个步骤。")
    for n, step in enumerate(steps if isinstance(steps, list) else []):
        path = f"funnel.steps[{n}]"
        if not isinstance(step, dict):
            add(path, "步骤必须为有效对象。")
            continue
        e = step.get("event")
        if not isinstance(e, dict) or not all(isinstance(e.get(k), str) and e[k].strip() for k in ("eventTable", "eventNameField", "eventName")):
            add(path + ".event", "请配置事件来源表、事件名字段和事件名称。")
        if "alias" in step and not isinstance(step["alias"], str):
            add(path + ".alias", "步骤显示名称必须为文本。")
        if f.get("relatedPropertyEnabled") is True:
            related = f["relatedProperty"] if "relatedProperty" in f else step.get("relatedProperty", step.get("related_property"))
            if not _is_field(related):
                add(path + ".relatedProperty", "请选择有效的关联属性。")
        issues.extend(_filter_issues(step.get("filters", {}), path + ".filters"))
    issues.extend(_filter_issues(raw.get("filters", {}), "filters"))
    if raw.get("groups"):
        add("groups", "漏斗固定步骤结果不支持普通维度分组，请移除分组配置。")
    if raw.get("calculatedMetrics") or raw.get("formulaMetrics") or raw.get("formula_metrics"):
        add("calculatedMetrics", "漏斗不支持公式指标。")
    if raw.get("approximate") not in (None, False):
        add("approximate", "漏斗主体计数不支持近似模式。")
    return issues


def build_funnel_plan(config: dict, *, metadata_fields: dict, allowed_fields_by_table: dict,
                      tracking_metadata, table_filters: dict, dialect: str, engine: str) -> FunnelSqlPlan:
    issues = validate_funnel_input(config)
    if issues:
        raise FunnelConfigurationError(issues)
    if dialect not in {"postgres", "mysql", "starrocks", "doris"}:
        fail("datasource", f"当前方言 {dialect} 未提供漏斗编译能力。")
    from common.core.config import settings
    timezone = settings.DASHBOARD_BUSINESS_TIMEZONE
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        fail("metadata.timezone", "业务时区配置无效。")
    tracking = tracking_metadata.model_dump() if hasattr(tracking_metadata, "model_dump") else (tracking_metadata or {})
    def canonical(name):
        matches = [t for t in metadata_fields if t == name]
        if not matches:
            matches = [t for t in metadata_fields if t.split(".")[-1] == name]
        if len(matches) != 1:
            fail("metadata.table", "事件表不存在、未授权或表名存在歧义。")
        return matches[0]
    if not tracking.get("enabled") or not tracking.get("default_event_table"):
        fail("metadata", "请先启用工作空间事件字典并配置默认事件表。")
    table = canonical(tracking["default_event_table"])
    def is_current_table(name):
        return isinstance(name, str) and (name == table or name == tracking["default_event_table"]
            or ("." not in name and name == table.split(".")[-1]))
    f = config["funnel"]
    definitions = metadata_fields[table]
    candidates = {name for name, definition in definitions.items() if definition.get("field_role") == "event_time"}
    for item in tracking.get("field_role_mappings", []):
        if item.get("role") == "event_time" and is_current_table(item.get("table")):
            candidates.add(item.get("field"))
    for item in tracking.get("fields", []):
        if item.get("field_role") == "event_time" and is_current_table(item.get("table_name")):
            candidates.add(item.get("field_name"))
    if tracking.get("default_event_time_field"):
        candidates.add(tracking["default_event_time_field"])
    if len(candidates) != 1 or next(iter(candidates)) not in definitions:
        fail("metadata.event_time", "需要唯一且已授权的 event_time 字段映射。")
    time_name = next(iter(candidates))
    time_definition = definitions[time_name]
    if time_definition.get("json_path") or time_definition.get("expression"):
        fail("metadata.event_time", "步骤时间需要明确的物理时间字段。")
    kind = str(time_definition.get("type") or "").lower()
    extra = time_definition.get("extra_properties") or {}
    encoding = extra.get("encoding")
    if NUMERIC.match(kind):
        if encoding not in {"epoch_seconds", "epoch_milliseconds"}:
            fail("metadata.event_time", "数值时间必须声明 epoch_seconds 或 epoch_milliseconds。")
    elif kind.startswith(("timestamp", "datetime")):
        if encoding not in (None, "datetime", "timestamp"):
            fail("metadata.event_time", "时间编码与字段类型冲突。")
        encoding = "timestamptz" if kind == "timestamptz" or "with time zone" in kind else "datetime"
        if encoding == "datetime" and extra.get("timezone") != timezone:
            fail("metadata.event_time", "无时区时间必须声明与业务时区一致的 timezone。")
        if encoding == "timestamptz" and dialect != "postgres":
            fail("metadata.event_time", "当前方言不支持带时区时间字段。")
    else:
        fail("metadata.event_time", "步骤时间必须为实际时间戳，不能用日期分区代替。")
    zone = exp.Literal.string(timezone).sql(dialect=dialect)
    steps = []
    related_types = set()
    root_related = f.get("relatedProperty")
    related_parameter = isinstance(root_related, dict) and root_related.get("kind") == "tracking-property"
    if related_parameter and root_related.get("eventName") not in {s["event"]["eventName"] for s in f["steps"]}:
        fail("funnel.relatedProperty", "关联参数必须来自当前步骤中的事件。")
    try:
        for index, step in enumerate(f["steps"]):
            path = f"funnel.steps[{index}]"
            event = step["event"]
            if canonical(event["eventTable"]) != table:
                fail(path + ".event", "漏斗事件必须属于当前工作空间默认事件表。")
            name = event["eventName"]
            mappings = [m for m in tracking.get("event_name_mappings", []) if name in _event_names(m)]
            if len(mappings) != 1:
                fail(path + ".event", "事件已不存在或事件字典定义不唯一。")
            mapping = mappings[0]
            if canonical(mapping.get("event_table") or mapping.get("table") or tracking["default_event_table"]) != table or (
                mapping.get("event_name_field") or tracking.get("default_event_name_field")) != event["eventNameField"]:
                fail(path + ".event", "事件来源与工作空间字典不一致。")
            properties = {}
            for prop in mapping.get("properties", []):
                key = prop.get("property_name") or prop.get("field_name") or prop.get("name")
                host, json_path = prop.get("source_field"), prop.get("json_path")
                if key and host in definitions and json_path:
                    semantic_type = _normalized_type(prop.get("property_type") or prop.get("semantic_type") or prop.get("field_type") or prop.get("type"))
                    if key in properties:
                        fail(path + ".event", "同一事件内参数名称重复，无法唯一解析。")
                    properties[key] = {**prop, "semantic_type": semantic_type, "type": semantic_type}
            resolver = _EventResolver(metadata_fields, allowed_fields_by_table, dialect, table, name, properties)
            physical = _Resolver(metadata_fields, allowed_fields_by_table, dialect)
            physical.table = table
            resolver.table = table
            entity, _ = resolver.field(f["entityField"], "funnel.entityField")
            event_column, _ = physical.field({"table": table, "field": event["eventNameField"]}, path + ".event")
            time, _ = physical.field({"table": table, "field": time_name}, "metadata.event_time")
            if encoding in {"epoch_seconds", "epoch_milliseconds"}:
                seconds = time if encoding == "epoch_seconds" else f"({time} / 1000.0)"
                if dialect == "postgres":
                    day = f"CAST(TO_TIMESTAMP({seconds}) AT TIME ZONE {zone} AS DATE)"
                else:
                    day = f"CAST(CONVERT_TZ(TIMESTAMPADD(SECOND, FLOOR({seconds}), CAST('1970-01-01 00:00:00' AS DATETIME)), '+00:00', {zone}) AS DATE)"
            elif dialect == "postgres":
                instant = time if encoding == "timestamptz" else f"({time} AT TIME ZONE {zone})"
                seconds = f"EXTRACT(EPOCH FROM {instant})"
                day = f"CAST({time} AT TIME ZONE {zone} AS DATE)" if encoding == "timestamptz" else f"CAST({time} AS DATE)"
            else:
                seconds = f"(TIMESTAMPDIFF(MICROSECOND, CAST('1970-01-01 00:00:00' AS DATETIME), CONVERT_TZ({time}, {zone}, '+00:00')) / 1000000.0)"
                day = f"CAST({time} AS DATE)"
            parameter_type = config["time"].get("date_parameter_type") or config["time"].get("dateParameterType")
            _, time_predicate, _ = _time_expression(physical, config["time"]["field"], parameter_type, "time.field")
            related = ""
            if f.get("relatedPropertyEnabled"):
                value = f["relatedProperty"] if "relatedProperty" in f else step.get("relatedProperty", step.get("related_property"))
                if related_parameter and value.get("eventName") != name:
                    # Root selects one logical event parameter. Its original
                    # mapping is validated on the anchor step; other steps use
                    # their own explicit dictionary mapping for that parameter.
                    value = {"table": value["table"], "field": value["field"],
                             "propertyName": value.get("propertyName") or value["field"],
                             "kind": "tracking-property", "eventName": name}
                related, definition = resolver.field(value, path + ".relatedProperty")
                related_types.add("number" if NUMERIC.match(str(definition.get("type"))) else str(definition.get("type")))
            predicates = [f"{event_column} = {exp.Literal.string(name).sql(dialect=dialect)}", time_predicate,
                          f"{entity} IS NOT NULL", f"{time} IS NOT NULL",
                          resolver.filters(config.get("filters", {}), "filters"),
                          resolver.filters(step.get("filters", {}), path + ".filters")]
            for policy_table, policy in table_filters.items():
                if canonical(policy_table) == table:
                    policy_issues = _filter_issues(policy, "workspace.required_filters")
                    if policy_issues:
                        raise FunnelConfigurationError(policy_issues)
                    predicates.append(physical.filters(policy, "workspace.required_filters"))
            steps.append(FunnelStepPlan(index + 1, step.get("alias", "").strip() or name, table, entity,
                                       seconds, day, encoding, related, " AND ".join(f"({p})" for p in predicates)))
    except (PropertyConfigurationError, RetentionConfigurationError) as exc:
        raise FunnelConfigurationError([FunnelIssue("FUNNEL_INVALID_CONFIG", i.path,
            i.message.replace("属性分析仅支持同一个授权源表", "漏斗字段必须属于当前默认事件表")) for i in exc.issues]) from exc
    if len(related_types) > 1:
        fail("funnel.relatedProperty", "各步骤关联属性类型必须一致，不能通过隐式转换关联。")
    window = funnel_window(f)
    seconds = window["value"] * {"day": 86400, "hour": 3600, "minute": 60}[window["unit"]] if window["mode"] == "duration" else 0
    return FunnelSqlPlan(dialect, engine, tuple(steps), window["mode"], seconds, timezone, f.get("relatedPropertyEnabled") is True)
