WITH scoped_events AS (
    SELECT 
        uid,
        event,
        time,
        dt
    FROM `event`
    WHERE `dt` BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
      AND `prod` = 110000036
      AND `event` IN ('Launch', 'UserActive', 'ServerPayLog')
),
step_1 AS (
    SELECT 
        uid AS entity_id,
        MIN(`time`) AS first_step_time,
        MIN(`time`) AS step_time
    FROM scoped_events
    WHERE `event` = 'Launch'
    GROUP BY uid
),
step_2 AS (
    SELECT 
        p.entity_id,
        p.first_step_time,
        MIN(e.`time`) AS step_time
    FROM step_1 p
    INNER JOIN scoped_events e ON e.uid = p.entity_id
    WHERE e.`event` = 'UserActive'
      AND e.`time` >= p.step_time
      AND e.`time` <= p.first_step_time + 86400000
    GROUP BY p.entity_id, p.first_step_time
),
step_3 AS (
    SELECT 
        p.entity_id,
        p.first_step_time,
        MIN(e.`time`) AS step_time
    FROM step_2 p
    INNER JOIN scoped_events e ON e.uid = p.entity_id
    WHERE e.`event` = 'ServerPayLog'
      AND e.`time` >= p.step_time
      AND e.`time` <= p.first_step_time + 86400000
    GROUP BY p.entity_id, p.first_step_time
),
step_counts AS (
    SELECT 1 AS step_order, '游戏启动' AS step_name, COUNT(*) AS step_count FROM step_1
    UNION ALL
    SELECT 2 AS step_order, '当日活跃' AS step_name, COUNT(*) AS step_count FROM step_2
    UNION ALL
    SELECT 3 AS step_order, '后端充值' AS step_name, COUNT(*) AS step_count FROM step_3
),
first_step_count AS (
    SELECT step_count FROM step_counts WHERE step_order = 1
),
step_counts_with_prev AS (
    SELECT 
        sc.step_order,
        sc.step_name,
        sc.step_count,
        fsc.step_count AS first_step_count,
        prev.step_count AS prev_step_count
    FROM step_counts sc
    CROSS JOIN first_step_count fsc
    LEFT JOIN step_counts prev ON sc.step_order = prev.step_order + 1
)
SELECT 
    `step_order`,
    `step_name`,
    `step_count`,
    CASE 
        WHEN `step_order` = 1 THEN 1.0
        ELSE CAST(`step_count` AS DECIMAL(10,2)) / NULLIF(`first_step_count`, 0)
    END AS `step_rate`,
    CASE 
        WHEN `step_order` = 1 THEN NULL
        ELSE CAST(`step_count` AS DECIMAL(10,2)) / NULLIF(`prev_step_count`, 0)
    END AS `step_conversion_rate`,
    CASE 
        WHEN `step_order` = 1 THEN NULL
        ELSE (`prev_step_count` - `step_count`) * 1.0 / NULLIF(`prev_step_count`, 0)
    END AS `step_dropoff_rate`
FROM step_counts_with_prev
ORDER BY `step_order`