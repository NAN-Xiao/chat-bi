"""Execute the emitted PostgreSQL SQL over typed inline VALUES, read only."""
import copy
import os
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import psycopg
import pytest

from distribution_sql_fixture import config, field, plan, property_config, simultaneous, FIELDS
from apps.dashboard.crud.distribution_sql_compiler import compile_distribution_sql
from common.core.config import settings
from test_distribution_sql_compiler import row, parameters


@pytest.fixture
def connection():
    dsn=os.environ.get("DISTRIBUTION_TEST_POSTGRES_DSN")
    if not dsn: pytest.skip("DISTRIBUTION_TEST_POSTGRES_DSN required for read-only inline fixtures")
    with psycopg.connect(dsn,connect_timeout=5) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        conn.execute("SET LOCAL TIME ZONE 'UTC'")
        yield conn
        conn.rollback()


def execute(conn,rows,c=None,*,fields=None):
    sql=parameters(compile_distribution_sql(plan(c,fields=fields)))
    sql=sql.replace("{{dashboard_start_timestamp}}","TIMESTAMP '2026-09-01 00:00:00'").replace("{{dashboard_end_exclusive_timestamp}}","TIMESTAMP '2026-09-03 00:00:00'")
    names=("subject","action","dt","category","amount","tag","occurred_at","payload")
    definitions=fields or FIELDS
    bindings=[]; values=[]
    for data in rows:
        values.append("("+",".join(f"%s::{definitions[n]['type']}" for n in names)+")")
        bindings.extend(data)
    if values:
        source="events("+",".join(names)+") AS (VALUES "+",".join(values)+"), "
    else:
        source="events AS (SELECT "+",".join(f"NULL::{definitions[n]['type']} AS {n}" for n in names)+" WHERE FALSE), "
    cursor=conn.execute("WITH "+source+sql[5:],bindings)
    return [dict(zip([d.name for d in cursor.description],r)) for r in cursor.fetchall()]


@pytest.mark.parametrize("aggregation,expected",[("sum",16),("avg",4),("min",1),("max",9),("count_distinct",4),("median",3),
    ("variance",9.5),("stddev",9.5**0.5),("percentile_05",1.15),("percentile_10",1.3),
    ("percentile_20",1.6),("percentile_25",1.75),("percentile_30",1.9),("percentile_40",2.4),
    ("percentile_60",3.6),("percentile_70",4.5),("percentile_75",5.25),("percentile_80",6),
    ("percentile_90",7.5),("percentile_95",8.25),("percentile_99",8.85)])
def test_native_property_statistic_bucket_values(connection,aggregation,expected):
    rows=execute(connection,[row("A",v) for v in [1,2,4,9,None]],property_config(aggregation))
    assert len(rows)==1 and float(rows[0]["interval_label"])==pytest.approx(expected)
    assert rows[0]["entity_count"]==rows[0]["total_entities"]==1


@pytest.mark.parametrize("mode",["auto","discrete","custom"])
def test_native_buckets_population_and_null_group(connection,mode):
    c=property_config(); c["groups"]=[field("category")]; c["distribution"]["interval"]={"mode":mode,"customBounds":[0,10]}
    rows=execute(connection,[row("A",None),row("B",0),row("C",12,date=20260902),row("D",24,group="x")],c)
    assert sum(r["entity_count"] for r in rows)==4
    null_bucket=next(r for r in rows if r["interval_order"]==0)
    assert null_bucket["total_entities"]==2 and null_bucket["group_1"] is None
    if mode=="auto": assert {r["interval_order"] for r in rows}=={0,1,7,12}
    assert execute(connection,[],c)==[]


@pytest.mark.parametrize("aggregation,expected",[("avg",110/3),("sum",110),("min",0),("max",100),("count",3),("count_distinct",3)])
def test_native_simultaneous_is_separate_from_main_counts(connection,aggregation,expected):
    c=simultaneous(config(),aggregation)
    rows=execute(connection,[row("A"),row("B"),row("C"),row("C"),row("A",0,event="B"),row("A",10,event="B"),row("B",100,event="B")],c)
    assert [r["entity_count"] for r in rows]==[2,1]
    assert [r["total_entities"] for r in rows]==[3,3]
    assert float(rows[0]["simultaneous_value"])==pytest.approx(expected)
    assert rows[1]["simultaneous_value"]==(0 if aggregation in {"count","count_distinct"} else None)


