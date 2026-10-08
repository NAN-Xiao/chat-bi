"""Execute generated queries using VALUES fixtures in a read-only transaction."""
import os
from decimal import Decimal
import pytest
import psycopg
from psycopg.rows import dict_row
from attribution_compiler_fixture import config, plan, field
from apps.dashboard.crud.attribution_sql_compiler import compile_attribution_sql

@pytest.fixture(scope="module")
def db():
    dsn = os.environ.get("ATTRIBUTION_TEST_POSTGRES_DSN")
    if not dsn: pytest.skip("ATTRIBUTION_TEST_POSTGRES_DSN is not configured")
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        yield connection
        connection.rollback()

def row(i, actor, kind, time, amount=None, channel=None, session=None, day="2026-09-01"):
    return (i, actor, kind, time, day, amount, channel, session, '{}')

def execute(db, rows, conf=None):
    sql = compile_attribution_sql(plan(conf))
    if rows:
        values = ','.join('(%s::bigint,%s::text,%s::text,%s::timestamptz,%s::date,%s::numeric,%s::text,%s::text,%s::jsonb)' for r in rows)
        source = f'events(id,actor,kind,occurred_at,day,amount,channel,session,payload) AS (VALUES {values})'
    else:
        source = 'events AS (SELECT NULL::bigint AS id,NULL::text AS actor,NULL::text AS kind,NULL::timestamptz AS occurred_at,NULL::date AS "day",NULL::numeric AS amount,NULL::text AS channel,NULL::text AS session,NULL::jsonb AS payload WHERE FALSE)'
    sql = sql.replace('WITH ',f'WITH {source}, ',1).replace('{{dashboard_start_date}}',"'2026-09-01'::date").replace('{{dashboard_end_date}}',"'2026-09-28'::date")
    result = db.execute(sql, [v for r in rows for v in r]).fetchall()
    if any(r.get('__attribution_data_error') for r in result): raise ValueError('事件时间或排序键为空或重复')
    return [{k:v for k,v in r.items() if k != '__attribution_data_error'} for r in result]

ROWS = [row(1,'a','email','2026-09-01 09:00+08'), row(2,'a','search','2026-09-01 10:00+08'),
        row(3,'a','convert','2026-09-01 11:00+08',100),row(4,'a','convert','2026-09-01 12:00+08',60),
        row(5,'b','email','2026-09-01 20:00+08'),row(6,'c','convert','2026-09-01 12:00+08',40)]

@pytest.mark.parametrize("method,email,search", [('first',160,0),('last',0,160),('linear',80,80)])
def test_multiple_targets_reuse_touch_and_keep_zero_rows(db,method,email,search):
    result = {r['attribution_event']:r for r in execute(db,ROWS,config(method))}
    assert result['email']['attributed_value'] == email
    assert result['search']['attributed_value'] == search
    assert result['email']['total_touch_count'] == 2
    assert result['search']['total_touch_count'] == 1
    for event in ('email','search'):
        expected = int((event == 'email' and email > 0) or (event == 'search' and search > 0))
        assert result[event]['effective_touch_count'] == expected
        assert result[event]['effective_entity_count'] == expected
    direct = result['直接转化']
    assert direct['attributed_value'] == 40 and direct['effective_touch_count'] == 0
    assert direct['effective_touch_rate'] is None
    assert sum(r['contribution_rate'] for r in result.values()) == 100

@pytest.mark.parametrize("aggregation,expected", [('count',2),('sum',160),('avg',80),('max',100),('min',60),('count_distinct',2)])
def test_first_nonadditive_aggregates_original_target_values(db,aggregation,expected):
    result = {r['attribution_event']:r for r in execute(db,ROWS,config('first',aggregation,False))}
    assert result['email']['attributed_value'] == expected
    assert result['email']['contribution_rate'] == 100
    assert result['search']['attributed_value'] == 0
    assert '直接转化' not in result

def test_same_timestamp_uses_stable_sequence(db):
    rows = [row(2,'a','search','2026-09-01 09:00+08'),row(1,'a','email','2026-09-01 09:00+08'),row(3,'a','convert','2026-09-01 10:00+08',100)]
    for method,chosen in [('first','email'),('last','search')]:
        result = {r['attribution_event']:r for r in execute(db,rows,config(method))}
        assert result[chosen]['attributed_value'] == 100

def test_exact_duration_extends_scan_and_excludes_future_touch(db):
    conf = config(); conf['attribution']['window'] = {'mode':'duration','unit':'minute','value':60}
    rows = [row(1,'a','email','2026-08-31 23:30+08',day='2026-08-31'),row(2,'a','search','2026-08-31 23:29:59.999999+08',day='2026-08-31'),
            row(3,'a','convert','2026-09-01 00:30+08',100),row(4,'a','search','2026-09-01 00:30:00.000001+08')]
    result = {r['attribution_event']:r for r in execute(db,rows,conf)}
    assert result['email']['attributed_value'] == 100
    assert result['search']['attributed_value'] == 0
    assert result['search']['total_touch_count'] == 2
    same_day = {r['attribution_event']:r for r in execute(db,rows,config())}
    assert same_day['直接转化']['attributed_value'] == 100
    assert same_day['search']['attributed_value'] == 0

def test_related_property_null_does_not_match(db):
    conf = config()
    for event in conf['attribution']['events']:
        event['relatedProperty'] = {'enabled':True,'targetProperty':field('session'),'touchProperty':field('session')}
    result = {r['attribution_event']:r for r in execute(db,ROWS,conf)}
    assert result['直接转化']['attributed_value'] == 200
    assert result['email']['effective_touch_count'] == 0

@pytest.mark.parametrize('side',['target','touch'])
def test_null_groups_join_and_denominator_does_not_multiply(db,side):
    conf = config(); conf['groups'] = [{**field('channel'),'attributionSide':side}]
    result = execute(db,ROWS,conf)
    assert all(r['group_1'] is None for r in result)
    assert sum(r['attributed_value'] for r in result) == 200
    assert sum(r['contribution_rate'] for r in result) == 100

def test_empty_and_touch_only_input(db):
    assert execute(db,[]) == []
    result = execute(db,[ROWS[0]])
    assert len(result) == 1 and result[0]['total_touch_count'] == 1
    assert result[0]['target_count'] == 0 and result[0]['contribution_rate'] is None

def test_each_touch_event_keeps_its_own_related_attribute_type(db):
    conf = config()
    for item, name in zip(conf['attribution']['events'],['amount','session']):
        item['relatedProperty'] = {'enabled':True,'targetProperty':field(name),'touchProperty':field(name)}
    rows = [row(1,'a','email','2026-09-01 09:00+08',100),row(2,'a','search','2026-09-01 09:01+08',session='s'),row(3,'a','convert','2026-09-01 10:00+08',100,session='s')]
    result = {r['attribution_event']:r for r in execute(db,rows,conf)}
    assert result['email']['attributed_value'] == 50
    assert result['search']['attributed_value'] == 50

@pytest.mark.parametrize('case',['null_time','null_order','duplicate_order'])
def test_invalid_source_data_is_explicit_and_atomic(db,case):
    rows = list(ROWS)
    if case == 'null_time': rows.append(row(7,'a','email',None))
    if case == 'null_order': rows.append(row(None,'a','email','2026-09-01 08:00+08'))
    if case == 'duplicate_order': rows.append(ROWS[0])
    with pytest.raises(ValueError,match='事件时间或排序键'): execute(db,rows,config('first'))
