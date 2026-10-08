import copy


def field(name):
    return {"table": "events", "field": name}


def event(name):
    return {"kind": "tracking-event", "table": "events", "field": "action", "eventTable": "events",
            "eventNameField": "action", "eventName": name}


FIELDS = {"subject": {"type": "text", "field_role": "subject_id"}, "action": {"type": "text"},
          "category": {"type": "text"}, "payload": {"type": "json"},
          "sequence": {"type": "bigint", "field_role": "event_sequence"},
          "occurred_at": {"type": "bigint", "field_role": "event_time", "extra_properties": {"encoding": "epoch_milliseconds"}},
          "day": {"type": "date"}}
TRACKING = {"enabled": True, "default_event_table": "events", "default_subject_field": "subject",
            "default_event_name_field": "action", "default_event_time_field": "occurred_at", "tables": [],
            "event_name_mappings": [{"event_name": name, "event_table": "events", "event_name_field": "action",
                "properties": [{"property_name": "score", "source_field": "payload", "json_path": "$.score", "property_type": "int"}]}
                for name in ("A", "B", "C")]}


def config():
    return {"analysisModel": "path", "analysis_model": "path", "chart": {"type": "sankey"},
            "time": {"field": field("day"), "grain": "day", "dateParameterType": "date",
                     "dateExpression": {"version": 1, "mode": "preset", "preset": "past_7_days"}},
            "groups": [], "filters": {}, "path": {"events": [{"event": event(n), "splitProperties": []} for n in "ABC"],
                "initialEvent": event("A"), "sessionGapSeconds": 1800}}


def plan(c=None, *, fields=None, tracking=None, allowed=None, dialect="postgres", engine=None, table_filters=None):
    from apps.dashboard.crud.path_sql_plan import build_path_plan
    f = copy.deepcopy(FIELDS if fields is None else fields)
    return build_path_plan(c or config(), metadata_fields={"events": f},
        allowed_fields_by_table={"events": set(f) if allowed is None else allowed}, dialect=dialect,
        engine=engine or dialect, tracking_metadata=copy.deepcopy(TRACKING if tracking is None else tracking),
        table_filters=table_filters or {}, business_timezone="Asia/Shanghai")
