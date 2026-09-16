WITH dashboard_date_bounds AS (
    SELECT STR_TO_DATE(CAST({{dashboard_start_yyyymmdd}} AS CHAR), '%Y%m%d') AS start_date, STR_TO_DATE(CAST({{dashboard_end_yyyymmdd}} AS CHAR), '%Y%m%d') AS end_date
),
dashboard_date_span AS (
    SELECT b.start_date, DATEDIFF(b.end_date, b.start_date) AS day_count
    FROM dashboard_date_bounds AS b
),
dashboard_digits AS (
    SELECT 0 AS n UNION ALL SELECT 1 AS n UNION ALL SELECT 2 AS n UNION ALL SELECT 3 AS n UNION ALL SELECT 4 AS n UNION ALL SELECT 5 AS n UNION ALL SELECT 6 AS n UNION ALL SELECT 7 AS n UNION ALL SELECT 8 AS n UNION ALL SELECT 9 AS n
),
dashboard_offsets_0 AS (
    SELECT b.start_date, b.day_count, d.n
    FROM dashboard_date_span AS b CROSS JOIN dashboard_digits AS d
    WHERE d.n <= b.day_count
),
dashboard_offsets_1 AS (
    SELECT p.start_date, p.day_count, p.n + d.n * 10 AS n
    FROM dashboard_offsets_0 AS p CROSS JOIN dashboard_digits AS d
    WHERE p.n + d.n * 10 <= p.day_count
),
dashboard_offsets_2 AS (
    SELECT p.start_date, p.day_count, p.n + d.n * 100 AS n
    FROM dashboard_offsets_1 AS p CROSS JOIN dashboard_digits AS d
    WHERE p.n + d.n * 100 <= p.day_count
),
dashboard_offsets_3 AS (
    SELECT p.start_date, p.day_count, p.n + d.n * 1000 AS n
    FROM dashboard_offsets_2 AS p CROSS JOIN dashboard_digits AS d
    WHERE p.n + d.n * 1000 <= p.day_count
),
dashboard_offsets_4 AS (
    SELECT p.start_date, p.day_count, p.n + d.n * 10000 AS n
    FROM dashboard_offsets_3 AS p CROSS JOIN dashboard_digits AS d
    WHERE p.n + d.n * 10000 <= p.day_count
),
dashboard_offsets_5 AS (
    SELECT p.start_date, p.day_count, p.n + d.n * 100000 AS n
    FROM dashboard_offsets_4 AS p CROSS JOIN dashboard_digits AS d
    WHERE p.n + d.n * 100000 <= p.day_count
),
dashboard_offsets_6 AS (
    SELECT p.start_date, p.day_count, p.n + d.n * 1000000 AS n
    FROM dashboard_offsets_5 AS p CROSS JOIN dashboard_digits AS d
    WHERE p.n + d.n * 1000000 <= p.day_count
),
dashboard_dates AS (
    SELECT DATE_ADD(p.start_date, INTERVAL p.n DAY) AS calendar_date
    FROM dashboard_offsets_6 AS p
),
targets AS (
    SELECT 
        ROW_NUMBER() OVER (ORDER BY e.uid, e.dt, e.time) AS target_id,
        e.uid AS entity_id,
        e.time AS target_time,
        STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS target_date,
        1 AS target_value
    FROM event AS e
    WHERE e.event = 'ServerPayLog'
      AND e.prod = 110000036
      AND e.dt >= {{dashboard_start_yyyymmdd}}
      AND e.dt <= {{dashboard_end_yyyymmdd}}
),
touches AS (
    SELECT 
        ROW_NUMBER() OVER (ORDER BY e.uid, e.dt, e.time) AS touch_id,
        e.uid AS entity_id,
        e.time AS touch_time,
        STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS touch_date,
        'Launch' AS attribution_event
    FROM event AS e
    WHERE e.event = 'Launch'
      AND e.prod = 110000036
      AND e.dt >= {{dashboard_start_yyyymmdd}}
      AND e.dt <= {{dashboard_end_yyyymmdd}}
),
matched AS (
    SELECT 
        t.target_id,
        tc.touch_id,
        tc.entity_id,
        t.target_time,
        t.target_date,
        tc.touch_time,
        tc.touch_date,
        t.target_value,
        tc.attribution_event
    FROM targets AS t
    LEFT JOIN touches AS tc
        ON tc.entity_id = t.entity_id
        AND tc.touch_date = t.target_date
        AND tc.touch_time <= t.target_time
),
weighted AS (
    SELECT 
        m.target_id,
        m.touch_id,
        m.entity_id,
        m.target_time,
        m.target_date,
        m.touch_time,
        m.touch_date,
        m.target_value,
        m.attribution_event,
        CASE WHEN m.touch_id IS NOT NULL THEN 1.0 / NULLIF(COUNT(m.touch_id) OVER (PARTITION BY m.target_id), 0) ELSE NULL END AS linear_weight
    FROM matched AS m
),
touches_total AS (
    SELECT 
        attribution_event,
        COUNT(DISTINCT touch_id) AS total_touch_count
    FROM touches
    GROUP BY attribution_event
),
selected_touches AS (
    SELECT 
        target_id,
        touch_id,
        entity_id,
        target_time,
        target_date,
        touch_time,
        touch_date,
        target_value,
        attribution_event,
        linear_weight
    FROM weighted
    WHERE touch_id IS NOT NULL
),
effective_touches AS (
    SELECT 
        attribution_event,
        COUNT(DISTINCT touch_id) AS effective_touch_count,
        COUNT(DISTINCT entity_id) AS effective_entity_count
    FROM selected_touches
    GROUP BY attribution_event
),
contributions AS (
    SELECT 
        attribution_event,
        COUNT(DISTINCT target_id) AS target_count,
        SUM(target_value * linear_weight) AS attributed_value
    FROM selected_touches
    GROUP BY attribution_event
),
direct_targets AS (
    SELECT 
        t.target_id,
        t.entity_id,
        t.target_time,
        t.target_date,
        t.target_value
    FROM targets AS t
    LEFT JOIN matched AS m ON m.target_id = t.target_id AND m.touch_id IS NOT NULL
    WHERE m.target_id IS NULL
),
direct_contribution AS (
    SELECT 
        '直接转化' AS attribution_event,
        COUNT(DISTINCT target_id) AS target_count,
        SUM(target_value) AS attributed_value
    FROM direct_targets
),
touch_results AS (
    SELECT 
        s.attribution_event,
        COALESCE(c.target_count, 0) AS target_count,
        s.total_touch_count,
        COALESCE(e.effective_touch_count, 0) AS effective_touch_count,
        COALESCE(e.effective_entity_count, 0) AS effective_entity_count,
        COALESCE(c.attributed_value, 0) AS attributed_value
    FROM touches_total AS s
    LEFT JOIN contributions AS c ON s.attribution_event = c.attribution_event
    LEFT JOIN effective_touches AS e ON s.attribution_event = e.attribution_event
),
complete AS (
    SELECT 
        attribution_event,
        target_count,
        total_touch_count,
        effective_touch_count,
        effective_entity_count,
        attributed_value
    FROM touch_results
    UNION ALL
    SELECT 
        d.attribution_event,
        d.target_count,
        0 AS total_touch_count,
        0 AS effective_touch_count,
        0 AS effective_entity_count,
        d.attributed_value
    FROM direct_contribution AS d
),
total_value AS (
    SELECT SUM(attributed_value) AS total FROM complete
)
SELECT 
    c.attribution_event AS `attribution_event`,
    c.target_count AS `target_count`,
    c.total_touch_count AS `total_touch_count`,
    c.effective_touch_count AS `effective_touch_count`,
    c.effective_touch_count * 100.0 / NULLIF(c.total_touch_count, 0) AS `effective_touch_rate`,
    c.effective_entity_count AS `effective_entity_count`,
    c.attributed_value AS `attributed_value`,
    c.attributed_value * 100.0 / NULLIF((SELECT total FROM total_value), 0) AS `contribution_rate`
FROM complete AS c
ORDER BY c.attribution_event