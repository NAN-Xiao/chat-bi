"""Opt-in engine verification using synthetic CTE rows, never business table writes."""
import os
from datetime import datetime
import pytest
from sqlglot import exp
from attribution_compiler_fixture import FIELDS, config, plan
from apps.dashboard.crud.attribution_sql_compiler import compile_attribution_sql

@pytest.fixture(scope='module')
def ds():
    source_id = os.environ.get('ATTRIBUTION_TEST_MYSQL_DATASOURCE_ID')
    if not source_id: pytest.skip('ATTRIBUTION_TEST_MYSQL_DATASOURCE_ID is not configured')
    from common.core.db import engine
    from sqlmodel import Session
    from apps.datasource.models.datasource import CoreDatasource
    with Session(engine) as session:
        datasource = session.get(CoreDatasource,int(source_id))
        assert datasource and datasource.type == 'mysql'
        session.expunge(datasource)
        return datasource

def execute(ds, conf):
    from apps.db.db import _unsafe_exec_sql_after_validation
    fields = {**FIELDS,'occurred_at':{'type':'bigint','field_role':'event_time','extra_properties':{'encoding':'epoch_milliseconds'}}}
    p = plan(conf,metadata_fields={'events':fields},dialect='mysql',engine='mysql')
    def instant(hour): return int(datetime.fromisoformat(f'2026-09-01T{hour:02}:00:00+08:00').timestamp()*1000)
    rows = [(1,'a','email',instant(9),100,'s'),(2,'a','search',instant(10),0,'s'),(3,'a','convert',instant(11),100,'s'),(4,'a','convert',instant(12),60,'s'),(5,'b','convert',instant(12),40,None)]
    branches = []
    for i,actor,kind,time,amount,session in rows:
        lit = lambda v: exp.convert(v).sql(dialect='mysql')
        branches.append(f"SELECT {i} AS id,{lit(actor)} AS actor,{lit(kind)} AS kind,{time} AS occurred_at,CAST('2026-09-01' AS DATE) AS `day`,{amount} AS amount,NULL AS channel,{lit(session)} AS session,NULL AS payload")
    sql = compile_attribution_sql(p).replace('WITH ','WITH events AS ('+' UNION ALL '.join(branches)+'), ',1)
    sql = sql.replace('{{dashboard_start_date}}',"'2026-09-01'").replace('{{dashboard_end_date}}',"'2026-09-28'")
    result = _unsafe_exec_sql_after_validation(ds,sql)
    assert all(r['__attribution_data_error'] == 0 for r in result['data'])
    return {r['attribution_event']:r for r in result['data']}

@pytest.mark.parametrize('method,email,search',[('linear',80,80),('first',160,0),('last',0,160)])
def test_mysql_native_templates_execute_real_engine(ds,method,email,search):
    result = execute(ds,config(method))
    assert result['email']['attributed_value'] == email
    assert result['search']['attributed_value'] == search
    assert result['直接转化']['attributed_value'] == 40
    assert result['直接转化']['effective_touch_rate'] is None
    assert result['email']['total_touch_count'] == 1

def test_mysql_duration_and_independent_related_columns(ds):
    from attribution_compiler_fixture import field
    conf = config(); conf['attribution']['window'] = {'mode':'duration','value':24,'unit':'hour'}
    for item,name in zip(conf['attribution']['events'],['amount','session']):
        item['relatedProperty'] = {'enabled':True,'targetProperty':field(name),'touchProperty':field(name)}
    assert execute(ds,conf)['email']['attributed_value'] == 50
