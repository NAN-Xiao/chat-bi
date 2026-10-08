"""Resolve path configuration against current authorized workspace metadata."""
from __future__ import annotations

from dataclasses import dataclass
import copy
from sqlglot import exp, parse_one

from apps.dashboard.crud.analysis_event_time import EventTimePlan, build_event_time_plan
from apps.dashboard.crud.funnel_sql_plan import _EventResolver, _filter_issues, _is_field
from apps.dashboard.crud.property_sql_plan import _Resolver, PropertyConfigurationError, NUMERIC, TEXT
from apps.dashboard.crud.interval_sql_plan import is_interval_order_type
from apps.system.crud.tracking_event_schema import _event_names, _normalized_type


@dataclass(frozen=True)
class PathIssue:
    code: str
    path: str
    message: str

    def __str__(self):
        return f"{self.path}：{self.message}"


class PathConfigurationError(ValueError):
    def __init__(self, issues):
        self.issues = tuple(issues)
        super().__init__("；".join(map(str, self.issues)))


def fail(path, message):
    raise PathConfigurationError([PathIssue("PATH_INVALID_CONFIG", path, message)])


@dataclass(frozen=True)
class PathEventPlan:
    event_name: str
    event_predicate: str
    split_expression: str
    split_property_name: str
    split_type: str


@dataclass(frozen=True)
class PathSqlPlan:
    table: str
    dialect: str
    engine: str
    entity_expression: str
    event_key_expression: str
    events: tuple[PathEventPlan, ...]
    initial_event_name: str
    time: EventTimePlan
    global_predicate: str
    mandatory_predicate: str
    order_expressions: tuple[str, ...]
    session_gap_seconds: int
    source_columns: tuple[str, ...]
    max_nodes: int = 10
    required_columns: tuple[str, ...] = ("path_source", "path_target", "path_value", "path_step")


def _typed_path_field(expression, definition, dialect, path):
    if definition.get("json_path") and dialect == "mysql":
        # JSON_UNQUOTE returns the text 'null' for JSON null on MySQL. Check
        # the original JSON encoding so the string "null" remains a string,
        # and JSON null cannot become numeric zero during the declared cast.
        tree = parse_one(expression, read=dialect)
        null_conditions = []
        for node in list(tree.walk()):
            if isinstance(node, exp.JSONExtractScalar):
                raw = exp.JSONExtract(this=node.this.copy(), expression=node.expression.copy())
            elif (isinstance(node, exp.Anonymous) and node.name.upper() == "JSON_UNQUOTE"
                  and len(node.expressions) == 1 and isinstance(node.expressions[0], exp.JSONExtract)):
                raw = node.expressions[0].copy()
            else:
                continue
            kind = exp.Anonymous(this="JSON_TYPE", expressions=[raw])
            # Inspect the JSON type, not its scalar text: casting/unquoting can
            # erase the distinction between JSON null and the string "null".
            condition = exp.or_(exp.Is(this=kind.copy(), expression=exp.Null()),
                                exp.EQ(this=kind, expression=exp.Literal.string("NULL")))
            null_conditions.append(condition)
        if null_conditions:
            # Test null before converting the JSON scalar to its declared type.
            tree = exp.Case(ifs=[exp.If(this=exp.or_(*null_conditions), true=exp.Null())], default=tree)
        expression = tree.sql(dialect=dialect)
    if definition.get("json_path") and _normalized_type(definition.get("semantic_type")) == "boolean":
        if dialect != "postgres":
            fail(path, "当前引擎尚未验证 JSON 布尔属性的原生编译能力，请使用已支持的属性类型。")
        return f"CAST({expression} AS BOOLEAN)", {**definition, "type": "boolean"}
    return expression, definition


class _PathFieldResolver(_Resolver):
    def field(self, value, path):
        return _typed_path_field(*super().field(value, path), self.dialect, path)


class _PathEventResolver(_EventResolver):
    """Validate selected declared types before generic JSON text extraction."""
    def field(self, value, path):
        name = (value.get("propertyName") or value.get("field")) if isinstance(value, dict) else None
        prop = self.properties.get(name) if isinstance(value, dict) and value.get("kind") == "tracking-property" else None
        declared = ""
        if prop:
            declared = str(prop.get("declared_type") or "").strip().lower()
            if not (NUMERIC.match(declared) or TEXT.match(declared) or declared in {
                "number", "string", "bool", "boolean", "数值", "数字", "整数", "小数", "文本", "字符串", "布尔", "布尔值"}):
                fail(path, "事件属性必须声明已支持的数值、文本或布尔标量类型。")
        # Validate the client mapping against the existing extraction first;
        # then apply the declared type for both event and workspace JSON fields.
        return _typed_path_field(*super().field(value, path), self.dialect, path)


def _identity(event):
    if not isinstance(event, dict):
        return None
    values = tuple(event.get(k) for k in ("eventTable", "eventNameField", "eventName"))
    return values if all(isinstance(v, str) and v.strip() for v in values) else None


