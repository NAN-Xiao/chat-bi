import asyncio
import copy
import sqlite3
from types import SimpleNamespace

import pytest
import sqlglot

from apps.dashboard.crud import ai_sql_generator as generator
from apps.dashboard.crud.interval_sql_compiler import compile_interval_sql, IntervalConfigurationError
from apps.dashboard.crud.interval_sql_validation import interval_start_date_issues, has_exact_interval_percentiles


FIELDS = {"events": {"subject", "action", "occurred_at", "day", "sequence", "category", "link", "payload"}}
SCHEMA = "# Table: events\n[\n" + ",\n".join(f"({name}:bigint, physical)" for name in sorted(FIELDS["events"])) + "\n]"
TRACKING = {"enabled": True, "fields": [
    {"table_name": "events", "field_name": "occurred_at", "field_role": "event_time", "extra_properties": {"encoding": "epoch_milliseconds"}},
    {"table_name": "events", "field_name": "sequence", "field_role": "event_sequence"},
]}


def field(name):
    return {"table": "events", "field": name}


def config():
    return {"analysis_model": "interval", "chart": {"type": "table"},
            "time": {"field": field("day"), "date_parameter_type": "date"}, "groups": [],
            "interval": {"entityField": field("subject"), "limitSeconds": 60,
                         "startEvent": {"kind": "tracking-event", "eventTable": "events", "eventNameField": "action", "eventName": "open"},
                         "endEvent": {"kind": "tracking-event", "eventTable": "events", "eventNameField": "action", "eventName": "close"}}}


def compile_sql(configuration=None, tracking=None, dialect="mysql", engine="mysql", fields=None):
    return compile_interval_sql(configuration or config(), TRACKING if tracking is None else tracking,
                                SCHEMA, dialect, engine, ["events"], FIELDS if fields is None else fields)


def execute(rows, configuration=None):
    sql = compile_sql(configuration).replace("{{dashboard_start_date}}", "'2026-09-01'").replace("{{dashboard_end_date}}", "'2026-09-03'")
    with sqlite3.connect(":memory:") as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("CREATE TABLE events(subject TEXT,action TEXT,occurred_at INT,day TEXT,sequence INT,category TEXT,link TEXT,payload TEXT)")
        connection.executemany("INSERT INTO events VALUES(?,?,?,?,?,?,?,?)", rows)
        return [dict(row) for row in connection.execute(sqlglot.transpile(sql, read="mysql", write="sqlite")[0])]


def event(sequence, action, milliseconds, *, subject="person", day="2026-09-01", category="first", link="key", payload="{}"):
    return (subject, action, milliseconds, day, sequence, category, link, payload)


@pytest.mark.parametrize("actions,count,average", [("open open close close", 1, 1), ("open close open close", 2, 1), ("close open", 0, None)])
def test_adjacent_transitions(actions, count, average):
    result = execute([event(index, action, index * 1000) for index, action in enumerate(actions.split())])
    assert sum(row["interval_count"] for row in result) == count
    if count:
        assert result[0]["avg_interval_seconds"] == average


def test_same_event_produces_n_minus_one_and_exact_fractional_quantiles():
    configuration = config()
    configuration["interval"]["endEvent"]["eventName"] = "open"
    result = execute([event(index, "open", milliseconds) for index, milliseconds in enumerate([0, 250, 1250, 3500])], configuration)[0]
    assert result["interval_count"] == 3
    assert result["entity_count"] == 1
    assert result["p25_interval_seconds"] == pytest.approx(.625)
    assert result["median_interval_seconds"] == 1
    assert result["p75_interval_seconds"] == pytest.approx(1.625)


def test_cross_midnight_and_changed_group_use_start_row():
    configuration = config()
    configuration["groups"] = [field("category")]
    result = execute([event(1, "open", 86399000), event(2, "close", 86401000, day="2026-09-02", category="second")], configuration)
    assert len(result) == 1
    assert (result[0]["interval_date"], result[0]["group_1"], result[0]["avg_interval_seconds"]) == ("2026-09-01", "first", 2)


