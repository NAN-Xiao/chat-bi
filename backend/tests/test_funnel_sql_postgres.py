"""Native read-only SQL result checks; the fixture creates no persistent objects."""
import copy
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import psycopg
import pytest

from apps.dashboard.crud.funnel_sql_compiler import compile_funnel_sql
from common.core.config import settings
from test_funnel_sql_plan import config, field, plan, FIELDS
from test_funnel_sql_compiler import params, row


@pytest.fixture
def connection():
    dsn = os.environ.get("FUNNEL_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("FUNNEL_TEST_POSTGRES_DSN required for read-only VALUES checks")
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        conn.execute("SET LOCAL TIME ZONE 'UTC'")
        yield conn
        conn.rollback()


def execute(conn, rows, conf=None, *, fields=None):
    p = plan(conf, fields=fields)
    sql = params(compile_funnel_sql(p))
    source = "events(subject,action,occurred_at,category,dt,payload) AS (VALUES "
    bindings = []
    values = []
    kind = (fields or FIELDS)["occurred_at"]["type"]
    for user,event,time,related,dt in rows:
        values.append(f"(%s::text,%s::text,%s::{kind},%s::text,%s::integer,NULL::jsonb)")
        bindings.extend([user,event,time,related,dt])
    if not values:
        source = f"events AS (SELECT NULL::text AS subject, NULL::text AS action, NULL::{kind} AS occurred_at, NULL::text AS category, NULL::integer AS dt, NULL::jsonb AS payload WHERE FALSE), "
    else:
        source += ",".join(values) + "), "
    return conn.execute("WITH " + source + sql[5:], bindings).fetchall()


def test_native_counts_ratios_and_later_candidate(connection):
    rows = [row("u1","A",0),row("u1","A",0),row("u1","B",1),row("u1","C",2),row("u2","A",0),
            row("u3","A",0),row("u3","B",1),row("u4","A",0),row("u4","A",200000000),row("u4","B",200000001),row("u4","C",200000002)]
    result=execute(connection,rows)
    assert [r[2] for r in result] == [4,3,2]
    assert [float(r[3]) for r in result] == [1,.75,.5]
    assert [float(r[4]) for r in result] == pytest.approx([1,.75,2/3],abs=1e-9)


def test_native_related_paths_empty_result_and_null_keys(connection):
    c=config(); c["funnel"].update(relatedPropertyEnabled=True,relatedProperty=field("category"))
    rows=[row("u","A",0,"X"),row("u","A",0,"Y"),row("u","B",1,"X"),row("u","C",2,"Y"),
          row("n","A",0,None),row("n","B",1,None)]
    assert [r[2] for r in execute(connection,rows,c)] == [2,1,0]
    assert execute(connection,[],c) == [(1,"A",0,None,None,None),(2,"B",0,None,None,None),(3,"C",0,None,None,None)]


@pytest.mark.parametrize("encoding",["epoch_seconds","epoch_milliseconds","datetime","timestamptz"])
def test_native_time_precision_and_business_calendar(connection,encoding):
    c=config(); fields=copy.deepcopy(FIELDS)
    fields["occurred_at"]={"type":"timestamp" if encoding=="datetime" else "timestamptz" if encoding=="timestamptz" else "numeric",
        "field_role":"event_time","extra_properties":{"encoding":encoding if encoding.startswith("epoch") else "datetime","timezone":settings.DASHBOARD_BUSINESS_TIMEZONE}}
    zone=ZoneInfo(settings.DASHBOARD_BUSINESS_TIMEZONE)
    def value(iso):
        time=datetime.fromisoformat(iso).replace(tzinfo=zone)
        if encoding=="datetime": return time.replace(tzinfo=None)
        if encoding=="timestamptz": return time
        # String/Decimal preserves sub-second boundary values in the database.
        from decimal import Decimal
        seconds=Decimal(str(time.timestamp()))
        return seconds*(1000 if encoding=="epoch_milliseconds" else 1)
    rows=[row("u","A",value("2026-09-01T23:59:00")),row("u","B",value("2026-09-02T00:00:00")),
          row("u","C",value("2026-09-02T23:59:00")),row("v","A",value("2026-09-01T23:59:00")),
          row("v","B",value("2026-09-02T00:00:00")),row("v","C",value("2026-09-02T23:59:00.001"))]
    assert [r[2] for r in execute(connection,rows,c,fields=fields)]==[2,2,1]
    c["funnel"]["window"]={"mode":"same_day"}
    assert [r[2] for r in execute(connection,rows,c,fields=fields)]==[2,0,0]


def test_native_ten_repeated_steps_and_step_filter(connection):
    c=config(); c["funnel"]["steps"]=[copy.deepcopy(c["funnel"]["steps"][0]) for _ in range(10)]
    assert [r[2] for r in execute(connection,[row("u","A",0)],c)]==[1]*10
    c["funnel"]["steps"][5]["filters"]={"rules":[{"field":field("category"),"operator":"eq","value":"Y"}]}
    assert [r[2] for r in execute(connection,[row("u","A",0)],c)]==[1]*5+[0]*5
