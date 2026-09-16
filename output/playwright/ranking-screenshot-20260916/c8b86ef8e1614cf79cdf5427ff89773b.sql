WITH scoped_events AS (
    SELECT 
        `event`.`uid`,
        `event`.`event`,
        JSON_UNQUOTE(JSON_EXTRACT(`event`.`personal`, '$.money')) AS pay_money,
        JSON_UNQUOTE(JSON_EXTRACT(`event`.`adinfo`, '$.mediaSource')) AS media_source,
        `event`.`dt`
    FROM `event`
    WHERE `event`.`dt` BETWEEN {{dashboard_start_yyyymmdd}} AND {{dashboard_end_yyyymmdd}}
      AND `event`.`prod` = 110000036
      AND `event`.`event` IN ('ServerPayLog', 'UserActive')
),
user_property AS (
    SELECT `uid`, `media_source`
    FROM (
        SELECT `uid`, `media_source`, ROW_NUMBER() OVER (PARTITION BY `uid` ORDER BY `dt` DESC) AS rn
        FROM scoped_events
    ) t
    WHERE rn = 1
),
entity_values AS (
    SELECT 
        s.`uid` AS `ranking_entity`,
        SUM(CASE WHEN s.`event` = 'ServerPayLog' THEN CAST(s.pay_money AS SIGNED) ELSE 0 END) AS `ranking_value`,
        COUNT(CASE WHEN s.`event` = 'UserActive' THEN 1 END) AS `simultaneous_metric_1`,
        p.`media_source` AS `ranking_property_1`
    FROM scoped_events s
    JOIN user_property p ON s.`uid` = p.`uid`
    GROUP BY s.`uid`, p.`media_source`
),
ranked AS (
    SELECT 
        RANK() OVER (ORDER BY `ranking_value` DESC, `ranking_entity`) AS `rank`,
        `ranking_entity`,
        `ranking_value`,
        `simultaneous_metric_1`,
        `ranking_property_1`
    FROM entity_values
)
SELECT 
    `rank`,
    `ranking_entity`,
    `ranking_value`,
    `simultaneous_metric_1`,
    `ranking_property_1`
FROM ranked
ORDER BY `rank`, `ranking_entity`