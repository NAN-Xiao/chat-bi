from event_sql_fixture import build, config, formula_config

def test_existing_dual_formula_lists_do_not_generate_duplicate_outputs():
    from copy import deepcopy
    c=formula_config();c["calculatedMetrics"]=deepcopy(c["formulaMetrics"])
    assert build(c).required_columns.count("人均金额")==1

def test_current_chart_type_and_quoted_metric_name_remain_unchanged():
    from apps.dashboard.crud.event_sql_compiler import compile_event_sql
    c=config();c["chart"]["type"]="line";c["metrics"][0]["alias"]='中文 指标 "1"'
    p=build(c);assert p.required_columns==("day_key",'中文 指标 "1"')
    assert 'AS "中文 指标 ""1"""' in compile_event_sql(p)
