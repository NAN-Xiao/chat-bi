"""Closed, bounded daily cohort SQL templates for resolved retention plans."""
from sqlglot import exp

from apps.dashboard.crud.retention_sql_plan import RetentionSqlPlan


def compile_retention_sql(plan: RetentionSqlPlan) -> str:
    dialect = plan.dialect

    def table(name):
        node = exp.to_table(name)
        for part in node.parts:
            part.set("quoted", True)
        return node.sql(dialect=dialect)

    def plus(value, days):
        return (f"({value} + INTERVAL '{days} DAY')" if dialect == "postgres"
                else f"DATE_ADD({value}, INTERVAL {days} DAY)")

    def source(event, date_alias, metric=False):
        columns = [f"{event.entity} AS entity_id", f"{event.date} AS {date_alias}"]
        if plan.related_enabled:
            columns.append(f"{event.related} AS related_property")
        if metric and event.metric:
            columns.append(f"{event.metric} AS metric_value")
        return "SELECT " + ", ".join(columns) + f"\n  FROM {table(event.table)}\n  WHERE {event.predicate}"

    group = ["cohort_date"] + (["related_property"] if plan.related_as_group else [])
    cohort_keys = ["cohort_date", "entity_id"] + (["related_property"] if plan.related_enabled else [])
    behavior_keys = ["entity_id", "behavior_date"] + (["related_property"] if plan.related_enabled else [])
    ctes = [f"dashboard_date_bounds AS (SELECT {plan.end_expression} AS end_date)",
            "initial_events AS (\n  " + source(plan.initial, "cohort_date") + "\n)",
            "cohort_unique AS (SELECT DISTINCT " + ", ".join(cohort_keys) + " FROM initial_events)",
            "cohort_sizes AS (SELECT " + ", ".join(group) + ", COUNT(DISTINCT entity_id) AS cohort_size\n"
            + "  FROM cohort_unique GROUP BY " + ", ".join(group) + ")",
            "return_events AS (\n  " + source(plan.returning, "behavior_date") + "\n)",
            "return_events_unique AS (SELECT DISTINCT " + ", ".join(behavior_keys) + " FROM return_events)"]
    match = "c.entity_id = b.entity_id AND b.behavior_date >= c.cohort_date AND b.behavior_date <= " + plus("c.cohort_date", plan.window_days)
    if plan.related_enabled:
        match += " AND c.related_property = b.related_property"
    offset = ("CAST(b.behavior_date AS DATE) - CAST(c.cohort_date AS DATE)" if dialect == "postgres"
              else "DATEDIFF(b.behavior_date, c.cohort_date)")
    matched = ["c.cohort_date", "c.entity_id", "b.behavior_date", f"{offset} AS period_offset"]
    if plan.related_enabled:
        matched.append("c.related_property")
    ctes.append("matched_returns AS (SELECT " + ", ".join(matched)
                + "\n  FROM cohort_unique AS c JOIN return_events_unique AS b ON " + match + ")")
    counts = [f"COUNT(DISTINCT CASE WHEN period_offset = {d} THEN entity_id END) AS retained_{d}" for d in range(plan.window_days + 1)]
    ctes.append("retention_counts AS (SELECT " + ", ".join(group + counts)
                + "\n  FROM matched_returns GROUP BY " + ", ".join(group) + ")")
    if plan.simultaneous:
        ctes.append("simultaneous_events AS (\n  " + source(plan.simultaneous, "behavior_date", True) + "\n)")
        # A distinct eligibility set makes the join many-to-one for each cohort,
        # preserving true event duplicates but never multiplying them by returns.
        keys = ["cohort_date", *behavior_keys]
        ctes.append("simultaneous_keys AS (SELECT DISTINCT " + ", ".join(keys) + " FROM matched_returns)")
        conditions = ["s.entity_id = k.entity_id", "s.behavior_date = k.behavior_date"]
        if plan.related_enabled:
            conditions.append("s.related_property = k.related_property")
        agg = plan.aggregation
        measure = "COUNT(*)" if agg == "count" else ("COUNT(DISTINCT s.metric_value)" if agg == "count_distinct" else f"{agg.upper()}(s.metric_value)")
        dims = [f"k.{key}" for key in group]
        ctes.append("simultaneous_aggregate AS (SELECT " + ", ".join(dims) + f", {measure} AS simultaneous_value"
                    + "\n  FROM simultaneous_keys AS k JOIN simultaneous_events AS s ON " + " AND ".join(conditions)
                    + "\n  GROUP BY " + ", ".join(dims) + ")")

    def join(alias):
        conditions = [f"c.cohort_date = {alias}.cohort_date"]
        if plan.related_as_group:
            conditions.append(f"(c.related_property = {alias}.related_property OR (c.related_property IS NULL AND {alias}.related_property IS NULL))")
        return " AND ".join(conditions)

    output = ["c.cohort_date AS cohort_date", "c.cohort_size AS cohort_size"]
    for d in range(plan.window_days + 1):
        mature = plus("c.cohort_date", d) + (" <= " if plan.end_inclusive else " < ") + "bounds.end_date"
        output.append(f"CASE WHEN {mature} THEN ROUND(COALESCE(r.retained_{d}, 0) * 100.0 / NULLIF(c.cohort_size, 0), 2) ELSE NULL END AS day_{d}")
    if plan.simultaneous:
        measure = "COALESCE(s.simultaneous_value, 0)" if plan.aggregation in {"count", "count_distinct"} else "s.simultaneous_value"
        output.append(measure + " AS simultaneous_value")
    if plan.related_as_group:
        output.append("c.related_property AS related_property")
    sql = "WITH " + ",\n".join(ctes) + "\nSELECT " + ",\n       ".join(output)
    sql += "\nFROM cohort_sizes AS c\nCROSS JOIN dashboard_date_bounds AS bounds\nLEFT JOIN retention_counts AS r ON " + join("r")
    if plan.simultaneous:
        sql += "\nLEFT JOIN simultaneous_aggregate AS s ON " + join("s")
    return sql + "\nORDER BY " + ", ".join("c." + name for name in group)
