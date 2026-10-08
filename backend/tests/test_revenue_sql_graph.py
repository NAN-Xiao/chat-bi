import asyncio

import pytest
import sqlglot

from apps.dashboard.crud import ai_sql_generator as generator
from apps.dashboard.models.dashboard_model import DashboardAiSqlGenerateRequest
from revenue_sql_fixture import METHODS, config, context, field


def run(monkeypatch, conf, collector=context):
    def forbidden(*args, **kwargs):
        pytest.fail("收入配置生成及失败路径不得创建或调用 LLM")
    monkeypatch.setattr(generator, "_create_dashboard_ai_sql_llm", forbidden)
    monkeypatch.setattr(generator, "_async_invoke_llm_json", forbidden)
    monkeypatch.setattr(generator, "_dashboard_config_prompt", forbidden)
    monkeypatch.setattr(generator, "_node_collect_context", collector)
    req = DashboardAiSqlGenerateRequest(datasource=1, chart_type="table", context=conf)
    return asyncio.run(generator._build_manual_chart_graph().ainvoke({"request": req, "graph_trace": []}))


@pytest.mark.parametrize("method", METHODS)
def test_every_revenue_method_compiles_without_llm(monkeypatch, method):
    result = run(monkeypatch, config(method))
    response = result["response"]
    assert response.success, response.issues
    assert response.result_config["type"] == "revenue_cohort_table"
    assert response.result_config["metric_method"] == method
    assert response.result_config["observation_days"] == 2
    parsed = sqlglot.parse_one(response.sql.replace("{{dashboard_start_yyyymmdd}}", "20260901")
                                .replace("{{dashboard_end_yyyymmdd}}", "20260903"), read="postgres")
    assert parsed.named_selects == ["cohort_date", "cohort_size", "day_0", "day_1", "day_2"]
    assert generator._route_after_sql_validate(result) == "explain_advice"
    assert response.sql == run(monkeypatch, config(method))["response"].sql


@pytest.mark.parametrize("scenario", ["days", "float_days", "cost_toggle", "missing_event", "missing_metric",
                                    "timestamp_encoding", "revoked", "tampered", "dialect"])
def test_revenue_failures_are_explicit_and_never_repaired_by_llm(monkeypatch, scenario):
    conf = config()
    collector = context
    if scenario == "days": conf["revenue"]["observationDays"] = 366
    if scenario == "float_days": conf["revenue"]["observationDays"] = 2.5
    if scenario == "cost_toggle": conf["revenue"]["cost"]["enabled"] = "false"
    if scenario == "missing_event": conf["revenue"]["paymentEvent"] = None
    if scenario == "missing_metric": conf["revenue"]["metric"]["field"] = None
    if scenario == "timestamp_encoding": conf["time"]["dateParameterType"] = "timestamp"
    if scenario == "revoked": collector = lambda s: {**context(s), "allowed_fields_by_table": {"events": {"day"}}}
    if scenario == "dialect": collector = lambda s: {**context(s), "sql_dialect": "sqlite"}
    if scenario == "tampered":
        monkeypatch.setattr(generator, "compile_revenue_sql", lambda plan: "SELECT 1 AS wrong", raising=False)
    result = run(monkeypatch, conf, collector)
    assert result["response"].success is False
    assert result["response"].sql == ""
    assert result["response"].issues
    assert generator._route_after_sql_validate(result) == "explain_advice"


def test_revenue_repair_node_is_closed(monkeypatch):
    def forbidden(*a, **kw): pytest.fail("repair must not create LLM")
    monkeypatch.setattr(generator, "_create_dashboard_ai_sql_llm", forbidden)
    result = asyncio.run(generator._async_node_repair_sql({"normalized_config": {"analysis_model": "revenue"}}))
    assert result["response"].success is False


def test_revenue_table_policy_cannot_be_bypassed_by_global_or(monkeypatch):
    def scoped(s):
        return {**context(s), "tenant_id": 99, "tracking_metadata": {"tenant_id": 99, "datasource_id": 1,
                "tables": [{"table_name": "events", "extra_properties": {"required_filters": {
                    "rules": [{"field": "category", "operator": "eq", "value": "allowed"}]}}}]}}
    conf = config(cost=True)
    conf["filters"] = {"logic": "or", "rules": [
        {"field": field("subject"), "operator": "eq", "value": "A"},
        {"field": field("subject"), "operator": "eq", "value": "B"}]}
    response = run(monkeypatch, conf, scoped)["response"]
    assert response.success, response.issues
    assert response.sql.count('"category" = \'allowed\'') == 4
    assert "cost_value" in response.sql


def json_config_and_context():
    conf = config(cost=True)
    for role, name in (("metric", "value"), ("cost", "expense")):
        conf["revenue"][role]["field"] = {**field(name), "kind":"tracking-property", "eventName":"purchase",
                                            "sourceField":"payload", "jsonPath":"$." + name}
    tracking = {"enabled":True, "default_event_table":"events", "default_event_name_field":"event_name",
                "event_name_mappings":[{"event_name":"start"}, {"event_name":"purchase", "properties":[
                    {"property_name":name,"source_field":"payload","json_path":"$."+name,"property_type":"double"}
                    for name in ("value","expense")]}]}
    return conf, lambda s: {**context(s), "tracking_metadata":tracking}


def test_json_metric_and_cost_use_server_types_through_actual_graph(monkeypatch):
    conf, collector = json_config_and_context()
    response = run(monkeypatch,conf,collector)["response"]
    assert response.success, response.issues
    assert "payload" in response.sql and "cost_value" in response.sql
