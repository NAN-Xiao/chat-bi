"""Native PostgreSQL, read-only VALUES fixtures; never creates business objects."""
import copy
import os
from datetime import datetime, timezone

import psycopg
import pytest

from apps.dashboard.crud.interval_sql_compiler import compile_interval_sql, GUARD_COLUMN
from test_interval_sql_plan import plan, config, FIELDS, field
from test_interval_sql_atomic import row


@pytest.fixture
def connection():
    dsn = os.environ.get("INTERVAL_TEST_POSTGRES_DSN")
    if not dsn: pytest.skip("INTERVAL_TEST_POSTGRES_DSN required")
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        conn.execute("SET LOCAL statement_timeout = '8s'")
        yield conn
        conn.rollback()


def execute(conn, rows, conf=None, fields=None, zone="UTC"):
    conn.execute("SELECT set_config('TimeZone', %s, true)", [zone])
    p = plan(conf, fields=fields)
    sql = compile_interval_sql(p)
    for name, value in {"start_date": "DATE '2026-09-01'", "end_date": "DATE '2026-09-03'",
                        "start_timestamp": "TIMESTAMP '2026-09-01 00:00:00'",
                        "end_exclusive_timestamp": "TIMESTAMP '2026-09-04 00:00:00'"}.items():
        sql = sql.replace("{{dashboard_" + name + "}}", value)
    kind = (fields or FIELDS)["occurred_at"]["type"]
    types = ["text", "text", kind, "date", "bigint", "text", "text", "bigint", "jsonb"]
    names = "subject,action,occurred_at,day,sequence,category,link,record_id,payload"
    if rows:
        source = f"events({names}) AS (VALUES " + ",".join("(" + ",".join("%s::" + t for t in types) + ")" for _ in rows) + "), "
        values = [v for r in rows for v in r]
    else:
        source = "events AS (SELECT " + ",".join(f"NULL::{t} AS {n}" for t, n in zip(types, names.split(','))) + " WHERE FALSE), "
        values = []
    cursor = conn.execute("WITH " + source + sql[5:], values)
    return [dict(zip([c.name for c in cursor.description], r)) for r in cursor.fetchall()]


def test_native_duplicates_and_null_order_fail(connection):
    values = [row("open", 0, 1), row("close", 0, 1)]
    for rows in (values, values[::-1], [row("open", 0, None)]):
        result = execute(connection, rows)
        assert len(result) == 1 and result[0][GUARD_COLUMN] == 1 and result[0]["interval_count"] is None


def test_native_empty_domains_have_exact_dates_and_null_measures(connection):
    result = execute(connection, [])
    assert [str(r["interval_date"]) for r in result] == ["2026-09-01", "2026-09-02", "2026-09-03"]
    assert all(r["interval_count"] == 0 and r["median_interval_seconds"] is None for r in result)
    c = config(); c["groups"] = [field("category")]
    assert execute(connection, [], c) == []
    result = execute(connection, [row("open", 0, 1, group=None), row("open", 0, 1, group="B", subject="v")], c)
    assert len(result) == 6 and all(r["interval_count"] == 0 for r in result)


def test_native_fractional_quantiles_and_start_group(connection):
    c = config(); c["interval"]["endEvent"]["eventName"] = "open"
    result = execute(connection, [row("open", t, i) for i, t in enumerate([0, 250, 1250, 3500])], c)[0]
    assert result["interval_count"] == 3 and float(result["p25_interval_seconds"]) == .625
    c = config(); c["groups"] = [field("category")]
    result = execute(connection, [row("open", 86399000, 1, group="start"), row("close", 86401000, 2, group="end", day="2026-09-02")], c)
    assert result[0]["group_1"] == "start" and float(result[0]["avg_interval_seconds"]) == 2


def test_timestamp_boundaries_and_session_timezone_do_not_change_results(connection):
    c = config(); c["time"].update(field=field("occurred_at"), date_parameter_type="timestamp")
    def ms(value): return int(datetime.fromisoformat(value).timestamp() * 1000)
    values = [row("open", ms("2026-08-31T16:00:00+00:00"), 1), row("close", ms("2026-08-31T16:00:00.500+00:00"), 2),
              row("open", ms("2026-09-03T16:00:00+00:00"), 3, subject="excluded"), row("close", ms("2026-09-03T16:00:01+00:00"), 4, subject="excluded")]
    utc = execute(connection, values, c, zone="UTC")
    assert utc == execute(connection, values, c, zone="America/New_York")
    assert len(utc) == 3 and utc[0]["interval_count"] == 1 and float(utc[0]["avg_interval_seconds"]) == .5


def test_aware_clock_preserves_elapsed_time_across_dst(connection):
    fields = copy.deepcopy(FIELDS)
    fields["occurred_at"] = {"type": "timestamptz", "field_role": "event_time", "extra_properties": {"encoding": "datetime"}}
    values = [row("open", datetime.fromisoformat("2026-03-08T01:59:59-05:00"), 1), row("close", datetime.fromisoformat("2026-03-08T03:00:01-04:00"), 2)]
    assert float(execute(connection, values, fields=fields)[0]["avg_interval_seconds"]) == 2
