"""Executable path SQL with a stable event sequence and configurable adjacency."""

PATH_SCHEMA = "# Table: events\n[\n(event_time:bigint, role=event_time; encoding=epoch_seconds)\n]"
PATH_CONFIG = {"initialEvent": {"eventTable": "events", "eventNameField": "event_name", "eventName": "A"}}


def path_sql(*, edge_order="step_in_session", partition="entity_id, session_id", lag=False,
             sequence="ROW_NUMBER() OVER (PARTITION BY entity_id, session_id ORDER BY event_time, event_id)", offset="",
             initial_event="A", session_join="s.entity_id=v.entity_id AND s.session_id=v.session_id"):
    source = f"LAG(event_name{offset}) OVER (PARTITION BY {partition} ORDER BY {edge_order})" if lag else "event_name"
    target = "event_name" if lag else f"LEAD(event_name{offset}) OVER (PARTITION BY {partition} ORDER BY {edge_order})"
    eligible = (f""", eligible_sessions AS (
    SELECT entity_id,session_id FROM session_steps WHERE step_in_session=1 AND event_name='{initial_event}'
)""" if initial_event is not None else "")
    join = f"JOIN eligible_sessions v ON {session_join}" if initial_event is not None else ""
    return f"""
WITH session_steps AS (
    SELECT entity_id, session_id, event_id, event_time, event_name,
           {sequence} AS step_in_session
    FROM events
){eligible}, path_nodes AS (
    SELECT s.entity_id, s.session_id, s.event_id, s.event_time, s.event_name, s.step_in_session
    FROM session_steps s {join} WHERE s.step_in_session <= 10
), edge_candidates AS (
    SELECT {source} AS path_source, {target} AS path_target,
           step_in_session {'- 1' if lag else ''} AS path_step
    FROM path_nodes
), edges AS (
    SELECT path_source, path_target, path_step FROM edge_candidates
    WHERE path_source IS NOT NULL AND path_target IS NOT NULL
)
SELECT path_source, path_target, COUNT(*) AS path_value, path_step
FROM edges GROUP BY path_source, path_target, path_step ORDER BY path_step
"""
