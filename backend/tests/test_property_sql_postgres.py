"""Opt-in real PostgreSQL QA using only VALUES CTEs in read-only transactions.

Set PROPERTY_TEST_POSTGRES_DSN explicitly. Never creates or reads business tables.
"""
import copy
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

import psycopg
import pytest

from apps.dashboard.crud.property_sql_compiler import compile_property_sql
from test_property_sql_plan import FIELDS, config, field, plan


@pytest.fixture
def connection():
    dsn = os.environ.get("PROPERTY_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("PROPERTY_TEST_POSTGRES_DSN not set; real engine QA is opt-in")
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        yield conn
        conn.rollback()


def run(connection, conf=None, metadata=None, source=None):
    source = source or """records(day, subject, region, amount, payload) AS (VALUES
      (20260901, 'u1', 'A', 10, '{"score":2}'::jsonb),
      (20260901, 'u1', 'A', 20, '{"score":3}'::jsonb),
      (20260901, 'u2', 'B', NULL, '{}'::jsonb),
      (20260903, 'u3', NULL, 5, '{"score":5}'::jsonb))"""
    query = compile_property_sql(plan(conf, metadata))
    query = query.replace("{{dashboard_start_yyyymmdd}}", "20260901").replace("{{dashboard_end_yyyymmdd}}", "20260903")
    query = query.replace("{{dashboard_start_timestamp}}", "TIMESTAMP '2026-09-01 00:00:00'").replace("{{dashboard_end_exclusive_timestamp}}", "TIMESTAMP '2026-09-04 00:00:00'")
    query = query.replace("{{dashboard_start_date}}", "DATE '2026-09-01'").replace("{{dashboard_end_date}}", "DATE '2026-09-03'")
    # Shadow the compiler's synthetic fixture source with VALUES, never a real table.
    assert query.startswith('WITH ') and 'FROM "records"' in query
    query = "WITH " + source + ", " + query[5:]
    return connection.execute(query).fetchall()


def test_postgres_daily_counts_sums_and_null_dimensions(connection):
    conf = config()
    conf["metrics"].append({"field": field("amount"), "aggregation": "sum"})
    assert run(connection, conf) == [(date(2026, 9, 1), 2, 30), (date(2026, 9, 2), 0, None), (date(2026, 9, 3), 1, 5)]
    conf["groups"] = [field("region")]
    rows = run(connection, conf)
    assert len(rows) == 9
    assert (date(2026, 9, 3), None, 1, 5) in rows


@pytest.mark.parametrize("grain", ["week", "month", "none"])
def test_postgres_distinct_is_computed_from_detail_at_selected_grain(connection, grain):
    conf = config()
    conf["time"]["grain"] = grain
    rows = run(connection, conf)
    assert len(rows) == 1 and rows[0][-1] == 3


def test_postgres_json_and_audiences(connection):
    conf = config()
    metadata = copy.deepcopy(FIELDS)
    metadata["records"]["payload.score"] = {"type": "number", "semantic_type": "number", "source_field": "payload", "json_path": "$.score"}
    conf["metrics"] = [{"field": field("payload.score"), "aggregation": "sum"}]
    conf["property"] = {"groupMode": "audience", "audiences": [
        {"name": "全部", "filters": {}},
        {"name": "A", "filters": {"rules": [{"field": field("region"), "operator": "eq", "value": "A"}]}},
    ]}
    rows = run(connection, conf, metadata)
    assert rows[:2] == [(date(2026, 9, 1), "全部", 5), (date(2026, 9, 1), "A", 5)]
    assert rows[-1] == (date(2026, 9, 3), "A", None)


@pytest.mark.parametrize("encoding", ["epoch_seconds", "epoch_milliseconds", "datetime", "timestamptz"])
def test_postgres_timestamp_bounds_do_not_depend_on_session_timezone(connection, encoding):
    conf = config()
    conf["time"]["date_parameter_type"] = "timestamp"
    metadata = copy.deepcopy(FIELDS)
    from common.core.config import settings
    zone = settings.DASHBOARD_BUSINESS_TIMEZONE
    start = datetime(2026, 9, 1, tzinfo=ZoneInfo(zone)).timestamp()
    end = datetime(2026, 9, 4, tzinfo=ZoneInfo(zone)).timestamp()
    if encoding.startswith('epoch'):
        factor = 1000 if encoding == 'epoch_milliseconds' else 1
        times = [str(int(start * factor)), str(int(end * factor) - 1), str(int(end * factor))]
        metadata["records"]["day"] = {"type": "bigint", "extra_properties": {"encoding": encoding}}
    elif encoding == 'datetime':
        times = ["TIMESTAMP '2026-09-01'", "TIMESTAMP '2026-09-03 23:59:59.999'", "TIMESTAMP '2026-09-04'"]
        metadata["records"]["day"] = {"type": "timestamp", "extra_properties": {"timezone": zone}}
    else:
        times = [f"TO_TIMESTAMP({start})", f"TO_TIMESTAMP({end} - 0.001)", f"TO_TIMESTAMP({end})"]
        metadata["records"]["day"] = {"type": "timestamptz"}
    connection.execute("SET LOCAL TIME ZONE 'UTC'")
    source = 'records(day, subject) AS (VALUES ' + ','.join(f"({value}, 'u{i}')" for i, value in enumerate(times)) + ')'
    assert run(connection, conf, metadata, source) == [(date(2026, 9, 1), 1), (date(2026, 9, 3), 1)]


def test_postgres_timestamp_property_group_uses_business_timezone(connection):
    from common.core.config import settings
    conf = config()
    conf["groups"] = [field("region", value="records.region")]
    conf["property"]["groupSettings"] = {"records.region": {"summarize": True, "timeGrain": "day"}}
    metadata = copy.deepcopy(FIELDS)
    metadata["records"]["region"] = {"type": "timestamptz"}
    moment = datetime(2026, 9, 1, tzinfo=ZoneInfo(settings.DASHBOARD_BUSINESS_TIMEZONE)).timestamp()
    source = f"records(day, subject, region) AS (VALUES (20260901, 'u1', TO_TIMESTAMP({moment})))"
    connection.execute("SET LOCAL TIME ZONE 'UTC'")
    rows = run(connection, conf, metadata, source)
    assert rows[0] == (date(2026, 9, 1), date(2026, 9, 1), 1)
