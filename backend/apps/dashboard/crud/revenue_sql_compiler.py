"""Unique daily cohorts, payer eligibility and independent income detail."""
from sqlglot import exp

from apps.dashboard.crud.revenue_sql_plan import RevenueSqlPlan


def compile_revenue_sql(plan: RevenueSqlPlan) -> str:
    def table(name):
        node = exp.to_table(name)
        for part in node.parts:
            part.set("quoted", True)
        return node.sql(dialect=plan.dialect)

    def plus(value, days):
        return f"({value} + INTERVAL '{days} DAY')" if plan.dialect == "postgres" else f"DATE_ADD({value}, INTERVAL {days} DAY)"

    groups = [f"group_{i + 1}" for i in range(len(plan.initial.groups))]
    keys = ["cohort_date", *groups]
    cohort_keys = ["cohort_date", "entity_id", *groups]
    initial = [f"{plan.initial.entity} AS entity_id", f"{plan.initial.date} AS cohort_date",
               *(f"{g} AS {alias}" for g, alias in zip(plan.initial.groups, groups))]
    payment = [f"{plan.payment.entity} AS entity_id", f"{plan.payment.date} AS behavior_date"]
    income = [f"{plan.metric_event.entity} AS entity_id", f"{plan.metric_event.date} AS behavior_date"]
    if plan.metric_event.metric: income.append(f"{plan.metric_event.metric} AS metric_value")
    ctes = [f"dashboard_date_bounds AS (SELECT {plan.end_expression} AS end_date)",
            "initial_events AS (SELECT " + ", ".join(initial) + f"\n  FROM {table(plan.initial.table)} WHERE {plan.initial.predicate})",
            "cohort_unique AS (SELECT DISTINCT " + ", ".join(cohort_keys) + " FROM initial_events)",
            "cohort_sizes AS (SELECT " + ", ".join(keys) + ", COUNT(DISTINCT entity_id) AS cohort_size\n"
            + "  FROM cohort_unique GROUP BY " + ", ".join(keys) + ")",
            "payment_events AS (SELECT " + ", ".join(payment) + f"\n  FROM {table(plan.payment.table)} WHERE {plan.payment.predicate})",
            "metric_events AS (SELECT " + ", ".join(income) + f"\n  FROM {table(plan.metric_event.table)} WHERE {plan.metric_event.predicate})"]
    offset = "CAST(b.behavior_date AS DATE) - CAST(c.cohort_date AS DATE)" if plan.dialect == "postgres" else "DATEDIFF(b.behavior_date, c.cohort_date)"
    matched = ["c.cohort_date", "c.entity_id", *(f"c.{g}" for g in groups), f"{offset} AS period_offset"]
    ctes.append("matched_payments AS (SELECT " + ", ".join(matched) + "\n  FROM cohort_unique AS c JOIN payment_events AS b"
                + " ON c.entity_id = b.entity_id AND b.behavior_date >= c.cohort_date AND b.behavior_date <= "
                + plus("c.cohort_date", plan.observation_days) + ")")
    # Only eligibility is deduplicated. Never join income detail to raw payments:
    # multiple qualifying payments must not multiply metric rows or cost.
    ctes.append("payer_cohorts AS (SELECT DISTINCT " + ", ".join(cohort_keys) + " FROM matched_payments)")
    metric_matched = ["c.cohort_date", "c.entity_id", *(f"c.{g}" for g in groups), f"{offset} AS period_offset"]
    if plan.metric_event.metric: metric_matched.append("b.metric_value")
    ctes.append("matched_metrics AS (SELECT " + ", ".join(metric_matched) + "\n  FROM payer_cohorts AS c JOIN metric_events AS b"
                + " ON c.entity_id = b.entity_id AND b.behavior_date >= c.cohort_date AND b.behavior_date <= "
                + plus("c.cohort_date", plan.observation_days) + ")")
    measures = ["COUNT(*) AS event_count", "COUNT(DISTINCT entity_id) AS entity_count"]
    if plan.metric_event.metric:
        measures.append(f"{'AVG' if plan.method == 'property_avg' else 'SUM'}(metric_value) AS metric_value")
    daily_keys = [*keys, "period_offset"]
    ctes.append("daily_values AS (SELECT " + ", ".join([*daily_keys, *measures])
                + "\n  FROM matched_metrics GROUP BY " + ", ".join(daily_keys) + ")")
    if plan.cost_event:
        cost = plan.cost_event
        property_column = f", {cost.cost} AS cost_value" if cost.cost else ""
        ctes.append(f"cost_events AS (SELECT {cost.entity} AS entity_id, {cost.date} AS behavior_date" + property_column
                    + f" FROM {table(cost.table)} WHERE {cost.predicate})")
        cost_keys = [f"c.{key}" for key in keys]
        ctes.append("matched_costs AS (SELECT " + ", ".join(cost_keys) + ", c.entity_id, b.behavior_date"
                    + (", b.cost_value" if cost.cost else "")
                    + " FROM cohort_unique AS c JOIN cost_events AS b"
                    + " ON c.entity_id = b.entity_id AND b.behavior_date >= c.cohort_date AND b.behavior_date <= "
                    + plus("c.cohort_date", plan.observation_days) + ")")
        method = plan.cost_method
        source = "matched_costs"
        if method in {"period_cumulative_entity_count", "period_average_entity_count"}:
            ctes.append("cost_daily_entities AS (SELECT " + ", ".join(keys)
                        + ", behavior_date, COUNT(DISTINCT entity_id) AS entity_count FROM matched_costs GROUP BY "
                        + ", ".join([*keys, "behavior_date"]) + ")")
            source = "cost_daily_entities"
            cost_measure = "SUM(entity_count)"
        else:
            cost_measure = {"property_sum":"SUM(cost_value)", "property_avg":"AVG(cost_value)",
                            "entity_count":"COUNT(DISTINCT entity_id)",
                            "per_entity_count":"COUNT(*) * 1.0 / NULLIF(COUNT(DISTINCT entity_id), 0)",
                            "count":"COUNT(*)", "period_cumulative_count":"COUNT(*)", "period_average_count":"COUNT(*)"}[method]
        if method in {"period_average_count", "period_average_entity_count"}:
            cost_measure += f" * 1.0 / {plan.observation_days + 1}"
        ctes.append("cohort_costs AS (SELECT " + ", ".join(keys) + f", {cost_measure} AS cost_value"
                    + f" FROM {source} GROUP BY " + ", ".join(keys) + ")")

    def value(day):
        if plan.method in {"property_sum", "property_avg"}:
            return f"MAX(CASE WHEN period_offset = {day} THEN metric_value END)"
        if plan.method == "per_entity_count":
            return f"MAX(CASE WHEN period_offset = {day} THEN event_count * 1.0 / NULLIF(entity_count, 0) END)"
        measure = "entity_count" if "entity_count" in plan.method else "event_count"
        cumulative = plan.method.startswith("period_")
        result = f"SUM(CASE WHEN period_offset {'<=' if cumulative else '='} {day} THEN {measure} ELSE 0 END)"
        if plan.method.startswith("period_average_"):
            result += f" * 1.0 / {day + 1}"
        return result

    aggregate = [f"{value(day)} AS day_{day}" for day in range(plan.observation_days + 1)]
    ctes.append("revenue_values AS (SELECT " + ", ".join([*keys, *aggregate])
                + "\n  FROM daily_values GROUP BY " + ", ".join(keys) + ")")
    comparison = "<=" if plan.end_inclusive else "<"
    output = ["c.cohort_date AS cohort_date", "c.cohort_size AS cohort_size"]
    for day in range(plan.observation_days + 1):
        expression = f"r.day_{day}"
        if plan.method not in {"property_avg", "per_entity_count"}:
            expression = f"COALESCE({expression}, 0)"
        output.append(f"CASE WHEN {plus('c.cohort_date', day)} {comparison} d.end_date THEN {expression} ELSE NULL END AS day_{day}")
    if plan.cost_event:
        cost_value = "k.cost_value" if plan.cost_method in {"property_avg", "per_entity_count"} else "COALESCE(k.cost_value, 0)"
        output.append(f"CASE WHEN {plus('c.cohort_date', plan.observation_days)} {comparison} d.end_date THEN {cost_value} ELSE NULL END AS cost_value")
    output.extend(f"c.{g} AS {g}" for g in groups)
    matches = ["c.cohort_date = r.cohort_date"] + [f"(c.{g} = r.{g} OR (c.{g} IS NULL AND r.{g} IS NULL))" for g in groups]
    query = "SELECT " + ",\n       ".join(output) + "\nFROM cohort_sizes AS c CROSS JOIN dashboard_date_bounds AS d\n"
    query += "LEFT JOIN revenue_values AS r ON " + " AND ".join(matches)
    if plan.cost_event:
        cost_matches = ["c.cohort_date = k.cohort_date"] + [f"(c.{g} = k.{g} OR (c.{g} IS NULL AND k.{g} IS NULL))" for g in groups]
        query += "\nLEFT JOIN cohort_costs AS k ON " + " AND ".join(cost_matches)
    query += "\nORDER BY " + ", ".join(f"c.{k}" for k in keys)
    return "WITH " + ",\n".join(ctes) + "\n" + query
