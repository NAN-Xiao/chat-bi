"""Fixed-shape exact ranking SQL; every metric is aggregated before joins."""
from sqlglot import exp
from apps.dashboard.crud.ranking_sql_plan import RankingSqlPlan

GUARD_COLUMN = "__ranking_property_error"


def compile_ranking_sql(plan: RankingSqlPlan) -> str:
    start, end = plan.parameter_tokens
    ctes = [f"ranking_parameter_bounds AS (SELECT {start} AS range_start, {end} AS range_end)"]
    aliases = ["ranking_value", *(f"simultaneous_metric_{i}" for i in range(1, len(plan.metrics)))]
    props = [f"ranking_property_{i + 1}" for i in range(len(plan.metrics[0].properties))]
    for i, (metric, alias) in enumerate(zip(plan.metrics, aliases)):
        selected = [f"{metric.entity} AS ranking_entity"]
        if metric.measure:
            selected.append(f"{metric.measure} AS metric_value")
        selected.extend(f"{p} AS {name}" for p, name in zip(metric.properties, props))
        table = exp.to_table(metric.table, quoted=True).sql(dialect=plan.dialect)
        ctes.append(f"ranking_source_{i} AS (SELECT {', '.join(selected)} FROM {table} WHERE {metric.predicate})")
        aggregate = ("COUNT(*)" if metric.aggregation == "count" else "COUNT(DISTINCT metric_value)" if metric.aggregation == "count_distinct"
                     else f"{metric.aggregation.upper()}(metric_value)")
        ctes.append(f"ranking_metric_{i} AS (SELECT ranking_entity, {aggregate} AS {alias} FROM ranking_source_{i} GROUP BY ranking_entity)")
    if props:
        ctes.append(f"ranking_properties AS (SELECT DISTINCT ranking_entity, {', '.join(props)} FROM ranking_source_0)")
        ctes.append("ranking_property_counts AS (SELECT ranking_entity, COUNT(*) AS property_count FROM ranking_properties GROUP BY ranking_entity)")
        ctes.append("ranking_guard AS (SELECT CASE WHEN EXISTS (SELECT 1 FROM ranking_property_counts WHERE property_count > 1) THEN 1 ELSE 0 END AS data_error)")
        ctes.append("ranking_unique_properties AS (SELECT p.* FROM ranking_properties p JOIN ranking_property_counts c ON p.ranking_entity = c.ranking_entity WHERE c.property_count = 1)")
    else:
        ctes.append("ranking_guard AS (SELECT 0 AS data_error)")
    selected = ["m0.ranking_entity", "m0.ranking_value"]
    joins = []
    for i, metric in enumerate(plan.metrics[1:], 1):
        alias = aliases[i]
        value = f"m{i}.{alias}"
        if metric.aggregation in {"count", "count_distinct"}:
            value = f"COALESCE({value}, 0)"
        selected.append(f"{value} AS {alias}")
        joins.append(f"LEFT JOIN ranking_metric_{i} m{i} ON m0.ranking_entity = m{i}.ranking_entity")
    if props:
        selected.extend(f"p.{name}" for name in props)
        joins.append("LEFT JOIN ranking_unique_properties p ON m0.ranking_entity = p.ranking_entity")
    ctes.append(f"ranking_values AS (SELECT {', '.join(selected)} FROM ranking_metric_0 m0 {' '.join(joins)})")
    order = f"CASE WHEN ranking_value IS NULL THEN 1 ELSE 0 END, ranking_value {plan.direction.upper()}"
    function = {"default": "ROW_NUMBER", "skip": "RANK", "dense": "DENSE_RANK"}[plan.tie_handling]
    if plan.tie_handling == "default":
        order += ", ranking_entity"
    rank_alias = exp.to_identifier("rank", quoted=True).sql(dialect=plan.dialect)
    data_columns = ["ranking_entity", *aliases, *props]
    ctes.append(f"ranking_ranked AS (SELECT {function}() OVER (ORDER BY {order}) AS {rank_alias}, {', '.join(data_columns)} FROM ranking_values)")
    return "WITH " + ",\n".join(ctes) + f"\nSELECT {rank_alias}, {', '.join(data_columns)}, g.data_error AS {GUARD_COLUMN} FROM ranking_ranked CROSS JOIN ranking_guard g ORDER BY {rank_alias}, ranking_entity"
