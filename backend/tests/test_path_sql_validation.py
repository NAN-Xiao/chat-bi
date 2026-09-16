from __future__ import annotations

import sqlite3

import pytest

from apps.dashboard.crud import ai_sql_generator
from path_sql_fixture import PATH_CONFIG, PATH_SCHEMA, path_sql


def issues(sql, schema=PATH_SCHEMA):
    return ai_sql_generator._path_sql_result_issues(sql, {"analysis_model": "path", "path": PATH_CONFIG}, schema=schema, sql_dialect="mysql")


def test_including_initial_event_in_scoped_data_does_not_gate_sessions():
    sql = path_sql(initial_event=None).replace("FROM events\n", "FROM events WHERE event_name IN ('A','B')\n")
    assert issues(sql)


@pytest.mark.parametrize("mutation", [
    lambda sql: sql.replace("step_in_session=1 AND event_name='A'", "step_in_session=2 AND event_name='A'"),
    lambda sql: sql.replace("step_in_session=1 AND event_name='A'", "step_in_session=1 OR event_name='A'"),
    lambda sql: sql.replace("event_name='A'", "event_name='B'"),
    lambda sql: sql.replace("JOIN eligible_sessions", "LEFT JOIN eligible_sessions"),
])
def test_only_actual_first_event_of_configured_session_can_anchor_path(mutation):
    assert issues(mutation(path_sql()))


@pytest.mark.parametrize("join", ["s.session_id=v.session_id", "s.entity_id=v.entity_id", "1=1"])
def test_initial_event_gate_must_match_all_sequence_partition_keys(join):
    assert issues(path_sql(session_join=join))


def test_unused_correct_initial_event_cte_cannot_gate_the_output():
    sql = path_sql().replace("JOIN eligible_sessions v ON s.entity_id=v.entity_id AND s.session_id=v.session_id", "")
    assert issues(sql)


@pytest.mark.parametrize("event_alias,output_alias", [("b", "a"), ("a", "b")])
def test_anchor_conditions_and_exported_keys_must_belong_to_the_same_session_row(event_alias, output_alias):
    sql = path_sql().replace(
        "SELECT entity_id,session_id FROM session_steps WHERE step_in_session=1 AND event_name='A'",
        f"SELECT {output_alias}.entity_id,{output_alias}.session_id FROM session_steps a CROSS JOIN session_steps b "
        f"WHERE a.step_in_session=1 AND {event_alias}.event_name='A'",
    )
    assert issues(sql)


def test_anchor_can_be_a_direct_self_join_with_complete_session_keys():
    sql = path_sql(initial_event=None).replace(
        "FROM session_steps s  WHERE", "FROM session_steps s JOIN session_steps a ON s.entity_id=a.entity_id AND s.session_id=a.session_id "
        "AND a.step_in_session=1 AND a.event_name='A' WHERE")
    assert issues(sql) == []


def test_start_event_selection_keeps_later_edges_and_excludes_late_initial_events():
    good = path_sql()
    bad = path_sql(initial_event=None)
    with sqlite3.connect(":memory:") as connection:
        connection.execute("CREATE TABLE events(entity_id INT,session_id INT,event_id INT,event_time INT,event_name TEXT)")
        connection.executemany("INSERT INTO events VALUES(?,?,?,?,?)", [
            (1,1,1,1,'A'),(1,1,2,2,'B'),(1,1,3,3,'C'),
            (2,1,4,1,'B'),(2,1,5,2,'A'),(2,1,6,3,'C'),
        ])
        assert list(connection.execute(good)) == [('A','B',1,1),('B','C',1,2)]
        assert len(list(connection.execute(bad))) == 4
    assert issues(good) == []
    assert issues(bad)


@pytest.mark.parametrize("order", ["event_name", "event_time DESC", "1", "DATE(FROM_UNIXTIME(event_time))"])
def test_original_path_sequence_must_start_with_full_event_time_ascending(order):
    sql = path_sql(sequence=f"ROW_NUMBER() OVER (PARTITION BY entity_id, session_id ORDER BY {order})")
    assert issues(sql)


@pytest.mark.parametrize("schema", ["", PATH_SCHEMA.replace("role=event_time", "role=partition_date"), PATH_SCHEMA.replace("Table: events", "Table: other_events")])
def test_path_time_sort_requires_authorized_table_qualified_role(schema):
    assert issues(path_sql(), schema=schema)


def test_path_preserves_order_when_declared_epoch_is_converted_before_numbering():
    sql = path_sql().replace("WITH session_steps", "WITH converted AS (SELECT entity_id, session_id, event_id, FROM_UNIXTIME(event_time) AS event_time, event_name FROM events), session_steps")
    sql = sql.replace("FROM events\n", "FROM converted\n")
    assert issues(sql) == []


