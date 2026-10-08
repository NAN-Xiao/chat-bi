"""Native read-only QA; synthetic VALUES never touch application/business tables."""
import copy
import os
from datetime import date

import psycopg
import pytest

from apps.dashboard.crud.revenue_sql_compiler import compile_revenue_sql
from revenue_sql_fixture import FIELDS, METHODS, config, field, plan


@pytest.fixture
def connection():
    dsn = os.environ.get("REVENUE_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("REVENUE_TEST_POSTGRES_DSN not set")
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        yield conn
        conn.rollback()


SOURCE = """events(subject, day, event_name, category, amount, cost, payload) AS (VALUES
 ('A',20260901,'start','allowed',NULL::numeric,NULL::numeric,'{}'::jsonb),
 ('A',20260901,'start','allowed',NULL,NULL,'{}'),
 ('B',20260901,'start','allowed',NULL,NULL,'{}'),
 ('A',20260902,'start','allowed',NULL,NULL,'{}'),
 ('C',20260903,'start',NULL,NULL,NULL,'{}'),
 (NULL,20260901,'start','allowed',NULL,NULL,'{}'),
 ('A',20260901,'purchase','allowed',10,1,'{"value":10,"expense":1}'),
 ('A',20260901,'purchase','allowed',10,1,'{"value":10,"expense":1}'),
 ('B',20260901,'purchase','allowed',30,3,'{"value":30,"expense":3}'),
 ('A',20260902,'purchase','allowed',20,2,'{"value":20,"expense":2}'),
 ('X',20260901,'purchase','allowed',1000,100,'{}'))"""


def execute(connection, conf=None, fields=None, source=SOURCE, tracking=None):
    sql = compile_revenue_sql(plan(conf, fields=fields, tracking=tracking))
    text_dates = (conf or config())["time"]["dateParameterType"] == "yyyymmdd_text"
    sql = sql.replace("{{dashboard_start_yyyymmdd}}", "'20260901'" if text_dates else "20260901")
    sql = sql.replace("{{dashboard_end_yyyymmdd}}", "'20260903'" if text_dates else "20260903")
    sql = sql.replace("{{dashboard_start_timestamp}}", "TIMESTAMP '2026-09-01 00:00:00'").replace("{{dashboard_end_exclusive_timestamp}}", "TIMESTAMP '2026-09-04 00:00:00'")
    sql = sql.replace("{{dashboard_start_date}}", "DATE '2026-09-01'").replace("{{dashboard_end_date}}", "DATE '2026-09-03'")
    assert sql.startswith("WITH ") and 'FROM "events"' in sql
    return connection.execute("WITH " + source + ", " + sql[5:]).fetchall()


EXPECTED = {"count": [3,1,0], "entity_count": [2,1,0], "per_entity_count": [1.5,1,None],
            "period_cumulative_count": [3,4,4], "period_average_count": [3,2,4/3],
            "period_cumulative_entity_count": [2,3,3], "period_average_entity_count": [2,1.5,1],
            "property_sum": [50,20,0], "property_avg": [50/3,20,None]}


@pytest.mark.parametrize("method", METHODS)
def test_all_metrics_keep_detail_and_daily_denominators(connection, method):
    rows = execute(connection, config(method))
    assert rows[0][:2] == (date(2026,9,1), 2)
    for value, expected in zip(rows[0][2:], EXPECTED[method]):
        assert value is None if expected is None else float(value) == pytest.approx(expected)
    assert rows[1][:2] == (date(2026,9,2), 1)
    assert rows[1][-1] is None
    assert rows[2][:2] == (date(2026,9,3), 1)
    assert rows[2][-2:] == (None,None)
    assert rows[2][2] is None if method in {"property_avg","per_entity_count"} else rows[2][2] == 0


def test_cost_is_detail_sum_and_requires_full_observation_window(connection):
    rows = execute(connection, config(cost=True))
    assert rows[0][-1] == 7  # repeated initial events do not double cost; equal detail values both count
    assert rows[1][-1] is None and rows[2][-1] is None


def test_null_cohort_dimension_is_preserved(connection):
    conf = config("count"); conf["groups"] = [field("category")]
    rows = execute(connection, conf)
    assert rows[0] == (date(2026,9,1),2,3,1,0,"allowed")
    assert rows[2] == (date(2026,9,3),1,0,None,None,None)


def test_global_filter_scopes_both_events_without_changing_cohort_size(connection):
    conf = config(); conf["filters"] = {"rules": [{"field": field("subject"), "operator": "eq", "value": "B"}]}
    assert execute(connection,conf) == [(date(2026,9,1),1,30,0,0)]


def test_all_null_properties_are_not_a_count_metric(connection):
    source = SOURCE.replace("10,1,", "NULL,1,").replace("30,3,", "NULL,3,")
    rows = execute(connection, config("property_avg"), source=source)
    assert rows[0][2] is None and rows[0][3] == 20


def test_native_numeric_json_amount_and_cost_match_physical_detail(connection):
    conf = config(cost=True)
    for role, name in (("metric", "value"), ("cost", "expense")):
        conf["revenue"][role]["field"] = {**field(name), "kind":"tracking-property", "eventName":"purchase",
                                            "sourceField":"payload", "jsonPath":"$." + name}
    tracking = {"enabled":True, "default_event_table":"events", "default_event_name_field":"event_name",
                "event_name_mappings":[{"event_name":"start"}, {"event_name":"purchase", "properties":[
                    {"property_name":name,"source_field":"payload","json_path":"$."+name,"property_type":"double"}
                    for name in ("value","expense")]}]}
    assert execute(connection,conf,tracking=tracking) == execute(connection,config(cost=True))


@pytest.mark.parametrize("parameter,kind,encoding", [("date","date",None), ("yyyymmdd_text","text",None),
                            ("timestamp","bigint","epoch_seconds"), ("timestamp","bigint","epoch_milliseconds"),
                            ("timestamp","timestamptz",None)])
def test_native_typed_dates_and_timestamp_end_boundary(connection, parameter, kind, encoding):
    from common.core.config import settings
    conf = config("count"); conf["time"]["dateParameterType"] = parameter
    fields = copy.deepcopy(FIELDS); fields["day"] = {"type":kind, "extra_properties":{"encoding":encoding}}
    if parameter == "yyyymmdd_text": expression = "CAST(day AS TEXT)"
    elif parameter == "date": expression = "TO_DATE(CAST(day AS TEXT),'YYYYMMDD')"
    else:
        instant = f"(TO_DATE(CAST(day AS TEXT),'YYYYMMDD')::timestamp AT TIME ZONE '{settings.DASHBOARD_BUSINESS_TIMEZONE}')"
        expression = instant if kind == "timestamptz" else f"CAST(EXTRACT(EPOCH FROM {instant}) * {1000 if encoding == 'epoch_milliseconds' else 1} AS BIGINT)"
    source = SOURCE.replace("events(","raw_events(",1) + f", events AS (SELECT subject, {expression} AS day, event_name, category, amount, cost, payload FROM raw_events)"
    assert execute(connection,conf,fields,source) == execute(connection,config("count"))
