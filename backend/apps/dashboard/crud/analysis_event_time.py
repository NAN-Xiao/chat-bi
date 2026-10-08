"""Authorized absolute-time and calendar boundaries shared by event compilers."""
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import re
from sqlglot import exp
from apps.dashboard.crud.dashboard_date_filter import dashboard_date_parameter_tokens
from apps.dashboard.crud.property_sql_plan import _Resolver, NUMERIC, TEXT, fail as field_fail

@dataclass(frozen=True)
class EventTimePlan:
    instant: str
    raw_time: str
    date: str
    predicate: str
    bounds: str
    business_timezone: str
    naive_timezones: tuple[str, ...]
    mysql_utc: bool
    mysql_timezones: tuple[str, ...]
    parameter_type: str
    start_day: str
    end_day: str


def build_event_time_plan(*, table, time_config, metadata_fields, allowed_fields_by_table,
                          tracking_metadata, dialect, engine, business_timezone,
                          parameter_cte, fail=field_fail):
    try: ZoneInfo(business_timezone)
    except (ZoneInfoNotFoundError, ValueError, TypeError): fail("metadata.timezone", "业务时区无效。")
    if table not in metadata_fields: fail("metadata", "事件表不存在或未授权。")
    tracking = tracking_metadata.model_dump() if hasattr(tracking_metadata, "model_dump") else dict(tracking_metadata or {})
    definitions = metadata_fields[table]
    names = {n for n, d in definitions.items() if d.get("field_role") == "event_time"}
    names.update(m.get("field") for m in tracking.get("field_role_mappings", [])
                 if isinstance(m, dict) and m.get("table") == table and m.get("role") == "event_time")
    if tracking.get("default_event_table") == table and tracking.get("default_event_time_field"):
        names.add(tracking["default_event_time_field"])
    if len(names) != 1 or next(iter(names)) not in definitions:
        fail("metadata.event_time", "需要唯一、已授权的事件时间字段。")
    name = next(iter(names))
    resolver = _Resolver(metadata_fields, allowed_fields_by_table, dialect)
    raw, definition = resolver.field({"table": table, "field": name}, "metadata.event_time")
    if definition.get("json_path") or definition.get("expression"):
        fail("metadata.event_time", "事件时间必须是明确的物理字段。")
    zone = exp.Literal.string(business_timezone).sql(dialect=dialect)
    naive = set()
    mysql_timezones = set()
    mysql_utc = False
    epoch = "CAST('1970-01-01 00:00:00' AS DATETIME)"

    def instant(column, d, path):
        nonlocal mysql_utc
        kind = re.sub(r"\(\s*\d+\s*\)", "", d.get("type", "").lower()).strip()
        extra = d.get("extra_properties") or {}
        if NUMERIC.match(kind):
            encoding = extra.get("encoding")
            if encoding not in {"epoch_seconds", "epoch_milliseconds"}: fail(path, "数值事件时间必须声明秒或毫秒编码。")
            # Keep an existing decimal's full scale. Integer promotion avoids
            # overflow in subtraction; exact decimal multiplication converts
            # milliseconds without depending on MySQL's division scale.
            number = (f"CAST({column} AS DECIMAL(38, 0))"
                      if re.fullmatch(r"(?:tinyint|smallint|mediumint|bigint|int\d*|integer)(?: unsigned)?", kind)
                      else column)
            return f"({number} * 0.001)" if encoding == "epoch_milliseconds" else number
        if not kind.startswith(("timestamp", "datetime", "timestamptz")):
            fail(path, "事件时间不能使用日期分区或文本字段。")
        if extra.get("encoding") not in (None, "datetime", "timestamp"):
            fail(path, "时间编码与字段类型冲突。")
        aware = kind == "timestamptz" or "with time zone" in kind
        if dialect == "mysql" and kind == "timestamp" and not any(n in engine.lower() for n in ("analyticdb", "doris", "starrocks")):
            mysql_utc = True
            return f"CAST(TIMESTAMPDIFF(MICROSECOND, {epoch}, {column}) AS DECIMAL(30, 6)) / 1000000.0"
        if aware:
            if dialect != "postgres": fail(path, "当前引擎尚未确认带时区时间能力。")
            return f"EXTRACT(EPOCH FROM {column})"
        source_zone = extra.get("timezone")
        try: ZoneInfo(source_zone)
        except (ZoneInfoNotFoundError, ValueError, TypeError): fail(path, "无时区事件时间需要声明有效源时区。")
        naive.add(source_zone)
        literal = exp.Literal.string(source_zone).sql(dialect=dialect)
        if dialect == "postgres": return f"EXTRACT(EPOCH FROM ({column} AT TIME ZONE {literal}))"
        mysql_timezones.add(source_zone)
        return f"CAST(TIMESTAMPDIFF(MICROSECOND, {epoch}, CONVERT_TZ({column}, {literal}, '+00:00')) AS DECIMAL(30, 6)) / 1000000.0"

    event_instant = instant(raw, definition, "metadata.event_time")
    time = time_config
    if (time.get("field") or {}).get("table") != table: fail("time.field", "日期字段必须来自当前事件表。")
    date_column, date_definition = resolver.field(time.get("field"), "time.field")
    parameter = time.get("date_parameter_type") or time.get("dateParameterType")
    tokens = dashboard_date_parameter_tokens(parameter)
    if len(tokens) != 2: fail("time.date_parameter_type", "请选择有效日期参数类型。")
    bounds = f"{parameter_cte} AS (SELECT {tokens[0]} AS range_start, {tokens[1]} AS range_end)"
    start, end = (f"(SELECT {n} FROM {parameter_cte})" for n in ("range_start", "range_end"))
    kind = date_definition.get("type", "").lower()
    extra = date_definition.get("extra_properties") or {}
    if parameter in {"date", "yyyymmdd_number", "yyyymmdd_text"}:
        # The existing explicit date parameter type defines the calendar key;
        # no new form or date_semantics declaration is needed for DATE/YYYYMMDD.
        if extra.get("date_semantics") not in (None, "business_date") or extra.get("timezone") not in (None, business_timezone):
            fail("time.field", "日期字段声明与当前业务日期时区冲突。")
        if parameter == "date":
            if kind != "date": fail("time.field", "date 参数需要物理 DATE 字段。")
            date = date_column
        else:
            encoding = extra.get("encoding")
            if (encoding is not None and str(encoding).lower() != "yyyymmdd") or not (NUMERIC.match(kind) if parameter.endswith("number") else TEXT.match(kind)):
                fail("time.field", "日期编码与参数类型不一致。")
            def decode(value):
                return f"TO_DATE(CAST({value} AS TEXT), 'YYYYMMDD')" if dialect == "postgres" else f"STR_TO_DATE(CAST({value} AS CHAR), '%Y%m%d')"
            date, start_day, end_day = decode(date_column), decode(start), decode(end)
        predicate = f"{date_column} >= {start} AND {date_column} <= {end}"
        if parameter == "date": start_day, end_day = start, end
    elif parameter == "timestamp":
        seconds = instant(date_column, date_definition, "time.field")
        if dialect == "postgres":
            local = f"(TO_TIMESTAMP(FLOOR({seconds})) AT TIME ZONE {zone})"
            lower, upper = (f"EXTRACT(EPOCH FROM ({b} AT TIME ZONE {zone}))" for b in (start, end))
        else:
            mysql_timezones.add(business_timezone)
            local = f"CONVERT_TZ(TIMESTAMPADD(MICROSECOND, ({seconds}) * 1000000, {epoch}), '+00:00', {zone})"
            lower, upper = (f"CAST(TIMESTAMPDIFF(MICROSECOND, {epoch}, CONVERT_TZ({b}, {zone}, '+00:00')) AS DECIMAL(30, 6)) / 1000000.0" for b in (start, end))
        date = f"CAST({local} AS DATE)"
        if NUMERIC.match(kind):
            factor = 1000 if extra.get("encoding") == "epoch_milliseconds" else 1
            predicate = f"{date_column} >= ({lower}) * {factor} AND {date_column} < ({upper}) * {factor}"
        else:
            predicate = f"({seconds}) >= ({lower}) AND ({seconds}) < ({upper})"
        start_day = f"CAST({start} AS DATE)"
        end_day = f"CAST({end} AS DATE) - 1" if dialect == "postgres" else f"DATE_SUB(CAST({end} AS DATE), INTERVAL 1 DAY)"
    else: fail("time.date_parameter_type", "不支持此日期参数。")
    return EventTimePlan(event_instant, raw, date, predicate, bounds, business_timezone,
                         tuple(sorted(naive)), mysql_utc, tuple(sorted(mysql_timezones)), parameter, start_day, end_day)
