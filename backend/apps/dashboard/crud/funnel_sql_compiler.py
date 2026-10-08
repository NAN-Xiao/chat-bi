"""Closed step-by-step funnel templates; no query inference or model repair."""
from sqlglot import exp

from apps.dashboard.crud.funnel_sql_plan import FunnelSqlPlan


def compile_funnel_sql(plan: FunnelSqlPlan) -> str:
    ctes = []
    same_day = plan.window_mode == "same_day"
    for step in plan.steps:
        table = exp.to_table(step.table)
        for part in table.parts:
            part.set("quoted", True)
        columns = [f"{step.entity} AS entity_id", f"{step.time} AS event_time"]
        if same_day:
            columns.append(f"{step.time_day} AS event_day")
        if plan.related_enabled:
            columns.append(f"{step.related} AS related_key")
        ctes.append(f"source_{step.order} AS (SELECT " + ", ".join(columns)
                    + f"\n  FROM {table.sql(dialect=plan.dialect)}\n  WHERE {step.predicate})")
        if step.order == 1:
            columns = ["entity_id", "event_time AS first_step_time", "event_time AS step_time"]
            if same_day:
                columns.append("event_day AS first_step_day")
            if plan.related_enabled:
                columns.append("related_key")
            ctes.append("step_1 AS (SELECT " + ", ".join(columns) + " FROM source_1)")
            continue
        keys = ["p.entity_id", "p.first_step_time"]
        conditions = ["e.entity_id = p.entity_id", "e.event_time >= p.step_time"]
        if same_day:
            keys.append("p.first_step_day")
            conditions.append("e.event_day = p.first_step_day")
        else:
            conditions.append(f"e.event_time - p.first_step_time <= {plan.window_seconds}")
        if plan.related_enabled:
            keys.append("p.related_key")
            conditions.append("e.related_key = p.related_key")
        ctes.append(f"step_{step.order} AS (SELECT " + ", ".join(keys) + ", MIN(e.event_time) AS step_time"
                    + f"\n  FROM step_{step.order - 1} AS p JOIN source_{step.order} AS e ON "
                    + " AND ".join(conditions) + "\n  GROUP BY " + ", ".join(keys) + ")")
    counts = [f"SELECT {s.order} AS step_order, {exp.Literal.string(s.label).sql(dialect=plan.dialect)} AS step_name, "
              f"COUNT(DISTINCT entity_id) AS step_count FROM step_{s.order}" for s in plan.steps]
    ctes.append("step_counts AS (\n  " + "\n  UNION ALL\n  ".join(counts) + ")")
    ctes.append("""step_metrics AS (
  SELECT sc.step_order, sc.step_name, sc.step_count,
         (SELECT first_sc.step_count FROM step_counts AS first_sc WHERE first_sc.step_order = 1) AS first_step_count,
         (SELECT prev_sc.step_count FROM step_counts AS prev_sc WHERE prev_sc.step_order = sc.step_order - 1) AS previous_step_count
  FROM step_counts AS sc)""")
    return "WITH " + ",\n".join(ctes) + """
SELECT step_order AS step_order, step_name AS step_name, step_count AS step_count,
       step_count * 1.0 / NULLIF(first_step_count, 0) AS step_rate,
       CASE WHEN first_step_count = 0 THEN NULL WHEN step_order = 1 THEN 1.0
            ELSE step_count * 1.0 / NULLIF(previous_step_count, 0) END AS step_conversion_rate,
       CASE WHEN first_step_count = 0 THEN NULL WHEN step_order = 1 THEN 0.0
            ELSE (previous_step_count - step_count) * 1.0 / NULLIF(previous_step_count, 0) END AS step_dropoff_rate
FROM step_metrics ORDER BY step_order"""
