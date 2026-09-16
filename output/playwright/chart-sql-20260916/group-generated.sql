WITH dashboard_date_bounds AS (
  SELECT
    STR_TO_DATE(CAST({{dashboard_start_yyyymmdd}} AS CHAR), '%Y%m%d') AS start_date,
    STR_TO_DATE(CAST({{dashboard_end_yyyymmdd}} AS CHAR), '%Y%m%d') AS end_date
), dashboard_date_span AS (
  SELECT
    b.start_date,
    DATEDIFF(b.end_date, b.start_date) AS day_count
  FROM dashboard_date_bounds AS b
), dashboard_digits AS (
  SELECT
    0 AS n
  UNION ALL
  SELECT
    1 AS n
  UNION ALL
  SELECT
    2 AS n
  UNION ALL
  SELECT
    3 AS n
  UNION ALL
  SELECT
    4 AS n
  UNION ALL
  SELECT
    5 AS n
  UNION ALL
  SELECT
    6 AS n
  UNION ALL
  SELECT
    7 AS n
  UNION ALL
  SELECT
    8 AS n
  UNION ALL
  SELECT
    9 AS n
), dashboard_offsets_0 AS (
  SELECT
    b.start_date,
    b.day_count,
    d.n
  FROM dashboard_date_span AS b
  CROSS JOIN dashboard_digits AS d
  WHERE
    d.n <= b.day_count
), dashboard_offsets_1 AS (
  SELECT
    p.start_date,
    p.day_count,
    p.n + d.n * 10 AS n
  FROM dashboard_offsets_0 AS p
  CROSS JOIN dashboard_digits AS d
  WHERE
    p.n + d.n * 10 <= p.day_count
), dashboard_offsets_2 AS (
  SELECT
    p.start_date,
    p.day_count,
    p.n + d.n * 100 AS n
  FROM dashboard_offsets_1 AS p
  CROSS JOIN dashboard_digits AS d
  WHERE
    p.n + d.n * 100 <= p.day_count
), dashboard_offsets_3 AS (
  SELECT
    p.start_date,
    p.day_count,
    p.n + d.n * 1000 AS n
  FROM dashboard_offsets_2 AS p
  CROSS JOIN dashboard_digits AS d
  WHERE
    p.n + d.n * 1000 <= p.day_count
), dashboard_offsets_4 AS (
  SELECT
    p.start_date,
    p.day_count,
    p.n + d.n * 10000 AS n
  FROM dashboard_offsets_3 AS p
  CROSS JOIN dashboard_digits AS d
  WHERE
    p.n + d.n * 10000 <= p.day_count
), dashboard_offsets_5 AS (
  SELECT
    p.start_date,
    p.day_count,
    p.n + d.n * 100000 AS n
  FROM dashboard_offsets_4 AS p
  CROSS JOIN dashboard_digits AS d
  WHERE
    p.n + d.n * 100000 <= p.day_count
), dashboard_offsets_6 AS (
  SELECT
    p.start_date,
    p.day_count,
    p.n + d.n * 1000000 AS n
  FROM dashboard_offsets_5 AS p
  CROSS JOIN dashboard_digits AS d
  WHERE
    p.n + d.n * 1000000 <= p.day_count
), dashboard_dates AS (
  SELECT
    DATE_ADD(p.start_date, INTERVAL p.n DAY) AS calendar_date
  FROM dashboard_offsets_6 AS p
), user_dimensions AS (
  SELECT DISTINCT
    `uid`
  FROM `event`
  WHERE
    `dt` BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
    AND `event` = 'Launch'
    AND `prod` = 110000036
    AND NOT `uid` IS NULL
), date_user_grid AS (
  SELECT
    d.calendar_date,
    u.`uid`
  FROM dashboard_dates AS d
  CROSS JOIN user_dimensions AS u
), launch_agg AS (
  SELECT
    STR_TO_DATE(CAST(`dt` AS CHAR), '%Y%m%d') AS event_date,
    `uid`,
    COUNT(*) AS launch_count
  FROM `event`
  WHERE
    `dt` BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
    AND `event` = 'Launch'
    AND `prod` = 110000036
    AND NOT `uid` IS NULL
  GROUP BY
    STR_TO_DATE(CAST(`dt` AS CHAR), '%Y%m%d'),
    `uid`
)
SELECT
  g.calendar_date AS `dt`,
  g.`uid` AS `uid`,
  COALESCE(l.launch_count, 0) AS `启动次数`
FROM date_user_grid AS g
LEFT JOIN launch_agg AS l
  ON g.calendar_date = l.event_date AND g.`uid` = l.`uid`
ORDER BY
  g.calendar_date,
  g.`uid`