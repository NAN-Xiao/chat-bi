import pytest
from event_sql_fixture import build, formula_config

@pytest.mark.parametrize("old,new",[("'Pay'","'Other'"),("SUM(","AVG("),("NULLIF(","COALESCE("),
    ('"amount"','"actor"'),("<= {{dashboard_end_yyyymmdd}}",">= {{dashboard_end_yyyymmdd}}"),
    ('AS "人均金额"','AS "other"'),("k.chart_group_1 = a0.chart_group_1","1 = 1")])
def test_template_mutations_cannot_pass_config_equivalence(old,new):
    from apps.dashboard.crud.event_sql_compiler import compile_event_sql
    from apps.dashboard.crud.event_sql_validation import event_compiled_contract_issues
    p=build(formula_config());sql=compile_event_sql(p)
    assert old in sql
    assert not event_compiled_contract_issues(sql,p)
    assert event_compiled_contract_issues(sql.replace(old,new),p)

@pytest.mark.parametrize("old,new",[("SUM(metric_value)","AVG(metric_value)"),("GROUP BY chart_date, chart_group_1","GROUP BY chart_group_1"),("'Pay'","'Other'")])
def test_lineage_checks_catch_a_faulty_template_even_if_expected_builder_is_faulty(monkeypatch,old,new):
    from apps.dashboard.crud import event_sql_validation as validation
    from apps.dashboard.crud.event_sql_compiler import compile_event_sql
    p=build(formula_config());bad=compile_event_sql(p).replace(old,new)
    monkeypatch.setattr(validation,"compile_event_sql",lambda p:bad)
    assert validation.event_compiled_contract_issues(bad,p), "不能只与编译器自己输出比较"


@pytest.mark.parametrize('dialect',['postgres','mysql'])
def test_json_numeric_filter_preserves_expression_through_lineage_expansion(dialect):
    from event_sql_fixture import config, field
    from apps.dashboard.crud.event_sql_compiler import compile_event_sql
    from apps.dashboard.crud.event_sql_validation import event_compiled_contract_issues
    c=config('sum');c['metrics'][0]['field']['eventName']='Pay'
    value={**field('value'),'kind':'tracking-property','propertyName':'value','eventName':'Pay'}
    c['metrics'][0]['metricField']=value
    c['metrics'][0]['filters']={'logic':'or','rules':[{'field':value,'operator':'gt','value':'1'}]}
    p=build(c,dialect=dialect)
    assert event_compiled_contract_issues(compile_event_sql(p),p)==[]


def test_predicate_canonicalization_preserves_operator_grouping():
    import sqlglot
    from apps.dashboard.crud.event_sql_contract import _unquoted, _implies
    parse=sqlglot.parse_one
    assert _unquoted(parse('COALESCE((a + b), 0)'))==_unquoted(parse('COALESCE(a + b, 0)'))
    assert _unquoted(parse('a * (b + c)'))!=_unquoted(parse('(a * b) + c'))
    assert not _implies(parse('x = 1 OR y = 2 AND z = 3'),parse('(x = 1 OR y = 2) AND z = 3'))
