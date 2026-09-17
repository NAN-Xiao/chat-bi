"""Chart configuration remains authoritative without workspace Data Skills."""
from copy import deepcopy

import pytest

from apps.dashboard.crud import ai_sql_generator as generator
from apps.dashboard.models.dashboard_model import DashboardAiSqlGenerateRequest, DashboardAiSqlGenerateResponse


def event_state(sql: str, *, aggregation: str = "count", filters=None):
    event = {"kind": "tracking-event", "eventTable": "activity", "eventNameField": "action", "eventName": "Open"}
    request = DashboardAiSqlGenerateRequest(datasource=1, chart_type="table", context={
        "analysisModel": "event",
        "metrics": [{"id": "m1", "alias": "指标 1", "field": event,
                     "metricField": {"table": "activity", "field": "actor_id"}, "aggregation": aggregation}],
        "groups": [], "filters": filters or {},
    })
    normalized = generator._normalize_manual_config(request)
    ir = generator._build_formula_ir(normalized)
    return {"request": request, "normalized_config": normalized, "formula_ir": ir,
            "sql_plan": generator._build_sql_plan(normalized, ir), "sql_dialect": "mysql",
            "data_skill": "", "graph_trace": [],
            "response": DashboardAiSqlGenerateResponse(success=True, sql=sql)}


def test_event_plan_declares_exact_measure_and_output_without_data_skills():
    state = event_state("")
    contract = state["sql_plan"]["result_contract"]
    assert contract["type"] == "event_table"
    assert contract["required_columns"] == ["指标 1"]
    assert contract["metrics"][0]["aggregation"] == "count"
    assert contract["metrics"][0]["event"] == "Open"
    assert contract["metrics"][0]["table"] == "activity"


def test_parse_failure_does_not_invent_missing_event_and_has_location():
    state = event_state("SELECT COUNT(*) AS 指标 1 FROM activity WHERE action='Open'")
    result = generator._node_validate_sql(state)["response"]
    assert not result.success
    assert not any("未引用配置事件" in item for item in result.issues)
    assert any("行" in item and "列" in item for item in result.issues)


@pytest.mark.parametrize("sql", [
    "SELECT COUNT(DISTINCT actor_id) AS `指标 1` FROM activity WHERE action='Open'",
    "SELECT AVG(actor_id) AS `指标 1` FROM activity WHERE action='Open'",
])
def test_configured_total_cannot_be_changed_to_people_or_average(sql):
    result = generator._node_validate_sql(event_state(sql))["response"]
    assert not result.success
    assert any("聚合" in issue for issue in result.issues)


def test_count_through_aggregate_cte_and_coalesce_is_valid():
    sql = "WITH a AS (SELECT COUNT(*) AS n FROM activity WHERE action='Open') SELECT COALESCE(n,0) AS `指标 1` FROM a"
    assert generator._node_validate_sql(event_state(sql))["response"].success


def test_configured_metric_alias_must_not_be_replaced():
    result = generator._node_validate_sql(event_state("SELECT COUNT(*) AS n FROM activity WHERE action='Open'"))["response"]
    assert not result.success
    assert any("指标 1" in issue and "结果列" in issue for issue in result.issues)


def test_global_filter_cannot_be_omitted_or_weakened_by_or():
    filters = {"logic": "and", "rules": [{"field": {"table": "activity", "field": "region"}, "operator": "eq", "value": "EU"}]}
    for predicate in ("action='Open'", "action='Open' AND (region='EU' OR region='US')"):
        state = event_state(f"SELECT COUNT(*) AS `指标 1` FROM activity WHERE {predicate}", filters=filters)
        result = generator._node_validate_sql(state)["response"]
        assert not result.success
        assert any("筛选" in issue for issue in result.issues)
    state = event_state("SELECT COUNT(*) AS `指标 1` FROM activity WHERE action='Open' AND region='EU'", filters=filters)
    assert generator._node_validate_sql(state)["response"].success


