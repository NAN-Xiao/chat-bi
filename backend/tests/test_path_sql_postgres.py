import copy
import json
import os
import pytest
import psycopg
from path_compiler_fixture import config, plan, field, FIELDS
from apps.dashboard.crud.path_sql_compiler import compile_path_sql


@pytest.fixture(scope="module")
def db():
    dsn=os.environ.get("PATH_TEST_POSTGRES_DSN")
    if not dsn: pytest.skip("PATH_TEST_POSTGRES_DSN is not configured")
    with psycopg.connect(dsn) as c:
        c.execute("SET TRANSACTION READ ONLY")
        yield c
        c.rollback()


def execute(db,rows,c=None,fields=None,tracking=None):
    sql=compile_path_sql(plan(c,fields=fields,tracking=tracking))
    time_type=(fields or FIELDS)["occurred_at"]["type"]
    values=','.join(f'(%s::text,%s::text,%s::{time_type},%s::bigint,%s::text,%s::json,%s::date)' for _ in rows)
    source=f'events(subject,action,occurred_at,sequence,category,payload,day) AS (VALUES {values})' if rows else (
        'events AS (SELECT NULL::text AS subject,NULL::text AS action,NULL::bigint AS occurred_at,NULL::bigint AS sequence,'
        'NULL::text AS category,NULL::json AS payload,NULL::date AS day WHERE FALSE)')
    sql=sql.replace('WITH ',f'WITH {source}, ',1).replace('{{dashboard_start_date}}',"'2026-09-01'::date").replace('{{dashboard_end_date}}',"'2026-09-28'::date")
    return db.execute(sql,[v for r in rows for v in r]).fetchall()


def row(subject,action,ms,seq,category=None,day="2026-09-01"):
    return (str(subject) if subject is not None else None,action,ms,seq,category,'{"score":0}',day)


def edges(result):
    return [(json.loads(a),json.loads(b),int(n),int(step)) for a,b,n,step,guard in result if guard==0]


def test_later_edges_anchor_and_repeated_sessions(db):
    rows=[row(1,"A",0,1),row(1,"B",1,2),row(1,"C",2,3),row(1,"A",1800003,4),row(1,"B",1800004,5),row(1,"C",1800005,6),
          row(2,"B",0,1),row(2,"A",1,2),row(2,"C",2,3)]
    assert edges(execute(db,rows))==[("A","B",2,1),("B","C",2,2)]


def test_exact_gap_and_nonparticipating_events(db):
    assert edges(execute(db,[row(1,"A",0,1),row(1,"B",1800000,2)]))==[("A","B",1,1)]
    assert execute(db,[row(1,"A",0,1),row(1,"B",1800001,2)])==[]
    assert execute(db,[row(1,"A",0,1),row(1,"X",1800000,2),row(1,"B",3600000,3)])==[]


def test_repetition_max_nodes_and_empty(db):
    result=edges(execute(db,[row(1,"A" if n%2==0 else "B",n,n) for n in range(11)]))
    assert len(result)==9 and result[-1][3]==9
    assert execute(db,[row(1,"A",0,1)])==[]
    assert execute(db,[])==[]


@pytest.mark.parametrize("rows", [[row(1,"A",0,1),row(1,"B",0,1)], [row(1,"A",None,1)], [row(1,"A",0,None)]])
def test_invalid_order_only_returns_error(db,rows):
    assert execute(db,rows)==[(None,None,None,None,1)]


def test_time_only_order_and_tie_keys(db):
    f=copy.deepcopy(FIELDS); f["sequence"].pop("field_role")
    assert execute(db,[row(1,"A",0,1),row(1,"B",0,2)],fields=f)==[(None,None,None,None,1)]
    assert edges(execute(db,[row(1,"B",0,2),row(1,"A",0,1)]))==[("A","B",1,1)]


def test_cross_day_does_not_reset_and_null_subject_excluded(db):
    assert edges(execute(db,[row(1,"A",0,1),row(1,"B",1,2,day="2026-09-02"),row(None,"A",None,None)]))==[("A","B",1,1)]


def test_split_null_empty_text_and_json_zero(db):
    c=config(); c["path"]["events"][0]["splitProperties"]=[field("category")]
    rows=[row(i,ev,n,n,category) for i,category in enumerate((None,"","null","x / y=\"z")) for n,ev in enumerate(("A","B"))]
    result=execute(db,rows,c)
    assert len(result)==4 and len({r[0] for r in result})==4
    c["path"]["events"][0]["splitProperties"]=[{**field("score"),"kind":"tracking-property","eventName":"A"}]
    assert len(execute(db,rows,c))==1


def test_json_boolean_false_filter_and_typed_split(db):
    from path_compiler_fixture import TRACKING
    t=copy.deepcopy(TRACKING); t["event_name_mappings"][0]["properties"][0]["property_type"]="boolean"
    c=config(); prop={**field("score"),"kind":"tracking-property","eventName":"A"}
    c["path"]["events"][0]["splitProperties"]=[prop]
    c["filters"]={"logic":"or","rules":[{"field":prop,"operator":"eq","value":False},
        {"field":field("action"),"operator":"eq","value":"B"}]}
    rows=[]
    for i,value in enumerate((True,False)):
        for n,ev in enumerate(("A","B")):
            r=list(row(i,ev,n,n));r[5]=json.dumps({"score":value});rows.append(r)
    result=execute(db,rows,c,tracking=t)
    assert len(result)==1 and result[0][0]=='"A" / "score"=false' and result[0][2]==1


def test_equal_numeric_split_values_share_one_node_regardless_of_scale(db):
    c=config(); c["path"]["events"][0]["splitProperties"]=[{**field("score"),"kind":"tracking-property","eventName":"A"}]
    rows=[]
    for i,value in enumerate(('1','1.0','1.00')):
        for n,ev in enumerate(("A","B")):
            r=list(row(i,ev,n,n));r[5]='{"score":'+value+'}';rows.append(r)
    result=execute(db,rows,c)
    assert len(result)==1 and result[0][0]=='"A" / "score"=1' and result[0][2]==3


@pytest.mark.parametrize("encoding,end",[("epoch_seconds","1800.000000001"),("epoch_milliseconds","1800000.000000001")])
def test_epoch_fractional_precision_is_not_rounded_at_session_boundary(db,encoding,end):
    f=copy.deepcopy(FIELDS);f["occurred_at"]["type"]="numeric(30,9)"
    f["occurred_at"]["extra_properties"]["encoding"]=encoding
    assert execute(db,[row(1,"A",0,1),row(1,"B",end,2)],fields=f)==[]
