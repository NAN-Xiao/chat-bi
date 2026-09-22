"""Compile configured interval analysis without a generative SQL repair loop."""
from __future__ import annotations

import copy
import re

import sqlglot
from sqlglot import exp

from apps.dashboard.crud.dashboard_date_filter import dashboard_date_parameter_tokens
from apps.dashboard.crud.event_sql_contract import _filter_expression
from apps.dashboard.crud.sql_generation_rules import build_date_scaffold


class IntervalConfigurationError(ValueError):
    pass


def _mapping(value):
    return value.model_dump() if hasattr(value, "model_dump") else dict(value or {})


def interval_time_metadata(tracking, table: str, schema: str) -> dict:
    config = _mapping(tracking)
    if not config.get("enabled"):
        raise IntervalConfigurationError("请启用工作空间事件元数据并配置事件时间字段。")
    fields = [_mapping(item) for item in config.get("fields", [])]
    candidates = {item["field_name"] for item in fields
                  if item.get("table_name") == table and item.get("field_role") == "event_time"}
    for item in config.get("field_role_mappings", []):
        if isinstance(item, dict) and item.get("table") == table and item.get("role") == "event_time":
            candidates.add(item.get("field"))
    if config.get("default_event_table") == table and config.get("default_event_time_field"):
        candidates.add(config["default_event_time_field"])
    if len(candidates) != 1 or not next(iter(candidates), None):
        raise IntervalConfigurationError("间隔分析需要唯一、明确的 event_time 字段角色配置。")
    name = next(iter(candidates))
    definitions = [item for item in fields if item.get("table_name") == table and item.get("field_name") == name]
    encodings = {(item.get("extra_properties") or {}).get("encoding") for item in definitions}
    encodings.discard(None)
    if len(encodings) > 1:
        raise IntervalConfigurationError("事件时间字段的时间编码配置冲突。")
    encoding = next(iter(encodings), None)
    current_table = ""
    physical_type = ""
    for line in schema.splitlines():
        match = re.match(r"\s*#\s*Table:\s*([^,]+)", line)
        if match:
            current_table = match.group(1).strip()
        if current_table == table:
            match = re.search(r"\(" + re.escape(name) + r"\s*:\s*([^,)]+)", line)
            if match:
                physical_type = match.group(1).strip().lower()
    if not encoding and physical_type in {"timestamp", "timestamptz", "datetime", "timestamp with time zone", "timestamp without time zone"}:
        encoding = "datetime"
    if encoding not in {"epoch_milliseconds", "epoch_seconds", "datetime"}:
        raise IntervalConfigurationError("事件时间字段必须声明 epoch_milliseconds、epoch_seconds 或日期时间类型，不能猜测数值时间单位。")
    order_fields = [item["field_name"] for item in fields if item.get("table_name") == table
                    and item.get("field_role") in {"event_id", "event_sequence"}]
    order_fields.extend(item["field"] for item in config.get("field_role_mappings", [])
                        if isinstance(item, dict) and item.get("table") == table
                        and item.get("role") in {"event_id", "event_sequence"} and item.get("field"))
    if any(item.get("source_field") or item.get("expression") for item in definitions):
        raise IntervalConfigurationError("当前间隔分析需要物理事件时间字段；请明确配置物理字段及其时间编码。")
    return {"field": name, "table": table, "encoding": encoding, "order_fields": sorted(set(order_fields))}


