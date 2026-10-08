"""Pure, fixed-shape path query compiler with an atomic ordering guard."""
import json
from sqlglot import exp
from apps.dashboard.crud.path_sql_plan import PathSqlPlan
from apps.dashboard.crud.property_sql_plan import NUMERIC

PATH_GUARD_COLUMN = "__path_order_error"


def _mysql_json_string(column):
    """Injective JSON string encoding using portable scalar string functions.

    Some MySQL-compatible analytical engines expose JSON_UNQUOTE but not
    JSON_QUOTE. Escaping via CHAR also avoids session SQL-mode backslashes.
    """
    value = f"CAST({column} AS CHAR)"
    for code, replacement in [(92, "CONCAT(CHAR(92), CHAR(92))"),
                              (34, "CONCAT(CHAR(92), CHAR(34))"),
                              *[(n, f"CONCAT(CHAR(92), 'u{n:04x}')") for n in range(32)]]:
        value = f"REPLACE({value}, CHAR({code}), {replacement})"
    return f"CONCAT(CHAR(34), {value}, CHAR(34))"


def compile_path_sql(plan: PathSqlPlan) -> str:
    p = plan
    literal = lambda value: exp.Literal.string(value).sql(dialect=p.dialect)
    table = exp.to_table(p.table, quoted=True).sql(dialect=p.dialect)
    nodes = []
    for event in p.events:
        label = literal(json.dumps(event.event_name, ensure_ascii=False))
        if event.split_expression:
            column = event.split_expression
            prefix = literal(json.dumps(event.event_name, ensure_ascii=False) + " / " +
                             json.dumps(event.split_property_name, ensure_ascii=False) + "=")
            if p.dialect == "postgres":
                if event.split_type.startswith(("numeric", "decimal", "number")):
                    # NUMERIC equality ignores scale; its text/JSON form does
                    # not. Normalize only decimal text, preserving all digits.
                    text = f"CAST({column} AS TEXT)"
                    value = (f"CASE WHEN POSITION('.' IN {text}) > 0 "
                             f"THEN RTRIM(RTRIM({text}, '0'), '.') ELSE {text} END")
                else:
                    value = f"CAST(TO_JSONB({column}) AS TEXT)"
            elif NUMERIC.match(event.split_type):
                value = f"CAST({column} AS CHAR)"
            elif event.split_type in {"bool", "boolean"}:
                value = f"CASE WHEN {column} IS NULL THEN NULL WHEN {column} THEN 'true' ELSE 'false' END"
            else:
                value = _mysql_json_string(column)
            label = f"CONCAT({prefix}, COALESCE({value}, 'null'))"
        nodes.append(f"WHEN {event.event_predicate} THEN {label}")
    aliases = [f"order_{i + 1}" for i in range(len(p.order_expressions))]
    columns = ["entity_id", "event_key", "event_time", "raw_event_time", *aliases, "node_label"]
    projection = [f"{p.entity_expression} AS entity_id", f"{p.event_key_expression} AS event_key",
                  f"{p.time.instant} AS event_time", f"{p.time.raw_time} AS raw_event_time",
                  *[f"{expression} AS {alias}" for expression, alias in zip(p.order_expressions, aliases)],
                  "CASE " + " ".join(nodes) + " END AS node_label"]
    keys = ["entity_id", "event_time", *aliases]
    nulls = " OR ".join(f"{v} IS NULL" for v in ["event_time", *aliases])
    order = ", ".join(f"{v} ASC" for v in ["event_time", *aliases])
    base = ", ".join(columns)
    ctes = [p.time.bounds,
        f"scoped_events AS (SELECT {', '.join(projection)} FROM {table} WHERE ({p.time.predicate}) "
        f"AND ({p.mandatory_predicate}) AND ({p.global_predicate}) AND {p.entity_expression} IS NOT NULL "
        f"AND ({' OR '.join(e.event_predicate for e in p.events)}))",
        f"order_conflicts AS (SELECT {', '.join(keys)} FROM scoped_events GROUP BY {', '.join(keys)} "
        f"HAVING COUNT(*) > 1 OR {nulls})",
        f"path_guard AS (SELECT CASE WHEN EXISTS(SELECT 1 FROM order_conflicts) THEN 1 ELSE 0 END AS {PATH_GUARD_COLUMN})",
        f"ordered_events AS (SELECT {base}, ROW_NUMBER() OVER (PARTITION BY entity_id ORDER BY {order}) AS event_sequence "
        f"FROM scoped_events WHERE (SELECT {PATH_GUARD_COLUMN} FROM path_guard) = 0)",
        f"event_gaps AS (SELECT {base}, event_sequence, LAG(event_time) OVER "
        "(PARTITION BY entity_id ORDER BY event_sequence ASC) AS previous_time FROM ordered_events)",
        f"session_flags AS (SELECT {base}, event_sequence, CASE WHEN previous_time IS NULL OR "
        f"event_time - previous_time > {p.session_gap_seconds} THEN 1 ELSE 0 END AS new_session FROM event_gaps)",
        f"sessionized AS (SELECT {base}, event_sequence, SUM(new_session) OVER (PARTITION BY entity_id "
        "ORDER BY event_sequence ASC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS session_id FROM session_flags)",
        f"session_steps AS (SELECT {base}, event_sequence, session_id, ROW_NUMBER() OVER "
        "(PARTITION BY entity_id, session_id ORDER BY event_sequence ASC) AS step_in_session FROM sessionized)",
        f"valid_sessions AS (SELECT entity_id, session_id FROM session_steps WHERE step_in_session = 1 AND event_key = {literal(p.initial_event_name)})",
        "path_nodes AS (SELECT s.entity_id, s.session_id, s.node_label, s.step_in_session FROM session_steps s "
        "INNER JOIN valid_sessions v ON s.entity_id = v.entity_id AND s.session_id = v.session_id "
        f"WHERE s.step_in_session <= {p.max_nodes})",
        "edge_candidates AS (SELECT entity_id, session_id, node_label AS path_source, "
        "LEAD(node_label) OVER (PARTITION BY entity_id, session_id ORDER BY step_in_session ASC) AS path_target, "
        "step_in_session AS path_step FROM path_nodes)",
        "edges AS (SELECT entity_id, session_id, path_source, path_target, path_step FROM edge_candidates WHERE path_target IS NOT NULL)",
        "path_result AS (SELECT path_source, path_target, COUNT(*) AS path_value, path_step "
        "FROM edges GROUP BY path_source, path_target, path_step)"]
    return "WITH " + ",\n".join(ctes) + "\n" + (
        f"SELECT {', '.join(p.required_columns)}, 0 AS {PATH_GUARD_COLUMN} FROM path_result\n"
        f"UNION ALL SELECT {', '.join('NULL AS ' + n for n in p.required_columns)}, 1 AS {PATH_GUARD_COLUMN} "
        f"FROM path_guard WHERE path_guard.{PATH_GUARD_COLUMN} = 1\n"
        "ORDER BY path_step ASC, path_value DESC, path_source ASC, path_target ASC")
