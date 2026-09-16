"""Small, executable funnel queries with independently mutable timing predicates."""

def funnel_sql(*, time="e.occurred_at", order="e.event_time >= p.step_time",
               bound="e.event_time - p.first_step_time <= 86400", third_bound=None):
    return f"""
WITH scoped_events AS (
    SELECT e.uid AS entity_id, e.action, {time} AS event_time FROM events e
), step_1 AS (
    SELECT entity_id, MIN(event_time) AS first_step_time, MIN(event_time) AS step_time
    FROM scoped_events WHERE action = 'begin' GROUP BY entity_id
), step_2 AS (
    SELECT p.entity_id, p.first_step_time, MIN(e.event_time) AS step_time
    FROM step_1 p JOIN scoped_events e ON e.entity_id = p.entity_id
    WHERE e.action = 'middle' AND {order} AND {bound}
    GROUP BY p.entity_id, p.first_step_time
), step_3 AS (
    SELECT p.entity_id, p.first_step_time, MIN(e.event_time) AS step_time
    FROM step_2 p JOIN scoped_events e ON e.entity_id = p.entity_id
    WHERE e.action = 'finish' AND {order} AND {third_bound or bound}
    GROUP BY p.entity_id, p.first_step_time
), step_counts AS (
    SELECT 1 AS step_order, 'begin' AS step_name, COUNT(DISTINCT entity_id) AS step_count FROM step_1
    UNION ALL SELECT 2, 'middle', COUNT(DISTINCT entity_id) FROM step_2
    UNION ALL SELECT 3, 'finish', COUNT(DISTINCT entity_id) FROM step_3
)
SELECT step_order, step_name, step_count,
       step_count * 1.0 / NULLIF(MAX(step_count) OVER (), 0) AS step_rate,
       CASE WHEN step_order = 1 THEN 1 ELSE step_count * 1.0 / NULLIF(LAG(step_count) OVER (ORDER BY step_order), 0) END AS step_conversion_rate,
       CASE WHEN step_order = 1 THEN 0 ELSE 1 - step_count * 1.0 / NULLIF(LAG(step_count) OVER (ORDER BY step_order), 0) END AS step_dropoff_rate
FROM step_counts ORDER BY step_order
"""