@pytest.mark.parametrize("encoding",["epoch_seconds","epoch_milliseconds","datetime","timestamptz"])
@pytest.mark.parametrize("kind,expected",[("days",2),("hours",3)])
def test_native_calendar_metrics_use_real_event_time_and_ignore_session_timezone(connection,encoding,kind,expected):
    c=config(); c["distribution"]["metric"]["kind"]=kind
    fields=copy.deepcopy(FIELDS)
    fields["occurred_at"]={"type":"timestamp" if encoding=="datetime" else "timestamptz" if encoding=="timestamptz" else "numeric",
        "field_role":"event_time","extra_properties":{"encoding":encoding,"timezone":settings.DASHBOARD_BUSINESS_TIMEZONE}}
    def value(iso):
        t=datetime.fromisoformat(iso).replace(tzinfo=ZoneInfo(settings.DASHBOARD_BUSINESS_TIMEZONE))
        if encoding=="datetime": return t.replace(tzinfo=None)
        if encoding=="timestamptz": return t
        return Decimal(str(t.timestamp()))*(1000 if encoding=="epoch_milliseconds" else 1)
    rows=[row("A",instant=value(t)) for t in ("2026-09-01T02:10:00","2026-09-01T02:20:00","2026-09-01T03:00:00","2026-09-02T02:10:00")]
    first=execute(connection,rows,c,fields=fields)
    connection.execute("SET LOCAL TIME ZONE 'America/New_York'")
    second=execute(connection,rows,c,fields=fields)
    assert first==second and float(first[0]["interval_label"])==expected


def test_native_timestamp_range_excludes_exact_end(connection):
    c=config(); c["time"].update(field=field("occurred_at"),dateParameterType="timestamp")
    zone=ZoneInfo(settings.DASHBOARD_BUSINESS_TIMEZONE)
    value=lambda s: int(datetime.fromisoformat(s).replace(tzinfo=zone).timestamp()*1000)
    rows=execute(connection,[row("A",instant=value("2026-09-01T00:00:00")),row("B",instant=value("2026-09-02T23:59:59")),row("C",instant=value("2026-09-03T00:00:00"))],c)
    assert sum(r["entity_count"] for r in rows)==2


def test_native_precise_custom_boundaries_do_not_merge_labels(connection):
    c=property_config(); c["distribution"]["interval"]={"mode":"custom","customBounds":[Decimal("1.0000000000001"),Decimal("1.0000000000002")]}
    rows=execute(connection,[row("A",Decimal("1")),row("B",Decimal("1.0000000000001")),row("C",Decimal("1.0000000000002"))],c)
    assert [r["interval_order"] for r in rows]==[1,2,3] and len({r["interval_label"] for r in rows})==3


@pytest.mark.parametrize("data_type,edge",[("integer",2000000000),("bigint",9000000000000000000)])
def test_native_integer_intermediates_do_not_overflow(connection,data_type,edge):
    fields=copy.deepcopy(FIELDS); fields["amount"]={"type":data_type}
    c=property_config("min"); c["distribution"]["interval"]["mode"]="auto"
    rows=execute(connection,[row("A",-edge),row("B",edge)],c,fields=fields)
    assert [r["interval_order"] for r in rows]==[1,12]


@pytest.mark.parametrize("data_type,edge",[("integer",2000000000),("bigint",9000000000000000000)])
def test_native_integer_percentile_interpolation_promotes_before_subtraction(connection,data_type,edge):
    fields=copy.deepcopy(FIELDS); fields["amount"]={"type":data_type}
    rows=execute(connection,[row("A",-edge),row("A",edge)],property_config("median"),fields=fields)
    assert len(rows)==1 and Decimal(rows[0]["interval_label"])==0


def test_native_float_near_maximum_cannot_escape_twelfth_bucket(connection):
    import math
    fields=copy.deepcopy(FIELDS); fields["amount"]={"type":"double precision"}
    c=property_config("min"); c["distribution"]["interval"]["mode"]="auto"
    rows=execute(connection,[row("A",-1e16),row("B",math.nextafter(1e16,-math.inf)),row("C",1e16)],c,fields=fields)
    assert [(r["interval_order"],r["entity_count"]) for r in rows]==[(1,1),(12,2)]
    assert rows[-1]["interval_label"].endswith("]")
