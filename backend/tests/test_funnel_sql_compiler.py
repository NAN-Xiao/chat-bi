import copy
import sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
import sqlglot

from apps.dashboard.crud.funnel_sql_compiler import compile_funnel_sql
from apps.dashboard.crud.funnel_sql_validation import funnel_result_contract_issues
from test_funnel_sql_plan import config, plan, field, FIELDS


def params(sql):
    return sql.replace("{{dashboard_start_yyyymmdd}}", "20260901").replace("{{dashboard_end_yyyymmdd}}", "20260928")


def run(rows, conf=None):
    # SQLite executes the portable arithmetic/joins; only business-local calendar
    # conversion is supplied as a scalar. Native timestamp engines are tested separately.
    p = plan(conf)
    sql = params(compile_funnel_sql(p))
    for step in p.steps:
        sql = sql.replace(step.time_day, 'business_day("occurred_at")')
    db = sqlite3.connect(":memory:")
    db.create_function("business_day", 1, lambda ms: datetime.fromtimestamp(ms / 1000, timezone.utc).astimezone(ZoneInfo(p.timezone)).date().isoformat())
    try:
        db.execute("CREATE TABLE events(subject TEXT, action TEXT, occurred_at INTEGER, category TEXT, dt INTEGER, payload TEXT)")
        db.executemany("INSERT INTO events VALUES (?,?,?,?,?,NULL)", [(u, e, t, k, dt) for u,e,t,k,dt in rows])
        return db.execute(sql).fetchall()
    finally:
        db.close()


def row(user, event, millis, related="X", dt=20260901):
    return (user, event, millis, related, dt)


def test_candidate_first_occurrences_keep_valid_later_path():
    rows = [row("u1","A",0), row("u1","A",0), row("u1","B",1), row("u1","C",2),
            row("u2","A",0), row("u3","A",0), row("u3","B",1),
            row("u4","A",0), row("u4","A",200000000), row("u4","B",200000001), row("u4","C",200000002)]
    result = run(rows)
    assert [r[2] for r in result] == [4,3,2]
    assert [r[3] for r in result] == [1,.75,.5]
    assert [r[4] for r in result] == pytest.approx([1,.75,2/3], abs=1e-9)
    assert [r[5] for r in result] == pytest.approx([0,.25,1/3], abs=1e-9)


def test_related_candidates_do_not_mix_and_null_keeps_first_step():
    c = config(); c["funnel"].update(relatedPropertyEnabled=True, relatedProperty=field("category"))
    rows = [row("u","A",0,"X"),row("u","A",0,"Y"),row("u","B",1,"X"),row("u","C",2,"Y"),
            row("n","A",0,None),row("n","B",1,None),row("n","C",2,None)]
    assert [r[2] for r in run(rows,c)] == [2,1,0]


def test_empty_and_zero_previous_step_keep_all_rows():
    result = run([])
    assert result == [(1,"A",0,None,None,None),(2,"B",0,None,None,None),(3,"C",0,None,None,None)]
    assert run([row("u","A",0)])[-1] == (3,"C",0,0,None,None)


def test_order_and_exact_window_boundary():
    rows = [row("bound","A",0),row("bound","B",0),row("bound","C",86400000),
            row("over","A",0),row("over","B",1),row("over","C",86400001),
            row("reverse","A",1),row("reverse","B",0),row("reverse","C",2),
            row("cumulative","A",0),row("cumulative","B",80000000),row("cumulative","C",90000000)]
    assert [r[2] for r in run(rows)] == [4,3,1]


def test_same_day_is_not_rolling_twenty_four_hours():
    from common.core.config import settings
    zone = ZoneInfo(settings.DASHBOARD_BUSINESS_TIMEZONE)
    start = int(datetime(2026,9,1,23,59,tzinfo=zone).timestamp() * 1000)
    rows = [row("u","A",start),row("u","B",start+120000),row("u","C",start+180000)]
    c = config(); c["funnel"]["window"] = {"mode":"same_day"}
    assert [r[2] for r in run(rows,c)] == [1,0,0]
    assert [r[2] for r in run(rows)] == [1,1,1]


def test_repeated_event_same_timestamp_uses_existing_non_strict_order():
    c = config()
    for step in c["funnel"]["steps"]: step["event"]["eventName"] = "A"
    assert [r[2] for r in run([row("u","A",0)],c)] == [1,1,1]


def test_date_scope_and_step_filters_apply_before_matching():
    c = config(); c["funnel"]["steps"][1]["filters"] = {"rules":[{"field":field("category"),"operator":"eq","value":"Y"}]}
    rows = [row("u","A",0),row("u","B",1),row("u","C",2),
            row("v","A",0),row("v","B",1,"Y"),row("v","C",2,dt=20260929)]
    assert [r[2] for r in run(rows,c)] == [2,1,0]


@pytest.mark.parametrize("dialect", ["postgres","mysql","starrocks","doris"])
def test_dialect_contract_and_mutation_rejection(dialect):
    p = plan(dialect=dialect)
    sql = compile_funnel_sql(p)
    tree = sqlglot.parse_one(params(sql), read=dialect)
    assert tuple(c.alias_or_name for c in tree.selects) == p.required_columns
    assert not funnel_result_contract_issues(sql,p)
    for changed in [sql.replace("86400", "86401"),sql.replace("'A'", "'invalid'"),
                    sql.replace(" * 1.0 /", " * 100.0 /"),sql.replace("{{dashboard_end_yyyymmdd}}", "{{dashboard_start_yyyymmdd}}"),
                    sql.replace("step_count AS step_count", "step_count AS wrong")]:
        assert changed != sql
        assert funnel_result_contract_issues(changed,p)


@pytest.mark.parametrize("encoding", ["epoch_seconds","epoch_milliseconds","datetime","timestamptz"])
def test_time_encodings_preserve_precision_in_compiled_sql(encoding):
    from common.core.config import settings
    fields = copy.deepcopy(FIELDS)
    fields["occurred_at"] = {"type": "timestamp" if encoding == "datetime" else "timestamptz" if encoding == "timestamptz" else "bigint",
        "field_role":"event_time", "extra_properties": {"encoding":encoding if encoding.startswith("epoch") else "datetime", "timezone":settings.DASHBOARD_BUSINESS_TIMEZONE}}
    p = plan(fields=fields)
    assert not funnel_result_contract_issues(compile_funnel_sql(p),p)
    if encoding == "epoch_milliseconds": assert "/ 1000.0" in p.steps[0].time
    if encoding in {"datetime","timestamptz"}: assert "EXTRACT(EPOCH" in p.steps[0].time
