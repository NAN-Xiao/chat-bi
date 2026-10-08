from types import SimpleNamespace

def field(name):
    return {"table": "events", "field": name}

def event(name):
    return {"kind": "tracking-event", "eventTable": "events", "eventNameField": "kind", "eventName": name, "field": "kind"}

FIELDS = {"id": {"type": "bigint", "field_role": "event_id"},
          "actor": {"type": "text"}, "kind": {"type": "text"},
          "occurred_at": {"type": "timestamptz", "field_role": "event_time"},
          "day": {"type": "date"}, "amount": {"type": "numeric"},
          "channel": {"type": "text"}, "session": {"type": "text"}, "payload": {"type": "jsonb"}}
ALLOWED = {"events": set(FIELDS)}
TRACKING = {"enabled": True, "default_event_table": "events", "default_event_name_field": "kind",
            "default_event_time_field": "occurred_at", "event_name_mappings": [{"event_name": name} for name in ("convert", "email", "search")]}

def config(method="linear", aggregation="sum", direct=True):
    return {"analysisModel": "attribution", "chart": {"type": "table"},
            "time": {"field": field("day"), "dateParameterType": "date", "dateExpression": {"version":1,"mode":"preset","preset":"past_7_days"}}, "groups": [], "filters": {},
            "attribution": {"entityField": field("actor"), "targetEvent": event("convert"),
                "targetEventFilters": {}, "method": method, "window": {"mode": "same_day", "value": 1, "unit": "day"},
                "targetMetric": {"aggregation": aggregation, "metricField": field("amount") if aggregation != "count" else None},
                "includeDirect": direct, "events": [{"event": event(n), "filters": {}, "relatedProperty": {"enabled": False}} for n in ("email", "search")]}}

def context(_):
    return {"schema": "# Table: events\n[\n" + "\n".join(f"({k}:{v['type']})," for k,v in FIELDS.items()) + "\n]",
        "allowed_tables": ["events"], "allowed_fields_by_table": ALLOWED, "sql_dialect": "postgres",
        "tracking_metadata": {**TRACKING, "fields": [{"table_name": "events", "field_name": k, **v} for k,v in FIELDS.items()]},
        "event_scope": {}, "datasource": SimpleNamespace(type="postgresql")}

def plan(conf=None, **kw):
    from apps.dashboard.crud.attribution_sql_plan import build_attribution_plan
    args = {"metadata_fields": {"events": FIELDS}, "allowed_fields_by_table": ALLOWED,
            "tracking_metadata": TRACKING, "table_filters": {}, "dialect": "postgres", "engine": "postgresql", "business_timezone": "Asia/Shanghai"}
    args.update(kw)
    return build_attribution_plan(conf or config(), **args)
