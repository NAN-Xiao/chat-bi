WITH scoped_events AS (
    SELECT `uid`, `event`
    FROM `event`
    WHERE `dt` >= {{dashboard_start_yyyymmdd}}
      AND `dt` <= {{dashboard_end_yyyymmdd}}
      AND `prod` = 110000036
      AND `event` = 'Launch'
),
entity_values AS (
    SELECT `uid` AS `ranking_entity`,
           COUNT(*) AS `ranking_value`
    FROM scoped_events
    GROUP BY `uid`
),
ranked AS (
    SELECT `ranking_entity`,
           `ranking_value`,
           RANK() OVER (ORDER BY `ranking_value` DESC, `ranking_entity`) AS `rank`
    FROM entity_values
)
SELECT `rank`, `ranking_entity`, `ranking_value`
FROM ranked
ORDER BY `rank`, `ranking_entity`