def test_same_sql_and_validation_error_retries_until_limit(monkeypatch):
    monkeypatch.setattr(generator.settings, "DASHBOARD_SQL_MAX_REPAIR_ATTEMPTS", 3)
    state = event_state("SELECT COUNT(*) AS n FROM activity WHERE action='Open'")
    for attempt in range(4):
        state["response"] = DashboardAiSqlGenerateResponse(success=True, sql=state["response"].sql)
        state["sql_repair_attempts"] = attempt
        state.update(generator._node_validate_sql(state))
        assert not state["response"].success
        expected = "repair_sql" if attempt < 3 else "explain_advice"
        assert generator._route_after_sql_validate(state) == expected
        assert "停止无效重试" not in state["response"].advice


@pytest.mark.parametrize("analysis_model", generator.ANALYSIS_MODEL_LABELS)
def test_repeated_validation_failure_does_not_stop_any_model_early(monkeypatch, analysis_model):
    monkeypatch.setattr(generator.settings, "DASHBOARD_SQL_MAX_REPAIR_ATTEMPTS", 3)
    state = {"normalized_config": {"analysis_model": analysis_model}, "sql_dialect": "mysql"}
    for attempt in range(4):
        response = DashboardAiSqlGenerateResponse(
            success=False, sql="SELECT 1", issues=["SQL 未通过结果契约。"], advice="请修复 SQL。",
        )
        state["sql_repair_attempts"] = attempt
        state.update(generator._sql_validation_result(state, response))
        assert generator._route_after_sql_validate(state) == ("repair_sql" if attempt < 3 else "explain_advice")
        assert response.advice == "请修复 SQL。"


def test_successful_repair_stops_before_limit(monkeypatch):
    monkeypatch.setattr(generator.settings, "DASHBOARD_SQL_MAX_REPAIR_ATTEMPTS", 3)
    state = event_state("SELECT COUNT(*) AS n FROM activity WHERE action='Open'")
    state.update(generator._node_validate_sql(state))
    state["sql_repair_attempts"] = 1
    state["response"] = DashboardAiSqlGenerateResponse(
        success=True, sql="SELECT COUNT(*) AS `指标 1` FROM activity WHERE action='Open'",
    )
    state.update(generator._node_validate_sql(state))
    assert state["response"].success
    assert generator._route_after_sql_validate(state) == "explain_advice"


def test_collects_independent_contract_errors_for_one_repair():
    result = generator._node_validate_sql(event_state(
        "SELECT CAST(COUNT(DISTINCT actor_id) AS UNSIGNED) AS `指标 1` FROM activity WHERE action='Other'"
    ))["response"]
    assert not result.success
    assert any("UNSIGNED" in issue for issue in result.issues)
    assert any("Open" in issue for issue in result.issues)
    assert any("聚合" in issue for issue in result.issues)


def test_metric_events_cannot_be_swapped_between_output_columns():
    state = event_state("")
    second = deepcopy(state["normalized_config"]["metrics"][0])
    second.update(id="m2", alias="指标 2")
    second["field"]["eventName"] = "Close"
    state["normalized_config"]["metrics"].append(second)
    state["sql_plan"] = generator._build_sql_plan(state["normalized_config"], state["formula_ir"])
    state["response"].sql = (
        "WITH a AS (SELECT COUNT(*) AS n FROM activity WHERE action='Open'), "
        "b AS (SELECT COUNT(*) AS n FROM activity WHERE action='Close') "
        "SELECT b.n AS `指标 1`, a.n AS `指标 2` FROM a CROSS JOIN b"
    )
    assert not generator._node_validate_sql(state)["response"].success


def test_total_count_cannot_drop_rows_with_null_measure_field():
    result = generator._node_validate_sql(event_state(
        "SELECT COUNT(actor_id) AS `指标 1` FROM activity WHERE action='Open'"
    ))["response"]
    assert not result.success


