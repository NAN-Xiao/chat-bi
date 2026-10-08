"""Generic, authorized event metadata for compiler tests."""
from copy import deepcopy

FIELDS = {"events": {"action": {"type": "text"}, "actor": {"type": "text"},
    "day_key": {"type": "integer"}, "amount": {"type": "numeric"},
    "category": {"type": "text"}, "region": {"type": "text"}, "payload": {"type": "jsonb"}}}
TRACKING = {"enabled": True, "default_event_table": "events", "default_event_name_field": "action",
    "event_name_mappings": [{"event_name": name, "event_table": "events", "event_name_field": "action",
        "properties": [{"property_name": "value", "source_field": "payload", "json_path": "$.value", "property_type": "number"}]}
        for name in ("View", "Pay")]}

def field(name): return {"table": "events", "field": name}
def event(name):
    return {"kind": "tracking-event", "eventTable": "events", "eventNameField": "action", "eventName": name}
def metric(name="View", aggregation="count", alias="次数", mid="m1", measure="actor"):
    return {"id": mid, "alias": alias, "field": event(name), "metricField": field(measure),
            "aggregation": aggregation, "filters": {"logic": "and", "rules": []}}
def config(aggregation="count", groups=False, card=False):
    return {"analysisModel": "event", "chart": {"type": "metric" if card else "table"},
        "time": {"field": field("day_key"), "grain": "day", "dateParameterType": "yyyymmdd_number",
                 "dateExpression": {"version": 1, "mode": "preset", "preset": "recent_30_days"}},
        "metrics": [metric(aggregation=aggregation, measure="amount" if aggregation in {"sum","avg","max","min"} else "actor")],
        "groups": [field("category")] if groups else [], "filters": {"logic":"and", "rules":[]}}
def formula_config(groups=True):
    c = config(groups=groups)
    c["metrics"] = [metric("Pay","sum","金额","money","amount"), metric("View","count_distinct","人数","people")]
    c["formulaMetrics"] = [{"id":"f1","alias":"人均金额","decimalPlaces":2,"tokens":[
        {"type":"metric","metricId":"money"},{"type":"operator","value":"/"},{"type":"metric","metricId":"people"}]}]
    return c
def build(conf=None, *, fields=None, tracking=None, allowed=None, dialect="postgres", policy=None):
    from apps.dashboard.crud import ai_sql_generator as g
    from apps.dashboard.models.dashboard_model import DashboardAiSqlGenerateRequest
    from apps.dashboard.crud.event_sql_plan import build_event_plan
    conf = deepcopy(conf if conf is not None else config())
    normalized = g._normalize_manual_config(DashboardAiSqlGenerateRequest(datasource=1, chart_type=conf["chart"]["type"], context=conf), datasource_type=dialect)
    return build_event_plan(normalized, g._build_formula_ir(normalized, validate_atomic_metrics=False), metadata_fields=deepcopy(fields or FIELDS),
        allowed_fields_by_table=allowed if allowed is not None else {t:set(f) for t,f in (fields or FIELDS).items()},
        tracking_metadata=deepcopy(tracking if tracking is not None else TRACKING), table_filters=policy or {},
        dialect=dialect, engine=dialect, business_timezone="Asia/Shanghai")

def context(state):
    from types import SimpleNamespace
    schema = "# Table: events\n" + "\n".join(f"({n}: {d['type']})" for n,d in FIELDS["events"].items())
    return {"schema":schema,"tracking_metadata":deepcopy(TRACKING),"allowed_tables":["events"],
        "allowed_fields_by_table":{"events":set(FIELDS["events"])},"sql_dialect":"postgres", "tenant_id":99,
        "datasource":SimpleNamespace(type="postgres",name="generic"),"event_scope":{"status":"active","issues":[]}}
