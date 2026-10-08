import copy
import os
from datetime import date

import psycopg
import pytest
import sqlglot

from apps.dashboard.crud.retention_sql_plan import build_retention_plan, RetentionConfigurationError
from apps.dashboard.crud.retention_sql_compiler import compile_retention_sql
from apps.dashboard.crud.retention_sql_validation import retention_result_contract_issues
from test_retention_sql_graph import config, field, event, FIELDS, ALLOWED


def plan(conf=None, dialect="postgres", metadata=None, tracking=None):
    return build_retention_plan(conf or config(), metadata_fields=metadata or {"events": FIELDS},
                                allowed_fields_by_table=ALLOWED, dialect=dialect,
                                tracking_metadata=tracking or {})


def parameters(sql):
    return sql.replace("{{dashboard_start_yyyymmdd}}", "20260901").replace("{{dashboard_end_yyyymmdd}}", "20260903")


@pytest.mark.parametrize("dialect", ["postgres", "mysql", "starrocks", "doris"])
def test_fixed_columns_and_contract(dialect):
    p = plan(dialect=dialect)
    sql = compile_retention_sql(p)
    tree = sqlglot.parse_one(parameters(sql), read=dialect)
    assert [x.alias_or_name for x in tree.selects] == ["cohort_date", "cohort_size", *[f"day_{d}" for d in range(8)]]
    assert not retention_result_contract_issues(sql, p)
    assert retention_result_contract_issues(sql.replace("100.0", "1.0"), p)
    assert retention_result_contract_issues(sql.replace("{{dashboard_end_yyyymmdd}}", "{{dashboard_start_yyyymmdd}}"), p)


@pytest.mark.parametrize("bad", ["toggle", "filter", "aggregation", "field", "expression", "cross_table"])
def test_invalid_config_is_rejected(bad):
    c = config()
    if bad == "toggle": c["retention"]["relatedProperty"]["enabled"] = "true"
    if bad == "filter": c["retention"]["initialEventFilters"] = {"logic": "xor", "rules": []}
    if bad == "aggregation": c["retention"]["simultaneous"] = {"enabled": True, "event": event("purchase"), "aggregation": "median"}
    if bad == "field": c["retention"]["entityField"] = field("missing")
    if bad == "expression": c["retention"]["entityField"]["expression"] = "subject OR 1=1"
    if bad == "cross_table": c["retention"]["returnEvent"] = event("return", "other")
    with pytest.raises(RetentionConfigurationError): plan(c)


@pytest.fixture
def connection():
    dsn = os.environ.get("RETENTION_TEST_POSTGRES_DSN")
    if not dsn: pytest.skip("RETENTION_TEST_POSTGRES_DSN required for read-only VALUES tests")
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        yield conn
        conn.rollback()


SOURCE = """events(day, subject, event_name, category, amount) AS (VALUES
 (20260901,'u1','start','A',NULL::numeric), (20260901,'u1','start','A',NULL),
 (20260901,'u1','start','B',NULL), (20260901,'u2','start','A',NULL),
 (20260903,'u3','start',NULL,NULL),
 (20260902,'u1','return','A',NULL), (20260902,'u1','return','A',NULL),
 (20260902,'u1','return','B',NULL), (20260903,'u1','return','A',NULL),
 (20260902,'u1','purchase','A',10), (20260902,'u1','purchase','A',20),
 (20260902,'u1','purchase','B',10), (20260903,'u1','purchase','A',30),
 (20260902,'u2','purchase','A',100))"""


def run(conn, conf=None, source=SOURCE):
    query = parameters(compile_retention_sql(plan(conf)))
    return conn.execute("WITH " + source + ", " + query[5:]).fetchall()


def test_duplicate_events_maturity_and_independent_denominator(connection):
    rows = run(connection)
    assert rows[0] == (date(2026, 9, 1), 2, 0, 50, 50, None, None, None, None, None)
    assert rows[1] == (date(2026, 9, 3), 1, 0, None, None, None, None, None, None, None)


@pytest.mark.parametrize("aggregation, expected", [("count", 4), ("sum", 70), ("avg", 17.5),
                                                     ("count_distinct", 3), ("min", 10), ("max", 30)])
