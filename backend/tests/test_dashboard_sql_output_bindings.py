import sqlglot
import pytest


def test_binding_quotes_configured_names_and_preserves_literals_and_order():
    from apps.dashboard.crud.sql_output_bindings import bind_output_columns
    sql = "SELECT COUNT(*) AS chart_metric_1, 'chart_metric_1' AS chart_group_1 FROM activity GROUP BY chart_group_1 ORDER BY chart_metric_1 DESC"
    result, issues = bind_output_columns(sql, {"chart_metric_1": "指标1", "chart_group_1": "来源 名称"}, "mysql")
    assert issues == []
    ast = sqlglot.parse_one(result, read="mysql")
    assert ast.named_selects == ["指标1", "来源 名称"]
    assert ast.args["order"].expressions[0].this.name == "指标1"
    assert "'chart_metric_1'" in result
    assert ast.expressions[0].args["alias"].args["quoted"]


@pytest.mark.parametrize("sql", [
    "SELECT 1 AS `指标 1`", "SELECT 1 AS chart_metric_2",
    "SELECT 1 AS chart_metric_1,2 AS chart_metric_1",
])
def test_binding_never_guesses_missing_or_ambiguous_columns(sql):
    from apps.dashboard.crud.sql_output_bindings import bind_output_columns
    result, issues = bind_output_columns(sql, {"chart_metric_1": "指标1"}, "mysql")
    assert issues
    assert result == sql


def test_binding_preserves_parameters_and_does_not_rename_inner_source_columns():
    from apps.dashboard.crud.sql_output_bindings import bind_output_columns
    sql = "WITH a AS (SELECT {{dashboard_start_yyyymmdd}} AS chart_metric_1) SELECT a.chart_metric_1 AS chart_metric_1 FROM a"
    result, issues = bind_output_columns(sql, {"chart_metric_1": "指标 1"}, "mysql")
    assert not issues
    assert "{{dashboard_start_yyyymmdd}}" in result
    assert "a.chart_metric_1" in result
    assert "AS `指标 1`" in result


def test_generation_plan_uses_machine_columns_while_validation_keeps_user_names():
    from apps.dashboard.crud.sql_output_bindings import generation_plan
    plan = {"result_contract": {"type": "event_table", "required_columns": ["dt", "指标1"], "date_field": "dt",
        "group_fields": [], "metric_fields": ["指标1"], "final_grain": ["dt"],
        "metrics": [{"id": "m1", "alias": "指标1"}], "formula_metrics": []},
        "output_bindings": {"chart_date": "dt", "chart_metric_1": "指标1"}}
    model_plan = generation_plan(plan, "mysql")
    assert model_plan["result_contract"]["required_columns"] == ["chart_date", "chart_metric_1"]
    assert model_plan["result_contract"]["metrics"][0]["alias"] == "chart_metric_1"
    assert plan["result_contract"]["required_columns"] == ["dt", "指标1"]


def test_binding_does_not_rewrite_aggregate_arguments_or_nested_queries():
    from apps.dashboard.crud.sql_output_bindings import bind_output_columns
    sql = "SELECT SUM(chart_metric_1) AS chart_metric_1 FROM (SELECT 2 AS chart_metric_1) a HAVING SUM(chart_metric_1)>0"
    result, issues = bind_output_columns(sql, {"chart_metric_1": "总量"}, "mysql")
    assert not issues
    ast = sqlglot.parse_one(result, read="mysql")
    assert ast.args["having"].find(sqlglot.exp.Column).name == "chart_metric_1"
    sql = "SELECT COUNT(*) AS chart_metric_1 FROM activity HAVING COUNT(*) > (SELECT MAX(chart_metric_1) FROM thresholds)"
    result, issues = bind_output_columns(sql, {"chart_metric_1": "总量"}, "mysql")
    assert not issues
    assert sqlglot.parse_one(result, read="mysql").args["having"].find(sqlglot.exp.Column).name == "chart_metric_1"
