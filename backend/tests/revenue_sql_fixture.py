from types import SimpleNamespace


def field(name):
    return {"table": "events", "field": name}


def event(name):
    return {"kind": "tracking-event", "eventTable": "events", "eventNameField": "event_name",
            "eventName": name, "field": "event_name"}


def config(method="property_sum", days=2, cost=False):
    return {"analysisModel": "revenue", "chart": {"type": "table"},
            "time": {"field": field("day"), "dateParameterType": "yyyymmdd_number",
                     "dateExpression": {"version": 1, "mode": "preset", "preset": "past_7_days"}},
            "revenue": {"entityField": field("subject"), "initialEvent": event("start"),
                        "paymentEvent": event("purchase"), "metricEvent": event("purchase"), "metric": {
                            "method": method, "field": field("amount") if method.startswith("property_") else None},
                        "cost": {"enabled": cost, "method": "property_sum" if cost else None, "event": event("purchase") if cost else None, "field": field("cost") if cost else None},
                        "observationDays": days}, "filters": {}, "groups": []}


FIELDS = {"subject": {"type": "varchar"}, "day": {"type": "integer"},
          "event_name": {"type": "varchar"}, "category": {"type": "varchar"},
          "amount": {"type": "numeric"}, "cost": {"type": "numeric"}, "payload": {"type": "jsonb"}}
ALLOWED = {"events": set(FIELDS)}
METHODS = ["count", "entity_count", "per_entity_count", "period_cumulative_count", "period_average_count",
           "period_cumulative_entity_count", "period_average_entity_count", "property_sum", "property_avg"]


def context(_):
    return {"schema": "# Table: events\n[\n" + "\n".join(f"({k}:{v['type']})," for k, v in FIELDS.items()) + "\n]",
            "allowed_tables": ["events"], "allowed_fields_by_table": ALLOWED,
            "sql_dialect": "postgres", "tracking_metadata": {}, "event_scope": {},
            "datasource": SimpleNamespace(type="postgresql")}


def plan(conf=None, fields=None, dialect="postgres", tracking=None, allowed=None, policies=None):
    from apps.dashboard.crud.revenue_sql_plan import build_revenue_plan
    return build_revenue_plan(conf or config(), metadata_fields={"events": fields or FIELDS},
                              allowed_fields_by_table=allowed or ALLOWED, dialect=dialect,
                              tracking_metadata=tracking, table_filters=policies)
