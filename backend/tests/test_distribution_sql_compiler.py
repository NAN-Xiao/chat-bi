import sqlite3

import pytest
import sqlglot

from distribution_sql_fixture import config, field, module, plan, property_config, simultaneous


def row(subject, amount=1, *, event="A", date=20260901, group=None, tag=None, instant=None):
    return (subject,event,date,group,amount,tag,instant,None)


def parameters(sql):
    return sql.replace("{{dashboard_start_yyyymmdd}}", "20260901").replace("{{dashboard_end_yyyymmdd}}", "20260930")


def execute(rows, c=None):
    sql=parameters(module("distribution_sql_compiler").compile_distribution_sql(plan(c)))
    with sqlite3.connect(":memory:") as db:
        db.create_function("LEAST", -1, min)
        db.create_function("TO_DATE",2,lambda value,fmt: f"{str(value)[:4]}-{str(value)[4:6]}-{str(value)[6:8]}" if value is not None else None)
        db.execute("CREATE TABLE events (subject TEXT, action TEXT, dt INT, category TEXT, amount NUMERIC, tag TEXT, occurred_at BIGINT, payload TEXT)")
        db.executemany("INSERT INTO events VALUES (?,?,?,?,?,?,?,?)",rows)
        cur=db.execute(sql)
        return [dict(zip([d[0] for d in cur.description],r)) for r in cur.fetchall()]


def test_counts_use_subjects_not_events_and_exclude_null_subjects():
    rows=execute([row("A"),row("A"),row("B"),row("C"),row(None)])
    assert [(r["interval_label"],r["entity_count"],r["total_entities"],r["entity_rate"]) for r in rows] == [("1",2,3,66.67),("2",1,3,33.33)]


def test_population_is_per_date_and_all_groups_including_null():
    c=config(); c["groups"]=[field("category"),field("tag")]
    rows=execute([row("A",group="x"),row("A",group="x"),row("B",group="x"),row("A",group="y"),
                  row("A"),row("B"),row("A",date=20260902,group="x")],c)
    assert {(r["distribution_date"],r["group_1"],r["total_entities"]) for r in rows} == {
        ("2026-09-01","x",2),("2026-09-01","y",1),("2026-09-01",None,2),("2026-09-02","x",1)}


def test_auto_boundaries_are_shared_across_dates_and_groups_max_is_twelfth():
    c=property_config(); c["distribution"]["interval"]["mode"]="auto"; c["groups"]=[field("category")]
    rows=execute([row("A",0,group="x"),row("B",12,group="y",date=20260902),row("C",24,group="z",date=20260903)],c)
    assert [r["interval_order"] for r in rows]==[1,7,12]
    assert [r["entity_count"] for r in rows]==[1,1,1]
    assert len({r["interval_label"] for r in rows})==3
    assert "24" in rows[-1]["interval_label"]


@pytest.mark.parametrize("values,orders", [([0,11.999],[1,2]),([0,12],[1,12]),([5,5],[1]),([-5,0,6],[1,2,3])])
def test_auto_threshold_equal_values_and_negatives(values,orders):
    c=property_config(); c["distribution"]["interval"]["mode"]="auto"
    assert [r["interval_order"] for r in execute([row(str(i),v) for i,v in enumerate(values)],c)]==orders


def test_custom_buckets_have_explicit_exclusive_and_inclusive_edges():
    c=property_config(); c["distribution"]["interval"]={"mode":"custom","customBounds":[0,10]}
    rows=execute([row(str(i),v) for i,v in enumerate([-1,0,9.9,10,20])],c)
    assert [(r["interval_order"],r["entity_count"]) for r in rows]==[(1,1),(2,2),(3,2)]
    assert [r["total_entities"] for r in rows]==[5,5,5]


def test_null_properties_form_a_visible_bucket_without_changing_denominator():
    c=property_config(); rows=execute([row("A",None),row("B",10)],c)
    assert [(r["interval_order"],r["entity_count"],r["total_entities"]) for r in rows]==[(0,1,2),(1,1,2)]
    assert rows[0]["interval_label"]=="无有效值"
    assert rows[0]["entity_rate"]==50
    assert execute([],c)==[]
    assert execute([row("A",None)],c)[0]["total_entities"]==1


def test_simultaneous_does_not_change_bucket_members_or_population():
    c=simultaneous(config(),"avg")
    rows=execute([row("A"),row("B"),row("A",0,event="B"),row("A",10,event="B"),row("B",100,event="B"),row("outside",999,event="B")],c)
    assert len(rows)==1 and rows[0]["entity_count"]==rows[0]["total_entities"]==2
    assert rows[0]["simultaneous_value"]==pytest.approx(110/3)


def test_event_and_date_filters_are_applied_before_aggregation():
    c=config(); c["distribution"]["eventFilters"]={"rules":[{"field":field("amount"),"operator":"gt","value":5}]}
    rows=execute([row("A",10),row("A",2),row("B",10,event="B"),row("C",10,date=20260831)],c)
    assert len(rows)==1 and rows[0]["interval_label"]=="1" and rows[0]["total_entities"]==1


@pytest.mark.parametrize("dialect",["postgres","mysql","starrocks","doris"])
@pytest.mark.parametrize("agg",["sum","median","variance","stddev","percentile_95"])
def test_all_templates_parse_in_declared_dialect(dialect,agg):
    c=simultaneous(property_config(agg),"count_distinct","tag"); c["distribution"]["interval"]["mode"]="auto"
    sql=module("distribution_sql_compiler").compile_distribution_sql(plan(c,dialect=dialect))
    assert len(sqlglot.parse(parameters(sql),read=dialect))==1