def test_daily_plan_has_complete_program_generated_scaffold_and_untruncated_rules():
    state = event_state("")
    state["normalized_config"]["time"] = {"field": {"table": "activity", "field": "day_key"},
        "grain": "day", "date_parameter_type": "yyyymmdd_number"}
    state.update(generator._node_build_sql_plan(state))
    assert state["sql_plan"]["date_scaffold"]["supported"]
    assert state["sql_plan"]["date_scaffold_required"]
    assert state["sql_plan"]["sql_rules"]["dialect_family"] == "mysql"
    assert state["sql_plan"]["date_scaffold"]["required_tokens"] == ["{{dashboard_start_yyyymmdd}}", "{{dashboard_end_yyyymmdd}}"]


def test_unused_extra_cte_cannot_satisfy_global_filter():
    filters = {"rules": [{"field": {"field": "region", "table": "activity"}, "operator": "eq", "value": "EU"}]}
    sql = "WITH unrelated AS (SELECT * FROM activity WHERE region='EU') SELECT COUNT(*) AS `指标 1` FROM activity WHERE action='Open'"
    assert not generator._node_validate_sql(event_state(sql, filters=filters))["response"].success


@pytest.mark.parametrize("measure", [
    "COUNT(CASE WHEN action='Open' THEN 1 ELSE 0 END)",
    "COUNT(IF(action='Open',1,0))", "COUNT(*) * 100",
])
def test_total_count_cannot_count_false_branches_or_apply_unconfigured_math(measure):
    sql = f"SELECT {measure} AS `指标 1` FROM activity"
    if measure == "COUNT(*) * 100":
        sql += " WHERE action='Open'"
    assert not generator._node_validate_sql(event_state(sql))["response"].success


def test_configured_event_table_cannot_be_replaced():
    sql = "SELECT COUNT(*) AS `指标 1` FROM other_activity WHERE action='Open'"
    assert not generator._node_validate_sql(event_state(sql))["response"].success


def test_conditional_sum_is_valid_total_count():
    sql = "SELECT SUM(CASE WHEN action='Open' THEN 1 ELSE 0 END) AS `指标 1` FROM activity WHERE action IN ('Open')"
    assert generator._node_validate_sql(event_state(sql))["response"].success


def test_count_one_is_valid_total():
    assert generator._node_validate_sql(event_state("SELECT COUNT(1) AS `指标 1` FROM activity WHERE action='Open'"))["response"].success


def test_left_join_filter_does_not_filter_preserved_fact_rows():
    filters = {"rules": [{"field": {"field": "region", "table": "activity"}, "operator": "eq", "value": "EU"}]}
    sql = "WITH other AS (SELECT * FROM activity WHERE region='EU') SELECT COUNT(*) AS `指标 1` FROM activity a LEFT JOIN other b ON a.actor_id=b.actor_id WHERE a.action='Open'"
    assert not generator._node_validate_sql(event_state(sql, filters=filters))["response"].success


@pytest.mark.parametrize("aggregation,measure", [
    ("sum", "SUM(CASE WHEN actor_id>0 THEN amount ELSE 0 END)"),
    ("count_distinct", "COUNT(DISTINCT CASE WHEN actor_id>0 THEN region END)"),
])
def test_measure_field_in_predicate_cannot_replace_actual_aggregate_argument(aggregation, measure):
    sql = f"SELECT {measure} AS `指标 1` FROM activity WHERE action='Open'"
    assert not generator._node_validate_sql(event_state(sql, aggregation=aggregation))["response"].success


