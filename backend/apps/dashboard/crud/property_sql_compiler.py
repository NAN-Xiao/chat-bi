"""Closed SQL templates for resolved property plans; no user SQL interpolation."""
from __future__ import annotations

from sqlglot import exp

from apps.dashboard.crud.property_sql_plan import PropertySqlPlan


def compile_property_sql(plan: PropertySqlPlan) -> str:
    def quote(name):
        return exp.to_identifier(name, quoted=True).sql(dialect=plan.dialect)

    def column(name, owner=""):
        return f"{owner}." + quote(name) if owner else quote(name)

    def string(value):
        return exp.Literal.string(value).sql(dialect=plan.dialect)

    def measure(metric):
        argument = metric.expression
        if metric.predicate != "TRUE":
            argument = f"CASE WHEN {metric.predicate} THEN {argument} END"
        if metric.aggregation == "count_distinct":
            return f"COUNT(DISTINCT {argument})"
        return f"{metric.aggregation.upper()}({argument})"

    table_node = exp.to_table(plan.source_table)
    for identifier in table_node.parts:
        identifier.set("quoted", True)
    table = table_node.sql(dialect=plan.dialect)
    ctes = [plan.scaffold_ctes] if plan.scaffold_ctes else []
    ctes.append("scoped_properties AS (\n  SELECT " + ", ".join(quote(c) for c in plan.source_columns)
                + f"\n  FROM {table}\n  WHERE ({plan.time_predicate}) AND ({plan.global_filter})\n)")
    date_columns = ["property_date"] if plan.date_expression else []
    group_columns = ["group_1"] if plan.audiences else [f"group_{i + 1}" for i in range(len(plan.groups))]
    metric_columns = [m.alias for m in plan.metrics]
    metric_selects = [f"{measure(m)} AS {quote(m.alias)}" for m in plan.metrics]
    any_metric = " OR ".join(f"({m.predicate})" for m in plan.metrics)

    def aggregate(audience=None, index=0):
        select, dimensions = [], []
        if plan.date_expression:
            select.append(f"{plan.date_expression} AS {quote('property_date')}")
            dimensions.append(plan.date_expression)
        if audience:
            select.extend([f"{string(audience[0])} AS {quote('group_1')}", f"{index} AS audience_order"])
        else:
            select.extend(f"{value} AS {quote(name)}" for value, name in zip(plan.groups, group_columns))
            dimensions.extend(plan.groups)
        select.extend(metric_selects)
        predicate = f"({audience[1]}) AND ({any_metric})" if audience else any_metric
        query = "SELECT " + ", ".join(select) + f"\n  FROM scoped_properties\n  WHERE {predicate}"
        if dimensions:
            query += "\n  GROUP BY " + ", ".join(dimensions)
        return query

    if plan.audiences:
        ctes.append("aggregated AS (\n  " + "\n  UNION ALL\n  ".join(aggregate(a, i) for i, a in enumerate(plan.audiences)) + "\n)")
    else:
        ctes.append("aggregated AS (\n  " + aggregate() + "\n)")

    if not plan.scaffold_ctes:
        query = "SELECT " + ", ".join(quote(c) for c in plan.required_columns) + "\nFROM aggregated"
        order = date_columns + (["audience_order"] if plan.audiences else group_columns)
    else:
        if plan.audiences:
            ctes.append("dimension_domain AS (\n  " + "\n  UNION ALL\n  ".join(
                f"SELECT {string(a[0])} AS {quote('group_1')}, {i} AS audience_order"
                for i, a in enumerate(plan.audiences)) + "\n)")
        elif plan.groups:
            ctes.append("dimension_domain AS (\n  SELECT DISTINCT " + ", ".join(
                f"{value} AS {quote(name)}" for value, name in zip(plan.groups, group_columns))
                + f"\n  FROM scoped_properties\n  WHERE {any_metric}\n)")
        selected = [f"d.calendar_date AS {quote('property_date')}"]
        selected.extend(f"{column(name, 'g')} AS {quote(name)}" for name in group_columns)
        for metric in plan.metrics:
            value = column(metric.alias, "a")
            if metric.aggregation in {"count", "count_distinct"}:
                value = f"COALESCE({value}, 0)"
            selected.append(f"{value} AS {quote(metric.alias)}")
        query = "SELECT " + ", ".join(selected) + "\nFROM dashboard_dates AS d"
        if group_columns:
            query += "\nCROSS JOIN dimension_domain AS g"
        conditions = [f"d.calendar_date = {column('property_date', 'a')}"]
        if plan.audiences:
            conditions.append("g.audience_order = a.audience_order")
        else:
            for name in group_columns:
                left, right = column(name, "g"), column(name, "a")
                conditions.append(f"({left} = {right} OR ({left} IS NULL AND {right} IS NULL))")
        query += "\nLEFT JOIN aggregated AS a ON " + " AND ".join(conditions)
        order = ["d.calendar_date"] + (["g.audience_order"] if plan.audiences else [column(c, "g") for c in group_columns])
    if order:
        query += "\nORDER BY " + ", ".join(order)
    return "WITH " + ",\n".join(ctes) + "\n" + query
