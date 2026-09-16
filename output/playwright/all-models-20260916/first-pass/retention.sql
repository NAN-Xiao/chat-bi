WITH bounds AS (
    SELECT STR_TO_DATE(CAST({{dashboard_start_yyyymmdd}} AS CHAR), '%Y%m%d') AS start_date, STR_TO_DATE(CAST({{dashboard_end_yyyymmdd}} AS CHAR), '%Y%m%d') AS end_date
),
cohort AS (
    SELECT DISTINCT `uid` AS entity_id, STR_TO_DATE(CAST(`dt` AS CHAR), '%Y%m%d') AS cohort_date
    FROM `event`
    WHERE `dt` >= {{dashboard_start_yyyymmdd}} AND `dt` <= {{dashboard_end_yyyymmdd}}
      AND `event` = 'Launch'
      AND `prod` = 110000036
),
behavior AS (
    SELECT DISTINCT `uid` AS entity_id, STR_TO_DATE(CAST(`dt` AS CHAR), '%Y%m%d') AS behavior_date
    FROM `event`
    WHERE `dt` >= {{dashboard_start_yyyymmdd}} AND `dt` <= {{dashboard_end_yyyymmdd}}
      AND `event` = 'UserActive'
      AND `prod` = 110000036
),
matched AS (
    SELECT c.entity_id, c.cohort_date, b.behavior_date,
           DATEDIFF(b.behavior_date, c.cohort_date) AS period_offset
    FROM cohort c
    LEFT JOIN behavior b ON c.entity_id = b.entity_id
      AND b.behavior_date >= c.cohort_date
      AND b.behavior_date <= DATE_ADD(c.cohort_date, INTERVAL 7 DAY)
)
SELECT
    `cohort_date`,
    COUNT(DISTINCT entity_id) AS `cohort_size`,
    ROUND(COUNT(DISTINCT CASE WHEN period_offset = 0 THEN entity_id END) * 100.0 / NULLIF(COUNT(DISTINCT entity_id), 0), 2) AS `day_0`,
    ROUND(COUNT(DISTINCT CASE WHEN period_offset = 1 THEN entity_id END) * 100.0 / NULLIF(COUNT(DISTINCT entity_id), 0), 2) AS `day_1`,
    ROUND(COUNT(DISTINCT CASE WHEN period_offset = 2 THEN entity_id END) * 100.0 / NULLIF(COUNT(DISTINCT entity_id), 0), 2) AS `day_2`,
    ROUND(COUNT(DISTINCT CASE WHEN period_offset = 3 THEN entity_id END) * 100.0 / NULLIF(COUNT(DISTINCT entity_id), 0), 2) AS `day_3`,
    ROUND(COUNT(DISTINCT CASE WHEN period_offset = 4 THEN entity_id END) * 100.0 / NULLIF(COUNT(DISTINCT entity_id), 0), 2) AS `day_4`,
    ROUND(COUNT(DISTINCT CASE WHEN period_offset = 5 THEN entity_id END) * 100.0 / NULLIF(COUNT(DISTINCT entity_id), 0), 2) AS `day_5`,
    ROUND(COUNT(DISTINCT CASE WHEN period_offset = 6 THEN entity_id END) * 100.0 / NULLIF(COUNT(DISTINCT entity_id), 0), 2) AS `day_6`,
    ROUND(COUNT(DISTINCT CASE WHEN period_offset = 7 THEN entity_id END) * 100.0 / NULLIF(COUNT(DISTINCT entity_id), 0), 2) AS `day_7`
FROM matched
GROUP BY `cohort_date`
ORDER BY `cohort_date`