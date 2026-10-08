import asyncio
from types import SimpleNamespace

import pytest

from apps.dashboard.crud import ai_sql_generator as generator
from apps.dashboard.models.dashboard_model import DashboardAiSqlGenerateRequest
from test_property_sql_plan import config, ALLOWED


def request():
    conf = config()
    conf["analysisModel"] = conf.pop("analysis_model")
    conf["time"]["dateExpression"] = {"version": 1, "mode": "preset", "preset": "past_7_days"}
    return DashboardAiSqlGenerateRequest(datasource=1, chart_type="table", context=conf)


def context(_state):
    return {"schema": "# Table: records\n[\n(subject:varchar),\n(day:integer),\n(region:varchar),\n(amount:numeric)\n]",
            "allowed_tables": ["records"], "allowed_fields_by_table": ALLOWED,
            "sql_dialect": "postgres", "tracking_metadata": {}, "event_scope": {},
            "datasource": None}


@pytest.mark.parametrize("scenario", ["valid", "config_error", "sql_error", "none", "static", "revoked"])
def test_property_graph_never_calls_llm(monkeypatch, scenario):
    def forbidden(*args, **kwargs):
        raise AssertionError("property must never create an LLM")

    monkeypatch.setattr(generator, "_create_dashboard_ai_sql_llm", forbidden)
    monkeypatch.setattr(generator, "_node_collect_context", context)
    req = request()
    if scenario == "config_error":
        req.context["property"]["groupMode"] = "invalid"
    if scenario == "none":
        req.context["time"]["grain"] = "none"
    if scenario == "static":
        req.context["time"] = {"grain": "none"}
    if scenario == "revoked":
        monkeypatch.setattr(generator, "_node_collect_context", lambda state: {**context(state), "allowed_fields_by_table": {"records": {"day"}}})
    if scenario == "sql_error":
        monkeypatch.setattr(generator, "compile_property_sql", lambda p: 'SELECT 1 AS wrong', raising=False)
    result = asyncio.run(generator._build_manual_chart_graph().ainvoke({"request": req, "graph_trace": []}))
    response = result["response"]
    assert response.success is (scenario in {"valid", "none", "static"}), response.issues
    assert generator._route_after_sql_validate(result) == "explain_advice"
    if scenario == "none":
        assert response.result_config["date_field"] == ""
        assert "property_date" not in response.sql
    if scenario == "config_error":
        assert response.sql == ""
        assert any("groupMode" in issue for issue in response.issues)


@pytest.mark.parametrize("model", ["property", " Property "])
def test_invalid_raw_property_mode_cannot_be_defaulted(monkeypatch, model):
    monkeypatch.setattr(generator, "_node_collect_context", context)
    req = request()
    req.context["analysisModel"] = model
    req.context["property"] = {"group_mode": "invalid"}
    result = asyncio.run(generator._build_manual_chart_graph().ainvoke({"request": req, "graph_trace": []}))
    assert result["response"].success is False
    assert result["response"].sql == ""


def required_filter_context(state):
    return {**context(state), "tenant_id": 99, "tracking_metadata": {
        "tenant_id": 99, "datasource_id": 1,
        "tables": [{"table_name": "records", "extra_properties": {
            "required_filters": {"logic": "and", "rules": [
                {"field": "region", "operator": "eq", "value": "A"}
            ]}
        }}]
    }}


def test_workspace_required_filter_is_applied_outside_user_or_and_to_all_audiences(monkeypatch):
    monkeypatch.setattr(generator, "_node_collect_context", required_filter_context)
    req = request()
    req.context["filters"] = {"logic": "or", "rules": [
        {"field": {"table": "records", "field": "subject"}, "operator": "eq", "value": "x"},
        {"field": {"table": "records", "field": "subject"}, "operator": "eq", "value": "y"},
    ]}
    req.context["property"] = {"groupMode": "audience", "audiences": [{"name": "all"}, {"name": "another"}]}
    result = asyncio.run(generator._build_manual_chart_graph().ainvoke({"request": req, "graph_trace": []}))
    response = result["response"]
    assert response.success, response.issues
    assert '"region" = \'A\'' in response.sql
    filters = result["normalized_config"]["filters"]
    assert filters["logic"] == "and"
    assert filters["rules"][0]["logic"] == "or"
    assert filters["rules"][1]["children"][0]["field"] == {"table": "records", "field": "region"}
    assert req.context["filters"]["logic"] == "or"  # Do not mutate the user's configuration.


@pytest.mark.parametrize("model", ["property", "event", "interval"])
def test_workspace_filter_is_shared_by_manual_analysis_models(model):
    req = request()
    req.context["analysisModel"] = model
    if model == "interval":
        # Exercise the real interval input contract rather than relabelling a
        # property payload that the interval normalizer correctly rejects.
        req.context["interval"] = {
            "entityField": {"table": "records", "field": "subject"},
            "limitSeconds": 90,
            "startEvent": {"kind": "tracking-event", "eventTable": "records", "eventNameField": "action", "eventName": "open"},
            "endEvent": {"kind": "tracking-event", "eventTable": "records", "eventNameField": "action", "eventName": "close"},
        }
    state = {"request": req, **required_filter_context({}), "graph_trace": []}
    state.update(generator._node_normalize_manual_config(state))
    assert not state.get("interval_input_issues")
    state.update(generator._node_build_formula_ir(state))
    if model in {"event", "interval"}:
        assert "region" in str(state[f"{model}_table_filters"])
    else:
        assert "region" in str(state["normalized_config"]["filters"])


@pytest.mark.parametrize("scope", ["tenant_id", "datasource_id"])
def test_required_table_filter_cannot_cross_context(monkeypatch, scope):
    def wrong(state):
        result = required_filter_context(state)
        result["tracking_metadata"][scope] = 999
        return result
    monkeypatch.setattr(generator, "_node_collect_context", wrong)
    result = asyncio.run(generator._build_manual_chart_graph().ainvoke({"request": request(), "graph_trace": []}))
    assert result["response"].success is False
    assert not result["response"].sql


@pytest.mark.parametrize("broken", [None, {}, {"logic": "xor", "rules": []},
                                   {"rules": [{"field": {"table": "other", "field": "region"}, "operator": "eq", "value": "A"}]}])
def test_invalid_required_filter_fails_closed(monkeypatch, broken):
    def invalid(state):
        result = required_filter_context(state)
        result["tracking_metadata"]["tables"][0]["extra_properties"]["required_filters"] = broken
        return result
    monkeypatch.setattr(generator, "_node_collect_context", invalid)
    result = asyncio.run(generator._build_manual_chart_graph().ainvoke({"request": request(), "graph_trace": []}))
    assert result["response"].success is False
    assert not result["response"].sql


def test_unrelated_table_policy_does_not_expand_query_tables(monkeypatch):
    def unrelated(state):
        result = required_filter_context(state)
        result["tracking_metadata"]["tables"][0]["table_name"] = "other"
        return result
    monkeypatch.setattr(generator, "_node_collect_context", unrelated)
    result = asyncio.run(generator._build_manual_chart_graph().ainvoke({"request": request(), "graph_trace": []}))
    assert result["response"].success
    assert '"region" = \'A\'' not in result["response"].sql
    assert '"other"' not in result["response"].sql
