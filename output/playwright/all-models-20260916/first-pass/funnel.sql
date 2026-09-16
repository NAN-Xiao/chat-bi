WITH dashboard_date_bounds AS (
    SELECT STR_TO_DATE(CAST({{dashboard_start_yyyymmdd}} AS CHAR), '%Y%m%d') AS start_date, STR_TO_DATE(CAST({{dashboard_end_yyyymmdd}} AS CHAR), '%Y%m%d') AS end_date
),
scoped_events AS (
    SELECT e.uid, e.event, STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS event_date, e.dt AS dt_key
    FROM `event` e
    CROSS JOIN dashboard_date_bounds b
    WHERE e.prod = 110000036
      AND e.dt >= {{dashboard_start_yyyymmdd}}
      AND e.dt <= {{dashboard_end_yyyymmdd}}
      AND e.event IN ('Launch', 'UserActive', 'ServerPayLog')
),
step_1 AS (
    SELECT s.uid, MIN(s.event_date) AS step1_date
    FROM scoped_events s
    WHERE s.event = 'Launch'
    GROUP BY s.uid
),
step_2 AS (
    SELECT s1.uid, MIN(s2.event_date) AS step2_date
    FROM step_1 s1
    INNER JOIN scoped_events s2 ON s2.uid = s1.uid AND s2.event = 'UserActive'
    WHERE s2.event_date >= s1.step1_date
      AND DATEDIFF(s2.event_date, s1.step1_date) <= 1
    GROUP BY s1.uid
),
step_3 AS (
    SELECT s2.uid, MIN(s3.event_date) AS step3_date
    FROM step_2 s2
    INNER JOIN scoped_events s3 ON s3.uid = s2.uid AND s3.event = 'ServerPayLog'
    WHERE s3.event_date >= s2.step2_date
      AND DATEDIFF(s3.event_date, s2.step2_date) <= 1
    GROUP BY s2.uid
),
step_counts AS (
    SELECT 1 AS step_order, '游戏启动' AS step_name, COUNT(DISTINCT s1.uid) AS step_count FROM step_1 s1
    UNION ALL
    SELECT 2 AS step_order, '当日活跃' AS step_name, COUNT(DISTINCT s2.uid) AS step_count FROM step_2 s2
    UNION ALL
    SELECT 3 AS step_order, '后端充值' AS step_name, COUNT(DISTINCT s3.uid) AS step_count FROM step_3 s3
),
first_step_count AS (
    SELECT step_count AS first_count FROM step_counts WHERE step_order = 1
)
SELECT 
    sc.`step_order`,
    sc.`step_name`,
    sc.`step_count`,
    CAST(sc.`step_count` AS DECIMAL(10,4)) / NULLIF(fsc.first_count, 0) AS `step_rate`,
    CASE 
        WHEN sc.step_order = 1 THEN 1.0
        ELSE CAST(sc.`step_count` AS DECIMAL(10,4)) / NULLIF(
            (SELECT step_count FROM step_counts sc2 WHERE sc2.step_order = sc.step_order - 1), 0
        )
    END AS `step_conversion_rate`,
    CASE 
        WHEN sc.step_order = 1 THEN 0.0
        ELSE (NULLIF((SELECT step_count FROM step_counts sc2 WHERE sc2.step_order = sc.step_order - 1), 0) - sc.`step_count`) / NULLIF(
            (SELECT step_count FROM step_counts sc2 WHERE sc2.step_order = sc.step_order - 1), 0
        )
    END AS `step_dropoff_rate`
FROM step_counts sc
CROSS JOIN first_step_count fsc
ORDER BY sc.step_order