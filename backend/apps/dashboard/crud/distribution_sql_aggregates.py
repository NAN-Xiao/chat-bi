"""Exact per-subject and per-bucket aggregates over compiler-owned relations."""
from dataclasses import dataclass

from apps.dashboard.crud.distribution_sql_plan import DistributionSqlPlan


@dataclass(frozen=True)
class AggregateSqlParts:
    ctes: tuple[str, ...]
    relation: str
    value_column: str


def key_join(left: str, right: str, keys: tuple[str, ...] | list[str]) -> str:
    return " AND ".join(f"({left}.{key} = {right}.{key} OR ({left}.{key} IS NULL AND {right}.{key} IS NULL))" for key in keys)


def compile_distribution_entity_values(plan: DistributionSqlPlan) -> AggregateSqlParts:
    keys = ("distribution_date", *plan.group_names, "entity_id")
    columns = ", ".join(keys)
    kind, agg = plan.metric_kind, plan.aggregation
    ctes, relation = [], "scoped_main"
    if kind == "count":
        measure = "COUNT(*)"
    elif kind in {"days", "hours"}:
        measure = "COUNT(DISTINCT event_time_value)"
    elif agg == "count_distinct":
        measure = "COUNT(DISTINCT metric_value)"
    elif agg in {"sum", "avg", "min", "max"}:
        measure = f"{agg.upper()}(metric_value)"
    elif agg in {"variance", "stddev"}:
        relation = "entity_mean_rows"
        ctes.append(f"{relation} AS (SELECT {columns}, metric_value, "
                    f"AVG(metric_value) OVER (PARTITION BY {columns}) AS entity_mean "
                    "FROM scoped_main WHERE entity_id IS NOT NULL)")
        variance = "AVG((metric_value - entity_mean) * (metric_value - entity_mean))"
        measure = f"SQRT({variance})" if agg == "stddev" else variance
    else:
        # NULL rows sort after every valid value and do not contribute to n.
        # Keeping them preserves subjects whose entire property sample is NULL.
        quantile = "0.5" if agg == "median" else str(int(agg.removeprefix("percentile_")) / 100)
        relation = "entity_percentile_rows"
        ctes.append(f"{relation} AS (SELECT {columns}, metric_value, "
                    f"ROW_NUMBER() OVER (PARTITION BY {columns} ORDER BY CASE WHEN metric_value IS NULL THEN 1 ELSE 0 END, metric_value) AS value_position, "
                    f"COUNT(metric_value) OVER (PARTITION BY {columns}) AS value_count "
                    "FROM scoped_main WHERE entity_id IS NOT NULL)")
        position = f"((value_count - 1) * {quantile})"
        lower = f"MAX(CASE WHEN value_position = FLOOR({position}) + 1 THEN metric_value END)"
        upper = f"MAX(CASE WHEN value_position = CEIL({position}) + 1 THEN metric_value END)"
        # Promote operands before subtraction: MIN/MAX of physical integer
        # fields retain integer width, even when the final result is decimal.
        measure = f"{lower} * 1.0 + ({upper} * 1.0 - {lower} * 1.0) * MAX({position} - FLOOR({position}))"
    ctes.append(f"entity_values AS (SELECT {columns}, {measure} AS distribution_value "
                f"FROM {relation} WHERE entity_id IS NOT NULL GROUP BY {columns})")
    return AggregateSqlParts(tuple(ctes), "entity_values", "distribution_value")


def compile_distribution_simultaneous(plan: DistributionSqlPlan) -> AggregateSqlParts | None:
    if plan.simultaneous_source is None:
        return None
    entity_keys = ("distribution_date", *plan.group_names, "entity_id")
    bucket_keys = ("distribution_date", *plan.group_names, "interval_order")
    keys = ", ".join(entity_keys)
    dims = ", ".join("b." + k for k in bucket_keys)
    agg = plan.simultaneous_aggregation
    ctes = []
    if agg == "count_distinct":
        ctes.append(f"simultaneous_values AS (SELECT DISTINCT {keys}, metric_value "
                    "FROM scoped_simultaneous WHERE entity_id IS NOT NULL AND metric_value IS NOT NULL)")
        relation, measure = "simultaneous_values", "COUNT(DISTINCT s.metric_value)"
    else:
        relation = "simultaneous_entities"
        if agg == "avg":
            stats = "SUM(metric_value) AS value_sum, COUNT(metric_value) AS value_count"
            measure = "SUM(s.value_sum) * 1.0 / NULLIF(SUM(s.value_count), 0)"
        elif agg == "count":
            stats = "COUNT(*) AS entity_value"
            measure = "COALESCE(SUM(s.entity_value), 0)"
        else:
            stats = f"{agg.upper()}(metric_value) AS entity_value"
            measure = f"{agg.upper()}(s.entity_value)"
        ctes.append(f"{relation} AS (SELECT {keys}, {stats} FROM scoped_simultaneous "
                    f"WHERE entity_id IS NOT NULL GROUP BY {keys})")
    ctes.append(f"simultaneous_buckets AS (SELECT {dims}, {measure} AS simultaneous_value "
                f"FROM bucketed AS b LEFT JOIN {relation} AS s ON {key_join('b', 's', entity_keys)} "
                f"GROUP BY {dims})")
    return AggregateSqlParts(tuple(ctes), "simultaneous_buckets", "simultaneous_value")