class IntervalSqlCompiler:
    def __init__(self, config, metadata, dialect, engine, allowed_tables, allowed_fields):
        self.config = config
        self.interval = config.get("interval") or {}
        self.metadata = metadata
        self.dialect = dialect
        self.engine = engine.lower()
        self.start = self.interval.get("startEvent") or self.interval.get("start_event") or {}
        self.end = self.interval.get("endEvent") or self.interval.get("end_event") or {}
        self.table = self.start.get("eventTable") or self.start.get("table")
        end_table = self.end.get("eventTable") or self.end.get("table")
        if not self.table or self.table != end_table:
            raise IntervalConfigurationError("间隔分析的确定性配对要求起终事件位于同一事件明细表；跨表事件需要先配置统一事件来源。")
        if self.table not in allowed_tables or not allowed_fields.get(self.table):
            raise IntervalConfigurationError("间隔事件表不存在或不在当前授权 Schema 中。")
        if dialect not in {"mysql", "postgres", "starrocks", "doris"}:
            raise IntervalConfigurationError(f"当前方言 {dialect} 尚未提供确定性间隔 SQL 编译能力。")
        self.allowed_fields = allowed_fields[self.table]

    def identifier(self, name):
        return exp.to_identifier(name, quoted=True).sql(dialect=self.dialect)

    def field(self, value):
        if not isinstance(value, dict) or value.get("table") != self.table:
            raise IntervalConfigurationError("间隔字段必须明确引用当前授权事件表。")
        if value.get("expression"):
            statements = sqlglot.parse(value["expression"], read=self.dialect)
            if len(statements) != 1 or statements[0] is None:
                raise IntervalConfigurationError("间隔字段表达式必须是单个标量表达式。")
            node = statements[0]
        else:
            name = value.get("field") or value.get("name")
            if not name:
                raise IntervalConfigurationError("间隔配置缺少字段名称。")
            node = exp.column(name, quoted=True)
        if any(isinstance(item, (exp.Query, exp.Command, exp.DDL, exp.DML, exp.Window, exp.AggFunc, exp.Placeholder, exp.Parameter)) for item in node.walk()):
            raise IntervalConfigurationError("间隔字段只允许当前事件行的标量表达式。")
        columns = list(node.find_all(exp.Column))
        if not columns:
            raise IntervalConfigurationError("间隔字段表达式必须引用授权字段。")
        for column in columns:
            qualifier = ".".join(part for part in (column.catalog, column.db, column.table) if part)
            if column.name not in self.allowed_fields or (qualifier and qualifier not in {self.table, self.table.split('.')[-1]}):
                raise IntervalConfigurationError(f"间隔字段不存在或无权限：{column.sql()}。")
            column.set("table", None)
            column.set("db", None)
            column.set("catalog", None)
            column.set("this", exp.to_identifier(column.name, quoted=True))
        return node.sql(dialect=self.dialect)

    def filters(self, value):
        if not value:
            return "TRUE"
        value = copy.deepcopy(value)

        def prepare(item):
            if not isinstance(item, dict):
                raise IntervalConfigurationError("间隔筛选配置必须是结构化条件。")
            children = item.get("children") if item.get("type") == "group" else item.get("rules")
            if children is not None:
                if item.get("logic", "and") not in {"and", "or"} or not isinstance(children, list):
                    raise IntervalConfigurationError("间隔筛选组合必须声明 AND/OR 和条件列表。")
                for child in children:
                    prepare(child)
            else:
                item["field"] = {**item.get("field", {}), "expression": self.field(item.get("field"))}

        prepare(value)
        expression = _filter_expression(value, self.dialect)
        return expression.sql(dialect=self.dialect) if expression is not None else "TRUE"

    def event_condition(self, event, filters):
        name = event.get("eventName") or event.get("event_name")
        column = event.get("eventNameField") or event.get("event_name_field")
        if not name or not column:
            raise IntervalConfigurationError("起终事件必须配置实际事件名和事件名字段。")
        field = self.field({"table": self.table, "field": column})
        literal = exp.Literal.string(name).sql(dialect=self.dialect)
        return f"({field} = {literal}) AND ({self.filters(filters)})"

    def compile(self):
        time = self.config.get("time") or {}
        parameter_type = time.get("date_parameter_type")
        tokens = dashboard_date_parameter_tokens(parameter_type)
        if len(tokens) != 2:
            raise IntervalConfigurationError("间隔分析缺少有效的看板日期参数类型。")
        if time.get("grain") not in {None, "", "day"}:
            raise IntervalConfigurationError("间隔分析当前按起点日期统计，请选择日粒度。")
        entity = self.field(self.interval.get("entityField") or self.interval.get("entity_field"))
        date_field = self.field(time.get("field"))
        event_time = self.field(self.metadata)
        if parameter_type in {"yyyymmdd_number", "yyyymmdd_text"}:
            date = (f"TO_DATE(CAST({date_field} AS TEXT), 'YYYYMMDD')" if self.dialect == "postgres"
                    else f"STR_TO_DATE(CAST({date_field} AS CHAR), '%Y%m%d')")
        else:
            date = f"CAST({date_field} AS DATE)"
        start_filter = self.interval.get("startEventFilters") or self.interval.get("start_event_filters")
        end_filter = self.interval.get("endEventFilters") or self.interval.get("end_event_filters")
        start_condition = self.event_condition(self.start, start_filter)
        end_condition = self.event_condition(self.end, end_filter)
        same_event = ((self.start.get("eventName") or self.start.get("event_name"))
                      == (self.end.get("eventName") or self.end.get("event_name")))
        if (self.start.get("eventNameField") or self.start.get("event_name_field")) != (self.end.get("eventNameField") or self.end.get("event_name_field")):
            raise IntervalConfigurationError("起终事件必须使用同一事件标识字段。")
        related = self.interval.get("relatedProperty") or {}
        related_enabled = related.get("enabled") is True
        related_start = related_end = None
        if related_enabled:
            related_start = self.field(related.get("startProperty") or related.get("start_property"))
            related_end = self.field(related.get("endProperty") or related.get("end_property"))
            if same_event and related_start != related_end:
                raise IntervalConfigurationError("同事件相邻配对的两端关联属性必须是同一个字段表达式。")
        groups = [self.field(field) for field in self.config.get("groups", [])]
        group_names = [f"group_{index + 1}" for index in range(len(groups))]
        limit = self.interval.get("limitSeconds", self.interval.get("limit_seconds"))
        if isinstance(limit, bool) or not isinstance(limit, int) or not 60 <= limit <= 15552000:
            raise IntervalConfigurationError("间隔上限必须是 1 分钟到 180 天的整数秒。")
        projections = [f"{entity} AS entity_id", f"{date} AS event_date", f"{event_time} AS event_time",
                       f"CASE WHEN {start_condition} THEN 1 ELSE 0 END AS is_start",
                       f"CASE WHEN {end_condition} THEN 1 ELSE 0 END AS is_end"]
        projections.extend(f"{field} AS {name}" for field, name in zip(groups, group_names))
        if related_enabled:
            projections.append(f"CASE WHEN {start_condition} THEN {related_start} ELSE {related_end} END AS related_key")
        order_names = []
        for index, name in enumerate(self.metadata.get("order_fields", [])):
            order_name = f"event_order_{index + 1}"
            projections.append(f"{self.field({'table': self.table, 'field': name})} AS {order_name}")
            order_names.append(order_name)
        table = exp.to_table(self.table, quoted=True).sql(dialect=self.dialect)
        comparison = "<" if parameter_type == "timestamp" else "<="
        source = (f"SELECT {', '.join(projections)} FROM {table} WHERE "
                  f"{date_field} >= {tokens[0]} AND {date_field} {comparison} {tokens[1]} "
                  f"AND ({self.filters(self.config.get('filters'))}) "
                  f"AND (({start_condition}) OR ({end_condition})) "
                  f"AND {entity} IS NOT NULL AND {event_time} IS NOT NULL")
        ctes = [f"interval_source AS ({source})"]
        scoped = "SELECT * FROM interval_source"
        if related_enabled:
            scoped += " WHERE related_key IS NOT NULL"
        ctes.append(f"interval_events AS ({scoped})")
        partition = "entity_id" + (", related_key" if related_enabled else "")
        order = ["event_time", *order_names]
        window = f"OVER (PARTITION BY {partition} ORDER BY {', '.join(order)})"
        previous = [f"LAG(event_time) {window} AS start_time", f"LAG(event_date) {window} AS interval_date",
                    f"LAG(is_start) {window} AS prev_is_start"]
        previous.extend(f"LAG({name}) {window} AS start_{name}" for name in group_names)
        ctes.append(f"interval_ordered AS (SELECT *, {', '.join(previous)} FROM interval_events)")
        paired_groups = [f"start_{name} AS {name}" for name in group_names]
        ctes.append("interval_pairs AS (SELECT " + ", ".join([
            "entity_id", "interval_date", "start_time", "event_time AS end_time", *paired_groups,
        ]) + " FROM interval_ordered WHERE is_end = 1 AND prev_is_start = 1)")
        encoding = self.metadata["encoding"]
        if encoding in {"epoch_seconds", "epoch_milliseconds"}:
            divisor = "1000.0" if encoding == "epoch_milliseconds" else "1.0"
            duration = f"(end_time - start_time) / {divisor}"
        elif self.dialect == "postgres":
            duration = "EXTRACT(EPOCH FROM (end_time - start_time))"
        else:
            duration = "TIMESTAMPDIFF(MICROSECOND, start_time, end_time) / 1000000.0"
        dimensions = ["interval_date", *group_names]
        ctes.append(f"interval_durations AS (SELECT entity_id, {', '.join(dimensions)}, {duration} AS interval_seconds FROM interval_pairs)")
        ctes.append(f"valid_intervals AS (SELECT * FROM interval_durations WHERE interval_seconds >= 0 AND interval_seconds <= {limit})")
        aggregates = ["COUNT(DISTINCT entity_id) AS entity_count", "COUNT(*) AS interval_count",
                      "MAX(interval_seconds) AS max_interval_seconds", "MIN(interval_seconds) AS min_interval_seconds",
                      "AVG(interval_seconds) AS avg_interval_seconds"]
        quantiles = [("0.75", "p75_interval_seconds"), ("0.50", "median_interval_seconds"), ("0.25", "p25_interval_seconds")]
        approximate = any(engine in self.engine for engine in ("analyticdb", "starrocks", "doris"))
        aggregate_source = "valid_intervals"
        if not approximate and self.dialect != "postgres":
            ctes.append("interval_percentile_rows AS (SELECT *, "
                        f"ROW_NUMBER() OVER (PARTITION BY {', '.join(dimensions)} ORDER BY interval_seconds) AS percentile_position, "
                        f"COUNT(*) OVER (PARTITION BY {', '.join(dimensions)}) AS percentile_count FROM valid_intervals)")
            aggregate_source = "interval_percentile_rows"
        for quantile, alias in quantiles:
            if approximate:
                function = "PERCENTILE_APPROX" if any(engine in self.engine for engine in ("starrocks", "doris")) else "APPROX_PERCENTILE"
                expression = f"{function}(interval_seconds, {quantile})"
            elif self.dialect == "postgres":
                expression = f"PERCENTILE_CONT({quantile}) WITHIN GROUP (ORDER BY interval_seconds)"
            else:
                expression = exact_percentile_expression(quantile)
            aggregates.append(f"{expression} AS {alias}")
        ctes.append(f"interval_aggregates AS (SELECT {', '.join(dimensions + aggregates)} FROM {aggregate_source} GROUP BY {', '.join(dimensions)})")
        scaffold = build_date_scaffold(time, self.dialect)
        if scaffold["supported"]:
            ctes.insert(0, scaffold["cte_sql"])
            output = ["calendar.calendar_date AS interval_date"]
            from_sql = "dashboard_dates AS calendar"
            conditions = ["calendar.calendar_date = stats.interval_date"]
            if group_names:
                ctes.append(f"interval_groups AS (SELECT DISTINCT {', '.join(group_names)} FROM interval_events WHERE is_start = 1)")
                from_sql += " CROSS JOIN interval_groups AS dimensions"
                output.extend(f"dimensions.{name} AS {name}" for name in group_names)
                conditions.extend(f"(dimensions.{name} = stats.{name} OR (dimensions.{name} IS NULL AND stats.{name} IS NULL))" for name in group_names)
            output.extend(["COALESCE(stats.entity_count, 0) AS entity_count", "COALESCE(stats.interval_count, 0) AS interval_count"])
            output.extend(f"stats.{alias} AS {alias}" for alias in ["max_interval_seconds", "min_interval_seconds", "avg_interval_seconds", *[item[1] for item in quantiles]])
            final = f"SELECT {', '.join(output)} FROM {from_sql} LEFT JOIN interval_aggregates AS stats ON {' AND '.join(conditions)} ORDER BY calendar.calendar_date"
        else:
            columns = dimensions + ["entity_count", "interval_count", "max_interval_seconds", "min_interval_seconds",
                                    "avg_interval_seconds", *[item[1] for item in quantiles]]
            final = f"SELECT {', '.join(columns)} FROM interval_aggregates ORDER BY {', '.join(dimensions)}"
        return "WITH " + ",\n".join(ctes) + "\n" + final


def compile_interval_sql(config, tracking, schema, dialect, engine, allowed_tables, allowed_fields):
    interval = config.get("interval") or {}
    start = interval.get("startEvent") or interval.get("start_event") or {}
    table = start.get("eventTable") or start.get("table")
    metadata = interval_time_metadata(tracking, table, schema)
    compiler = IntervalSqlCompiler(config, metadata, dialect, engine, allowed_tables, allowed_fields)
    return compiler.compile()


def exact_percentile_expression(quantile):
    position = f"(percentile_count - 1) * {quantile}"
    lower = f"MAX(CASE WHEN percentile_position = FLOOR({position}) + 1 THEN interval_seconds END)"
    upper = f"MAX(CASE WHEN percentile_position = CEIL({position}) + 1 THEN interval_seconds END)"
    return f"{lower} + ({upper} - {lower}) * MAX({position} - FLOOR({position}))"
