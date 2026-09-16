WITH dashboard_date_bounds AS (
    SELECT 
        STR_TO_DATE(CAST({{dashboard_start_yyyymmdd}} AS CHAR), '%Y%m%d') AS start_date,
        STR_TO_DATE(CAST({{dashboard_end_yyyymmdd}} AS CHAR), '%Y%m%d') AS end_date
),
cohort AS (
    SELECT DISTINCT
        STR_TO_DATE(CAST(`event`.`dt` AS CHAR), '%Y%m%d') AS cohort_date,
        `event`.`uid` AS entity_id
    FROM `event`
    WHERE `event`.`dt` >= {{dashboard_start_yyyymmdd}}
      AND `event`.`dt` <= {{dashboard_end_yyyymmdd}}
      AND `event`.`event` = 'Launch'
      AND `event`.`prod` = 110000036
),
behavior AS (
    SELECT DISTINCT
        STR_TO_DATE(CAST(`event`.`dt` AS CHAR), '%Y%m%d') AS behavior_date,
        `event`.`uid` AS entity_id
    FROM `event`
    WHERE `event`.`dt` >= {{dashboard_start_yyyymmdd}}
      AND `event`.`dt` <= {{dashboard_end_yyyymmdd}}
      AND `event`.`event` = 'UserActive'
      AND `event`.`prod` = 110000036
),
matched AS (
    SELECT 
        c.entity_id,
        c.cohort_date,
        b.behavior_date,
        DATEDIFF(b.behavior_date, c.cohort_date) AS period_offset
    FROM cohort c
    LEFT JOIN behavior b 
        ON c.entity_id = b.entity_id
        AND b.behavior_date >= c.cohort_date
        AND b.behavior_date <= DATE_ADD(c.cohort_date, INTERVAL 7 DAY)
)
SELECT 
    m.`cohort_date`,
    COUNT(DISTINCT m.`entity_id`) AS `cohort_size`,
    CASE WHEN DATE_ADD(m.`cohort_date`, INTERVAL 0 DAY) <= b.end_date
        THEN ROUND(COUNT(DISTINCT CASE WHEN m.`period_offset` = 0 THEN m.`entity_id` END) * 100.0 / NULLIF(COUNT(DISTINCT m.`entity_id`), 0), 2)
        ELSE NULL END AS `day_0`,
    CASE WHEN DATE_ADD(m.`cohort_date`, INTERVAL 1 DAY) <= b.end_date
        THEN ROUND(COUNT(DISTINCT CASE WHEN m.`period_offset` = 1 THEN m.`entity_id` END) * 100.0 / NULLIF(COUNT(DISTINCT m.`entity_id`), 0), 2)
        ELSE NULL END AS `day_1`,
    CASE WHEN DATE_ADD(m.`cohort_date`, INTERVAL 2 DAY) <= b.end_date
        THEN ROUND(COUNT(DISTINCT CASE WHEN m.`period_offset` = 2 THEN m.`entity_id` END) * 100.0 / NULLIF(COUNT(DISTINCT m.`entity_id`), 0), 2)
        ELSE NULL END AS `day_2`,
    CASE WHEN DATE_ADD(m.`cohort_date`, INTERVAL 3 DAY) <= b.end_date
        THEN ROUND(COUNT(DISTINCT CASE WHEN m.`period_offset` = 3 THEN m.`entity_id` END) * 100.0 / NULLIF(COUNT(DISTINCT m.`entity_id`), 0), 2)
        ELSE NULL END AS `day_3`,
    CASE WHEN DATE_ADD(m.`cohort_date`, INTERVAL 4 DAY) <= b.end_date
        THEN ROUND(COUNT(DISTINCT CASE WHEN m.`period_offset` = 4 THEN m.`entity_id` END) * 100.0 / NULLIF(COUNT(DISTINCT m.`entity_id`), 0), 2)
        ELSE NULL END AS `day_4`,
    CASE WHEN DATE_ADD(m.`cohort_date`, INTERVAL 5 DAY) <= b.end_date
        THEN ROUND(COUNT(DISTINCT CASE WHEN m.`period_offset` = 5 THEN m.`entity_id` END) * 100.0 / NULLIF(COUNT(DISTINCT m.`entity_id`), 0), 2)
        ELSE NULL END AS `day_5`,
    CASE WHEN DATE_ADD(m.`cohort_date`, INTERVAL 6 DAY) <= b.end_date
        THEN ROUND(COUNT(DISTINCT CASE WHEN m.`period_offset` = 6 THEN m.`entity_id` END) * 100.0 / NULLIF(COUNT(DISTINCT m.`entity_id`), 0), 2)
        ELSE NULL END AS `day_6`,
    CASE WHEN DATE_ADD(m.`cohort_date`, INTERVAL 7 DAY) <= b.end_date
        THEN ROUND(COUNT(DISTINCT CASE WHEN m.`period_offset` = 7 THEN m.`entity_id` END) * 100.0 / NULLIF(COUNT(DISTINCT m.`entity_id`), 0), 2)
        ELSE NULL END AS `day_7`
FROM matched m
CROSS JOIN dashboard_date_bounds b
GROUP BY m.`cohort_date`
ORDER BY m.`cohort_date`