def test_null_entities_times_and_limit_boundaries():
    rows = []
    for index, duration in enumerate([0, 60000, 60001]):
        rows.extend([event(1, "open", 0, subject=str(index)), event(2, "close", duration, subject=str(index))])
    rows.extend([event(1, "open", 0, subject=None), event(2, "close", 10, subject=None), event(3, "open", None)])
    result = execute(rows)[0]
    assert result["interval_count"] == result["entity_count"] == 2
    assert result["min_interval_seconds"] == 0
    assert result["max_interval_seconds"] == 60


def test_equal_timestamps_follow_configured_sequence_not_event_label():
    assert execute([event(2, "open", 0), event(1, "close", 0)]) == []
    assert execute([event(1, "open", 0), event(2, "close", 0)])[0]["interval_count"] == 1


def test_related_keys_partition_and_exclude_null():
    configuration = config()
    configuration["interval"]["relatedProperty"] = {"enabled": True, "startProperty": field("link"), "endProperty": field("link")}
    result = execute([event(1, "open", 0, link="one"), event(2, "open", 1000, link="two"),
                      event(3, "close", 2000, link="one"), event(4, "close", 3000, link="two"),
                      event(5, "open", 4000, link=None), event(6, "close", 5000, link=None)], configuration)[0]
    assert result["interval_count"] == 2
    assert result["avg_interval_seconds"] == 2


def test_end_filters_do_not_change_start_filters_and_global_or_is_preserved():
    configuration = config()
    configuration["interval"]["startEventFilters"] = {"logic": "and", "rules": [{"field": field("category"), "operator": "eq", "value": "start"}]}
    configuration["interval"]["endEventFilters"] = {"logic": "and", "rules": [{"field": field("category"), "operator": "eq", "value": "end"}]}
    configuration["filters"] = {"logic": "or", "rules": [{"field": field("subject"), "operator": "eq", "value": "person"}, {"field": field("link"), "operator": "is_null"}]}
    result = execute([event(1, "open", 0, category="start"), event(2, "open", 1000, category="end"),
                      event(3, "close", 2000, category="start"), event(4, "close", 3000, category="end")], configuration)
    assert result[0]["avg_interval_seconds"] == 3


@pytest.mark.parametrize("grain", [None, "day"])
@pytest.mark.parametrize("dialect,engine", [("mysql", "analyticdb mysql"), ("mysql", "mysql"), ("postgres", "postgres"), ("doris", "doris"), ("starrocks", "starrocks")])
def test_compiled_sql_passes_existing_validators(grain, dialect, engine):
    configuration = config()
    configuration["time"]["grain"] = grain
    configuration["groups"] = [field("category")]
    sql = compile_sql(configuration, dialect=dialect, engine=engine)
    state = {"normalized_config": configuration, "sql_dialect": dialect, "schema": SCHEMA, "graph_trace": [],
             "datasource": SimpleNamespace(type=dialect, type_name=engine),
             "response": generator.DashboardAiSqlGenerateResponse(success=True, sql=sql, chart_type="table")}
    result = generator._node_validate_sql(state)["response"]
    assert result.success, result.issues
    assert interval_start_date_issues(sql.replace("LAG(event_date) OVER", "LAG(event_date, 2) OVER"), dialect)


def test_calendar_join_cannot_hide_wrong_date_lineage():
    configuration = config()
    configuration["time"]["grain"] = "day"
    sql = compile_sql(configuration)
    assert not interval_start_date_issues(sql)
    assert interval_start_date_issues(sql.replace("calendar.calendar_date = stats.interval_date", "calendar.calendar_date > stats.interval_date"))
    assert interval_start_date_issues(sql.replace("calendar.calendar_date = stats.interval_date", "(calendar.calendar_date = stats.interval_date OR 1=1)"))


