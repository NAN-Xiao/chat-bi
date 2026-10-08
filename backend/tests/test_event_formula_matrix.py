"""Event conditions and calculator formulas against independent expected values."""
from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest
import sqlglot

from event_sql_fixture import build, config, formula_config, field, metric
from apps.dashboard.crud.event_sql_plan import EventConfigurationError
from apps.dashboard.crud.event_sql_compiler import compile_event_sql
from test_event_sql_postgres import connection, execute, SOURCE


def tokens(expression):
    return [({'type':'metric','metricId':v} if v in {'money','people'} else
             {'type':'operator','value':v} if v in {'+','-','*','/'} else
             {'type':'paren','value':v} if v in {'(',')'} else
             {'type':'number','value':v}) for v in expression.split()]


def formula(expression, places=2):
    c=formula_config(groups=False);c['chart']['type']='metric'
    c['formulaMetrics'][0].update(tokens=tokens(expression), decimalPlaces=places)
    return c


FORMULAS=[
    ('money + people',22), ('money - people',18), ('money * people',40),
    ('money / people',10), ('money + people * 3',26),
    ('( money + people ) * 3',66), ('( money - people ) / ( people + 1 )',6),
    ('money / people / 2',5), ('money - people - 3',15),
    ('money / ( people / 2 )',20), ('money * .125 + 1.25',3.75),
    ('0 - money',-20), ('( 0 - people ) * 1.5',-3), ('1 / 8',.13),
    ('money / ( people - people )',None), ('money / ( 3 - 3 )',None),
]


@pytest.mark.parametrize('expression,expected',FORMULAS)
def test_native_operator_priority_parentheses_and_zero_denominator(connection,expression,expected):
    rows=execute(connection,formula(expression))
    assert len(rows)==1 and rows[0][:2]==(20,2)
    assert rows[0][-1] is None if expected is None else rows[0][-1]==Decimal(str(expected))


@pytest.mark.parametrize('dialect',['postgres','mysql','starrocks','doris'])
@pytest.mark.parametrize('expression,expected',FORMULAS)
def test_formula_matrix_parses_without_dialect_substitution(dialect,expression,expected):
    plan=build(formula(expression),dialect=dialect)
    sql=compile_event_sql(plan).replace('{{dashboard_start_yyyymmdd}}','20260901').replace('{{dashboard_end_yyyymmdd}}','20260903')
    assert tuple(sqlglot.parse_one(sql,read=dialect).named_selects)==plan.required_columns


@pytest.mark.parametrize('places,expected',[(0,0),(2,.33),(6,.333333),(10,.3333333333)])
def test_rounding_is_applied_after_arithmetic(connection,places,expected):
    assert execute(connection,formula('1 / 3',places))[0][-1]==Decimal(str(expected))


@pytest.mark.parametrize('scope',['global','metric'])
@pytest.mark.parametrize('op,column,value,expected',[
    ('eq','category','A',2),('ne','category','A',1),('contains','category','A',2),
    ('gt','amount',9,2),('lt','amount',11,2),('between','amount',[10,10],2),
    ('is_null','amount',None,1),('is_not_null','amount',None,2),
])
def test_every_supported_filter_operator_in_global_and_metric_scope(connection,scope,op,column,value,expected):
    c=config(card=True);c['metrics'][0]=metric('Pay')
    predicate={'rules':[{'field':field(column),'operator':op,'value':value}]}
    (c if scope=='global' else c['metrics'][0])['filters']=predicate
    assert execute(connection,c)==[(expected,)]


def test_formula_atoms_keep_separate_local_filters_with_global_or_and_two_groups(connection):
    c=formula_config(groups=True);c['groups'].append(field('region'))
    c['filters']={'logic':'and','rules':[
        {'type':'group','logic':'or','children':[
            {'field':field('category'),'operator':'eq','value':'A'},
            {'field':field('category'),'operator':'eq','value':'B'}]},
        {'field':field('region'),'operator':'ne','value':'Z'}]}
    for m in c['metrics']:
        m['filters']={'rules':[{'field':field('actor'),'operator':'eq','value':'u1'}]}
    atoms=c.pop('metrics');c['metrics']=[]
    c['formulaMetrics'][0]['tokens']=[{'type':'atomicMetric','metric':atoms[0]},
                                    {'type':'operator','value':'/'}, {'type':'atomicMetric','metric':atoms[1]}]
    assert execute(connection,c)==[(date(2026,9,1),'A','X',10),
                                  (date(2026,9,2),'A','X',None),(date(2026,9,3),'A','X',None)]


def test_multiple_formulas_share_metrics_without_multiplying_results(connection):
    c=formula('money + people')
    c['formulaMetrics'].extend([
        {'id':'f2','alias':'比例','tokens':tokens('money / people')},
        {'id':'f3','alias':'混合','tokens':tokens('( money + people ) * 3')}])
    assert execute(connection,c)==[(20,2,22,10,66)]


def test_null_numeric_aggregate_is_not_silently_replaced_with_zero_in_formula(connection):
    c=formula('money + people')
    c['filters']={'rules':[{'field':field('category'),'operator':'eq','value':'B'}]}
    assert execute(connection,c)==[(None,1,None)]


@pytest.mark.parametrize('expression',['money / 0','money +','( money + people','money people',
                                     '- money','money ^ people','-1.5 * people'])
def test_invalid_formula_is_rejected_before_execution(expression):
    with pytest.raises(EventConfigurationError):build(formula(expression))


@pytest.mark.parametrize('aggregation',['min','max'])
@pytest.mark.parametrize('atomic',[False,True])
def test_nonnumeric_aggregate_cannot_enter_numeric_formula(aggregation,atomic):
    c=config(card=True); m=metric('View',aggregation,mid='money',measure='actor')
    c['metrics']=[] if atomic else [m]
    operand={'type':'atomicMetric','metric':m} if atomic else {'type':'metric','metricId':'money'}
    c['formulaMetrics']=[{'id':'f','alias':'invalid','tokens':[operand,{'type':'operator','value':'+'},{'type':'number','value':'1'}]}]
    with pytest.raises(EventConfigurationError):build(c)


@pytest.mark.parametrize('aggregation,expected',[('min','u1'),('max','u3')])
def test_standalone_text_extrema_remain_valid(connection,aggregation,expected):
    c=config(card=True);c['metrics']=[metric('View',aggregation,measure='actor')]
    assert execute(connection,c)==[(expected,)]


def test_nonnumeric_formula_returns_explicit_issue_without_sql_or_llm(monkeypatch):
    from test_event_sql_graph import run
    c=formula('money + 1');c['metrics'][0]=metric('View','max',mid='money',measure='actor')
    response=run(monkeypatch,c)['response']
    assert not response.success and response.sql==''
    assert any('不是数值' in issue for issue in response.issues)
