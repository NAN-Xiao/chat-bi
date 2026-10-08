import asyncio
import pytest
from event_sql_fixture import config, formula_config, context, field
from apps.dashboard.crud import ai_sql_generator as g
from apps.dashboard.models.dashboard_model import DashboardAiSqlGenerateRequest

def run(monkeypatch,c,collector=context):
    def forbidden(*a,**k):pytest.fail("事件模型不能调用 LLM 或构造 prompt")
    for name in ("_create_dashboard_ai_sql_llm","_async_invoke_llm_json","_invoke_llm_json","_dashboard_config_prompt"):
        monkeypatch.setattr(g,name,forbidden)
    monkeypatch.setattr(g,"_node_collect_context",collector)
    return asyncio.run(g._build_manual_chart_graph().ainvoke({"request":DashboardAiSqlGenerateRequest(datasource=1,context=c,chart_type=c["chart"]["type"]),"graph_trace":[]}))

@pytest.mark.parametrize("aggregation",["count","count_distinct","sum","avg","min","max"])
def test_event_graph_never_calls_llm(monkeypatch,aggregation):
    state=run(monkeypatch,config(aggregation,groups=True));r=state["response"]
    assert r.success,r.issues
    assert r.analysis_model=="event" and r.chart_type=="table"
    assert not state.get("output_binding_issues"), "编译器最终列无需经过模型输出键绑定"

def test_formula_only_graph_keeps_original_columns_and_display_names(monkeypatch):
    c=formula_config();m=c.pop("metrics");c["metrics"]=[]
    c["formulaMetrics"][0]["tokens"][0]={"type":"atomicMetric","metric":m[0]}
    c["formulaMetrics"][0]["tokens"][2]={"type":"atomicMetric","metric":m[1]}
    r=run(monkeypatch,c)["response"];assert r.success,r.issues
    assert 'AS "人均金额"' in r.sql and "人均金额" in r.result_config["display_names"]

@pytest.mark.parametrize("scenario",["invalid","revoked","dialect","tampered"])
def test_event_failure_returns_empty_sql_without_repair(monkeypatch,scenario):
    c=config();collector=context
    if scenario=="invalid":c["metrics"].append("bad")
    if scenario=="revoked":collector=lambda s:{**context(s),"allowed_fields_by_table":{"events":{"actor"}}}
    if scenario=="dialect":collector=lambda s:{**context(s),"sql_dialect":"sqlite"}
    if scenario=="tampered":monkeypatch.setattr(g,"compile_event_sql",lambda p:"SELECT 1 AS bad",raising=False)
    state=run(monkeypatch,c,collector);r=state["response"]
    assert not r.success and r.sql=="" and r.issues
    assert all(n["node"]!="repair_sql" for n in state["graph_trace"])

def test_event_repair_is_closed(monkeypatch):
    monkeypatch.setattr(g,"_create_dashboard_ai_sql_llm",lambda *a,**k:pytest.fail("模型修复未关闭"))
    r=asyncio.run(g._async_node_repair_sql({"normalized_config":{"analysis_model":"event"}}))["response"]
    assert not r.success and r.sql==""

def test_json_event_parameter_without_client_expression_is_resolved_by_server(monkeypatch):
    c=config("sum")
    c["metrics"][0]["metricField"]={**field("value"),"kind":"tracking-property","eventName":"View","propertyName":"value",
        "sourceField":"payload","jsonPath":"$.value","isJsonSubfield":True}
    r=run(monkeypatch,c)["response"];assert r.success,r.issues
    m=c["metrics"][0];c["metrics"]=[];c["formulaMetrics"]=[{"id":"f","alias":"金额","tokens":[{"type":"atomicMetric","metric":m}]}]
    r=run(monkeypatch,c)["response"];assert r.success,r.issues

def test_every_metric_enforces_workspace_filter_outside_user_or(monkeypatch):
    def scoped(s):
        v=context(s);v["tracking_metadata"].update(tenant_id=99,datasource_id=1,tables=[{"table_name":"events","extra_properties":{"required_filters":{"rules":[{"field":"region","operator":"eq","value":"X"}]}}}]);return v
    c=formula_config();c["filters"]={"logic":"or","rules":[{"field":field("category"),"operator":"eq","value":"A"},{"field":field("category"),"operator":"eq","value":"B"}]}
    r=run(monkeypatch,c,scoped)["response"];assert r.success,r.issues
    assert r.sql.count('"region" = \'X\'')==2
