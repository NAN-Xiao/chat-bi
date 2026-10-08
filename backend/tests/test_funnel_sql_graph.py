import asyncio
import copy

import pytest

from apps.dashboard.crud import ai_sql_generator as generator
from apps.dashboard.models.dashboard_model import DashboardAiSqlGenerateRequest
from test_funnel_sql_plan import config, field, FIELDS, TRACKING


def context(_):
    tracking = copy.deepcopy(TRACKING)
    tracking["fields"] = [{"table_name": "events", "field_name": name, **definition} for name, definition in FIELDS.items()]
    return {"schema": "# Table: events\n[\n" + "\n".join(f"({k}:{v['type']})," for k,v in FIELDS.items()) + "\n]",
            "allowed_tables": ["events"], "allowed_fields_by_table": {"events": set(FIELDS)},
            "sql_dialect": "postgres", "tracking_metadata": tracking, "event_scope": {}, "datasource": None}


@pytest.mark.parametrize("scenario", ["valid", "same_event", "related", "config_error", "plan_error", "compile_error", "sql_error", "revoked", "no_metadata"])
def test_funnel_graph_never_calls_llm(monkeypatch, scenario):
    def forbidden(*args, **kwargs):
        pytest.fail("funnel must never create LLM")
    monkeypatch.setattr(generator, "_create_dashboard_ai_sql_llm", forbidden)
    monkeypatch.setattr(generator, "_node_collect_context", context)
    c = config()
    if scenario == "same_event": c["funnel"]["steps"][1]["event"]["eventName"] = "A"
    if scenario == "related": c["funnel"].update(relatedPropertyEnabled=True, relatedProperty=field("category"))
    if scenario == "config_error": c["funnel"]["steps"][1] = None
    if scenario == "plan_error": c["funnel"]["steps"][1]["event"]["eventName"] = "unknown"
    if scenario == "compile_error":
        def compiler(_): raise ValueError("injected compiler failure")
        monkeypatch.setattr(generator, "compile_funnel_sql", compiler, raising=False)
    if scenario == "sql_error": monkeypatch.setattr(generator, "compile_funnel_sql", lambda p: "SELECT 1 AS wrong", raising=False)
    if scenario == "revoked": monkeypatch.setattr(generator, "_node_collect_context", lambda s: {**context(s), "allowed_fields_by_table": {"events": {"dt"}}})
    if scenario == "no_metadata": monkeypatch.setattr(generator, "_node_collect_context", lambda s: {**context(s), "tracking_metadata": {}})
    req = DashboardAiSqlGenerateRequest(datasource=1, chart_type="funnel", context=c)
    result = asyncio.run(generator._build_manual_chart_graph().ainvoke({"request": req,"graph_trace":[]}))
    assert result["response"].success is (scenario in {"valid","same_event","related"}), result["response"].issues
    assert generator._route_after_sql_validate(result) == "explain_advice"
    assert "repair_funnel_sql" not in str(result.get("graph_trace"))
    if result["response"].success:
        assert result["response"].result_config["type"] == "funnel"
        assert result["response"].chart_type == "funnel"


@pytest.mark.parametrize("model", ["funnel","retention","property","interval"])
def test_deterministic_repair_entry_is_closed(monkeypatch, model):
    monkeypatch.setattr(generator,"_create_dashboard_ai_sql_llm",lambda *a,**kw: pytest.fail("repair must not call LLM"))
    result = asyncio.run(generator._async_node_repair_sql({"normalized_config":{"analysis_model":model}}))
    assert result["response"].success is False


def test_policy_applies_to_all_steps_without_overriding_user_or(monkeypatch):
    def scoped(s):
        result=context(s); result["tenant_id"]=99
        result["tracking_metadata"].update(tenant_id=99,datasource_id=1,tables=[{"table_name":"events","extra_properties":{
            "required_filters":{"rules":[{"field":"category","operator":"eq","value":"allowed"}]}}}])
        return result
    monkeypatch.setattr(generator,"_node_collect_context",scoped)
    c=config(); c["filters"]={"logic":"or","rules":[{"field":field("subject"),"operator":"eq","value":v} for v in ("u1","u2")]}
    request=DashboardAiSqlGenerateRequest(datasource=1, context=c)
    result=asyncio.run(generator._build_manual_chart_graph().ainvoke({"request":request}))
    assert result["response"].success, result["response"].issues
    assert result["response"].sql.count('"category" = \'allowed\'') == 3


@pytest.mark.parametrize("entry", ["compile_dashboard_sql", "generate_dashboard_ai_sql"])
def test_both_public_entries_compile_funnel(monkeypatch, entry):
    monkeypatch.setattr(generator,"_node_collect_context",context)
    monkeypatch.setattr(generator,"_create_dashboard_ai_sql_llm",lambda *a,**kw: pytest.fail("no model"))
    monkeypatch.setattr(generator,"MANUAL_CHART_GRAPH",generator._build_manual_chart_graph())
    response=asyncio.run(getattr(generator,entry)(None,None,DashboardAiSqlGenerateRequest(datasource=1,context=config())))
    assert response.success, response.issues