def test_exact_percentiles_reject_wrong_ranking_partition_and_formula():
    sql = compile_sql()
    assert has_exact_interval_percentiles(sql, "mysql")
    assert not has_exact_interval_percentiles(sql.replace("PARTITION BY interval_date ORDER BY interval_seconds", "PARTITION BY entity_id ORDER BY interval_seconds"), "mysql")
    assert not has_exact_interval_percentiles(sql.replace("* 0.75", "* 0.95"), "mysql")


@pytest.mark.parametrize("mutation", ["disabled", "missing_time", "unknown_encoding", "ambiguous_time"])
def test_metadata_errors_are_explicit(mutation):
    tracking = copy.deepcopy(TRACKING)
    if mutation == "disabled":
        tracking["enabled"] = False
    elif mutation == "missing_time":
        tracking["fields"] = tracking["fields"][1:]
    elif mutation == "unknown_encoding":
        tracking["fields"][0]["extra_properties"] = {}
    else:
        tracking["field_role_mappings"] = [{"table": "events", "field": "day", "role": "event_time"}]
    with pytest.raises(IntervalConfigurationError):
        compile_sql(tracking=tracking)


def test_missing_order_role_does_not_block_interval_sql_generation():
    tracking = copy.deepcopy(TRACKING)
    tracking["fields"] = tracking["fields"][:1]

    sql = compile_sql(tracking=tracking)

    assert "event_order_1" not in sql
    assert "ORDER BY event_time)" in sql


@pytest.mark.parametrize("expression", ["(SELECT occurred_at FROM secret)", "occurred_at; DELETE FROM events", "secret.value", "SUM(occurred_at)"])
def test_unauthorized_or_non_scalar_fields_are_rejected(expression):
    configuration = config()
    configuration["groups"] = [{**field("category"), "expression": expression}]
    with pytest.raises(IntervalConfigurationError):
        compile_sql(configuration)


def test_permission_restrictions_are_not_replaced_by_tracking_metadata():
    with pytest.raises(IntervalConfigurationError):
        compile_sql(fields={"events": FIELDS["events"] - {"occurred_at"}})
    with pytest.raises(IntervalConfigurationError):
        compile_sql(fields={})


@pytest.mark.parametrize("valid", [True, False])
def test_generation_and_validation_never_call_llm(monkeypatch, valid):
    async def forbidden(*args, **kwargs):
        pytest.fail("Interval compilation must not invoke an LLM")
    monkeypatch.setattr(generator, "_create_dashboard_ai_sql_llm", forbidden)
    state = {"normalized_config": config(), "tracking_metadata": TRACKING if valid else {}, "schema": SCHEMA,
             "sql_dialect": "mysql", "allowed_tables": ["events"], "allowed_fields_by_table": FIELDS, "graph_trace": []}
    for _ in range(5):
        state.update(asyncio.run(generator._async_node_generate_sql(state)))
        state.update(generator._node_validate_sql(state))
        assert state["response"].success is valid, state["response"].issues
        assert generator._route_after_sql_validate(state) == "explain_advice"


def test_interval_validation_recompiles_stale_sql_before_contract_checks():
    state = {
        "normalized_config": config(),
        "tracking_metadata": TRACKING,
        "schema": SCHEMA,
        "sql_dialect": "mysql",
        "allowed_tables": ["events"],
        "allowed_fields_by_table": FIELDS,
        "datasource": SimpleNamespace(type="mysql", type_name="mysql"),
        "response": generator.DashboardAiSqlGenerateResponse(
            success=True,
            sql="SELECT stale_sql",
            chart_type="table",
        ),
        "graph_trace": [],
    }

    result = generator._node_validate_sql(state)["response"]

    assert result.success is True, result.issues
    assert "stale_sql" not in result.sql
    assert "interval_date" in result.sql
