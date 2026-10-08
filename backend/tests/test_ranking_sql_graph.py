import asyncio
import pytest
from apps.dashboard.crud import ai_sql_generator as generator
from apps.dashboard.models.dashboard_model import DashboardAiSqlGenerateRequest
from ranking_sql_fixture import config, context, field


def run(monkeypatch, conf, collector=context):
    def forbidden(*a, **kw): pytest.fail("排行榜不得创建或调用 LLM")
    for name in ("_create_dashboard_ai_sql_llm", "_async_invoke_llm_json", "_dashboard_config_prompt"):
        monkeypatch.setattr(generator, name, forbidden)
    monkeypatch.setattr(generator, "_node_collect_context", collector)
    request = DashboardAiSqlGenerateRequest(datasource=1,chart_type="table",context=conf)
    return asyncio.run(generator._build_manual_chart_graph().ainvoke({"request":request,"graph_trace":[]}))


@pytest.mark.parametrize("aggregation", ["count","count_distinct","sum","avg","min","max"])
def test_ranking_generates_and_explains_without_llm(monkeypatch,aggregation):
    response = run(monkeypatch,config(aggregation))["response"]
    assert response.success, response.issues
    assert response.result_config["type"] == "ranking_table"
    assert response.result_config["execution_contract"]["kind"] == "ranking"
    assert "ranking-contract-v1" in response.sql


@pytest.mark.parametrize("scenario", ["invalid","revoked","tampered","dialect"])
def test_failure_paths_never_fall_back_to_llm(monkeypatch,scenario):
    conf = config(); collector = context
    if scenario == "invalid": conf["ranking"]["tieHandling"] = "unknown"
    if scenario == "revoked": collector = lambda s: {**context(s),"allowed_fields_by_table":{"events":{"subject"}}}
    if scenario == "dialect": collector = lambda s: {**context(s),"sql_dialect":"sqlite"}
    if scenario == "tampered": monkeypatch.setattr(generator,"compile_ranking_sql",lambda p: "SELECT 1 AS wrong",raising=False)
    state = run(monkeypatch,conf,collector)
    assert not state["response"].success
    assert state["response"].sql == ""
    assert state["response"].issues
    assert generator._route_after_sql_validate(state) == "explain_advice"


def test_ranking_repair_is_closed(monkeypatch):
    def forbidden(*a,**k): pytest.fail("repair created LLM")
    monkeypatch.setattr(generator,"_create_dashboard_ai_sql_llm",forbidden)
    state = asyncio.run(generator._async_node_repair_sql({"normalized_config":{"analysis_model":"ranking"}}))
    assert not state["response"].success


def test_required_filters_apply_to_every_metric_outside_global_or(monkeypatch):
    def scoped(s):
        return {**context(s),"tracking_metadata":{"tenant_id":99,"datasource_id":1,"tables":[{
            "table_name":"events","extra_properties":{"required_filters":{"rules":[{
                "field":"category","operator":"eq","value":"allowed"}]}}}]}}
    conf = config(); conf["filters"] = {"logic":"or","rules":[
        {"field":field("subject"),"operator":"eq","value":"A"},
        {"field":field("subject"),"operator":"eq","value":"B"}]}
    response = run(monkeypatch,conf,scoped)["response"]
    assert response.success, response.issues
    assert response.sql.count('"category" = \'allowed\'') == 3