def test_configured_group_must_be_a_real_dimension_at_aggregate_grain():
    state = event_state("SELECT 'EU' AS region, COUNT(*) AS `指标 1` FROM activity WHERE action='Open'")
    state["normalized_config"]["groups"] = [{"table": "activity", "field": "region"}]
    state["sql_plan"] = generator._build_sql_plan(state["normalized_config"], state["formula_ir"])
    assert not generator._node_validate_sql(state)["response"].success
    state["response"].sql = "SELECT region, COUNT(*) AS `指标 1` FROM activity WHERE action='Open' GROUP BY region"
    assert generator._node_validate_sql(state)["response"].success


def test_formula_result_must_apply_configured_operator_and_denominator():
    state = event_state("SELECT COUNT(*) AS `指标 1`, 0 AS ratio FROM activity WHERE action='Open'")
    state["normalized_config"]["formula_metrics"] = [{"id": "f1", "alias": "ratio", "tokens": [
        {"type": "metric", "metricId": "m1"}, {"type": "operator", "value": "/"}, {"type": "number", "value": "100"}]}]
    state["formula_ir"] = generator._build_formula_ir(state["normalized_config"])
    state["sql_plan"] = generator._build_sql_plan(state["normalized_config"], state["formula_ir"])
    assert not generator._node_validate_sql(state)["response"].success
    state["response"].sql = "WITH a AS (SELECT COUNT(*) AS n FROM activity WHERE action='Open') SELECT n AS `指标 1`, n/NULLIF(100,0) AS ratio FROM a"
    assert generator._node_validate_sql(state)["response"].success


def test_date_tokens_in_unused_cte_do_not_bound_fact_scan():
    state = event_state("")
    state["normalized_config"]["time"] = {"field": {"table": "activity", "field": "day_key"},
        "grain": "day", "date_parameter_type": "yyyymmdd_number"}
    state["sql_plan"] = generator._build_sql_plan(state["normalized_config"], state["formula_ir"])
    prefix = "WITH bounds AS (SELECT {{dashboard_start_yyyymmdd}} AS a, {{dashboard_end_yyyymmdd}} AS b) "
    base = "SELECT day_key,COUNT(*) AS `指标 1` FROM activity WHERE action='Open'"
    state["response"].sql = prefix + base + " GROUP BY day_key"
    assert not generator._node_validate_sql(state)["response"].success
    state["response"].sql = base + " AND day_key BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}} GROUP BY day_key"
    assert generator._node_validate_sql(state)["response"].success
    state["response"].sql = base + " AND day_key >= {{dashboard_start_yyyymmdd}} AND day_key <= {{dashboard_end_yyyymmdd}} GROUP BY day_key"
    assert generator._node_validate_sql(state)["response"].success


def test_conditional_sum_zero_else_does_not_widen_metric_event():
    sql = "SELECT SUM(CASE WHEN action='Open' THEN actor_id ELSE 0 END) AS `指标 1` FROM activity"
    assert generator._node_validate_sql(event_state(sql, aggregation="sum"))["response"].success


def test_sql_plan_provides_exact_quoted_output_aliases():
    state = event_state("")
    state.update(generator._node_build_sql_plan(state))
    assert state["sql_plan"]["result_contract"]["quoted_output_columns"] == ["`指标 1`"]


@pytest.mark.parametrize("measure", ["ABS(SUM(actor_id))", "SUM(DISTINCT actor_id)",
    "ROUND(SUM(actor_id),0)", "SUM(actor_id) OVER ()",
    "CASE WHEN SUM(actor_id)>100 THEN SUM(actor_id) ELSE 0 END"])
def test_base_measure_does_not_allow_unconfigured_transforms(measure):
    sql = f"SELECT {measure} AS `指标 1` FROM activity WHERE action='Open'"
    assert not generator._node_validate_sql(event_state(sql, aggregation="sum"))["response"].success


