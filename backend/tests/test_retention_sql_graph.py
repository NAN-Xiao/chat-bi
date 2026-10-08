import asyncio

import pytest

from apps.dashboard.crud import ai_sql_generator as generator
from apps.dashboard.models.dashboard_model import DashboardAiSqlGenerateRequest


def field(name, table="events"):
    return {"table": table, "field": name}


def event(name, table="events"):
    return {"kind": "tracking-event", "eventTable": table, "eventNameField": "event_name",
            "eventName": name, "field": "event_name"}


def config():
    return {"analysisModel": "retention", "chart": {"type": "table"},
            "time": {"field": field("day"), "dateParameterType": "yyyymmdd_number",
                     "dateExpression": {"version": 1, "mode": "preset", "preset": "past_7_days"}},
            "retention": {"entityField": field("subject"), "initialEvent": event("start"),
                          "returnEvent": event("return"), "simultaneous": {"enabled": False},
                          "relatedProperty": {"enabled": False}}, "filters": {}, "groups": []}


FIELDS = {"subject": {"type": "varchar"}, "day": {"type": "integer"},
          "event_name": {"type": "varchar"}, "category": {"type": "varchar"}, "amount": {"type": "numeric"}}
ALLOWED = {"events": set(FIELDS)}


def context(_):
    return {"schema": "# Table: events\n[\n" + "\n".join(f"({k}:{v['type']})," for k, v in FIELDS.items()) + "\n]",
            "allowed_tables": ["events"], "allowed_fields_by_table": ALLOWED,
            "sql_dialect": "postgres", "tracking_metadata": {}, "event_scope": {}, "datasource": None}


@pytest.mark.parametrize("scenario", ["valid", "same_event", "config_error", "compile_error", "sql_error", "revoked"])
def test_retention_graph_never_calls_llm(monkeypatch, scenario):
    def forbidden(*args, **kwargs):
        raise AssertionError("retention must never create an LLM")
    monkeypatch.setattr(generator, "_create_dashboard_ai_sql_llm", forbidden)
    monkeypatch.setattr(generator, "_node_collect_context", context)
    conf = config()
    if scenario == "same_event":
        conf["retention"]["returnEvent"] = event("start")
    if scenario == "config_error":
        conf["retention"]["simultaneous"] = {"enabled": "false"}
    if scenario == "compile_error":
        conf["time"]["dateParameterType"] = "timestamp"  # numeric time needs explicit epoch metadata
    if scenario == "sql_error":
        monkeypatch.setattr(generator, "compile_retention_sql", lambda p: "SELECT 1 AS wrong", raising=False)
    if scenario == "revoked":
        monkeypatch.setattr(generator, "_node_collect_context", lambda s: {**context(s), "allowed_fields_by_table": {"events": {"day"}}})
    req = DashboardAiSqlGenerateRequest(datasource=1, chart_type="table", context=conf)
    result = asyncio.run(generator._build_manual_chart_graph().ainvoke({"request": req, "graph_trace": []}))
    assert result["response"].success is (scenario in {"valid", "same_event"}), result["response"].issues
    assert generator._route_after_sql_validate(result) == "explain_advice"
    assert "repair_retention_sql" not in str(result.get("graph_trace"))
    if scenario == "valid":
        assert result["response"].result_config["type"] == "cohort_table"


def test_retention_repair_node_is_closed(monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError("repair must not create LLM")
    monkeypatch.setattr(generator, "_create_dashboard_ai_sql_llm", forbidden)
    result = asyncio.run(generator._async_node_repair_sql({"normalized_config": {"analysis_model": "retention"}}))
    assert result["response"].success is False


def test_retention_required_filter_is_compiled_for_every_source(monkeypatch):
    def scoped(s):
        return {**context(s), "tenant_id": 99, "tracking_metadata": {"tenant_id": 99, "datasource_id": 1,
                "tables": [{"table_name": "events", "extra_properties": {
            "required_filters": {"rules": [{"field": "category", "operator": "eq", "value": "allowed"}]}
        }}]}}
    monkeypatch.setattr(generator, "_node_collect_context", scoped)
    req = DashboardAiSqlGenerateRequest(datasource=1, chart_type="table", context=config())
    result = asyncio.run(generator._build_manual_chart_graph().ainvoke({"request": req, "graph_trace": []}))
    assert result["response"].success, result["response"].issues
    assert result["response"].sql.count('"category" = \'allowed\'') == 2
