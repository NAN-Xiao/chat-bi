WITH scoped_events AS (
    SELECT
        `e`.`uid`,
        `e`.`time` AS event_time,
        `e`.`event` AS event_name,
        `e`.`dt`
    FROM `event` AS `e`
    WHERE `e`.`prod` = 110000036
      AND `e`.`dt` >= {{dashboard_start_yyyymmdd}}
      AND `e`.`dt` <= {{dashboard_end_yyyymmdd}}
      AND `e`.`event` IN ('Launch', 'UserActive')
),
ordered_events AS (
    SELECT
        `s`.`uid`,
        `s`.`event_time`,
        `s`.`event_name`,
        `s`.`dt`,
        LAG(`s`.`event_time`) OVER (PARTITION BY `s`.`uid` ORDER BY `s`.`event_time` ASC) AS prev_event_time
    FROM scoped_events AS `s`
),
sessionized AS (
    SELECT
        `o`.`uid`,
        `o`.`event_time`,
        `o`.`event_name`,
        `o`.`dt`,
        SUM(CASE WHEN `o`.`prev_event_time` IS NULL OR (`o`.`event_time` - `o`.`prev_event_time`) > 1800000 THEN 1 ELSE 0 END)
            OVER (PARTITION BY `o`.`uid` ORDER BY `o`.`event_time` ASC) AS session_id
    FROM ordered_events AS `o`
),
session_steps AS (
    SELECT
        `s`.`uid`,
        `s`.`session_id`,
        `s`.`event_time`,
        `s`.`event_name`,
        `s`.`dt`,
        ROW_NUMBER() OVER (PARTITION BY `s`.`uid`, `s`.`session_id` ORDER BY `s`.`event_time` ASC) AS step_in_session
    FROM sessionized AS `s`
),
path_nodes AS (
    SELECT
        `s`.`uid`,
        `s`.`session_id`,
        `s`.`event_time`,
        `s`.`event_name`,
        `s`.`dt`,
        `s`.`step_in_session`
    FROM session_steps AS `s`
    WHERE `s`.`step_in_session` <= 10
),
edge_candidates AS (
    SELECT
        `p`.`uid`,
        `p`.`session_id`,
        `p`.`event_name` AS path_source,
        LEAD(`p`.`event_name`) OVER (PARTITION BY `p`.`uid`, `p`.`session_id` ORDER BY `p`.`step_in_session` ASC) AS path_target,
        `p`.`step_in_session` AS path_step
    FROM path_nodes AS `p`
),
edges AS (
    SELECT
        `e`.`path_source`,
        `e`.`path_target`,
        `e`.`path_step`
    FROM edge_candidates AS `e`
    WHERE `e`.`path_target` IS NOT NULL
)
SELECT
    `path_source`,
    `path_target`,
    COUNT(*) AS `path_value`,
    `path_step`
FROM edges
GROUP BY `path_step`, `path_source`, `path_target`
ORDER BY `path_step`, `path_value` DESC