def validate_path_input(raw: dict) -> list[PathIssue]:
    issues = []
    def add(path, message): issues.append(PathIssue("PATH_INVALID_CONFIG", path, message))
    if not isinstance(raw, dict) or not isinstance(raw.get("path"), dict):
        return [PathIssue("PATH_INVALID_CONFIG", "path", "路径配置必须为对象。")]
    p = raw["path"]
    events = p.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= 30:
        add("path.events", "需要 1 到 30 个不同的参与事件。")
        events = []
    identities = []
    for i, item in enumerate(events):
        loc = f"path.events[{i}]"
        if not isinstance(item, dict) or _identity(item.get("event")) is None:
            add(loc, "请选择具有明确来源表、事件名字段和名称的事件。")
            continue
        identities.append(_identity(item["event"]))
        properties = item.get("splitProperties", [])
        if not isinstance(properties, list) or len(properties) > 1 or any(not _is_field(v) for v in properties):
            add(loc + ".splitProperties", "每个事件最多选择一个明确的拆分属性。")
        if any(item.get(k) for k in ("filters", "eventFilters", "event_filters")):
            add(loc, "路径参与事件不支持单独筛选，请使用全局筛选。")
    if len(set(identities)) != len(identities): add("path.events", "参与事件不能重复。")
    if _identity(p.get("initialEvent")) not in identities:
        add("path.initialEvent", "初始事件必须来自参与事件，且事件来源一致。")
    gap = p.get("sessionGapSeconds")
    if type(gap) is not int or not 1 <= gap <= 86400:
        add("path.sessionGapSeconds", "会话间隔必须为 1 到 86400 的整数秒。")
    if raw.get("groups"):
        add("groups", "路径分析不支持独立分组，请在原分析模型清除分组后重新选择路径分析。")
    if any(raw.get(k) for k in ("metrics", "calculatedMetrics", "formulaMetrics", "formula_metrics", "approximate")):
        add("path", "路径分析不支持额外指标、公式或近似计算。")
    time = raw.get("time")
    if not isinstance(time, dict) or not _is_field(time.get("field")):
        add("time.field", "请选择明确的日期范围字段。")
    elif (time.get("dateParameterType") or time.get("date_parameter_type")) not in ("date", "yyyymmdd_number", "yyyymmdd_text", "timestamp"):
        add("time.dateParameterType", "日期参数类型无效。")
    chart = raw.get("chart") or {}
    if not isinstance(chart, dict) or chart.get("type", "sankey") != "sankey":
        add("chart.type", "路径分析只支持桑基图。")
    issues.extend(PathIssue("PATH_INVALID_CONFIG", i.path, i.message) for i in _filter_issues(raw.get("filters", {}), "filters"))
    return issues


