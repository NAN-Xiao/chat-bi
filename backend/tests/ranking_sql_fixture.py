from types import SimpleNamespace


def field(name):
    return {"table": "events", "field": name}


def event(name):
    return {"kind": "tracking-event", "eventTable": "events", "eventNameField": "event_name",
            "eventName": name, "field": "event_name"}


def config(aggregation="count", tie="skip", direction="desc", properties=True):
    return {"analysisModel": "ranking", "chart": {"type": "table"}, "groups": [], "filters": {},
            "time": {"field": field("day"), "dateParameterType": "yyyymmdd_number",
                     "dateExpression": {"version": 1, "mode": "preset", "preset": "past_7_days"}},
            "ranking": {"entityField": field("subject"), "metric": {
                "event": event("visit"), "aggregation": aggregation,
                "metricField": field("amount") if aggregation != "count" else None, "direction": direction},
                "tieHandling": tie, "simultaneousMetrics": [
                    {"event": event("purchase"), "aggregation": "sum", "metricField": field("amount")},
                    {"event": event("purchase"), "aggregation": "count"}],
                "simultaneousProperties": [field("category")] if properties else []}}


FIELDS = {"subject": {"type": "varchar"}, "day": {"type": "integer"}, "event_name": {"type": "varchar"},
          "category": {"type": "varchar"}, "amount": {"type": "numeric"}, "payload": {"type": "jsonb"}}
ALLOWED = {"events": set(FIELDS)}


def plan(conf=None, fields=None, allowed=None, dialect="postgres", tracking=None, policies=None):
    from apps.dashboard.crud.ranking_sql_plan import build_ranking_plan
    return build_ranking_plan(config() if conf is None else conf, metadata_fields={"events": FIELDS if fields is None else fields},
        allowed_fields_by_table=ALLOWED if allowed is None else allowed, dialect=dialect,
        tracking_metadata=tracking, table_filters=policies)


def context(_):
    return {"schema": "# Table: events\n[\n" + "\n".join(f"({k}:{v['type']})," for k,v in FIELDS.items()) + "\n]",
        "allowed_tables": ["events"], "allowed_fields_by_table": ALLOWED, "sql_dialect": "postgres",
        "tracking_metadata": {}, "event_scope": {}, "tenant_id": 99, "datasource": SimpleNamespace(type="postgresql")}
