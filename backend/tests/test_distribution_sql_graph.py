import asyncio
import copy
from types import SimpleNamespace

import pytest

from apps.dashboard.crud import ai_sql_generator as generator
from apps.dashboard.models.dashboard_model import DashboardAiSqlGenerateRequest
from distribution_sql_fixture import config, field, property_config, simultaneous, FIELDS, TRACKING


def context(_):
    tracking=copy.deepcopy(TRACKING)
    tracking["fields"]=[{"table_name":"events","field_name":k,**v} for k,v in FIELDS.items()]
    return {"schema":"# Table: events\n[\n"+"\n".join(f"({k}:{v['type']})," for k,v in FIELDS.items())+"\n]",
            "allowed_tables":["events"], "allowed_fields_by_table":{"events":set(FIELDS)},
            "sql_dialect":"postgres", "tracking_metadata":tracking, "event_scope":{}, "datasource":None}


@pytest.mark.parametrize("case",["valid","simultaneous","custom","property","config_error","plan_error","compile_error","sql_error","revoked","no_metadata"])
def test_distribution_graph_cannot_enter_model_on_any_outcome(monkeypatch,case):
    def forbidden(*a,**kw): pytest.fail("distribution attempted model/prompt access")
    monkeypatch.setattr(generator,"_create_dashboard_ai_sql_llm",forbidden)
    monkeypatch.setattr(generator,"_dashboard_sql_system_prompt",forbidden)
    monkeypatch.setattr(generator,"_node_collect_context",context)
    c=config()
    if case=="simultaneous": c=simultaneous(c,"avg")
    if case=="custom": c["distribution"]["interval"]={"mode":"custom","customBounds":[0,10]}
    if case=="property": c=property_config("median")
    if case=="config_error": c["distribution"]["interval"]["mode"]="unknown"
    if case=="plan_error": c["distribution"]["event"]["eventName"]="unknown"
    if case=="compile_error":
        def broken(_): raise ValueError("compiler failure")
        monkeypatch.setattr(generator,"compile_distribution_sql",broken,raising=False)
    if case=="sql_error": monkeypatch.setattr(generator,"compile_distribution_sql",lambda p:"SELECT 1 AS wrong",raising=False)
    if case=="revoked": monkeypatch.setattr(generator,"_node_collect_context",lambda s:{**context(s),"allowed_fields_by_table":{"events":{"dt"}}})
    if case=="no_metadata": monkeypatch.setattr(generator,"_node_collect_context",lambda s:{**context(s),"tracking_metadata":{}})
    req=DashboardAiSqlGenerateRequest(datasource=1,context=c)
    state=asyncio.run(generator._build_manual_chart_graph().ainvoke({"request":req,"graph_trace":[]}))
    result=state["response"]
    assert result.success is (case in {"valid","simultaneous","custom","property"}),result.issues
    assert generator._route_after_sql_validate(state)=="explain_advice"
    assert result.analysis_model=="distribution" and result.chart_type=="table"
    if not result.success: assert result.issues


def test_direct_repair_entry_cannot_call_model(monkeypatch):
    monkeypatch.setattr(generator,"_create_dashboard_ai_sql_llm",lambda *a,**kw:pytest.fail("no repair model"))
    result=asyncio.run(generator._async_node_repair_sql({"normalized_config":{"analysis_model":"distribution"}}))
    assert not result["response"].success


@pytest.mark.parametrize("entry",["compile_distribution_dashboard_sql","compile_dashboard_sql","generate_dashboard_ai_sql"])
def test_service_entries_use_same_compiler_without_ai(monkeypatch,entry):
    assert hasattr(generator,entry),"dedicated compiler service is missing"
    monkeypatch.setattr(generator,"_node_collect_context",context)
    monkeypatch.setattr(generator,"MANUAL_CHART_GRAPH",generator._build_manual_chart_graph())
    monkeypatch.setattr(generator,"_create_dashboard_ai_sql_llm",lambda *a,**kw:pytest.fail("no model"))
    result=asyncio.run(getattr(generator,entry)(None,None,DashboardAiSqlGenerateRequest(datasource=1,context=config())))
    assert result.success,result.issues
    assert result.result_config["type"]=="distribution_table"


def test_required_policy_reaches_both_event_sources(monkeypatch):
    def scoped(s):
        result=context(s); result["tenant_id"]=99
        result["tracking_metadata"].update(tenant_id=99,datasource_id=1,tables=[{"table_name":"events","extra_properties":{
            "required_filters":{"rules":[{"field":"category","operator":"eq","value":"allowed"}]}}}])
        return result
    monkeypatch.setattr(generator,"_node_collect_context",scoped)
    monkeypatch.setattr(generator,"_create_dashboard_ai_sql_llm",lambda *a,**kw:pytest.fail("no model"))
    req=DashboardAiSqlGenerateRequest(datasource=1,context=simultaneous(config()))
    state=asyncio.run(generator._build_manual_chart_graph().ainvoke({"request":req}))
    assert state["response"].success,state["response"].issues
    assert state["response"].sql.count('"category" = \'allowed\'')==2


def test_real_collector_has_no_ai_dependencies(monkeypatch):
    from apps.datasource.crud import sql_engine
    from apps.ai_model.embedding import EmbeddingModelCache
    datasource=SimpleNamespace(id=1,name="source",type="postgresql")
    class Session:
        def get(self,*args): return datasource
    def forbidden(*a,**kw): pytest.fail("configuration compilation invoked an AI dependency")
    monkeypatch.setattr(generator,"require_current_tenant_id",lambda user:99)
    monkeypatch.setattr(generator,"get_tracking_config",lambda *a,**kw:{"enabled":False})
    monkeypatch.setattr(generator,"_dashboard_config_prompt",forbidden)
    monkeypatch.setattr(EmbeddingModelCache,"get_model",forbidden)
    for name in ("find_data_skills","find_tracking_prompt_context","get_ai_table_schema"):
        monkeypatch.setattr(sql_engine,name,forbidden)
    monkeypatch.setattr(sql_engine,"has_datasource_access",lambda *a:True)
    monkeypatch.setattr(sql_engine,"get_compilation_table_schema",lambda **kw:("# Table: events\n[(subject:varchar)]",["events"]))
    req=DashboardAiSqlGenerateRequest(datasource=1,context=config())
    result=generator._node_collect_context({"session":Session(),"current_user":SimpleNamespace(id=1,tenant_id=99),"request":req})
    assert result["allowed_fields_by_table"]=={"events":{"subject"}}
    assert result["data_skill"]=="" and result["skill_model_id"] is None
