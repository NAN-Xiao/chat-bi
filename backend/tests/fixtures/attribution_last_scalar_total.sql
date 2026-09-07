WITH bounds AS (
  SELECT
    CAST({{dashboard_start_yyyymmdd}} AS SIGNED) AS start_dt,
    CAST({{dashboard_end_yyyymmdd}} AS SIGNED) AS end_dt
),
targets AS (
  SELECT
    e.event_id AS target_id,
    e.user_id AS entity_id,
    e.occurred_at AS target_time,
    STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS target_date,
    1 AS target_value
  FROM event e
  CROSS JOIN bounds b
  WHERE e.event_name = 'purchase'
    AND e.dt >= b.start_dt
    AND e.dt <= b.end_dt
),
touches AS (
  SELECT
    e.event_id AS touch_id,
    e.user_id AS entity_id,
    e.occurred_at AS touch_time,
    STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS touch_date,
    'login' AS attribution_event
  FROM event e
  CROSS JOIN bounds b
  WHERE e.event_name = 'login'
    AND e.dt >= b.start_dt
    AND e.dt <= b.end_dt
),
matched AS (
  SELECT
    t.target_id,
    t.entity_id,
    t.target_time,
    t.target_date,
    t.target_value,
    tc.touch_id,
    tc.touch_time,
    tc.touch_date,
    tc.attribution_event
  FROM targets t
  JOIN touches tc
    ON t.entity_id = tc.entity_id
   AND tc.touch_date = t.target_date
   AND tc.touch_time <= t.target_time
),
ranked_touches AS (
  SELECT
    m.target_id,
    m.entity_id,
    m.target_time,
    m.target_date,
    m.target_value,
    m.touch_id,
    m.touch_time,
    m.touch_date,
    m.attribution_event,
    ROW_NUMBER() OVER (PARTITION BY m.target_id ORDER BY m.touch_time DESC) AS touch_rank
  FROM matched m
),
selected_touches AS (
  SELECT
    target_id,
    entity_id,
    target_time,
    target_date,
    target_value,
    touch_id,
    touch_time,
    touch_date,
    attribution_event
  FROM ranked_touches
  WHERE touch_rank = 1
),
contributions AS (
  SELECT
    attribution_event,
    COUNT(DISTINCT target_id) AS target_count,
    SUM(target_value) AS attributed_value
  FROM selected_touches
  GROUP BY attribution_event
),
touches_total AS (
  SELECT
    attribution_event,
    COUNT(DISTINCT touch_id) AS total_touch_count
  FROM touches
  GROUP BY attribution_event
),
effective_touches AS (
  SELECT
    attribution_event,
    COUNT(DISTINCT touch_id) AS effective_touch_count,
    COUNT(DISTINCT entity_id) AS effective_entity_count
  FROM selected_touches
  GROUP BY attribution_event
),
direct_targets AS (
  SELECT
    t.target_id,
    t.target_value
  FROM targets t
  LEFT JOIN matched m ON t.target_id = m.target_id
  WHERE m.target_id IS NULL
),
direct_contribution AS (
  SELECT
    '直接转化' AS attribution_event,
    COUNT(DISTINCT target_id) AS target_count,
    SUM(target_value) AS attributed_value
  FROM direct_targets
),
all_contributions AS (
  SELECT attribution_event, target_count, attributed_value FROM contributions
  UNION ALL
  SELECT attribution_event, target_count, attributed_value FROM direct_contribution
),
total_value AS (
  SELECT SUM(attributed_value) AS grand_total FROM all_contributions
),
touch_stats_base AS (
  SELECT
    tt.attribution_event,
    tt.total_touch_count,
    COALESCE(et.effective_touch_count, 0) AS effective_touch_count,
    COALESCE(et.effective_entity_count, 0) AS effective_entity_count,
    COALESCE(ac.target_count, 0) AS target_count,
    COALESCE(ac.attributed_value, 0) AS attributed_value
  FROM touches_total tt
  LEFT JOIN effective_touches et ON tt.attribution_event = et.attribution_event
  LEFT JOIN all_contributions ac ON tt.attribution_event = ac.attribution_event
),
final_result AS (
  SELECT
    ts.attribution_event,
    ts.target_count,
    ts.total_touch_count,
    ts.effective_touch_count,
    CASE
      WHEN ts.total_touch_count > 0 THEN ROUND(ts.effective_touch_count * 100.0 / NULLIF(ts.total_touch_count, 0), 2)
      ELSE NULL
    END AS effective_touch_rate,
    ts.effective_entity_count,
    ts.attributed_value,
    ROUND(ts.attributed_value * 100.0 / NULLIF((SELECT grand_total FROM total_value), 0), 2) AS contribution_rate
  FROM touch_stats_base ts
  UNION ALL
  SELECT
    dc.attribution_event,
    dc.target_count,
    0 AS total_touch_count,
    0 AS effective_touch_count,
    NULL AS effective_touch_rate,
    0 AS effective_entity_count,
    dc.attributed_value,
    ROUND(dc.attributed_value * 100.0 / NULLIF((SELECT grand_total FROM total_value), 0), 2) AS contribution_rate
  FROM direct_contribution dc
  WHERE EXISTS (SELECT 1 FROM direct_targets)
)
SELECT
  attribution_event,
  target_count,
  total_touch_count,
  effective_touch_count,
  effective_touch_rate,
  effective_entity_count,
  attributed_value,
  contribution_rate
FROM final_result
ORDER BY attribution_event
