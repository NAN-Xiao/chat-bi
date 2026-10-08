"""Independent cost detail must not depend on payer or revenue multiplicity."""
from datetime import date

import pytest

from revenue_sql_fixture import config, event, field, plan
from apps.dashboard.crud.revenue_sql_plan import RevenueConfigurationError, validate_revenue_input
from test_revenue_sql_postgres import connection, execute


def cost_config():
    conf = config(cost=True)
    conf['revenue']['cost']['event'] = event('expense')
    return conf


SOURCE = """events(subject, day, event_name, category, amount, cost, payload) AS (VALUES
 ('A',20260901,'start','one',NULL::numeric,NULL::numeric,'{}'::jsonb),
 ('A',20260901,'start','one',NULL,NULL,'{}'),
 ('B',20260901,'start','one',NULL,NULL,'{}'),
 ('C',20260903,'start',NULL,NULL,NULL,'{}'),
 ('A',20260901,'purchase','one',10,999,'{}'),
 ('A',20260901,'purchase','one',10,999,'{}'),
 ('A',20260901,'expense','one',NULL,2,'{}'),
 ('A',20260901,'expense','one',NULL,2,'{}'),
 ('B',20260902,'expense','one',NULL,3,'{}'),
 ('X',20260901,'expense','one',NULL,1000,'{}'),
 ('A',20260904,'expense','one',NULL,1000,'{}'),
 ('C',20260903,'expense',NULL,NULL,5,'{}'))"""


def test_native_cost_keeps_equal_amount_details_and_nonpaying_cohort_members(connection):
    conf = cost_config(); conf['groups'] = [field('category')]
    rows = execute(connection, conf, source=SOURCE)
    assert rows == [(date(2026,9,1),2,20,0,0,7,'one'),
                    (date(2026,9,3),1,0,None,None,None,None)]


def test_enabled_cost_requires_explicit_event_without_payment_fallback():
    conf = cost_config(); del conf['revenue']['cost']['event']
    assert any(i.path == 'revenue.cost.event' for i in validate_revenue_input(conf))


def test_cost_property_resolves_against_cost_event_only():
    conf = cost_config()
    conf['revenue']['cost']['field'] = {**field('cost'), 'eventName':'expense'}
    actual = plan(conf)
    assert "'expense'" in actual.cost_event.predicate
    assert actual.cost_event.cost and not actual.payment.cost
    conf['revenue']['cost']['field']['eventName'] = 'purchase'
    with pytest.raises(RevenueConfigurationError): plan(conf)


@pytest.mark.parametrize('mutation',['table','missing_dictionary_event'])
def test_cost_event_obeys_authorized_table_and_workspace_dictionary(mutation):
    conf = cost_config()
    tracking = None
    if mutation == 'table': conf['revenue']['cost']['event']['eventTable']='private'
    else: tracking={'enabled':True,'default_event_table':'events','default_event_name_field':'event_name',
                    'event_name_mappings':[{'event_name':'start'},{'event_name':'purchase'}]}
    with pytest.raises(RevenueConfigurationError): plan(conf,tracking=tracking)


def test_disabled_cost_does_not_resolve_stale_event_or_field():
    conf = cost_config(); conf['revenue']['cost']={'enabled':False,'event':event('private'), 'field':field('missing')}
    actual=plan(conf)
    assert actual.cost_event is None and 'cost_value' not in actual.required_columns


@pytest.mark.parametrize('method,expected', [
    ('count',4), ('entity_count',2), ('per_entity_count',2),
    ('period_cumulative_count',4), ('period_average_count',4/3),
    ('period_cumulative_entity_count',3), ('period_average_entity_count',1),
    ('property_sum',11), ('property_avg',2.75),
])
def test_cost_supports_the_same_metric_choices_with_window_semantics(connection, method, expected):
    conf=cost_config(); conf['revenue']['cost']['method']=method
    if not method.startswith('property_'):conf['revenue']['cost']['field']=None
    source=SOURCE.replace(" ('B',20260902", " ('A',20260902,'expense','one',NULL,4,'{}'),\n ('B',20260902")
    rows=execute(connection,conf,source=source)
    assert float(rows[0][-1]) == pytest.approx(expected)
    assert rows[1][-1] is None


@pytest.mark.parametrize('method', [None, '', 'unsupported', [], {}])
def test_missing_or_unknown_cost_method_does_not_become_sum_or_count(method):
    conf=cost_config(); conf['revenue']['cost']['method']=method
    assert any(i.path == 'revenue.cost.method' for i in validate_revenue_input(conf))
