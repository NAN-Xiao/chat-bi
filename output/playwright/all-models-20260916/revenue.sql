WITH dashboard_date_bounds AS (
    SELECT STR_TO_DATE(CAST({{dashboard_start_yyyymmdd}} AS CHAR), '%Y%m%d') AS start_date, STR_TO_DATE(CAST({{dashboard_end_yyyymmdd}} AS CHAR), '%Y%m%d') AS end_date
),
cohort AS (
    SELECT DISTINCT
        STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS cohort_date,
        e.uid AS entity_id
    FROM `event` AS e
    WHERE e.event = 'Launch'
      AND e.prod = 110000036
      AND e.dt >= {{dashboard_start_yyyymmdd}}
      AND e.dt <= {{dashboard_end_yyyymmdd}}
),
cohort_size AS (
    SELECT cohort_date, COUNT(DISTINCT entity_id) AS cohort_size
    FROM cohort
    GROUP BY cohort_date
),
payment_events AS (
    SELECT
        e.uid AS entity_id,
        STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS payment_date,
        CAST(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.money')) AS DECIMAL(18,2)) AS money
    FROM `event` AS e
    WHERE e.event = 'ServerPayLog'
      AND e.prod = 110000036
      AND e.dt >= {{dashboard_start_yyyymmdd}}
      AND e.dt <= {{dashboard_end_yyyymmdd}}
),
matched AS (
    SELECT
        c.cohort_date,
        c.entity_id,
        p.payment_date,
        p.money,
        DATEDIFF(p.payment_date, c.cohort_date) AS day_offset
    FROM cohort AS c
    INNER JOIN payment_events AS p ON c.entity_id = p.entity_id
    WHERE p.payment_date >= c.cohort_date
      AND DATEDIFF(p.payment_date, c.cohort_date) BETWEEN 0 AND 7
),
daily_values AS (
    SELECT
        cohort_date,
        day_offset,
        SUM(money) AS day_amount
    FROM matched
    GROUP BY cohort_date, day_offset
)
SELECT
    cs.cohort_date,
    cs.cohort_size,
    CASE WHEN DATE_ADD(cs.cohort_date, INTERVAL 0 DAY) <= b.end_date THEN COALESCE(SUM(CASE WHEN dv.day_offset = 0 THEN dv.day_amount END), 0) ELSE NULL END AS `day_0`,
    CASE WHEN DATE_ADD(cs.cohort_date, INTERVAL 1 DAY) <= b.end_date THEN COALESCE(SUM(CASE WHEN dv.day_offset = 1 THEN dv.day_amount END), 0) ELSE NULL END AS `day_1`,
    CASE WHEN DATE_ADD(cs.cohort_date, INTERVAL 2 DAY) <= b.end_date THEN COALESCE(SUM(CASE WHEN dv.day_offset = 2 THEN dv.day_amount END), 0) ELSE NULL END AS `day_2`,
    CASE WHEN DATE_ADD(cs.cohort_date, INTERVAL 3 DAY) <= b.end_date THEN COALESCE(SUM(CASE WHEN dv.day_offset = 3 THEN dv.day_amount END), 0) ELSE NULL END AS `day_3`,
    CASE WHEN DATE_ADD(cs.cohort_date, INTERVAL 4 DAY) <= b.end_date THEN COALESCE(SUM(CASE WHEN dv.day_offset = 4 THEN dv.day_amount END), 0) ELSE NULL END AS `day_4`,
    CASE WHEN DATE_ADD(cs.cohort_date, INTERVAL 5 DAY) <= b.end_date THEN COALESCE(SUM(CASE WHEN dv.day_offset = 5 THEN dv.day_amount END), 0) ELSE NULL END AS `day_5`,
    CASE WHEN DATE_ADD(cs.cohort_date, INTERVAL 6 DAY) <= b.end_date THEN COALESCE(SUM(CASE WHEN dv.day_offset = 6 THEN dv.day_amount END), 0) ELSE NULL END AS `day_6`,
    CASE WHEN DATE_ADD(cs.cohort_date, INTERVAL 7 DAY) <= b.end_date THEN COALESCE(SUM(CASE WHEN dv.day_offset = 7 THEN dv.day_amount END), 0) ELSE NULL END AS `day_7`
FROM cohort_size AS cs
CROSS JOIN dashboard_date_bounds AS b
LEFT JOIN daily_values AS dv ON cs.cohort_date = dv.cohort_date
GROUP BY cs.cohort_date, cs.cohort_size, b.end_date
ORDER BY cs.cohort_date