def test_path_rejects_resorting_timestamp_peers_after_assigning_step_numbers():
    assert issues(path_sql(edge_order="event_time"))


@pytest.mark.parametrize("lag", [False, True])
def test_path_reuses_prior_sequence_for_adjacent_edges_and_source_step(lag):
    sql = path_sql(lag=lag)
    assert issues(sql) == []
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE events(entity_id INT, session_id INT, event_id INT, event_time INT, event_name TEXT)")
    connection.executemany("INSERT INTO events VALUES (1, 1, ?, ?, ?)", [(1, 1000, "A"), (2, 1000, "A"), (3, 1000, "A"), (4, 2000, "B")])
    assert list(connection.execute(sql)) == [("A", "A", 1, 1), ("A", "A", 1, 2), ("A", "B", 1, 3)]
    # Reversing equal-time peers is one legal database evaluation of the old
    # time-only ORDER BY. It shifts the A->B edge from source step 3 to step 1.
    if not lag:
        bad = path_sql(edge_order="event_time, event_id DESC")
        assert list(connection.execute(bad)) == [("A", "B", 1, 1), ("A", "A", 1, 2), ("A", "A", 1, 3)]
        assert issues(bad)
    connection.close()


@pytest.mark.parametrize("order", ["step_in_session DESC", "event_time, step_in_session", "event_time", "1"])
def test_path_requires_ascending_reuse_of_the_same_sequence(order):
    assert issues(path_sql(edge_order=order))


@pytest.mark.parametrize("sequence", ["event_time", "RANK() OVER (PARTITION BY entity_id, session_id ORDER BY event_time)", "1"])
def test_path_sequence_name_does_not_substitute_for_row_number_lineage(sequence):
    assert issues(path_sql(sequence=sequence))


def test_path_edge_partition_cannot_drop_entity_or_session_boundary():
    assert issues(path_sql(partition="session_id"))
    assert issues(path_sql(partition="entity_id"))


def test_path_edge_offset_must_be_one():
    assert issues(path_sql(offset=", 2"))
    assert issues(path_sql(offset=", 1")) == []


def test_path_step_must_use_the_sequence_that_orders_adjacency():
    sql = path_sql().replace("step_in_session  AS path_step", "ROW_NUMBER() OVER (PARTITION BY entity_id, session_id ORDER BY event_time) AS path_step")
    assert issues(sql)


def test_path_lag_source_step_is_previous_sequence_position():
    assert issues(path_sql(lag=True).replace("step_in_session - 1 AS path_step", "step_in_session AS path_step"))


def test_path_sequence_renaming_and_projection_preserve_lineage():
    assert issues(path_sql().replace("step_in_session", "session_step")) == []


def test_unused_correct_window_cannot_validate_the_actual_timestamp_sorted_edge():
    sql = path_sql(edge_order="event_time").replace("WITH session_steps", "WITH unused_correct AS (SELECT LEAD(event_name) OVER (ORDER BY step_in_session) AS next_event FROM unused), session_steps")
    assert issues(sql)


def test_same_select_row_number_and_lead_timestamp_order_is_not_sequence_reuse():
    sql = """WITH edges AS (
        SELECT event_name AS path_source, LEAD(event_name) OVER (PARTITION BY entity_id, session_id ORDER BY event_time) AS path_target,
               ROW_NUMBER() OVER (PARTITION BY entity_id, session_id ORDER BY event_time) AS path_step
        FROM events)
        SELECT path_source, path_target, path_step, COUNT(*) AS path_value FROM edges
        GROUP BY path_source, path_target, path_step"""
    assert issues(sql)


@pytest.mark.parametrize("valid", [False, True])
def test_generation_routes_timestamp_resorting_to_repair(valid):
    normalized = {"analysis_model": "path", "path": PATH_CONFIG}
    response = ai_sql_generator._node_validate_sql({
        "response": ai_sql_generator.DashboardAiSqlGenerateResponse(
            success=True, sql=path_sql(edge_order="step_in_session" if valid else "event_time"),
            chart_type="sankey", analysis_model="path",
        ),
        "normalized_config": normalized,
        "sql_dialect": "mysql",
        "schema": PATH_SCHEMA,
        "graph_trace": [],
    })["response"]
    assert response.success is valid, response.issues
    if not valid:
        assert any("不能再次按时间排序" in issue for issue in response.issues)
        assert ai_sql_generator._route_after_sql_validate({"response": response, "normalized_config": normalized, "sql_repair_attempts": 0}) == "repair_sql"
