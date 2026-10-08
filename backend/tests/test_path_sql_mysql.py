"""Opt-in read-only constant fixtures on the explicitly selected MySQL datasource."""
import copy
import json
import os
import pytest
from sqlmodel import Session
from sqlglot import exp
from common.core.db import engine
from apps.datasource.models.datasource import CoreDatasource
from apps.db.db import get_session
from apps.dashboard.crud.path_sql_compiler import compile_path_sql
from path_compiler_fixture import config, plan, field, TRACKING


@pytest.fixture
def mysql():
    identity=os.environ.get("PATH_TEST_MYSQL_DATASOURCE_ID")
    if not identity: pytest.skip("PATH_TEST_MYSQL_DATASOURCE_ID required")
    with Session(engine) as core:
        ds=core.get(CoreDatasource,int(identity))
        assert ds is not None and ds.type=="mysql"
        with get_session(ds,timeout=20) as db:
            yield db
            db.rollback()


def run(mysql,values,kind,targets=None):
    t=copy.deepcopy(TRACKING);t["event_name_mappings"][0]["properties"][0]["property_type"]=kind
    c=config();c["path"]["events"][0]["splitProperties"]=[{**field("score"),"kind":"tracking-property","eventName":"A"}]
    sql=compile_path_sql(plan(c,tracking=t,dialect="mysql"))
    rows=[]
    quote=lambda s:exp.Literal.string(s).sql(dialect="mysql")
    for i,value in enumerate(values):
        for n,event in enumerate(("A",targets[i] if targets else "B")):
            rows.append(f"SELECT {quote(str(i))} AS subject,{quote(event)} AS action,{n} AS occurred_at,{n} AS sequence,"
                        f"{quote('{'+chr(34)+'score'+chr(34)+':'+value+'}')} AS payload,CAST('2026-09-28' AS DATE) AS day")
    sql=sql.replace('WITH ', 'WITH events AS ('+' UNION ALL '.join(rows)+'), ',1)
    sql=sql.replace('{{dashboard_start_date}}',"CAST('2026-09-28' AS DATE)").replace('{{dashboard_end_date}}',"CAST('2026-09-28' AS DATE)")
    return mysql.connection().exec_driver_sql(sql).fetchall()


def test_json_text_null_is_not_literal_null(mysql):
    rows=run(mysql,['null','"null"','""'],'string',targets=['B','C','B'])
    assert {(r[0],r[1]):int(r[2]) for r in rows}=={
        ('"A" / "score"=null','"B"'):1, ('"A" / "score"="null"','"C"'):1, ('"A" / "score"=""','"B"'):1}


def test_json_numeric_null_is_not_zero(mysql):
    rows=run(mysql,['null','0','"0"'],'int')
    assert len(rows)==2 and any(r[0]=='"A" / "score"=null' and r[2]==1 for r in rows)
    assert sum(int(r[2]) for r in rows)==3


def test_text_node_encoding_round_trips_quotes_controls_and_unicode(mysql):
    values=['a"b\\c','line\n\tend','\x00',':: / =','中文']
    rows=run(mysql,[json.dumps(v,ensure_ascii=False) for v in values],'string')
    assert {json.loads(r[0].split('=',1)[1]) for r in rows}==set(values)
