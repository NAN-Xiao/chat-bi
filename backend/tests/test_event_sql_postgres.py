"""Real read-only VALUES execution with independent literal expected values."""
import os
from copy import deepcopy
from datetime import date
import psycopg
import pytest
from event_sql_fixture import build, config, formula_config, field, metric

SOURCE="""events(action, actor, day_key, amount, category, region, payload) AS (VALUES
 ('View','u1',20260901,NULL::numeric,'A','X','{}'::jsonb),
 ('View','u1',20260901,NULL,'A','X','{}'),
 ('Pay','u1',20260901,10,'A','X','{"value":10}'),
 ('Pay','u2',20260901,10,'A','X','{"value":10}'),
 ('View','u3',20260903,NULL,'B','Y','{}'),
 ('Pay','u3',20260903,NULL,'B','Y','{}'),
 ('Other','u4',20260902,999,'C','Z','{}'))"""

@pytest.fixture
def connection():
    dsn=os.environ.get("EVENT_TEST_POSTGRES_DSN")
    if not dsn:pytest.skip("EVENT_TEST_POSTGRES_DSN not set")
    with psycopg.connect(dsn,connect_timeout=5) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        yield conn
        conn.rollback()

def execute(conn,c,source=SOURCE):
    from apps.dashboard.crud.event_sql_compiler import compile_event_sql
    sql=compile_event_sql(build(c)).replace("{{dashboard_start_yyyymmdd}}","20260901").replace("{{dashboard_end_yyyymmdd}}","20260903")
    return conn.execute("WITH "+source+", "+sql[5:]).fetchall()

def test_independent_measures_and_formula_do_not_multiply_details(connection):
    c=formula_config();rows=execute(connection,c)
    assert len(rows)==6
    assert rows[0]==(date(2026,9,1),'A',20,1,20)
    assert rows[1]==(date(2026,9,1),'B',None,0,None)
    assert rows[2:4]==[(date(2026,9,2),'A',None,0,None),(date(2026,9,2),'B',None,0,None)]
    assert rows[-1]==(date(2026,9,3),'B',None,1,None)

def test_trend_date_is_a_real_date_even_when_source_uses_numeric_partition_key(connection):
    rows=execute(connection,config())
    assert rows[0][0]==date(2026,9,1)

@pytest.mark.parametrize("aggregation,want",[("count",2),("count_distinct",2),("sum",20),("avg",10),("min",10),("max",10)])
def test_all_aggregates_preserve_real_equal_value_rows(connection,aggregation,want):
    c=config(aggregation,groups=True);c["metrics"][0]=metric("Pay",aggregation,measure="actor" if aggregation=="count_distinct" else "amount")
    rows=execute(connection,c);assert rows[0][2]==want
    assert rows[2][2]==(0 if aggregation in {"count","count_distinct"} else None)

def test_group_domain_contains_complete_tuples_only(connection):
    c=config(groups=True);c["groups"].append(field("region"));rows=execute(connection,c)
    assert len(rows)==6 and {(r[1],r[2]) for r in rows}=={('A','X'),('B','Y')}

def test_null_dimension_is_preserved(connection):
    c=config(groups=True);rows=execute(connection,c,SOURCE.replace("'A','X'","NULL,'X'"))
    assert len(rows)==6 and any(r[1] is None and r[2]==2 for r in rows)

def test_formula_only_atoms_are_not_lost(connection):
    c=formula_config();m=c.pop("metrics");c["metrics"]=[]
    c["formulaMetrics"][0]["tokens"][0]={"type":"atomicMetric","metric":m[0]}
    c["formulaMetrics"][0]["tokens"][2]={"type":"atomicMetric","metric":m[1]}
    assert execute(connection,c)[0]==(date(2026,9,1),'A',20)

def test_card_has_one_full_range_aggregate_without_repeated_dates(connection):
    c=config(card=True);assert execute(connection,c)==[(3,)]

def test_empty_group_source_does_not_invent_categories(connection):
    c=config(groups=True);c["filters"]={"rules":[{"field":field("category"),"operator":"eq","value":"none"}]}
    assert execute(connection,c)==[]

def test_empty_ungrouped_trend_preserves_dates(connection):
    c=config();c["filters"]={"rules":[{"field":field("category"),"operator":"eq","value":"none"}]}
    assert execute(connection,c)==[(date(2026,9,1),0),(date(2026,9,2),0),(date(2026,9,3),0)]

def test_json_parameter_is_computed_from_each_real_detail(connection):
    c=config("sum",groups=True);c["metrics"][0]["field"]["eventName"]="Pay"
    c["metrics"][0]["metricField"]={**field("value"),"kind":"tracking-property","propertyName":"value","eventName":"Pay"}
    assert execute(connection,c)[0]==(date(2026,9,1),'A',20)

def test_constant_only_formula_calendar_and_card(connection):
    c=config();c["metrics"]=[];c["formulaMetrics"]=[{"id":"f","alias":"常量","tokens":[{"type":"number","value":"3"}]}]
    assert execute(connection,c)==[(date(2026,9,1),3),(date(2026,9,2),3),(date(2026,9,3),3)]
    c["chart"]["type"]="metric";assert execute(connection,c)==[(3,)]
