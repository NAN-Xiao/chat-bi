"""Closed attribution templates: detail identities precede all target/touch joins."""
from sqlglot import exp
from apps.dashboard.crud.attribution_sql_plan import AttributionSqlPlan

GUARD_COLUMN = '__attribution_data_error'


def compile_attribution_sql(plan: AttributionSqlPlan) -> str:
    p = plan
    groups = [f"group_{i+1}" for i in range(len(p.group_sides))]
    target_groups = [g for g,s in zip(groups,p.group_sides) if s == "target"]
    touch_groups = [g for g,s in zip(groups,p.group_sides) if s == "touch"]
    keys = [*groups,"attribution_event"]
    table = exp.to_table(p.table)
    for part in table.parts: part.set("quoted", True)
    source = table.sql(dialect=p.dialect)
    literal = lambda value: exp.Literal.string(value).sql(dialect=p.dialect)
    zone = literal(p.time.business_timezone)
    # Absolute instants retain fractional seconds; only calendar conversion floors.
    local_date = f"CAST(TO_TIMESTAMP(FLOOR({p.time.instant})) AT TIME ZONE {zone} AS DATE)"
    lower = f"EXTRACT(EPOCH FROM (CAST({p.time.start_day} AS TIMESTAMP) AT TIME ZONE {zone}))"
    upper = f"EXTRACT(EPOCH FROM ((CAST({p.time.end_day} AS TIMESTAMP) + INTERVAL '1 DAY') AT TIME ZONE {zone}))"
    if p.time.parameter_type == "timestamp":
        lower = f"EXTRACT(EPOCH FROM ((SELECT range_start FROM attribution_parameter_bounds) AT TIME ZONE {zone}))"
        upper = f"EXTRACT(EPOCH FROM ((SELECT range_end FROM attribution_parameter_bounds) AT TIME ZONE {zone}))"
        if p.window_mode == "same_day":
            # For totals the first calendar day starts at midnight, even for a partial target range.
            touch_lower = f"EXTRACT(EPOCH FROM (CAST({p.time.start_day} AS TIMESTAMP) AT TIME ZONE {zone}))"
        else: touch_lower = f"({lower} - {p.window_seconds})"
    else: touch_lower = f"({lower} - {p.window_seconds})"
    if p.dialect == "mysql":
        epoch = "CAST('1970-01-01 00:00:00' AS DATETIME)"
        local_date = f"CAST(CONVERT_TZ(TIMESTAMPADD(SECOND, FLOOR({p.time.instant}), {epoch}), '+00:00', {zone}) AS DATE)"
        def seconds(value):
            return f"TIMESTAMPDIFF(SECOND, {epoch}, CONVERT_TZ(CAST({value} AS DATETIME), {zone}, '+00:00'))"
        lower = seconds(p.time.start_day)
        upper = seconds(f"DATE_ADD({p.time.end_day}, INTERVAL 1 DAY)")
        touch_lower = f"({lower} - {p.window_seconds})"

    def aggregate(value="target_value", weighted=False):
        if p.aggregation in {"count", "sum"}:
            return f"SUM({value}{' * linear_weight' if weighted else ''})"
        if p.aggregation == "count_distinct": return f"COUNT(DISTINCT {value})"
        return f"{p.aggregation.upper()}({value})"

    def match(left, right, columns):
        return " AND ".join(f"({left}.{g} = {right}.{g} OR ({left}.{g} IS NULL AND {right}.{g} IS NULL))" for g in columns) or "TRUE"

    def select(query_columns, from_sql, group_keys=()):
        return "SELECT " + ", ".join(query_columns) + " FROM " + from_sql + (" GROUP BY " + ", ".join(group_keys) if group_keys else "")

    ctes = [p.time.bounds]
    def cte(name, sql): ctes.append(f"{name} AS ({sql})")
    extension_days = (p.window_seconds + 86399) // 86400
    start_day = (f"({p.time.start_day} - INTERVAL '{extension_days} DAY')" if p.dialect == 'postgres'
                 else f"DATE_SUB({p.time.start_day}, INTERVAL {extension_days} DAY)")
    if p.time.parameter_type == 'timestamp':
        partition_predicate = f'({p.time.date}) >= {start_day} AND ({p.time.date}) <= {p.time.end_day}'
    else:
        partition_start = start_day
        if p.time.parameter_type.startswith('yyyymmdd'):
            partition_start = (f"TO_CHAR({start_day}, 'YYYYMMDD')" if p.dialect == 'postgres'
                               else f"DATE_FORMAT({start_day}, '%Y%m%d')")
            if p.time.parameter_type == 'yyyymmdd_number':
                partition_start = f"CAST({partition_start} AS {'BIGINT' if p.dialect == 'postgres' else 'SIGNED'})"
        partition_predicate = f'{p.range_field} >= {partition_start} AND {p.range_field} <= (SELECT range_end FROM attribution_parameter_bounds)'
    invalid = [select(['1 AS invalid'],f"{source} WHERE ({p.target.predicate}) AND ({p.time.predicate}) AND {p.time.raw_time} IS NULL")]
    invalid += [select(['1 AS invalid'],f"{source} WHERE ({t.predicate}) AND ({partition_predicate}) AND {p.time.raw_time} IS NULL") for t in p.touches]
    cte('invalid_times',' UNION ALL '.join(invalid))
    # Query-local IDs must sort by every value that affects matching/contribution;
    # physically identical duplicates are interchangeable, distinct rows are not.
    order = ", ".join(dict.fromkeys([p.time.instant, p.entity, *p.orders, p.metric, *p.target.groups,
                                    *(t.related_target for t in p.touches if t.related_target)]))
    target_columns = [f"ROW_NUMBER() OVER (ORDER BY {order}) AS target_id", f"{p.entity} AS entity_id",
        f"{p.time.instant} AS target_time", f"{local_date} AS target_date", f"{p.metric} AS target_value",
        *(f"{value} AS {g}" for g,value in zip(groups,p.target.groups)),
        *(f"{t.related_target or 'NULL'} AS related_{i}" for i,t in enumerate(p.touches))]
    cte("targets", select(target_columns, f"{source} WHERE ({p.target.predicate}) AND ({p.time.predicate}) AND ({p.time.instant}) >= {lower} AND ({p.time.instant}) < {upper}"))
    touch_branches = []
    for i,touch in enumerate(p.touches):
        columns = [f"{p.entity} AS entity_id", f"{p.time.instant} AS touch_time", f"{local_date} AS touch_date",
            f"{literal(touch.name)} AS attribution_event", f"{i} AS event_index",
            *(f"{touch.related_touch if i == n and touch.related_touch else 'NULL'} AS touch_related_{n}" for n in range(len(p.touches))),
            *(f"{value} AS {g}" for g,value in zip(groups,touch.groups)),
            *(f"{value} AS order_{n}" for n,value in enumerate(p.orders))]
        touch_branches.append(select(columns, f"{source} WHERE ({touch.predicate}) AND ({partition_predicate}) AND ({p.time.instant}) >= {touch_lower} AND ({p.time.instant}) < {upper}"))
    cte("touch_source", " UNION ALL ".join(touch_branches))
    touch_columns = ["entity_id", "touch_time", "touch_date", "attribution_event", "event_index", *(f"touch_related_{n}" for n in range(len(p.touches))), *groups,
                     *(f"order_{n}" for n in range(len(p.orders)))]
    touch_order = ["touch_time", "entity_id", "event_index", *(f"order_{n}" for n in range(len(p.orders))), *groups, *(f"touch_related_{n}" for n in range(len(p.touches)))]
    cte("touches", select([f"ROW_NUMBER() OVER (ORDER BY {', '.join(touch_order)}) AS touch_id", *touch_columns], "touch_source"))
    if p.method != 'linear':
        order_keys = ['entity_id','touch_time','event_index',*(f'order_{n}' for n in range(len(p.orders)))]
        cte('order_conflicts',select(order_keys,'touches',order_keys) + ' HAVING COUNT(*) > 1 OR ' + ' OR '.join(f'order_{n} IS NULL' for n in range(len(p.orders))))
        conflict = 'EXISTS (SELECT 1 FROM invalid_times) OR EXISTS (SELECT 1 FROM order_conflicts)'
    else: conflict = 'EXISTS (SELECT 1 FROM invalid_times)'
    cte('attribution_guard',f'SELECT CASE WHEN {conflict} THEN 1 ELSE 0 END AS {GUARD_COLUMN}')
    window = "tc.touch_date = t.target_date" if p.window_mode == "same_day" else f"tc.touch_time >= t.target_time - {p.window_seconds}"
    related = [f"(tc.event_index = {i} AND t.related_{i} = tc.touch_related_{i})" if touch.related_target else f"tc.event_index = {i}" for i,touch in enumerate(p.touches)]
    chosen_groups = [f"{'tc' if side == 'touch' else 't'}.{g} AS {g}" for g,side in zip(groups,p.group_sides)]
    direction = "DESC" if p.method == "last" else "ASC"
    ranks = [f"tc.touch_time {direction}", *(f"tc.order_{n} {direction}" for n in range(len(p.orders))), "tc.event_index ASC"]
    matched_columns = ["t.target_id", "t.target_time", "t.target_date", "t.target_value", "tc.touch_id", "tc.entity_id", "tc.touch_time", "tc.touch_date", "tc.attribution_event", *chosen_groups,
        "COUNT(tc.touch_id) OVER (PARTITION BY t.target_id) AS touch_count", f"ROW_NUMBER() OVER (PARTITION BY t.target_id ORDER BY {', '.join(ranks)}) AS touch_rank"]
    cte("matched", select(matched_columns, f"targets AS t JOIN touches AS tc ON t.entity_id = tc.entity_id AND tc.touch_time <= t.target_time AND {window} AND ({' OR '.join(related)})"))
    selected = ["target_id", "target_value", "touch_id", "entity_id", *keys]
    weight = "1.0 / NULLIF(touch_count, 0)" if p.method == "linear" else "1.0"
    cte("selected_touches", select([*selected, f"{weight} AS linear_weight"], "matched" + (" WHERE touch_rank = 1" if p.method != "linear" else "")))
    cte("contributions", select([*keys, "COUNT(DISTINCT target_id) AS target_count", f"{aggregate(weighted=True)} AS attributed_value"], "selected_touches", keys))
    cte("effective_touches", select([*keys, "COUNT(DISTINCT touch_id) AS effective_touch_count", "COUNT(DISTINCT entity_id) AS effective_entity_count"], "selected_touches", keys))
    if target_groups:
        cte("target_groups", select([f"DISTINCT {', '.join(target_groups)}"], "targets"))
    else: cte("target_groups", "SELECT 1 AS group_marker")
    total_keys = [*touch_groups, "attribution_event"]
    cte("touch_counts", select([*total_keys,"COUNT(DISTINCT touch_id) AS total_touch_count"], "touches", total_keys))
    cte("touches_total", select([*(f"{'t' if g in target_groups else 'tc'}.{g} AS {g}" for g in groups), "tc.attribution_event", "tc.total_touch_count"], "target_groups AS t CROSS JOIN touch_counts AS tc"))
    measures = ["target_count","total_touch_count","effective_touch_count","effective_entity_count","attributed_value"]
    output_keys = [f"s.{g} AS {g}" for g in keys]
    cte("touch_results", select([*output_keys,"COALESCE(c.target_count, 0) AS target_count", "s.total_touch_count",
        "COALESCE(e.effective_touch_count, 0) AS effective_touch_count", "COALESCE(e.effective_entity_count, 0) AS effective_entity_count",
        "CASE WHEN c.target_count IS NULL THEN 0 ELSE c.attributed_value END AS attributed_value"],
        f"touches_total AS s LEFT JOIN contributions AS c ON {match('s','c',keys)} LEFT JOIN effective_touches AS e ON {match('s','e',keys)}"))
    cte("direct_targets", select(["t.target_id","t.target_value", *(f"t.{g}" for g in target_groups)], "targets AS t WHERE NOT EXISTS (SELECT 1 FROM matched AS m WHERE m.target_id = t.target_id)"))
    complete_columns = [*keys,*measures]
    complete = select(complete_columns, "touch_results")
    if p.include_direct:
        direct_keys = [g if g in target_groups else f"NULL AS {g}" for g in groups]
        direct = select([*direct_keys, f"{literal('直接转化')} AS attribution_event", "COUNT(DISTINCT target_id) AS target_count",
            "0 AS total_touch_count", "0 AS effective_touch_count", "0 AS effective_entity_count", f"{aggregate()} AS attributed_value"], "direct_targets", target_groups)
        # An aggregate with no groups returns one empty row; do not invent a direct conversion.
        if not target_groups: direct += " HAVING COUNT(*) > 0"
        complete += " UNION ALL " + direct
    cte("complete", complete)
    eligible = "targets AS t" if p.include_direct else "targets AS t WHERE EXISTS (SELECT 1 FROM matched AS m WHERE m.target_id = t.target_id)"
    cte("eligible_targets", select(["t.target_id","t.target_value", *(f"t.{g}" for g in target_groups)], eligible))
    cte("total_value", select([*target_groups, f"{aggregate()} AS total"], "eligible_targets", target_groups))
    rate = "c.attributed_value * 100.0 / NULLIF(d.total, 0)"
    result = select([*(f"c.{g} AS {g}" for g in groups), "c.attribution_event AS attribution_event", "c.target_count AS target_count",
        "c.total_touch_count AS total_touch_count", "c.effective_touch_count AS effective_touch_count",
        "c.effective_touch_count * 100.0 / NULLIF(c.total_touch_count, 0) AS effective_touch_rate",
        "c.effective_entity_count AS effective_entity_count", "c.attributed_value AS attributed_value", f"{rate} AS contribution_rate"],
        "complete AS c LEFT JOIN total_value AS d ON " + match("c","d",target_groups))
    cte('attribution_results',result)
    result = select([*p.required_columns,f'0 AS {GUARD_COLUMN}'],f'attribution_results WHERE (SELECT {GUARD_COLUMN} FROM attribution_guard) = 0')
    result += ' UNION ALL ' + select([*(f'NULL AS {g}' for g in p.required_columns),f'1 AS {GUARD_COLUMN}'],f'attribution_guard AS guard_source WHERE guard_source.{GUARD_COLUMN} = 1')
    result += ' ORDER BY ' + ', '.join(keys)
    return "WITH " + ",\n".join(ctes) + "\n" + result
