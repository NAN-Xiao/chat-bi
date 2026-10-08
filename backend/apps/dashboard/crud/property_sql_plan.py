"""Resolve property analysis against authorized metadata, without model inference."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import sqlglot
from sqlglot import exp

from apps.dashboard.crud.dashboard_date_filter import dashboard_date_parameter_tokens
from apps.dashboard.crud.sql_generation_rules import build_date_scaffold
from apps.system.crud.tracking_expression import compile_tracking_json_expression, normalize_tracking_property_type


@dataclass(frozen=True)
class PropertyIssue:
    code: str
    path: str
    message: str

    def __str__(self):
        return f"{self.path}：{self.message}"


class PropertyConfigurationError(ValueError):
    def __init__(self, issues):
        self.issues = tuple(issues)
        super().__init__("；".join(map(str, self.issues)))


def fail(path, message, code="PROPERTY_INVALID_CONFIG"):
    raise PropertyConfigurationError([PropertyIssue(code, path, message)])


@dataclass(frozen=True)
class PropertyMetric:
    expression: str
    aggregation: str
    predicate: str
    alias: str


@dataclass(frozen=True)
class PropertySqlPlan:
    source_table: str
    dialect: str
    engine: str
    date_expression: str
    time_predicate: str
    global_filter: str
    groups: tuple[str, ...]
    metrics: tuple[PropertyMetric, ...]
    audiences: tuple[tuple[str, str], ...]
    required_columns: tuple[str, ...]
    display_names: tuple[tuple[str, str], ...]
    scaffold_ctes: str
    source_columns: tuple[str, ...]
    suggestions: tuple[str, ...]


AGGREGATIONS = {"count", "count_distinct", "sum", "avg", "min", "max"}
OPERATORS = {"eq", "ne", "contains", "gt", "lt", "between", "is_null", "is_not_null"}
NUMERIC = re.compile(r"^(?:tinyint|smallint|mediumint|bigint|int\d*|integer|float\d*|double|decimal|numeric|number|real)\b", re.I)
TEXT = re.compile(r"^(?:varchar|nvarchar|char|nchar|character|bpchar|text|string)\b", re.I)


def validate_property_input(context: dict) -> list[PropertyIssue]:
    """Validate raw values before a normalizer can discard or default them."""
    issues = []

    def add(path, message):
        issues.append(PropertyIssue("PROPERTY_INVALID_CONFIG", path, message))

    def field(value, path):
        if not isinstance(value, dict) or any(not isinstance(value.get(key), str) or not value[key] for key in ("table", "field")):
            add(path, "属性必须明确提供表名和字段名。")

    def filters(value, path, nested=False):
        if not isinstance(value, dict):
            add(path, "筛选必须是结构化条件。")
            return
        if not value and not nested:
            return
        key = "children" if value.get("type") == "group" else "rules"
        if key in value or not nested:
            if value.get("logic", "and") not in ("and", "or"):
                add(path + ".logic", "筛选逻辑只能是 AND 或 OR。")
            children = value.get(key)
            if not isinstance(children, list) or (nested and not children):
                add(path, "筛选组需要有效条件列表，不能包含空分组。")
                return
            for i, child in enumerate(children):
                filters(child, f"{path}.{key}[{i}]", True)
            return
        if value.get("type") == "group" or not isinstance(value.get("field"), dict) or not value["field"].get("field"):
            add(path, "筛选条件缺少字段或子条件。")
        field(value.get("field"), path + ".field")
        if not isinstance(value.get("operator"), str) or value.get("operator") not in OPERATORS:
            add(path + ".operator", "属性分析不支持该筛选操作符。")
        if value.get("operator") not in ("is_null", "is_not_null") and value.get("value") in (None, ""):
            add(path + ".value", "筛选值不能为空；空值请使用为空或非空。")

    if not isinstance(context, dict):
        return [PropertyIssue("PROPERTY_INVALID_CONFIG", "context", "配置必须是对象。")]
    prop = context.get("property", {})
    if not isinstance(prop, dict):
        add("property", "属性配置必须是对象。")
        prop = {}
    for alias in ("group_mode", "group_settings", "audience_groups"):
        if alias in prop:
            add(f"property.{alias}", "请使用当前属性配置字段 groupMode、groupSettings 和 audiences。")
    if prop.get("groupMode", "property") not in ("property", "audience"):
        add("property.groupMode", "分组模式无效。")
    time = context.get("time", {})
    if not isinstance(time, dict):
        add("time", "时间配置必须是对象。")
    elif time.get("grain", "none") not in ("day", "week", "month", "none"):
        add("time.grain", "时间粒度无效。")
    if isinstance(time, dict):
        if time.get("field"):
            field(time["field"], "time.field")
        for key in ("dateParameterType", "date_parameter_type"):
            if key in time and time[key] not in ("", "date", "yyyymmdd_number", "yyyymmdd_text", "timestamp"):
                add(f"time.{key}", "日期参数类型无效。")
    for name in ("metrics", "groups"):
        if not isinstance(context.get(name, []), list):
            add(name, "必须是列表。")
    metrics = context.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        add("metrics", "属性分析至少需要配置一个分析指标。")
    else:
        for i, item in enumerate(metrics):
            if not isinstance(item, dict) or not isinstance(item.get("aggregation"), str) or item.get("aggregation") not in AGGREGATIONS:
                add(f"metrics[{i}]", "指标聚合方式无效。")
            else:
                field(item.get("field"), f"metrics[{i}].field")
                if item.get("metricField") is not None:
                    field(item["metricField"], f"metrics[{i}].metricField")
                if "filters" in item:
                    filters(item["filters"], f"metrics[{i}].filters")
    groups = context.get("groups", [])
    if isinstance(groups, list):
        for i, item in enumerate(groups):
            field(item, f"groups[{i}]")
    if context.get("approximate"):
        add("approximate", "属性编译使用精确聚合，不支持近似计算。")
    if "filters" in context:
        filters(context["filters"], "filters")
    if any(context.get(key) for key in ("formula_metrics", "formulaMetrics", "calculatedMetrics")):
        add("formula_metrics", "属性分析暂不支持公式指标。")
    settings = prop.get("groupSettings", {})
    if not isinstance(settings, dict):
        add("property.groupSettings", "分组设置必须是对象。")
    else:
        for key, setting in settings.items():
            if isinstance(setting, dict) and "time_grain" in setting:
                add(f"property.groupSettings.{key}.time_grain", "时间分组请使用 timeGrain。")
            if (not isinstance(setting, dict) or setting.get("timeGrain", "day") not in ("day", "week", "month")
                    or not isinstance(setting.get("summarize", True), bool)):
                add(f"property.groupSettings.{key}", "时间分组设置无效。")
            if not isinstance(groups, list) or not any(isinstance(g, dict) and g.get("value") == key for g in groups):
                add(f"property.groupSettings.{key}", "时间分组设置引用了未选择的分组。")
    if prop.get("groupMode") == "audience":
        if context.get("groups"):
            add("groups", "人群模式不能同时配置属性分组。")
        audiences = prop.get("audiences")
        if not isinstance(audiences, list) or not audiences:
            add("property.audiences", "按人群分析至少需要配置一个人群。")
        else:
            names = set()
            for i, audience in enumerate(audiences):
                path = f"property.audiences[{i}]"
                if not isinstance(audience, dict):
                    add(path, "人群配置必须是对象。")
                    continue
                name = audience.get("name")
                if not isinstance(name, str) or not name.strip() or name.strip() in names:
                    add(path + ".name", "人群名称必须非空且唯一。")
                else:
                    names.add(name.strip())
                if "filters" in audience:
                    filters(audience["filters"], path + ".filters")
                if "filter" in audience:
                    add(path + ".filter", "人群筛选请使用 filters。")
    return issues


def _mapping(value):
    return value.model_dump() if hasattr(value, "model_dump") else dict(value or {})


def property_metadata_fields(schema: str, tracking: Any) -> dict[str, dict[str, dict]]:
    """Read server-produced authorized schema and workspace field mappings."""
    tables = {}
    table = ""
    fields = {}
    event_scoped = False

    def flush_section():
        # Event projections repeat the physical table header, but their
        # expressions require an event predicate. They are not public fields.
        if table and fields and not event_scoped:
            target = tables.setdefault(table, {})
            for name, definition in fields.items():
                if name in target and target[name] != definition:
                    fail("metadata", f"属性字段 {table}.{name} 的类型定义冲突。")
                target[name] = definition

    for line in schema.splitlines():
        match = re.match(r"\s*# Table:\s*([^,]+)", line)
        if match:
            flush_section()
            table = match[1].strip()
            fields = {}
            event_scoped = False
        elif re.match(r"\s*# (?:Event|Required predicate):", line):
            event_scoped = True
        elif table:
            match = re.match(r"\s*\(([^():,]+):\s*([\w ]+(?:\([^)]*\))?)", line)
            if match:
                fields[match[1].strip()] = {"type": match[2].strip()}
    flush_section()
    for item in _mapping(tracking).get("fields", []):
        item = _mapping(item)
        requested = item.get("table_name")
        matches = [name for name in tables if name == requested or name.split(".")[-1] == requested]
        if len(matches) != 1:
            continue
        fields = tables[matches[0]]
        name = item.get("field_name")
        source = item.get("source_field")
        if name in fields and not source:
            fields[name] = {**item, "type": fields[name]["type"]}
        elif source in fields and item.get("json_path"):
            fields[name] = {**item, "type": item.get("semantic_type") or "text"}
    return tables


class _Resolver:
    def __init__(self, metadata, allowed, dialect):
        self.metadata, self.allowed, self.dialect = metadata, allowed, dialect
        self.table = ""
        self.columns = set()

    def field(self, value, path):
        if not isinstance(value, dict) or value.get("kind") == "tracking-event":
            fail(path, "必须选择授权属性字段。", "PROPERTY_FIELD_UNAVAILABLE")
        table, name = value.get("table"), value.get("field")
        matches = [t for t in self.metadata if t == table]
        if not matches:
            matches = [t for t in self.metadata if t.split(".")[-1] == table]
        if len(matches) != 1 or name not in self.metadata[matches[0]]:
            fail(path, "所选字段已不存在或无访问权限。", "PROPERTY_FIELD_UNAVAILABLE")
        table = matches[0]
        if self.table and self.table != table:
            fail(path, "属性分析仅支持同一个授权源表。", "PROPERTY_MULTIPLE_SOURCE_TABLES")
        self.table = table
        definition = self.metadata[table][name]
        host = definition.get("source_field") or name
        permitted = self.allowed.get(table, self.allowed.get(table.split(".")[-1], set()))
        if host not in permitted:
            fail(path, "属性来源列已不存在或无访问权限。", "PROPERTY_FIELD_UNAVAILABLE")
        self.columns.add(host)
        expression = exp.column(host, quoted=True)
        source, json_path = definition.get("source_field"), definition.get("json_path")
        # The current field-list API explicitly names a physical field as its
        # own source; tracking metadata may leave that redundant mapping empty.
        for sent, trusted in ((value.get("sourceField") or value.get("source_field"), host),
                              (value.get("jsonPath") or value.get("json_path"), json_path)):
            if sent and sent != trusted:
                fail(path, "字段映射与工作空间元数据不一致。", "PROPERTY_FIELD_UNAVAILABLE")
        if source and json_path:
            # Semantic labels describe business meaning, not the SQL value
            # type. The shared JSON compiler casts "number" to numeric and
            # extracts all other semantic labels as text.
            definition = {**definition, "type": "numeric" if normalize_tracking_property_type(definition.get("semantic_type")) == "number" else "text"}
            text = compile_tracking_json_expression(table, source, json_path,
                                                    definition.get("semantic_type"), self.dialect)
            if not text:
                fail(path, "当前方言不支持此 JSON 属性映射。", "PROPERTY_UNSUPPORTED_CAPABILITY")
            expression = sqlglot.parse_one(text, read=self.dialect)
            for col in expression.find_all(exp.Column):
                col.set("table", None)
                col.set("db", None)
                col.set("catalog", None)
        if value.get("expression"):
            try:
                supplied = sqlglot.parse(value["expression"], read=self.dialect)
                if len(supplied) != 1 or supplied[0] is None:
                    raise ValueError()
                for col in supplied[0].find_all(exp.Column):
                    if col.table and col.table not in {table, table.split(".")[-1]}:
                        raise ValueError()
                    col.set("table", None)
                    col.set("db", None)
                    col.set("catalog", None)
                    col.set("this", exp.to_identifier(col.name, quoted=True))
                if supplied[0] != expression:
                    raise ValueError()
            except (ValueError, sqlglot.errors.SqlglotError):
                fail(path, "表达式与授权字段映射不一致。", "PROPERTY_FIELD_UNAVAILABLE")
        return expression.sql(dialect=self.dialect), definition

    def filters(self, value, path):
        if not value:
            return "TRUE"
        key = "children" if value.get("type") == "group" else "rules"
        if key in value:
            parts = [self.filters(child, f"{path}.{key}[{i}]") for i, child in enumerate(value[key])]
            return (" " + value.get("logic", "and").upper() + " ").join(f"({p})" for p in parts) or "TRUE"
        column, definition = self.field(value["field"], path + ".field")
        operator, raw = value["operator"], value.get("value")
        kind = str(definition.get("type") or "").lower()

        def literal(item):
            if NUMERIC.match(kind):
                try:
                    if isinstance(item, bool):
                        raise InvalidOperation()
                    number = Decimal(str(item))
                    if not number.is_finite():
                        raise InvalidOperation()
                    return exp.Literal.number(str(number)).sql(dialect=self.dialect), number
                except (InvalidOperation, ValueError):
                    fail(path + ".value", "数值筛选需要有效的有限数字。")
            if kind in {"bool", "boolean"}:
                if isinstance(item, str) and item.strip().lower() in ("true", "false"):
                    item = item.strip().lower() == "true"
                if not isinstance(item, bool):
                    fail(path + ".value", "布尔属性需要 true 或 false。")
                return exp.convert(item).sql(dialect=self.dialect), item
            if not isinstance(item, str):
                fail(path + ".value", "该属性的筛选值必须是文本。")
            if kind == "date" or kind.startswith(("timestamp", "datetime")):
                try:
                    (date.fromisoformat if kind == "date" else datetime.fromisoformat)(item)
                except ValueError:
                    fail(path + ".value", "日期筛选值格式无效。")
            return exp.Literal.string(item).sql(dialect=self.dialect), item

        if operator in {"is_null", "is_not_null"}:
            return f"{column} IS {'NOT ' if operator == 'is_not_null' else ''}NULL"
        if operator == "between":
            values = [v.strip() for v in raw.split(",")] if isinstance(raw, str) else raw
            if not isinstance(values, list) or len(values) != 2 or any(v in (None, "") for v in values):
                fail(path + ".value", "范围筛选需要两个非空边界。")
            low, lo = literal(values[0])
            high, hi = literal(values[1])
            if lo > hi:
                fail(path + ".value", "范围起点不能大于终点。")
            return f"{column} BETWEEN {low} AND {high}"
        if operator == "contains":
            if not isinstance(raw, str) or not TEXT.match(kind):
                fail(path + ".value", "包含筛选只能用于文本属性。")
            escaped = raw.replace("!", "!!").replace("%", "!%").replace("_", "!_")
            return f"{column} LIKE {exp.Literal.string('%' + escaped + '%').sql(dialect=self.dialect)} ESCAPE '!'"
        symbol = {"eq": "=", "ne": "<>", "gt": ">", "lt": "<"}[operator]
        return f"{column} {symbol} {literal(raw)[0]}"


def _bucket(expression, grain, dialect):
    if grain == "day":
        return f"CAST({expression} AS DATE)"
    if dialect == "postgres":
        return f"CAST(DATE_TRUNC('{grain}', {expression}) AS DATE)"
    if grain == "week":
        return f"DATE_SUB(CAST({expression} AS DATE), INTERVAL WEEKDAY({expression}) DAY)"
    return f"CAST(DATE_FORMAT({expression}, '%Y-%m-01') AS DATE)"


def _local_timestamp(column, definition, dialect, path):
    from common.core.config import settings
    kind = str(definition.get("type") or "").lower()
    zone = (definition.get("extra_properties") or {}).get("timezone")
    if kind == "timestamptz" or "with time zone" in kind:
        if dialect != "postgres":
            fail(path, "当前方言不支持此带时区时间属性。", "PROPERTY_TIME_MAPPING_REQUIRED")
        tz = exp.Literal.string(settings.DASHBOARD_BUSINESS_TIMEZONE).sql(dialect=dialect)
        return f"({column} AT TIME ZONE {tz})"
    if zone != settings.DASHBOARD_BUSINESS_TIMEZONE:
        fail(path, "无时区时间字段需声明与业务时区一致的 timezone 元数据。", "PROPERTY_TIME_MAPPING_REQUIRED")
    return column


def build_property_plan(normalized_config: dict, *, metadata_fields: dict[str, dict[str, dict]],
                        allowed_fields_by_table: dict[str, set[str]], dialect: str, engine: str) -> PropertySqlPlan:
    issues = validate_property_input(normalized_config)
    if issues:
        raise PropertyConfigurationError(issues)
    if dialect not in {"postgres", "mysql"}:
        fail("datasource", "属性编译当前仅支持 PostgreSQL 和 MySQL 方言。", "PROPERTY_UNSUPPORTED_CAPABILITY")
    resolver = _Resolver(metadata_fields, allowed_fields_by_table, dialect)
    metrics, names = [], []
    for i, metric in enumerate(normalized_config["metrics"]):
        path = f"metrics[{i}]"
        expression, definition = resolver.field(metric.get("field"), path + ".field")
        if metric.get("metricField") is not None and resolver.field(metric["metricField"], path + ".metricField")[0] != expression:
            fail(path, "指标字段与度量字段不一致。")
        aggregation = metric["aggregation"]
        kind = str(definition.get("type") or "")
        comparable = bool(NUMERIC.match(kind) or TEXT.match(kind) or kind.lower().startswith(("date", "timestamp")))
        if (aggregation in {"sum", "avg"} and not NUMERIC.match(kind)) or (aggregation in {"max", "min"} and not comparable):
            fail(path + ".aggregation", "聚合方式与属性类型不匹配。", "PROPERTY_INVALID_AGGREGATION")
        alias = f"property_metric_{i + 1}"
        metrics.append(PropertyMetric(expression, aggregation, resolver.filters(metric.get("filters", {}), path + ".filters"), alias))
        names.append((alias, str(metric.get("displayName") or metric.get("alias") or f"指标{i + 1}")))
    global_filter = resolver.filters(normalized_config.get("filters", {}), "filters")
    prop = normalized_config.get("property", {})
    groups = []
    for i, group in enumerate(normalized_config.get("groups", [])):
        expression, definition = resolver.field(group, f"groups[{i}]")
        setting = prop.get("groupSettings", {}).get(group.get("value"), {})
        if setting and setting.get("summarize", True):
            kind = str(definition.get("type") or "").lower()
            encoding = str((definition.get("extra_properties") or {}).get("encoding") or "").lower()
            if kind == "date":
                pass
            elif kind.startswith(("timestamp", "datetime")):
                expression = _local_timestamp(expression, definition, dialect, f"groups[{i}]")
            elif encoding == "yyyymmdd" and (NUMERIC.match(kind) or TEXT.match(kind)):
                expression = (f"TO_DATE(CAST({expression} AS TEXT), 'YYYYMMDD')" if dialect == "postgres"
                              else f"STR_TO_DATE(CAST({expression} AS CHAR), '%Y%m%d')")
            else:
                fail(f"groups[{i}]", "时间分组需要明确的日期类型或日期编码元数据。")
            expression = _bucket(expression, setting.get("timeGrain", "day"), dialect)
        groups.append(expression)
        names.append((f"group_{i + 1}", str(group.get("displayName") or group.get("field"))))
    audiences = []
    if prop.get("groupMode", "property") == "audience":
        for i, audience in enumerate(prop["audiences"]):
            audiences.append((audience["name"].strip(), resolver.filters(audience.get("filters", {}), f"property.audiences[{i}].filters")))
        names.append(("group_1", "人群"))
    time = normalized_config.get("time", {})
    grain = time.get("grain", "none")
    parameter_type = time.get("date_parameter_type") or time.get("dateParameterType") or ""
    date_expression, time_predicate, scaffold, suggestions = "", "TRUE", "", []
    if time.get("field"):
        column, definition = resolver.field(time["field"], "time.field")
        kind = str(definition.get("type") or "").lower()
        tokens = dashboard_date_parameter_tokens(parameter_type)
        if not tokens:
            fail("time.dateParameterType", "请明确时间字段的日期参数类型。", "PROPERTY_TIME_MAPPING_REQUIRED")
        start, end = tokens
        if parameter_type in {"yyyymmdd_number", "yyyymmdd_text"}:
            if parameter_type == "yyyymmdd_number" and not NUMERIC.match(kind):
                fail("time.field", "数值日期参数必须对应数值日期字段。", "PROPERTY_TIME_MAPPING_REQUIRED")
            if parameter_type == "yyyymmdd_text" and not kind.startswith(("varchar", "char", "text", "string")):
                fail("time.field", "文本日期参数必须对应文本日期字段。", "PROPERTY_TIME_MAPPING_REQUIRED")
            parsed = (f"TO_DATE(CAST({column} AS TEXT), 'YYYYMMDD')" if dialect == "postgres"
                      else f"STR_TO_DATE(CAST({column} AS CHAR), '%Y%m%d')")
        elif parameter_type == "date" and kind == "date":
            parsed = column
        elif parameter_type == "timestamp" and NUMERIC.match(kind):
            from common.core.config import settings
            encoding = (definition.get("extra_properties") or {}).get("encoding")
            if encoding not in {"epoch_seconds", "epoch_milliseconds"}:
                fail("time.field", "数值时间字段必须声明 epoch_seconds 或 epoch_milliseconds。", "PROPERTY_TIME_MAPPING_REQUIRED")
            factor = 1000 if encoding == "epoch_milliseconds" else 1
            tz = exp.Literal.string(settings.DASHBOARD_BUSINESS_TIMEZONE).sql(dialect=dialect)
            if dialect == "postgres":
                parsed = f"(TO_TIMESTAMP({column} / {factor}.0) AT TIME ZONE {tz})"
                start, end = (f"(EXTRACT(EPOCH FROM ({token} AT TIME ZONE {tz})) * {factor})" for token in (start, end))
            else:
                epoch = "CAST('1970-01-01 00:00:00' AS DATETIME)"
                parsed = f"CONVERT_TZ(TIMESTAMPADD(SECOND, {column} / {factor}.0, {epoch}), '+00:00', {tz})"
                start, end = (f"(TIMESTAMPDIFF(SECOND, {epoch}, CONVERT_TZ({token}, {tz}, '+00:00')) * {factor})" for token in (start, end))
        elif parameter_type == "timestamp" and kind.startswith(("timestamp", "datetime")):
            # Timestamp tokens are local SQL timestamp literals, never epoch numbers.
            from common.core.config import settings
            aware = "with time zone" in kind or kind == "timestamptz"
            parsed = _local_timestamp(column, definition, dialect, "time.field")
            if aware and dialect == "postgres":
                tz = exp.Literal.string(settings.DASHBOARD_BUSINESS_TIMEZONE).sql(dialect=dialect)
                start, end = f"({start} AT TIME ZONE {tz})", f"({end} AT TIME ZONE {tz})"
        else:
            fail("time.field", "时间字段类型与日期参数不匹配；请配置明确的日期字段。", "PROPERTY_TIME_MAPPING_REQUIRED")
        time_predicate = f"{column} >= {start} AND {column} {'<' if parameter_type == 'timestamp' else '<='} {end}"
        if grain != "none":
            date_expression = _bucket(parsed, grain, dialect)
            capability = build_date_scaffold({**time, "date_parameter_type": parameter_type}, dialect)
            if capability["supported"]:
                scaffold = capability["cte_sql"]
            else:
                suggestions.append("当前时间粒度或参数类型仅返回有事实的时间桶，不补齐缺失日期。")
    elif grain != "none" or parameter_type or time.get("date_expression") or time.get("dateExpression") or time.get("range"):
        fail("time.field", "时间分组或范围筛选需要明确的时间字段。", "PROPERTY_TIME_MAPPING_REQUIRED")
    group_columns = ("group_1",) if audiences else tuple(f"group_{i + 1}" for i in range(len(groups)))
    required = (("property_date",) if date_expression else ()) + group_columns + tuple(m.alias for m in metrics)
    if date_expression:
        names.append(("property_date", "日期"))
    return PropertySqlPlan(resolver.table, dialect, engine, date_expression, time_predicate, global_filter,
                           tuple(groups), tuple(metrics), tuple(audiences), required, tuple(names), scaffold,
                           tuple(sorted(resolver.columns)), tuple(suggestions))
