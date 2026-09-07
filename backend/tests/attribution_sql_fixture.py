def attribution_sql(method="linear", mode="same_day", include_direct=True, grouped=False, count_style="window",
                    target_value="1", window_value=7, window_unit="DAY", start=None, end=None, related=False):
    boundary = "t.target_date = tc.touch_date" if mode == "same_day" else f"tc.touch_time >= t.target_time - INTERVAL {window_value} {window_unit}"
    join = "LEFT JOIN" if include_direct else "JOIN"
    ordering = "DESC" if method == "last" else "ASC"
    weight = "1.0 / NULLIF(touch_count, 0)" if method == "linear" else "1.0"
    selection = "" if method == "linear" else "WHERE touch_rank = 1"
    group_select = "group_1, " if grouped else ""
    group_by = "group_1, " if grouped else ""
    partition = "PARTITION BY group_1" if grouped else ""
    query = f"""
WITH targets AS (
    SELECT event_id AS target_id, actor AS entity_id, occurred_at AS target_time,
           DATE(occurred_at) AS target_date, {target_value} AS target_value, channel AS group_1
           {", session_id AS target_related" if related else ""}
    FROM events WHERE kind = 'conversion'
    {f"AND occurred_at >= '{start}' AND occurred_at < '{end}'" if start else ""}
), touches AS (
    SELECT event_id AS touch_id, actor AS entity_id, occurred_at AS touch_time,
           DATE(occurred_at) AS touch_date, kind AS attribution_event
           {", session_id AS touch_related" if related else ""}
    FROM events WHERE kind IN ('email', 'search')
    {f"AND occurred_at >= '{start}' - INTERVAL {window_value} {window_unit} AND occurred_at < '{end}'" if start and mode != "same_day" else ""}
), matched AS (
    SELECT t.target_id, tc.entity_id, t.target_time, t.target_date, t.target_value,
           tc.touch_id,
           t.group_1, tc.touch_time, tc.touch_date, tc.attribution_event,
           COUNT(tc.touch_time) OVER (PARTITION BY t.target_id) AS touch_count,
           ROW_NUMBER() OVER (PARTITION BY t.target_id ORDER BY tc.touch_time {ordering}, tc.attribution_event) AS touch_rank
    FROM targets t {join} touches tc
      ON t.entity_id = tc.entity_id AND tc.touch_time <= t.target_time
     AND {boundary}
     {"AND t.target_related = tc.touch_related" if related else ""}
), weighted AS (
    SELECT target_id, target_value, group_1,
           touch_id, entity_id,
           COALESCE(attribution_event, 'direct') AS attribution_event,
           CASE WHEN touch_count = 0 THEN 1.0 ELSE {weight} END AS linear_weight
    FROM matched {selection}
), aggregated AS (
    SELECT {group_select}attribution_event, COUNT(DISTINCT target_id) AS target_count,
           SUM(target_value * linear_weight) AS attributed_value,
           COUNT(DISTINCT touch_id) AS effective_touch_count,
           COUNT(DISTINCT entity_id) AS effective_entity_count
    FROM weighted GROUP BY {group_by}attribution_event
), touches_total AS (
    SELECT {group_select}attribution_event, COUNT(DISTINCT touch_id) AS total_touch_count
    FROM touches {"CROSS JOIN (SELECT DISTINCT group_1 FROM targets) g" if grouped else ""}
    GROUP BY {group_by}attribution_event
), complete AS (
    SELECT {"s.group_1," if grouped else ""} s.attribution_event,
           COALESCE(a.target_count, 0) AS target_count,
           COALESCE(a.attributed_value, 0) AS attributed_value,
           s.total_touch_count,
           COALESCE(a.effective_touch_count, 0) AS effective_touch_count,
           COALESCE(a.effective_entity_count, 0) AS effective_entity_count
    FROM touches_total s LEFT JOIN aggregated a ON s.attribution_event = a.attribution_event
    {"AND (s.group_1 = a.group_1 OR (s.group_1 IS NULL AND a.group_1 IS NULL))" if grouped else ""}
    UNION ALL
    SELECT {group_select}attribution_event, target_count, attributed_value,
           0 AS total_touch_count, effective_touch_count, effective_entity_count
    FROM aggregated WHERE attribution_event = 'direct'
)
SELECT {group_select}attribution_event, target_count, attributed_value,
       attributed_value * 100.0 / NULLIF(SUM(attributed_value) OVER ({partition}), 0) AS contribution_rate,
       total_touch_count, effective_touch_count,
       effective_touch_count * 100.0 / NULLIF(total_touch_count, 0) AS effective_touch_rate,
       effective_entity_count
FROM complete
"""
    if count_style == "grouped":
        query = query.replace(
            "COUNT(tc.touch_time) OVER (PARTITION BY t.target_id) AS touch_count,",
            "",
        ).replace(
            "), weighted AS (",
            "), counts AS (SELECT target_id, COUNT(touch_time) AS hits FROM matched GROUP BY target_id), weighted AS (",
        ).replace(
            "SELECT target_id, target_value, group_1,",
            "SELECT m.target_id, m.target_value, m.group_1,",
        ).replace("touch_count =", "c.hits =").replace("NULLIF(touch_count,", "NULLIF(c.hits,").replace(
            "\n    FROM matched " + selection + "\n",
            "\n    FROM matched m JOIN counts c ON m.target_id = c.target_id " + selection + "\n",
        )
    elif count_style == "inline":
        query = query.replace("1.0 / NULLIF(touch_count, 0)", "1.0 / NULLIF(COUNT(touch_time) OVER (PARTITION BY target_id), 0)")
    return query
