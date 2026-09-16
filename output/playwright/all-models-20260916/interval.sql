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
scoped_events AS (
    SELECT `uid`, `event`, `dt`, `time`,
           STR_TO_DATE(CAST(`dt` AS CHAR), '%Y%m%d') AS event_date,
           FROM_UNIXTIME(`time` / 1000) AS event_time
    FROM `event`
    WHERE `event` = 'Launch'
      AND `prod` = 110000036
      AND `dt` >= {{dashboard_start_yyyymmdd}}
      AND `dt` <= {{dashboard_end_yyyymmdd}}
),
ordered_events AS (
    SELECT `uid`, `event`, `dt`, `time`, event_date, event_time,
           LAG(event_time) OVER (PARTITION BY `uid` ORDER BY event_time, `time`) AS prev_event_time,
           LAG(event_date) OVER (PARTITION BY `uid` ORDER BY event_time, `time`) AS prev_event_date
    FROM scoped_events
),
paired AS (
    SELECT `uid`, prev_event_date AS start_date, event_date AS end_date,
           prev_event_time AS start_time, event_time AS end_time
    FROM ordered_events
    WHERE prev_event_time IS NOT NULL
),
valid_intervals AS (
    SELECT start_date AS interval_date, `uid`,
           TIMESTAMPDIFF(SECOND, start_time, end_time) AS interval_seconds
    FROM paired
    WHERE end_time >= start_time
      AND TIMESTAMPDIFF(SECOND, start_time, end_time) <= 3600
)
SELECT `interval_date`,
       COUNT(DISTINCT `uid`) AS `entity_count`,
       COUNT(*) AS `interval_count`,
       MAX(`interval_seconds`) AS `max_interval_seconds`,
       APPROX_PERCENTILE(`interval_seconds`, 0.75) AS `p75_interval_seconds`,
       APPROX_PERCENTILE(`interval_seconds`, 0.50) AS `median_interval_seconds`,
       APPROX_PERCENTILE(`interval_seconds`, 0.25) AS `p25_interval_seconds`,
       MIN(`interval_seconds`) AS `min_interval_seconds`,
       AVG(`interval_seconds`) AS `avg_interval_seconds`
FROM valid_intervals
GROUP BY `interval_date`
ORDER BY `interval_date`