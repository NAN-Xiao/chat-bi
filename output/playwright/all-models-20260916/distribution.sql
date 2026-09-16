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
base_events AS (
    SELECT 
        STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS distribution_date,
        e.uid AS entity_id
    FROM event e
    WHERE e.dt >= {{dashboard_start_yyyymmdd}}
      AND e.dt <= {{dashboard_end_yyyymmdd}}
      AND e.event = 'Launch'
      AND e.prod = 110000036
      AND e.uid IS NOT NULL
),
entity_values AS (
    SELECT 
        distribution_date,
        entity_id,
        COUNT(*) AS distribution_value
    FROM base_events
    GROUP BY distribution_date, entity_id
),
interval_bounds AS (
    SELECT 
        MIN(distribution_value) AS min_value,
        MAX(distribution_value) AS max_value,
        MAX(distribution_value) - MIN(distribution_value) AS value_range
    FROM entity_values
),
bucketed AS (
    SELECT 
        ev.distribution_date,
        ev.entity_id,
        ev.distribution_value,
        CASE 
            WHEN ib.value_range < 12 THEN ev.distribution_value
            WHEN ib.max_value = ib.min_value THEN 1
            WHEN ev.distribution_value = ib.max_value THEN 12
            ELSE LEAST(12, FLOOR((ev.distribution_value - ib.min_value) * 12.0 / NULLIF(ib.value_range, 0)) + 1)
        END AS interval_order,
        CASE 
            WHEN ib.value_range < 12 THEN CAST(ev.distribution_value AS CHAR)
            WHEN ib.max_value = ib.min_value THEN CAST(ev.distribution_value AS CHAR)
            WHEN ev.distribution_value = ib.max_value THEN CONCAT('≥', CAST(ib.max_value AS CHAR))
            ELSE CONCAT(
                CAST(ib.min_value + FLOOR((ev.distribution_value - ib.min_value) * 12.0 / NULLIF(ib.value_range, 0)) * ib.value_range / 12.0 AS SIGNED),
                '-',
                CAST(ib.min_value + (FLOOR((ev.distribution_value - ib.min_value) * 12.0 / NULLIF(ib.value_range, 0)) + 1) * ib.value_range / 12.0 AS SIGNED)
            )
        END AS interval_label
    FROM entity_values ev
    CROSS JOIN interval_bounds ib
),
totals AS (
    SELECT 
        distribution_date,
        COUNT(DISTINCT entity_id) AS total_entities
    FROM entity_values
    GROUP BY distribution_date
)
SELECT 
    DATE_FORMAT(b.distribution_date, '%Y-%m-%d') AS `distribution_date`,
    t.total_entities AS `total_entities`,
    b.interval_order AS `interval_order`,
    b.interval_label AS `interval_label`,
    COUNT(DISTINCT b.entity_id) AS `entity_count`,
    ROUND(COUNT(DISTINCT b.entity_id) * 100.0 / NULLIF(t.total_entities, 0), 2) AS `entity_rate`
FROM bucketed b
JOIN totals t ON b.distribution_date = t.distribution_date
GROUP BY b.distribution_date, t.total_entities, b.interval_order, b.interval_label
ORDER BY b.distribution_date, b.interval_order