@pytest.mark.parametrize("related", [False, True])
def test_simultaneous_uses_matched_detail_without_fanout(connection, aggregation, expected, related):
    c = config()
    c["retention"]["simultaneous"] = {"enabled": True, "event": event("purchase"),
                                     "aggregation": aggregation, "metricField": field("amount")}
    if related:
        c["retention"]["relatedProperty"] = {"enabled": True, "initialProperty": field("category"),
                                              "returnProperty": field("category"), "simultaneousProperty": field("category"), "asGroup": False}
    rows = run(connection, c)
    assert rows[0][1:5] == (2, 0, 50, 50)
    assert rows[0][-1] == expected


def test_related_group_keeps_null_cohort_without_matching_null_keys(connection):
    c = config()
    c["retention"]["relatedProperty"] = {"enabled": True, "initialProperty": field("category"),
                                          "returnProperty": field("category"), "asGroup": True}
    rows = run(connection, c)
    assert len(rows) == 3
    assert rows[0][1:4] == (2, 0, 50)
    assert rows[1][1:4] == (1, 0, 100)
    assert rows[2][-1] is None and rows[2][1] == 1


def test_event_dictionary_cannot_be_rebound_to_another_event_field():
    c = config()
    c["retention"]["initialEvent"]["eventNameField"] = "category"
    tracking = {"enabled": True, "default_event_table": "events", "default_event_name_field": "event_name",
                "event_name_mappings": [{"event_name": "start"}, {"event_name": "return"}]}
    with pytest.raises(RetentionConfigurationError): plan(c, tracking=tracking)


def test_cross_table_uses_selected_subject_role_and_scoped_filters():
    c = config()
    c["retention"]["returnEvent"] = event("return", "visits")
    metadata = {"events": copy.deepcopy(FIELDS), "visits": copy.deepcopy(FIELDS)}
    metadata["events"]["subject"]["field_role"] = "customer_key"
    metadata["visits"]["customer"] = metadata["visits"].pop("subject")
    metadata["visits"]["customer"]["field_role"] = "customer_key"
    tracking = {"field_role_mappings": [{"table": "visits", "field": "day", "role": "event_time"}]}
    p = build_retention_plan(c, metadata_fields=metadata,
                             allowed_fields_by_table={t: set(fields) for t, fields in metadata.items()},
                             dialect="postgres", tracking_metadata=tracking)
    assert p.returning.entity == '"customer"'


@pytest.mark.parametrize("as_group", [False, True])
def test_event_filters_and_global_filter_preserve_cohort_population(connection, as_group):
    c = config()
    c["retention"]["initialEventFilters"] = {"rules": [{"field": field("subject"), "operator": "eq", "value": "u2"}]}
    rows = run(connection, c)
    assert rows == [(date(2026, 9, 1), 1, 0, 0, 0, None, None, None, None, None)]
    c["retention"].pop("initialEventFilters")
    c["retention"]["returnEventFilters"] = {"rules": [{"field": field("subject"), "operator": "eq", "value": "u2"}]}
    rows = run(connection, c)
    assert rows[0][1:5] == (2, 0, 0, 0)
    c["filters"] = {"logic": "and", "rules": [{"field": field("category"), "operator": "eq", "value": "A"}]}
    assert len(run(connection, c)) == 1


@pytest.mark.parametrize("kind", ["int", "double", "decimal", "number"])
def test_event_json_numeric_type_uses_shared_metadata_semantics(kind):
    c = config()
    c["retention"]["simultaneous"] = {"enabled": True, "event": event("return"), "aggregation": "sum",
                                     "metricField": field("score")}
    metadata = {"events": {**FIELDS, "payload": {"type": "jsonb"}}}
    tracking = {"enabled": True, "default_event_table": "events", "default_event_name_field": "event_name",
                "event_name_mappings": [{"event_name": "start"}, {"event_name": "return", "properties": [
                    {"property_name": "score", "property_type": kind, "source_field": "payload", "json_path": "$.score"}]}]}
    p = build_retention_plan(c, metadata_fields=metadata, allowed_fields_by_table={"events": set(metadata["events"])},
                             dialect="postgres", tracking_metadata=tracking)
    assert "AS DECIMAL" in p.simultaneous.metric


