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
scoped_properties AS (
    SELECT `event`.`dt`, `event`.`uid`
    FROM `event`
    WHERE `event`.`dt` >= {{dashboard_start_yyyymmdd}}
      AND `event`.`dt` <= {{dashboard_end_yyyymmdd}}
      AND `event`.`prod` = 110000036
),
aggregated AS (
    SELECT CAST(DATE_FORMAT(sp.dt, '%Y%m%d') AS SIGNED) AS property_date,
           COUNT(DISTINCT sp.uid) AS property_metric_1
    FROM scoped_properties sp
    GROUP BY CAST(DATE_FORMAT(sp.dt, '%Y%m%d') AS SIGNED)
)
SELECT CAST(DATE_FORMAT(dd.calendar_date, '%Y%m%d') AS SIGNED) AS `property_date`,
       COALESCE(a.property_metric_1, 0) AS `property_metric_1`
FROM dashboard_dates dd
LEFT JOIN aggregated a
  ON CAST(DATE_FORMAT(dd.calendar_date, '%Y%m%d') AS SIGNED) = a.property_date
ORDER BY `property_date`