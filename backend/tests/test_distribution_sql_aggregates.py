"""Independent numerical oracles, executing the aggregate templates in memory."""
import math
import sqlite3

import pytest

from distribution_sql_fixture import module, plan, config, field, property_config, simultaneous


def main_values(values, aggregation="sum", *, groups=False, kind="property"):
    c = property_config(aggregation)
    c["distribution"]["metric"]["kind"] = kind
    if groups: c["groups"] = [field("category")]
    parts = module("distribution_sql_aggregates").compile_distribution_entity_values(plan(c))
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE scoped_main (distribution_date TEXT, entity_id TEXT, metric_value NUMERIC, event_time_value TEXT, group_1 TEXT)")
        db.executemany("INSERT INTO scoped_main VALUES (?,?,?,?,?)", values)
        sql = "WITH " + ",\n".join(parts.ctes) + f" SELECT * FROM {parts.relation} ORDER BY entity_id"
        cursor = db.execute(sql)
        return [dict(zip([d[0] for d in cursor.description], r)) for r in cursor.fetchall()]


@pytest.mark.parametrize("aggregation,expected", [("sum",16), ("avg",4), ("min",1), ("max",9), ("count_distinct",4),
    ("median",3), ("percentile_95",8.25), ("variance",9.5), ("stddev", math.sqrt(9.5))])
def test_property_statistics_are_per_subject_and_exact(aggregation, expected):
    rows = [("2026-09-01", "A", v, None, None) for v in [1,2,4,9,None]]
    rows += [("2026-09-01", "B", 100, None, None)]
    result = main_values(rows, aggregation)
    assert result[0]["distribution_value"] == pytest.approx(expected)
    assert len(result) == 2
    assert result[1]["distribution_value"] == (0 if aggregation in {"variance","stddev"} else 1 if aggregation == "count_distinct" else 100)


@pytest.mark.parametrize("aggregation", ["sum","avg","min","max","median","percentile_05","variance","stddev","count_distinct"])
def test_all_null_values_preserve_subject(aggregation):
    result = main_values([("2026-09-01","A",None,None,None)],aggregation)
    assert len(result) == 1
    assert result[0]["distribution_value"] == (0 if aggregation == "count_distinct" else None)


def test_percentile_preserves_duplicates_negatives_and_fractional_values():
    rows = [("2026-09-01","A",v,None,None) for v in [-2,-2,-2,0.5,10]]
    assert main_values(rows,"median")[0]["distribution_value"] == -2
    assert main_values(rows,"percentile_95")[0]["distribution_value"] == pytest.approx(8.1)


@pytest.mark.parametrize("kind,expected", [("count",3),("days",2),("hours",2)])
def test_count_keeps_event_duplicates_and_time_counts_distinct_calendar_keys(kind,expected):
    rows=[("2026-09-01","A",None,v,None) for v in ["2026-09-01 03", "2026-09-01 03", "2026-09-02 03"]]
    assert main_values(rows,kind=kind)[0]["distribution_value"] == expected


def test_null_group_keys_do_not_drop_variance_or_percentile_subjects():
    rows=[("2026-09-01","A",v,None,None) for v in [1,3]]
    assert main_values(rows,"variance",groups=True)[0]["distribution_value"] == 1
    assert main_values(rows,"median",groups=True)[0]["distribution_value"] == 2


def sim_values(aggregation, values):
    c=simultaneous(config(),aggregation,"tag" if aggregation=="count_distinct" else "amount")
    c["groups"]=[field("category")]
    parts=module("distribution_sql_aggregates").compile_distribution_simultaneous(plan(c))
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE bucketed (distribution_date TEXT, group_1 TEXT, entity_id TEXT, interval_order INT)")
        db.executemany("INSERT INTO bucketed VALUES (?,?,?,?)",[("2026-09-01",None,"A",1),("2026-09-01",None,"B",1),("2026-09-01",None,"C",2)])
        db.execute("CREATE TABLE scoped_simultaneous (distribution_date TEXT, group_1 TEXT, entity_id TEXT, metric_value)")
        db.executemany("INSERT INTO scoped_simultaneous VALUES (?,?,?,?)",[("2026-09-01",None,s,v) for s,v in values])
        return db.execute("WITH "+",\n".join(parts.ctes)+f" SELECT interval_order, simultaneous_value FROM {parts.relation} ORDER BY interval_order").fetchall()


def test_simultaneous_average_is_weighted_by_valid_events_not_subjects():
    rows=sim_values("avg",[("A",0),("A",10),("A",None),("B",100),("outsider",999)])
    assert rows[0][1] == pytest.approx(110/3)
    assert rows[1] == (2,None)


def test_simultaneous_distinct_deduplicates_shared_values_across_subjects():
    assert sim_values("count_distinct",[("A","x"),("A","y"),("B","y"),("B","z")]) == [(1,3),(2,0)]


@pytest.mark.parametrize("aggregation,expected", [("count",3),("sum",110),("min",0),("max",100)])
def test_simultaneous_merge_keeps_null_groups_and_empty_membership(aggregation,expected):
    assert sim_values(aggregation,[("A",0),("A",10),("B",100)]) == [(1,expected),(2,0 if aggregation=="count" else None)]
