import asyncio
import pytest
from apps.dashboard.crud import ai_sql_generator as generator
from apps.dashboard.models.dashboard_model import DashboardAiSqlGenerateRequest
from attribution_compiler_fixture import config, context

def run(monkeypatch, conf, collector=context):
    def forbidden(*a, **kw): pytest.fail("归因编译及失败路径不得创建/调用 LLM 或构造模型提示词")
    for name in ("_create_dashboard_ai_sql_llm", "_async_invoke_llm_json", "_dashboard_config_prompt"):
        monkeypatch.setattr(generator, name, forbidden)
    monkeypatch.setattr(generator, "_node_collect_context", collector)
    req = DashboardAiSqlGenerateRequest(datasource=1, chart_type="table", context=conf)
    return asyncio.run(generator._build_manual_chart_graph().ainvoke({"request":req,"graph_trace":[]}))

@pytest.mark.parametrize("method,aggregation", [(m,a) for m in ("first","last") for a in ("count","sum","avg","min","max","count_distinct")] + [("linear","count"),("linear","sum")])
def test_attribution_graph_compiles_and_keeps_existing_result_contract(monkeypatch, method, aggregation):
    result = run(monkeypatch, config(method,aggregation))
    response = result["response"]
    assert response.success, response.issues
    assert response.result_config["type"] == "attribution_table"
    assert response.analysis_model == "attribution"
    assert generator._route_after_sql_validate(result) == "explain_advice"

@pytest.mark.parametrize("case", ["method","linear_avg","tamper","permissions"])
def test_graph_errors_are_explicit_without_repair(monkeypatch, case):
    conf = config(); collector = context
    if case == "method": conf["attribution"]["method"] = "invalid"
    if case == "linear_avg": conf["attribution"]["targetMetric"]["aggregation"] = "avg"
    if case == "permissions": collector = lambda s: {**context(s),"allowed_fields_by_table":{"events":{"day","kind"}}}
    if case == "tamper": monkeypatch.setattr(generator,"compile_attribution_sql",lambda p:"SELECT 1 AS wrong", raising=False)
    result = run(monkeypatch, conf, collector)
    assert not result["response"].success
    assert result["response"].sql == ""
    assert result["response"].issues

def test_repair_entry_is_closed(monkeypatch):
    def forbidden(*a, **kw): pytest.fail("repair called LLM")
    monkeypatch.setattr(generator,"_create_dashboard_ai_sql_llm",forbidden)
    result = asyncio.run(generator._async_node_repair_sql({"normalized_config":{"analysis_model":"attribution"}}))
    assert not result["response"].success

def test_legacy_and_compilation_services_accept_attribution(monkeypatch):
    async def execute(session,user,request): return "compiled"
    monkeypatch.setattr(generator,"_execute_manual_chart_graph",execute)
    req = DashboardAiSqlGenerateRequest(datasource=1,chart_type="table",context=config())
    assert asyncio.run(generator.generate_dashboard_ai_sql(None,None,req)) == "compiled"
    assert asyncio.run(generator.compile_dashboard_sql(None,None,req)) == "compiled"

def test_mysql_full_graph_validates_guard_alias_scope(monkeypatch):
    def mysql_context(state):
        value = context(state)
        value['sql_dialect'] = 'mysql'; value['datasource'].type = 'mysql'
        value['schema'] = value['schema'].replace('occurred_at:timestamptz','occurred_at:bigint')
        for f in value['tracking_metadata']['fields']:
            if f['field_name'] == 'occurred_at': f.update(type='bigint',extra_properties={'encoding':'epoch_milliseconds'})
        return value
    response = run(monkeypatch,config(),mysql_context)['response']
    assert response.success, response.issues
