"""Render the fixed interval query from an immutable authorized plan."""
from sqlglot import exp

from apps.dashboard.crud.interval_sql_plan import IntervalConfigurationError, IntervalSqlPlan

GUARD_COLUMN = "__interval_order_error"


def exact_percentile_expression(quantile):
    position = f"(percentile_count - 1) * {quantile}"
    lower = f"MAX(CASE WHEN percentile_position = FLOOR({position}) + 1 THEN interval_seconds END)"
    upper = f"MAX(CASE WHEN percentile_position = CEIL({position}) + 1 THEN interval_seconds END)"
    return f"{lower} + ({upper} - {lower}) * MAX({position} - FLOOR({position}))"


def compile_interval_sql(plan: IntervalSqlPlan) -> str:
    p = plan
    groups = p.group_names
    order_names = tuple(f"event_order_{i + 1}" for i in range(len(p.order_fields)))
    related = p.related_start is not None
    projections = [f"{p.entity} AS entity_id", f"{p.time.date} AS event_date", f"{p.time.instant} AS event_time",
                   f"CASE WHEN {p.start} THEN 1 ELSE 0 END AS is_start", f"CASE WHEN {p.end} THEN 1 ELSE 0 END AS is_end"]
    projections += [f"{value} AS {name}" for value, name in zip(p.groups, groups)]
    projections += [f"{value} AS {name}" for value, name in zip(p.order_fields, order_names)]
    if related:
        projections += [f"CASE WHEN {p.start} THEN {p.related_start} ELSE {p.related_end} END AS related_key"]
    table = exp.to_table(p.table, quoted=True).sql(dialect=p.dialect)
    ctes = [p.time.bounds, p.time.scaffold,
            f"interval_source AS (SELECT {', '.join(projections)} FROM {table} WHERE ({p.time.predicate}) "
            f"AND ({p.filters}) AND (({p.start}) OR ({p.end})) AND {p.entity} IS NOT NULL AND {p.time.raw_time} IS NOT NULL)",
            "interval_events AS (SELECT * FROM interval_source" + (" WHERE related_key IS NOT NULL" if related else "") + ")"]
    partition = ["entity_id", *(["related_key"] if related else [])]
    key = [*partition, "event_time", *order_names]
    null_keys = " OR ".join(f"{n} IS NULL" for n in ["event_time", *order_names])
    ctes += [f"interval_order_conflicts AS (SELECT 1 AS conflict FROM interval_events GROUP BY {', '.join(key)} HAVING COUNT(*) > 1 OR {null_keys})",
             f"interval_guard AS (SELECT CASE WHEN EXISTS(SELECT 1 FROM interval_order_conflicts) THEN 1 ELSE 0 END AS {GUARD_COLUMN})"]
    window = f"OVER (PARTITION BY {', '.join(partition)} ORDER BY {', '.join(['event_time', *order_names])})"
    previous = [f"LAG(event_time) {window} AS start_time", f"LAG(event_date) {window} AS interval_date", f"LAG(is_start) {window} AS prev_is_start"]
    previous += [f"LAG({n}) {window} AS start_{n}" for n in groups]
    ctes += [f"interval_ordered AS (SELECT *, {', '.join(previous)} FROM interval_events WHERE (SELECT {GUARD_COLUMN} FROM interval_guard) = 0)"]
    pairs = ["entity_id", "interval_date", "start_time", "event_time AS end_time", *[f"start_{n} AS {n}" for n in groups]]
    ctes += [f"interval_pairs AS (SELECT {', '.join(pairs)} FROM interval_ordered WHERE is_end = 1 AND prev_is_start = 1)"]
    dimensions = ["interval_date", *groups]
    ctes += [f"interval_durations AS (SELECT entity_id, {', '.join(dimensions)}, end_time - start_time AS interval_seconds FROM interval_pairs)",
             f"valid_intervals AS (SELECT * FROM interval_durations WHERE interval_seconds >= 0 AND interval_seconds <= {p.limit_seconds})"]
    approx = any(name in p.engine for name in ("analyticdb", "starrocks", "doris"))
    source = "valid_intervals"
    if not approx and p.dialect != "postgres":
        ctes += [f"interval_percentile_rows AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY {', '.join(dimensions)} ORDER BY interval_seconds) AS percentile_position, COUNT(*) OVER (PARTITION BY {', '.join(dimensions)}) AS percentile_count FROM valid_intervals)"]
        source = "interval_percentile_rows"
    aggregates = ["COUNT(DISTINCT entity_id) AS entity_count", "COUNT(*) AS interval_count", "MAX(interval_seconds) AS max_interval_seconds",
                  "MIN(interval_seconds) AS min_interval_seconds", "AVG(interval_seconds) AS avg_interval_seconds"]
    for q, alias in (("0.75", "p75_interval_seconds"), ("0.50", "median_interval_seconds"), ("0.25", "p25_interval_seconds")):
        if approx:
            fn = "PERCENTILE_APPROX" if any(name in p.engine for name in ("starrocks", "doris")) else "APPROX_PERCENTILE"
            expression = f"{fn}(interval_seconds, {q})"
        elif p.dialect == "postgres": expression = f"PERCENTILE_CONT({q}) WITHIN GROUP (ORDER BY interval_seconds)"
        else: expression = exact_percentile_expression(q)
        aggregates.append(f"{expression} AS {alias}")
    ctes += [f"interval_aggregates AS (SELECT {', '.join(dimensions + aggregates)} FROM {source} GROUP BY {', '.join(dimensions)})"]
    selections = ["calendar.calendar_date AS interval_date"]
    sources = "dashboard_dates AS calendar"
    conditions = ["calendar.calendar_date = stats.interval_date"]
    if groups:
        ctes += [f"interval_groups AS (SELECT DISTINCT {', '.join(groups)} FROM interval_events WHERE is_start = 1)"]
        sources += " CROSS JOIN interval_groups AS dimensions"
        selections += [f"dimensions.{n} AS {n}" for n in groups]
        conditions += [f"(dimensions.{n} = stats.{n} OR (dimensions.{n} IS NULL AND stats.{n} IS NULL))" for n in groups]
    for name in p.required_columns[len(dimensions):]:
        value = f"COALESCE(stats.{name}, 0)" if name in {"entity_count", "interval_count"} else f"stats.{name}"
        selections.append(f"{value} AS {name}")
    ctes += [f"interval_result AS (SELECT {', '.join(selections)} FROM {sources} LEFT JOIN interval_aggregates AS stats ON {' AND '.join(conditions)})"]
    # The error branch inherits business column types from the normal branch.
    # It remains observable when there is no dimension domain or valid pair.
    final = (f"SELECT {', '.join(p.required_columns)}, 0 AS {GUARD_COLUMN} FROM interval_result WHERE (SELECT {GUARD_COLUMN} FROM interval_guard) = 0\n"
             f"UNION ALL SELECT {', '.join('NULL AS ' + n for n in p.required_columns)}, 1 AS {GUARD_COLUMN} FROM interval_guard WHERE interval_guard.{GUARD_COLUMN} = 1\n"
             f"ORDER BY {GUARD_COLUMN} DESC, {', '.join(dimensions)}")
    return "WITH " + ",\n".join(ctes) + "\n" + final