def build_path_plan(config: dict, *, metadata_fields: dict, allowed_fields_by_table: dict,
                    dialect: str, engine: str, tracking_metadata, table_filters: dict,
                    business_timezone: str) -> PathSqlPlan:
    issues = validate_path_input(config)
    if issues: raise PathConfigurationError(issues)
    if dialect not in {"postgres", "mysql", "starrocks", "doris"}:
        fail("datasource", "当前数据源没有已验证的路径编译能力。")
    t = copy.deepcopy(tracking_metadata.model_dump() if hasattr(tracking_metadata, "model_dump") else tracking_metadata or {})
    def canonical(name):
        matches = [v for v in metadata_fields if v == name]
        if not matches: matches = [v for v in metadata_fields if v.split(".")[-1] == name]
        if len(matches) != 1: fail("metadata.table", "事件表不存在、未授权或存在歧义。")
        return matches[0]
    if not t.get("enabled") or not t.get("default_event_table"):
        fail("metadata", "请启用工作空间事件字典并配置默认事件表。")
    table = canonical(t["default_event_table"])
    def current(name): return name in {table, t["default_event_table"], table.split(".")[-1]}
    definitions = metadata_fields[table]
    def roles(role):
        names = {n for n, d in definitions.items() if d.get("field_role") == role}
        names.update(m.get("field") for m in t.get("field_role_mappings", [])
            if isinstance(m, dict) and current(m.get("table")) and m.get("role") == role)
        names.update(m.get("field_name") for m in t.get("fields", [])
            if isinstance(m, dict) and current(m.get("table_name")) and m.get("field_role") == role)
        return names
    subject = t.get("default_subject_field")
    if not subject or roles("subject_id") - {subject}:
        fail("metadata.default_subject_field", "请配置唯一且一致的默认主体字段。")
    physical = _PathFieldResolver(metadata_fields, allowed_fields_by_table, dialect); physical.table = table
    ref = lambda name: {"table": table, "field": name}
    try:
        entity, _ = physical.field(ref(subject), "metadata.default_subject_field")
        key_name = t.get("default_event_name_field")
        if roles("event_name") - {key_name}: fail("metadata.event_name", "事件名字段角色与默认配置冲突。")
        key, _ = physical.field(ref(key_name), "metadata.default_event_name_field")
        # Normalize table qualification only after proving that it names this authorized table.
        t["default_event_table"] = table
        time_roles = roles("event_time")
        t["field_role_mappings"] = [*t.get("field_role_mappings", []),
            *[{"table": table, "field": n, "role": "event_time"} for n in time_roles]]
        time_config = copy.deepcopy(config["time"])
        if canonical(time_config["field"]["table"]) != table: fail("time.field", "日期字段必须来自当前事件表。")
        time_config["field"]["table"] = table
        time = build_event_time_plan(table=table, time_config=time_config, metadata_fields=metadata_fields,
            allowed_fields_by_table=allowed_fields_by_table, tracking_metadata=t, dialect=dialect, engine=engine,
            business_timezone=business_timezone, parameter_cte="path_parameter_bounds", fail=fail)
        orders = []
        for role in ("event_sequence", "event_id"):
            names = roles(role)
            if len(names) > 1: fail("metadata." + role, "同一排序角色只能配置一个字段。")
            for name in names:
                expression, definition = physical.field(ref(name), "metadata." + role)
                if definition.get("json_path") or definition.get("expression") or not is_interval_order_type(definition.get("type", "")):
                    fail("metadata." + role, "排序字段必须是物理整数或文本字段。")
                if expression not in orders: orders.append(expression)
        events, resolvers = [], {}
        columns = set(physical.columns)
        for i, item in enumerate(config["path"]["events"]):
            ev = item["event"]; name = ev["eventName"]; loc = f"path.events[{i}]"
            if canonical(ev["eventTable"]) != table or ev["eventNameField"] != key_name:
                fail(loc, "参与事件必须使用当前工作空间默认事件表及事件名字段。")
            mappings = [m for m in t.get("event_name_mappings", []) if name in _event_names(m)]
            if len(mappings) != 1: fail(loc, "事件不存在或事件字典定义不唯一。")
            m = mappings[0]
            if canonical(m.get("event_table") or m.get("table") or table) != table or (m.get("event_name_field") or key_name) != key_name:
                fail(loc, "事件来源与工作空间字典不一致。")
            properties = {}
            for prop in m.get("properties", []):
                prop_name = prop.get("property_name") or prop.get("field_name") or prop.get("name")
                if not prop_name: continue
                if prop_name in properties: fail(loc, "事件属性名称重复。")
                declared = prop.get("property_type") or prop.get("semantic_type") or prop.get("field_type") or prop.get("type")
                kind = _normalized_type(declared)
                properties[prop_name] = {**prop, "declared_type": declared, "semantic_type": kind, "type": kind}
            resolver = _PathEventResolver(metadata_fields, allowed_fields_by_table, dialect, table, name, properties)
            resolver.table = table; resolvers[name] = resolver
            split, prop_name, kind = "", "", ""
            for prop in item.get("splitProperties", []):
                if prop.get("eventName") and prop["eventName"] != name: fail(loc, "拆分属性不属于当前事件。")
                split, definition = resolver.field(prop, loc + ".splitProperties[0]")
                kind = definition.get("type", "").lower()
                if not (NUMERIC.match(kind) or TEXT.match(kind) or kind in {"bool", "boolean"}):
                    fail(loc, "拆分属性必须是数值、文本或布尔标量。")
                prop_name = prop.get("propertyName") or prop["field"]
            events.append(PathEventPlan(name, f"{key} = {exp.Literal.string(name).sql(dialect=dialect)}", split, prop_name, kind))
            columns.update(resolver.columns)

        def filters(value, path):
            if not value: return "TRUE"
            group = "children" if value.get("type") == "group" else "rules"
            if group in value:
                parts = [filters(v, f"{path}.{group}[{i}]") for i, v in enumerate(value[group])]
                return (" " + value.get("logic", "and").upper() + " ").join(f"({v})" for v in parts) or "TRUE"
            f = value["field"]
            if f.get("kind") == "tracking-property":
                owner = f.get("eventName")
                if owner not in resolvers: fail(path, "筛选属性必须属于当前参与事件。")
                result = resolvers[owner].filters(value, path)
                columns.update(resolvers[owner].columns)
                return f"({key} = {exp.Literal.string(owner).sql(dialect=dialect)} AND ({result}))"
            return physical.filters(value, path)
        global_filter = filters(config.get("filters", {}), "filters")
        mandatory = []
        for policy_table, rules in table_filters.items():
            if canonical(policy_table) != table: fail("metadata.table_filters", "强制筛选属于其他事件表。")
            problems = _filter_issues(rules, "metadata.table_filters")
            if problems: raise PathConfigurationError([PathIssue("PATH_INVALID_CONFIG", p.path, p.message) for p in problems])
            mandatory.append(physical.filters(rules, "metadata.table_filters"))
        columns.update(physical.columns)
        return PathSqlPlan(table, dialect, engine, entity, key, tuple(events), config["path"]["initialEvent"]["eventName"],
            time, global_filter, " AND ".join(f"({v})" for v in mandatory) or "TRUE", tuple(orders),
            config["path"]["sessionGapSeconds"], tuple(sorted(columns)))
    except PropertyConfigurationError as exc:
        raise PathConfigurationError([PathIssue("PATH_INVALID_CONFIG", p.path, p.message) for p in exc.issues]) from exc
