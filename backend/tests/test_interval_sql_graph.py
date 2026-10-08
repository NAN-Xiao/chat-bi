import asyncio
from types import SimpleNamespace

import pytest

from apps.dashboard.crud import ai_sql_generator as g
from test_interval_sql_plan import plan, config


def test_graph_compiles_once_and_never_calls_llm(monkeypatch):
    def forbidden(*a, **k): pytest.fail("interval must not construct an LLM")
    monkeypatch.setattr(g, "_create_dashboard_ai_sql_llm", forbidden)
    compiler = g.compile_interval_sql
    calls = []
    def counted(p):
        calls.append(p)
        return compiler(p)
    monkeypatch.setattr(g, "compile_interval_sql", counted)
    state = {"normalized_config": config(), "interval_plan": plan(), "sql_dialect": "postgres",
             "datasource": SimpleNamespace(type="postgresql"), "graph_trace": []}
    state.update(asyncio.run(g._async_node_generate_sql(state)))
    state.update(g._node_validate_sql(state))
    assert state["response"].success, state["response"].issues
    assert len(calls) == 1
    assert g._route_after_sql_validate(state) == "explain_advice"
    state["response"].sql = state["response"].sql.replace("<= 90", "<= 91")
    state.update(g._node_validate_sql(state))
    assert not state["response"].success and "<= 91" in state["response"].sql
    assert len(calls) == 1


def test_bad_configuration_failure_never_uses_repair_model(monkeypatch):
    monkeypatch.setattr(g, "_create_dashboard_ai_sql_llm", lambda *a: pytest.fail("LLM"))
    state = {"normalized_config": config(), "interval_input_issues": ["metadata.event_time: missing"], "graph_trace": []}
    state.update(asyncio.run(g._async_node_generate_sql(state)))
    assert not state["response"].success and not state["response"].sql
    assert g._route_after_sql_validate(state) == "explain_advice"
    asyncio.run(g._async_node_repair_sql(state))


def test_real_graph_builds_plan_and_returns_authenticated_sql(monkeypatch):
    import copy
    from test_interval_sql_plan import TRACKING, FIELDS
    from apps.dashboard.models.dashboard_model import DashboardAiSqlGenerateRequest
    from apps.dashboard.crud.interval_execution_contract import read_interval_contract
    from apps.db.db import check_sql_read
    tracking = copy.deepcopy(TRACKING)
    tracking.update(tenant_id=1, datasource_id=2, fields=[{"table_name": "events", "field_name": n, **d} for n, d in FIELDS.items()])
    schema = "# Table: events\n[\n" + ",\n".join(f"({name}:{value['type']}, physical)" for name, value in FIELDS.items()) + "\n]"
    datasource = SimpleNamespace(id=2, type="postgresql", name="test")
    class Context:
        @staticmethod
        def build_for_compilation(**kwargs):
            return SimpleNamespace(datasource=datasource, schema=schema, sql_dialect="postgres", allowed_tables=["events"],
                data_skill="", tracking_config="", skill_model_id=None)
    monkeypatch.setattr(g, "BusinessSqlContextService", Context)
    monkeypatch.setattr(g, "get_tracking_config", lambda *a, **k: tracking)
    monkeypatch.setattr(g, "require_current_tenant_id", lambda _: 1)
    monkeypatch.setattr(g, "_create_dashboard_ai_sql_llm", lambda *a: pytest.fail("LLM must not be constructed"))
    context = {**config(), "analysisModel": "interval"}
    context["time"]["dateExpression"] = {"version": 1, "mode": "preset", "preset": "past_7_days"}
    request = DashboardAiSqlGenerateRequest(datasource=2, chart_type="table", context=context)
    result = asyncio.run(g._execute_manual_chart_graph(SimpleNamespace(get=lambda *a: datasource), SimpleNamespace(id=1, tenant_id=1), request))
    assert result.success, result.issues
    assert read_interval_contract(result.sql) == result.result_config["execution_contract"]
    assert check_sql_read(result.sql, datasource)[0]
