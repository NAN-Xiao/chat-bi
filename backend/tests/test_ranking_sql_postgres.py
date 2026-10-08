import os
import psycopg
import pytest
from apps.dashboard.crud.ranking_sql_compiler import compile_ranking_sql
from ranking_sql_fixture import config, plan, field

SOURCE = """events(subject,day,event_name,category,amount,payload) AS (VALUES
 ('A',20260901,'visit','one',10::numeric,'{}'::jsonb),('A',20260901,'visit','one',10,'{}'),
 ('B',20260901,'visit','two',30,'{}'),('B',20260901,'visit','two',NULL,'{}'),
 ('C',20260901,'visit',NULL,NULL,'{}'),(NULL,20260901,'visit','one',99,'{}'),
 ('A',20260901,'purchase','one',5,'{}'),('A',20260901,'purchase','one',5,'{}'),
 ('X',20260901,'purchase','one',1000,'{}'),('A',20260801,'visit','old',1000,'{}'))"""

@pytest.fixture
def connection():
    dsn = os.getenv("RANKING_TEST_POSTGRES_DSN")
    if not dsn: pytest.skip("RANKING_TEST_POSTGRES_DSN not set")
    with psycopg.connect(dsn,connect_timeout=5) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        yield conn
        conn.rollback()

def execute(conn,conf=None,source=SOURCE):
    sql = compile_ranking_sql(plan(conf))
    sql = sql.replace("{{dashboard_start_yyyymmdd}}","20260901").replace("{{dashboard_end_yyyymmdd}}","20260928")
    return conn.execute("WITH " + source + ", " + sql.removeprefix("WITH ")).fetchall()

@pytest.mark.parametrize("tie,ranks", [("default",[1,2,3]),("skip",[1,1,3]),("dense",[1,1,2])])
def test_ties_and_independent_metrics(connection,tie,ranks):
    rows = execute(connection,config(tie=tie))
    assert [r[0] for r in rows] == ranks
    assert [r[1] for r in rows] == ["A","B","C"]
    assert rows[0][2:] == (2,10,2,"one",0)
    assert rows[1][2:] == (2,None,0,"two",0)
    assert rows[2][2:] == (1,None,0,None,0)

@pytest.mark.parametrize("agg,expected", [("sum",{"A":20,"B":30,"C":None}),("avg",{"A":10,"B":30,"C":None}),
 ("min",{"A":10,"B":30,"C":None}),("max",{"A":10,"B":30,"C":None}),("count_distinct",{"A":1,"B":1,"C":0})])
def test_aggregates_preserve_null_semantics(connection,agg,expected):
    rows = execute(connection,config(agg))
    assert {r[1]:r[2] for r in rows} == expected
    if agg != "count_distinct": assert rows[-1][1] == "C"

def test_ascending_keeps_null_last(connection):
    rows = execute(connection,config("sum",direction="asc"))
    assert [r[1] for r in rows] == ["A","B","C"]

@pytest.mark.parametrize("changed", ["other","NULL"])
def test_attribute_conflict_marks_every_row_even_outside_preview(connection,changed):
    replacement = "NULL" if changed == "NULL" else "'other'"
    source = SOURCE.replace("('A',20260901,'visit','one',10,'{}')",f"('A',20260901,'visit',{replacement},10,'{{}}')")
    rows = execute(connection,source=source)
    assert all(r[-1] == 1 for r in rows)

def test_no_attribute_selection_does_not_block_conflicting_source(connection):
    rows = execute(connection,config(properties=False),SOURCE.replace("'one',10,'{}'","'other',10,'{}'"))
    assert all(r[-1] == 0 for r in rows)

def test_global_filter_and_empty_result(connection):
    conf = config(); conf["filters"] = {"rules":[{"field":field("subject"),"operator":"eq","value":"A"}]}
    assert len(execute(connection,conf)) == 1
    conf["filters"]["rules"][0]["value"] = "missing"
    assert execute(connection,conf) == []