def test_nested_filter_children_from_editor_are_enforced():
    filters = {"logic": "and", "rules": [{"type": "group", "logic": "or", "children": [
        {"field": {"table": "activity", "field": "region"}, "operator": "eq", "value": country}
        for country in ["EU", "US"]]}]}
    sql = "SELECT COUNT(*) AS `指标 1` FROM activity WHERE action='Open'"
    assert not generator._node_validate_sql(event_state(sql, filters=filters))["response"].success
    for suffix in [" AND (region='EU' OR region='US')", " AND region IN ('EU','US')"]:
        assert generator._node_validate_sql(event_state(sql+suffix, filters=filters))["response"].success


def test_range_string_from_editor_uses_field_type_and_both_bounds():
    filters = {"rules": [{"field": {"table": "activity", "field": "actor_id", "type": "bigint"},
                          "operator": "between", "value": "1,10"}]}
    sql = "SELECT COUNT(*) AS `指标 1` FROM activity WHERE action='Open' AND actor_id BETWEEN 1 AND 10"
    assert generator._node_validate_sql(event_state(sql, filters=filters))["response"].success
    assert not generator._node_validate_sql(event_state(sql.replace('AND 10', 'AND 11'), filters=filters))["response"].success


def test_group_domain_cannot_include_unselected_events():
    state = event_state("")
    state["normalized_config"]["groups"] = [{"table": "activity", "field": "actor_id"}]
    state["sql_plan"] = generator._build_sql_plan(state["normalized_config"], state["formula_ir"])
    base = """WITH dimensions AS (SELECT DISTINCT actor_id FROM activity {domain_filter}),
        facts AS (SELECT actor_id,COUNT(*) AS n FROM activity WHERE action='Open' GROUP BY actor_id)
        SELECT d.actor_id,COALESCE(f.n,0) AS `指标 1` FROM dimensions d LEFT JOIN facts f ON d.actor_id=f.actor_id"""
    state["response"].sql = base.format(domain_filter="")
    result = generator._node_validate_sql(state)["response"]
    assert not result.success
    assert any("维度" in issue and "范围" in issue for issue in result.issues)
    state["response"].sql = base.format(domain_filter="WHERE action='Open'")
    assert generator._node_validate_sql(state)["response"].success


def test_group_domain_keeps_global_and_metric_filters():
    filters = {"rules": [{"field": {"table": "activity", "field": "region"}, "operator": "eq", "value": "EU"}]}
    state = event_state("", filters=filters)
    state["normalized_config"]["groups"] = [{"table": "activity", "field": "actor_id"}]
    state["sql_plan"] = generator._build_sql_plan(state["normalized_config"], state["formula_ir"])
    state["response"].sql = """WITH dimensions AS (SELECT DISTINCT actor_id FROM activity WHERE action='Open'),
        facts AS (SELECT actor_id,COUNT(*) AS n FROM activity WHERE action='Open' AND region='EU' GROUP BY actor_id)
        SELECT d.actor_id,COALESCE(f.n,0) AS `指标 1` FROM dimensions d LEFT JOIN facts f ON d.actor_id=f.actor_id"""
    assert not generator._node_validate_sql(state)["response"].success


def test_union_domain_cannot_hide_an_unfiltered_branch():
    state = event_state("")
    state["normalized_config"]["groups"] = [{"table": "activity", "field": "actor_id"}]
    state["sql_plan"] = generator._build_sql_plan(state["normalized_config"], state["formula_ir"])
    state["response"].sql = """WITH dimensions AS (
        SELECT actor_id FROM activity WHERE action='Open' UNION SELECT actor_id FROM activity),
        facts AS (SELECT actor_id,COUNT(*) AS n FROM activity WHERE action='Open' GROUP BY actor_id)
        SELECT d.actor_id,COALESCE(f.n,0) AS `指标 1` FROM dimensions d LEFT JOIN facts f ON d.actor_id=f.actor_id"""
    assert not generator._node_validate_sql(state)["response"].success
    state["response"].sql = state["response"].sql.replace(
        "UNION SELECT actor_id FROM activity)", "UNION SELECT actor_id FROM activity WHERE action='Open')",
    )
    assert generator._node_validate_sql(state)["response"].success
