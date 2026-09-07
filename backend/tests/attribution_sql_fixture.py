def attribution_sql(method="linear", mode="same_day", include_direct=True, grouped=False):
    boundary = "t.target_date = tc.touch_date" if mode == "same_day" else "tc.touch_time >= t.target_time - INTERVAL 7 DAY"
    join = "LEFT JOIN" if include_direct else "JOIN"
    ordering = "DESC" if method == "last" else "ASC"
    weight = "1.0 / NULLIF(touch_count, 0)" if method == "linear" else "1.0"
    selection = "" if method == "linear" else "WHERE touch_rank = 1"
    group_select = "group_1, " if grouped else ""
    group_by = "group_1, " if grouped else ""
    partition = "PARTITION BY group_1" if grouped else ""
    return f"""
WITH targets AS (
    SELECT event_id AS target_id, actor AS entity_id, occurred_at AS target_time,
           DATE(occurred_at) AS target_date, 1 AS target_value, channel AS group_1
    FROM events WHERE kind = 'conversion'
), touches AS (
    SELECT actor AS entity_id, occurred_at AS touch_time,
           DATE(occurred_at) AS touch_date, kind AS attribution_event
    FROM events WHERE kind IN ('email', 'search')
), matched AS (
    SELECT t.target_id, t.entity_id, t.target_time, t.target_date, t.target_value,
           t.group_1, tc.touch_time, tc.touch_date, tc.attribution_event,
           COUNT(tc.touch_time) OVER (PARTITION BY t.target_id) AS touch_count,
           ROW_NUMBER() OVER (PARTITION BY t.target_id ORDER BY tc.touch_time {ordering}, tc.attribution_event) AS touch_rank
    FROM targets t {join} touches tc
      ON t.entity_id = tc.entity_id AND tc.touch_time <= t.target_time
     AND {boundary}
), weighted AS (
    SELECT target_id, target_value, group_1,
           COALESCE(attribution_event, 'direct') AS attribution_event,
           CASE WHEN touch_count = 0 THEN 1.0 ELSE {weight} END AS linear_weight
    FROM matched {selection}
), aggregated AS (
    SELECT {group_select}attribution_event, COUNT(DISTINCT target_id) AS target_count,
           SUM(target_value * linear_weight) AS attributed_value
    FROM weighted GROUP BY {group_by}attribution_event
)
SELECT {group_select}attribution_event, target_count, attributed_value,
       attributed_value * 100.0 / NULLIF(SUM(attributed_value) OVER ({partition}), 0) AS contribution_rate
FROM aggregated
"""
