"""Fixed distribution templates. Input expressions have already been authorized."""
from sqlglot import exp

from apps.dashboard.crud.distribution_sql_aggregates import (
    compile_distribution_entity_values, compile_distribution_simultaneous, key_join,
)
from apps.dashboard.crud.distribution_sql_plan import DistributionSqlPlan


def compile_distribution_sql(plan: DistributionSqlPlan) -> str:
    p = plan
    dims = ("distribution_date", *p.group_names)
    entity_columns = (*dims, "entity_id", "distribution_value", "total_entities")

    def text(value):
        return exp.Literal.string(value).sql(dialect=p.dialect)

    def as_text(value):
        return f"CAST({value} AS {'TEXT' if p.dialect == 'postgres' else 'CHAR'})"

    def concat(*values):
        return "(" + " || ".join(values) + ")" if p.dialect == "postgres" else "CONCAT(" + ", ".join(values) + ")"

    def source(s):
        table = exp.to_table(s.table)
        for part in table.parts:
            part.set("quoted", True)
        columns = [f"{s.date_expression} AS distribution_date", f"{s.entity_expression} AS entity_id"]
        columns += [f"{expression} AS {name}" for name, expression in zip(p.group_names, s.group_expressions)]
        if s.value_expression:
            columns.append(f"{s.value_expression} AS metric_value")
        if s.event_time_expression:
            columns.append(f"{s.event_time_expression} AS event_time_value")
        return "SELECT " + ", ".join(columns) + f" FROM {table.sql(dialect=p.dialect)} WHERE {s.predicate}"

    ctes = ["scoped_main AS (" + source(p.main_source) + ")"]
    ctes.extend(compile_distribution_entity_values(p).ctes)
    ctes.append("population AS (SELECT " + ", ".join((*dims, "entity_id", "distribution_value"))
                + f", COUNT(*) OVER (PARTITION BY {', '.join(dims)}) AS total_entities "
                  "FROM entity_values WHERE entity_id IS NOT NULL)")
    join = ""
    extras = []
    if p.interval_mode in {"auto", "discrete"}:
        ctes.append("value_domain AS (SELECT distribution_value, DENSE_RANK() OVER (ORDER BY distribution_value) AS discrete_order "
                    "FROM entity_values WHERE distribution_value IS NOT NULL GROUP BY distribution_value)")
        join = " LEFT JOIN value_domain AS v ON p.distribution_value = v.distribution_value"
    if p.interval_mode == "auto":
        ctes.append("global_bounds AS (SELECT MIN(distribution_value) AS min_val, MAX(distribution_value) AS max_val FROM entity_values)")
        join += " CROSS JOIN global_bounds AS g"
        extras = ["g.min_val", "g.max_val"]
        span = "(g.max_val * 1.0 - g.min_val * 1.0)"
        offset = "(p.distribution_value * 1.0 - g.min_val * 1.0)"
        # Guard every value, not only the exact maximum: a float immediately
        # below max can round to the full span during division.
        number = (f"CASE WHEN p.distribution_value IS NULL THEN 0 WHEN {span} < 12 THEN v.discrete_order "
                  "WHEN p.distribution_value >= g.max_val THEN 12 ELSE "
                  f"LEAST(12, FLOOR({offset} * 12.0 / NULLIF({span}, 0)) + 1) END")
    elif p.interval_mode == "discrete":
        number = "CASE WHEN p.distribution_value IS NULL THEN 0 ELSE v.discrete_order END"
    else:
        cases = " ".join(f"WHEN p.distribution_value < {b} THEN {n + 1}" for n, b in enumerate(p.custom_bounds))
        number = f"CASE WHEN p.distribution_value IS NULL THEN 0 {cases} ELSE {len(p.custom_bounds) + 1} END"
    ctes.append("bucket_numbers AS (SELECT " + ", ".join([*("p." + c for c in entity_columns), *extras, f"{number} AS interval_order"])
                + " FROM population AS p" + join + ")")
    if p.interval_mode == "auto":
        span = "(max_val * 1.0 - min_val * 1.0)"
        lower = f"min_val * 1.0 + {span} * (interval_order - 1) / 12.0"
        upper = f"CASE WHEN interval_order = 12 THEN max_val ELSE min_val * 1.0 + {span} * interval_order / 12.0 END"
        label = (f"CASE WHEN {span} < 12 THEN " + as_text("distribution_value") + " ELSE "
                 + concat(text("["), as_text(lower), text(", "), as_text(upper), "CASE WHEN interval_order = 12 THEN ']' ELSE ')' END") + " END")
    elif p.interval_mode == "discrete":
        label = as_text("distribution_value")
    else:
        bounds = [format(b, "f") for b in p.custom_bounds]
        labels = [f"(-∞, {bounds[0]})", *(f"[{a}, {b})" for a, b in zip(bounds, bounds[1:])), f"[{bounds[-1]}, +∞)"]
        label = "CASE " + " ".join(f"WHEN interval_order = {n + 1} THEN {text(value)}" for n, value in enumerate(labels)) + " END"
    ctes.append("bucketed AS (SELECT " + ", ".join((*entity_columns, "interval_order"))
                + f", CASE WHEN interval_order = 0 THEN {text('无有效值')} ELSE {label} END AS interval_label FROM bucket_numbers)")
    simultaneous = compile_distribution_simultaneous(p)
    if simultaneous:
        ctes.append("scoped_simultaneous AS (" + source(p.simultaneous_source) + ")")
        ctes.extend(simultaneous.ctes)
    selects = ["b." + c for c in dims]
    selects += ["MAX(b.total_entities) AS total_entities", "b.interval_order", "b.interval_label",
                "COUNT(DISTINCT b.entity_id) AS entity_count",
                "ROUND(COUNT(DISTINCT b.entity_id) * 100.0 / NULLIF(MAX(b.total_entities), 0), 2) AS entity_rate"]
    tail = "FROM bucketed AS b"
    if simultaneous:
        selects.append("MAX(s.simultaneous_value) AS simultaneous_value")
        tail += f" LEFT JOIN {simultaneous.relation} AS s ON " + key_join("b", "s", (*dims, "interval_order"))
    groups = ", ".join("b." + k for k in (*dims, "interval_order", "interval_label"))
    return "WITH " + ",\n".join(ctes) + "\nSELECT " + ",\n       ".join(selects) + "\n" + tail + "\nGROUP BY " + groups + "\nORDER BY " + ", ".join("b." + k for k in (*dims, "interval_order"))
