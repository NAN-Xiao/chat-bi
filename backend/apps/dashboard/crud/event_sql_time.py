"""Typed calendar boundaries for event aggregation, without exact-event-time assumptions."""
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from sqlglot import exp
from apps.dashboard.crud.dashboard_date_filter import dashboard_date_parameter_tokens
from apps.dashboard.crud.property_sql_plan import NUMERIC, _bucket
from apps.dashboard.crud.sql_generation_rules import build_daily_date_scaffold

@dataclass(frozen=True)
class EventAggregationTimePlan:
    predicate: str = "TRUE"
    bucket: str = ""
    scaffold_ctes: str = ""
    scaffold_bucket: str = ""
    output_expression: str = ""
    alias: str = ""
    grain: str = ""
    parameter_type: str = ""

def build_event_aggregation_time_plan(time_config: dict, *, resolver, dialect: str,
        engine: str, business_timezone: str, include_date: bool) -> EventAggregationTimePlan:
    from apps.dashboard.crud.event_sql_plan import fail
    value=time_config.get("field")
    if not value:
        if include_date: fail("time.field", "日期趋势必须选择授权时间字段。")
        return EventAggregationTimePlan()
    column, definition=resolver.field(value,"time.field")
    kind=definition.get("type","").lower()
    parameter=time_config.get("date_parameter_type") or time_config.get("dateParameterType")
    tokens=dashboard_date_parameter_tokens(parameter)
    if not tokens: fail("time.dateParameterType","日期参数类型无效。")
    start,end=tokens
    start_day,end_day=start,end
    if parameter in {"yyyymmdd_number","yyyymmdd_text"}:
        if parameter=="yyyymmdd_number" and not NUMERIC.match(kind) or parameter=="yyyymmdd_text" and not kind.startswith(("varchar","char","text","string")):
            fail("time.field","时间字段类型与日期参数不匹配。")
        def parsed(item):
            return f"TO_DATE(CAST({item} AS TEXT), 'YYYYMMDD')" if dialect=="postgres" else f"STR_TO_DATE(CAST({item} AS CHAR), '%Y%m%d')"
        date=parsed(column);start_day,end_day=parsed(start),parsed(end)
    elif parameter=="date" and kind=="date": date=column
    elif parameter=="timestamp":
        try: ZoneInfo(business_timezone)
        except (ZoneInfoNotFoundError,ValueError,TypeError):fail("time.timezone","业务时区配置无效。")
        zone=exp.Literal.string(business_timezone).sql(dialect=dialect)
        start_day=f"CAST({start} AS DATE)"
        end_day=f"CAST({end} AS DATE) - 1" if dialect=="postgres" else f"DATE_SUB(CAST({end} AS DATE), INTERVAL 1 DAY)"
        extra=definition.get("extra_properties") or {}
        if NUMERIC.match(kind):
            encoding=extra.get("encoding")
            if encoding not in {"epoch_seconds","epoch_milliseconds"}:fail("time.field","数值时间必须声明秒或毫秒编码。")
            factor=1000 if encoding=="epoch_milliseconds" else 1
            if dialect=="postgres":
                date=f"CAST(TO_TIMESTAMP({column} / {factor}.0) AT TIME ZONE {zone} AS DATE)"
                start,end=(f"(EXTRACT(EPOCH FROM ({t} AT TIME ZONE {zone})) * {factor})" for t in tokens)
            else:
                epoch="CAST('1970-01-01 00:00:00' AS DATETIME)"
                date=f"CAST(CONVERT_TZ(TIMESTAMPADD(SECOND, {column} / {factor}.0, {epoch}), '+00:00', {zone}) AS DATE)"
                start,end=(f"(TIMESTAMPDIFF(SECOND, {epoch}, CONVERT_TZ({t}, {zone}, '+00:00')) * {factor})" for t in tokens)
        elif kind.startswith(("timestamp","datetime","timestamptz")):
            aware=kind=="timestamptz" or "with time zone" in kind
            if aware:
                if dialect!="postgres":fail("time.field","当前方言未支持带时区时间。")
                date=f"CAST({column} AT TIME ZONE {zone} AS DATE)"
                start,end=(f"({t} AT TIME ZONE {zone})" for t in tokens)
            else:
                source_zone=extra.get("timezone")
                try:ZoneInfo(source_zone)
                except (ZoneInfoNotFoundError,ValueError,TypeError):fail("time.field","无时区时间字段必须声明有效源时区。")
                source=exp.Literal.string(source_zone).sql(dialect=dialect)
                if dialect=="postgres":
                    date=f"CAST(({column} AT TIME ZONE {source}) AT TIME ZONE {zone} AS DATE)"
                    start,end=(f"(({t} AT TIME ZONE {zone}) AT TIME ZONE {source})" for t in tokens)
                else:
                    # MySQL TIMESTAMP depends on session timezone. Such schemas need
                    # an execution contract; a plain compiler must not guess it.
                    if kind.startswith("timestamp") and not any(n in engine.lower() for n in ("doris","starrocks","analyticdb")):
                        fail("time.field","MySQL TIMESTAMP 需要明确会话时区执行配置；请使用已配置 DATETIME 日期字段。")
                    date=f"CAST(CONVERT_TZ({column}, {source}, {zone}) AS DATE)"
                    start,end=(f"CONVERT_TZ({t}, {zone}, {source})" for t in tokens)
        else:fail("time.field","时间字段类型与日期参数不匹配。")
    else:fail("time.field","时间字段类型与日期参数不匹配。")
    predicate=f"{column} >= {start} AND {column} {'<' if parameter=='timestamp' else '<='} {end}"
    grain=time_config.get("grain") or "day"
    if not include_date:return EventAggregationTimePlan(predicate=predicate,parameter_type=parameter)
    if not isinstance(grain,str) or grain not in {"day","week","month"}:fail("time.grain","不支持的时间粒度。")
    scaffold=build_daily_date_scaffold(start_day,end_day,dialect)
    if not scaffold["supported"]:fail("time",scaffold["reason"])
    bucket=_bucket(date,grain,dialect)
    scaffold_bucket=_bucket("dashboard_dates.calendar_date",grain,dialect)
    # Parameter encoding belongs to the fact predicate. Trend consumers need a
    # real calendar date, independent of whether the physical partition is an
    # integer, text, DATE or timestamp. Keep only the configured output name.
    output="k.chart_date"
    return EventAggregationTimePlan(predicate,bucket,scaffold["cte_sql"],scaffold_bucket,output,value.get("field"),grain,parameter)
