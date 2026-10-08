"""Authorized, domain-neutral distribution fixtures shared by behavior tests."""
import copy
import importlib
import importlib.util


def module(name="distribution_sql_plan"):
    path = "apps.dashboard.crud." + name
    assert importlib.util.find_spec(path) is not None, f"missing deterministic compiler module: {name}"
    return importlib.import_module(path)


def field(name, table="events"):
    return {"table": table, "field": name}


def event(name):
    return {"kind": "tracking-event", "table": "events", "field": "action",
            "eventTable": "events", "eventNameField": "action", "eventName": name}


FIELDS = {"subject": {"type": "varchar"}, "action": {"type": "varchar"},
          "dt": {"type": "integer"}, "category": {"type": "varchar"},
          "amount": {"type": "numeric"}, "tag": {"type": "varchar"}, "payload": {"type": "jsonb"},
          "occurred_at": {"type": "bigint", "field_role": "event_time",
                          "extra_properties": {"encoding": "epoch_milliseconds"}}}
TRACKING = {"enabled": True, "default_event_table": "events", "default_event_name_field": "action",
            "event_name_mappings": [{"event_name": name} for name in ("A", "B")]}


def config():
    return {"analysisModel": "distribution", "chart": {"type": "table"}, "groups": [], "filters": {},
            "time": {"field": field("dt"), "grain": "day", "dateParameterType": "yyyymmdd_number",
                     "dateExpression": {"version": 1, "mode": "preset", "preset": "past_7_days"}},
            "distribution": {"entityField": field("subject"), "event": event("A"), "eventFilters": {},
                             "metric": {"kind": "count", "field": None, "aggregation": "sum"},
                             "interval": {"mode": "discrete", "customBounds": []},
                             "simultaneous": {"enabled": False, "event": None, "aggregation": "count", "metricField": None}}}


def plan(conf=None, *, dialect="postgres", fields=None, tracking=None, allowed=None, policies=None):
    metadata = copy.deepcopy(FIELDS if fields is None else fields)
    return module().build_distribution_plan(config() if conf is None else conf,
        metadata_fields={"events": metadata}, allowed_fields_by_table={"events": set(metadata) if allowed is None else allowed},
        tracking_metadata=copy.deepcopy(TRACKING if tracking is None else tracking),
        table_filters=policies or {}, dialect=dialect, engine=dialect)


def property_config(aggregation="sum"):
    c = config()
    c["distribution"]["metric"] = {"kind": "property", "field": field("amount"), "aggregation": aggregation}
    return c


def simultaneous(c, aggregation="count", name="amount"):
    c["distribution"]["simultaneous"] = {"enabled": True, "event": event("B"),
        "aggregation": aggregation, "metricField": None if aggregation == "count" else field(name)}
    return c