@pytest.mark.parametrize("encoding", ["yyyymmdd_number", "yyyymmdd_text", "date", "timestamp"])
def test_postgres_date_encodings_and_cross_year(connection, encoding):
    c = config()
    c["time"]["dateParameterType"] = encoding
    metadata = {"events": copy.deepcopy(FIELDS)}
    from common.core.config import settings
    metadata["events"]["day"] = {"type": {"yyyymmdd_number": "integer", "yyyymmdd_text": "varchar", "date": "date", "timestamp": "timestamp"}[encoding],
                                  "extra_properties": {"timezone": settings.DASHBOARD_BUSINESS_TIMEZONE}}
    def value(day):
        if encoding == "yyyymmdd_number": return day.replace("-", "")
        if encoding == "yyyymmdd_text": return "'" + day.replace("-", "") + "'"
        return ("DATE " if encoding == "date" else "TIMESTAMP ") + "'" + day + "'"
    sql = compile_retention_sql(plan(c, metadata=metadata))
    for key, val in {"start_yyyymmdd": "20251231", "end_yyyymmdd": "20260101", "start_date": "DATE '2025-12-31'",
                     "end_date": "DATE '2026-01-01'", "start_timestamp": "TIMESTAMP '2025-12-31'",
                     "end_exclusive_timestamp": "TIMESTAMP '2026-01-02'"}.items():
        if encoding == "yyyymmdd_text" and key.endswith("yyyymmdd"):
            val = "'" + val + "'"  # Same typed literal contract as dashboard date substitution.
        sql = sql.replace("{{dashboard_" + key + "}}", val)
    source = f"events(day,subject,event_name) AS (VALUES ({value('2025-12-31')}, 'u1','start'), ({value('2026-01-01')}, 'u1','return'))"
    rows = connection.execute("WITH " + source + ", " + sql[5:]).fetchall()
    assert rows == [(date(2025,12,31), 1, 0, 100, None, None, None, None, None, None)]


def test_unique_short_table_reference_resolves_to_authorized_qualified_table():
    p = build_retention_plan(config(), metadata_fields={"public.events": FIELDS},
                             allowed_fields_by_table={"public.events": set(FIELDS)}, dialect="postgres")
    assert p.initial.table == "public.events"


def test_source_policies_apply_to_each_event_not_as_cross_table_global_filter():
    c = config()
    c["retention"]["returnEvent"] = event("return", "visits")
    metadata = {"events": copy.deepcopy(FIELDS), "visits": copy.deepcopy(FIELDS)}
    for defs in metadata.values():
        defs["subject"]["field_role"] = "account_key"
        defs["day"]["field_role"] = "event_time"
    policies = {table: {"rules": [{"field": field("category", table), "operator": "eq", "value": value}]}
                for table, value in [("events", "initial-policy"), ("visits", "return-policy")]}
    p = build_retention_plan(c, metadata_fields=metadata, allowed_fields_by_table={t: set(f) for t,f in metadata.items()},
                             dialect="postgres", table_filters=policies)
    assert "initial-policy" in p.initial.predicate and "return-policy" not in p.initial.predicate
    assert "return-policy" in p.returning.predicate and "initial-policy" not in p.returning.predicate


@pytest.mark.parametrize("encoding", ["epoch_seconds", "epoch_milliseconds", "timestamptz"])
def test_epoch_and_timezone_boundaries(connection, encoding):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from common.core.config import settings
    c = config()
    c["time"]["dateParameterType"] = "timestamp"
    metadata = {"events": copy.deepcopy(FIELDS)}
    metadata["events"]["day"] = {"type": "timestamptz" if encoding == "timestamptz" else "bigint",
                                  "extra_properties": {"encoding": encoding}}
    p = plan(c, metadata=metadata)
    sql = compile_retention_sql(p).replace("{{dashboard_start_timestamp}}", "TIMESTAMP '2024-02-28'").replace(
        "{{dashboard_end_exclusive_timestamp}}", "TIMESTAMP '2024-03-01'")
    def val(day):
        epoch = datetime.fromisoformat(day).replace(tzinfo=ZoneInfo(settings.DASHBOARD_BUSINESS_TIMEZONE)).timestamp()
        return f"TO_TIMESTAMP({epoch})" if encoding == "timestamptz" else str(int(epoch * (1000 if encoding == "epoch_milliseconds" else 1)))
    source = f"events(day,subject,event_name) AS (VALUES ({val('2024-02-28')},'u1','start'), ({val('2024-02-29')},'u1','return'), ({val('2024-03-01')},'u2','start'))"
    connection.execute("SET LOCAL TIME ZONE 'UTC'")
    rows = connection.execute("WITH " + source + ", " + sql[5:]).fetchall()
    assert rows == [(date(2024,2,28), 1, 0, 100, None, None, None, None, None, None)]
