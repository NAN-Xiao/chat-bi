WITH scoped_events AS (
    SELECT 
        `uid`,
        `time`,
        `event`,
        STR_TO_DATE(CAST(`dt` AS CHAR), '%Y%m%d') AS event_date
    FROM `event`
    WHERE `event` IN ('Launch', 'UserActive')
      AND `dt` >= {{dashboard_start_yyyymmdd}}
      AND `dt` <= {{dashboard_end_yyyymmdd}}
      AND `prod` = 110000036
),
ordered_events AS (
    SELECT 
        `uid`,
        `time`,
        `event`,
        event_date,
        LAG(`time`) OVER (PARTITION BY `uid` ORDER BY `time`) AS prev_time
    FROM scoped_events
),
sessionized AS (
    SELECT 
        `uid`,
        `time`,
        `event`,
        event_date,
        SUM(CASE WHEN prev_time IS NULL OR (`time` - prev_time) > 1800000 THEN 1 ELSE 0 END) 
            OVER (PARTITION BY `uid` ORDER BY `time`) AS session_id
    FROM ordered_events
),
session_steps AS (
    SELECT 
        `uid`,
        session_id,
        `time`,
        `event`,
        event_date,
        ROW_NUMBER() OVER (PARTITION BY `uid`, session_id ORDER BY `time`) AS step_in_session
    FROM sessionized
),
valid_sessions AS (
    SELECT DISTINCT `uid`, session_id
    FROM session_steps
    WHERE step_in_session = 1 AND `event` = 'Launch'
),
path_nodes AS (
    SELECT 
        s.`uid`,
        s.session_id,
        s.`time`,
        s.`event`,
        s.event_date,
        s.step_in_session
    FROM session_steps s
    INNER JOIN valid_sessions v ON s.`uid` = v.`uid` AND s.session_id = v.session_id
    WHERE s.step_in_session <= 10
),
edge_candidates AS (
    SELECT 
        `uid`,
        session_id,
        step_in_session,
        `event` AS path_source,
        LEAD(`event`) OVER (PARTITION BY `uid`, session_id ORDER BY `time`) AS path_target,
        step_in_session AS path_step
    FROM path_nodes
),
edges AS (
    SELECT 
        path_source,
        path_target,
        path_step
    FROM edge_candidates
    WHERE path_target IS NOT NULL
)
SELECT 
    `path_source`,
    `path_target`,
    COUNT(*) AS `path_value`,
    `path_step`
FROM edges
GROUP BY `path_step`, `path_source`, `path_target`
ORDER BY `path_step`, `path_value` DESC