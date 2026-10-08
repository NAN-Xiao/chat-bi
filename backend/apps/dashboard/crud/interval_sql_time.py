"""Interval calendar scaffolding over the shared event-time contract."""
from apps.dashboard.crud.analysis_event_time import build_event_time_plan
from apps.dashboard.crud.interval_sql_plan import IntervalTimePlan, fail
from apps.dashboard.crud.sql_generation_rules import build_daily_date_scaffold


def build_interval_time_plan(config, *, metadata_fields, dialect, engine, business_timezone, tracking_metadata):
    t = build_event_time_plan(table=((config.get("interval") or {}).get("startEvent") or {}).get("eventTable"),
        time_config=config.get("time") or {}, metadata_fields=metadata_fields,
        allowed_fields_by_table={table: set(fields) for table, fields in metadata_fields.items()},
        dialect=dialect, engine=engine, business_timezone=business_timezone,
        tracking_metadata=tracking_metadata, parameter_cte="interval_parameter_bounds", fail=fail)
    scaffold = build_daily_date_scaffold(t.start_day, t.end_day, dialect)
    if not scaffold["supported"]: fail("time", scaffold["reason"])
    return IntervalTimePlan(t.instant, t.raw_time, t.date, t.predicate, t.bounds, scaffold["cte_sql"],
                           t.business_timezone, t.naive_timezones, t.mysql_utc, t.mysql_timezones, t.parameter_type)
