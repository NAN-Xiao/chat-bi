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
    SELECT
        `event`.`uid` AS entity_id,
        `event`.`time` AS event_time_ms,
        STR_TO_DATE(CAST(`event`.`dt` AS CHAR), '%Y%m%d') AS interval_date,
        `event`.`event` AS event_name
    FROM `event`
    WHERE `event`.`dt` >= {{dashboard_start_yyyymmdd}}
      AND `event`.`dt` <= {{dashboard_end_yyyymmdd}}
      AND `event`.`event` = 'Launch'
      AND `event`.`prod` = 110000036
),
ordered_events AS (
    SELECT
        entity_id,
        event_time_ms,
        interval_date,
        ROW_NUMBER() OVER (PARTITION BY entity_id ORDER BY event_time_ms) AS event_order
    FROM scoped_events
),
paired AS (
    SELECT
        curr.entity_id,
        curr.interval_date,
        FROM_UNIXTIME(prev.event_time_ms / 1000.0) AS start_time,
        FROM_UNIXTIME(curr.event_time_ms / 1000.0) AS end_time
    FROM ordered_events AS curr
    JOIN ordered_events AS prev
      ON curr.entity_id = prev.entity_id
      AND curr.event_order = prev.event_order + 1
),
valid_intervals AS (
    SELECT
        interval_date,
        entity_id,
        TIMESTAMPDIFF(SECOND, start_time, end_time) AS interval_seconds
    FROM paired
    WHERE end_time >= start_time
      AND TIMESTAMPDIFF(SECOND, start_time, end_time) <= 3600
)
SELECT
    `interval_date`,
    COUNT(DISTINCT `entity_id`) AS `entity_count`,
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