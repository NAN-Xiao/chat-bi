WITH dashboard_date_bounds AS (
    SELECT STR_TO_DATE(CAST({{dashboard_start_yyyymmdd}} AS CHAR), '%Y%m%d') AS start_date,
           STR_TO_DATE(CAST({{dashboard_end_yyyymmdd}} AS CHAR), '%Y%m%d') AS end_date
),
dashboard_date_span AS (
    SELECT b.start_date, DATEDIFF(b.end_date, b.start_date) AS day_count
    FROM dashboard_date_bounds AS b
),
dashboard_digits AS (
    SELECT 0 AS n UNION ALL SELECT 1 AS n UNION ALL SELECT 2 AS n UNION ALL SELECT 3 AS n UNION ALL SELECT 4 AS n
    UNION ALL SELECT 5 AS n UNION ALL SELECT 6 AS n UNION ALL SELECT 7 AS n UNION ALL SELECT 8 AS n UNION ALL SELECT 9 AS n
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
dashboard_dates AS (
    SELECT DATE_ADD(p.start_date, INTERVAL p.n DAY) AS calendar_date
    FROM dashboard_offsets_2 AS p
),
cohort AS (
    SELECT STR_TO_DATE(CAST(`e`.`dt` AS CHAR), '%Y%m%d') AS cohort_date,
           `e`.`uid` AS entity_id
    FROM `event` AS `e`
    WHERE `e`.`event` = 'Launch'
      AND `e`.`dt` >= {{dashboard_start_yyyymmdd}}
      AND `e`.`dt` <= {{dashboard_end_yyyymmdd}}
      AND `e`.`prod` = 110000036
),
cohort_base AS (
    SELECT cohort_date,
           COUNT(DISTINCT entity_id) AS cohort_size
    FROM cohort
    GROUP BY cohort_date
),
payment_events AS (
    SELECT STR_TO_DATE(CAST(`e`.`dt` AS CHAR), '%Y%m%d') AS payment_date,
           `e`.`uid` AS entity_id,
           CAST(JSON_UNQUOTE(JSON_EXTRACT(`e`.`personal`, '$.money')) AS DECIMAL(18,2)) AS payment_amount
    FROM `event` AS `e`
    WHERE `e`.`event` = 'ServerPayLog'
      AND `e`.`dt` >= {{dashboard_start_yyyymmdd}}
      AND `e`.`dt` <= {{dashboard_end_yyyymmdd}}
      AND `e`.`prod` = 110000036
),
matched AS (
    SELECT c.cohort_date,
           c.entity_id,
           p.payment_date,
           p.payment_amount,
           DATEDIFF(p.payment_date, c.cohort_date) AS day_offset
    FROM cohort AS c
    INNER JOIN payment_events AS p
        ON c.entity_id = p.entity_id
        AND p.payment_date >= c.cohort_date
        AND p.payment_date <= DATE_ADD(c.cohort_date, INTERVAL 7 DAY)
),
daily_values AS (
    SELECT cohort_date,
           day_offset,
           SUM(COALESCE(payment_amount, 0)) AS daily_revenue
    FROM matched
    GROUP BY cohort_date, day_offset
),
cohort_with_size AS (
    SELECT cb.cohort_date,
           cb.cohort_size,
           dv.day_offset,
           dv.daily_revenue
    FROM cohort_base AS cb
    LEFT JOIN daily_values AS dv
        ON cb.cohort_date = dv.cohort_date
),
observation_end AS (
    SELECT STR_TO_DATE(CAST({{dashboard_end_yyyymmdd}} AS CHAR), '%Y%m%d') AS obs_end_date
)
SELECT 
    `cohort_with_size`.`cohort_date`,
    `cohort_with_size`.`cohort_size`,
    CASE WHEN DATE_ADD(`cohort_with_size`.`cohort_date`, INTERVAL 0 DAY) <= `observation_end`.`obs_end_date`
         THEN COALESCE(SUM(CASE WHEN `cohort_with_size`.`day_offset` = 0 THEN `cohort_with_size`.`daily_revenue` ELSE 0 END), 0)
         ELSE NULL END AS `day_0`,
    CASE WHEN DATE_ADD(`cohort_with_size`.`cohort_date`, INTERVAL 1 DAY) <= `observation_end`.`obs_end_date`
         THEN COALESCE(SUM(CASE WHEN `cohort_with_size`.`day_offset` = 1 THEN `cohort_with_size`.`daily_revenue` ELSE 0 END), 0)
         ELSE NULL END AS `day_1`,
    CASE WHEN DATE_ADD(`cohort_with_size`.`cohort_date`, INTERVAL 2 DAY) <= `observation_end`.`obs_end_date`
         THEN COALESCE(SUM(CASE WHEN `cohort_with_size`.`day_offset` = 2 THEN `cohort_with_size`.`daily_revenue` ELSE 0 END), 0)
         ELSE NULL END AS `day_2`,
    CASE WHEN DATE_ADD(`cohort_with_size`.`cohort_date`, INTERVAL 3 DAY) <= `observation_end`.`obs_end_date`
         THEN COALESCE(SUM(CASE WHEN `cohort_with_size`.`day_offset` = 3 THEN `cohort_with_size`.`daily_revenue` ELSE 0 END), 0)
         ELSE NULL END AS `day_3`,
    CASE WHEN DATE_ADD(`cohort_with_size`.`cohort_date`, INTERVAL 4 DAY) <= `observation_end`.`obs_end_date`
         THEN COALESCE(SUM(CASE WHEN `cohort_with_size`.`day_offset` = 4 THEN `cohort_with_size`.`daily_revenue` ELSE 0 END), 0)
         ELSE NULL END AS `day_4`,
    CASE WHEN DATE_ADD(`cohort_with_size`.`cohort_date`, INTERVAL 5 DAY) <= `observation_end`.`obs_end_date`
         THEN COALESCE(SUM(CASE WHEN `cohort_with_size`.`day_offset` = 5 THEN `cohort_with_size`.`daily_revenue` ELSE 0 END), 0)
         ELSE NULL END AS `day_5`,
    CASE WHEN DATE_ADD(`cohort_with_size`.`cohort_date`, INTERVAL 6 DAY) <= `observation_end`.`obs_end_date`
         THEN COALESCE(SUM(CASE WHEN `cohort_with_size`.`day_offset` = 6 THEN `cohort_with_size`.`daily_revenue` ELSE 0 END), 0)
         ELSE NULL END AS `day_6`,
    CASE WHEN DATE_ADD(`cohort_with_size`.`cohort_date`, INTERVAL 7 DAY) <= `observation_end`.`obs_end_date`
         THEN COALESCE(SUM(CASE WHEN `cohort_with_size`.`day_offset` = 7 THEN `cohort_with_size`.`daily_revenue` ELSE 0 END), 0)
         ELSE NULL END AS `day_7`
FROM `cohort_with_size`
CROSS JOIN `observation_end`
GROUP BY `cohort_with_size`.`cohort_date`, `cohort_with_size`.`cohort_size`, `observation_end`.`obs_end_date`
ORDER BY `cohort_with_size`.`cohort_date`