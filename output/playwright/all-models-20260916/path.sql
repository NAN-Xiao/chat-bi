WITH scoped_events AS (
    SELECT 
        `e`.`uid` AS entity_id,
        `e`.`time` AS event_time,
        `e`.`event` AS event_name,
        `e`.`dt` AS dt
    FROM `event` AS `e`
    WHERE `e`.`prod` = 110000036
      AND `e`.`dt` >= {{dashboard_start_yyyymmdd}}
      AND `e`.`dt` <= {{dashboard_end_yyyymmdd}}
      AND `e`.`event` IN ('Launch', 'UserActive')
),
ordered_events AS (
    SELECT 
        entity_id,
        event_time,
        event_name,
        dt,
        LAG(event_time) OVER (PARTITION BY entity_id ORDER BY event_time ASC) AS prev_event_time
    FROM scoped_events
),
sessionized AS (
    SELECT 
        entity_id,
        event_time,
        event_name,
        dt,
        SUM(CASE WHEN prev_event_time IS NULL OR (event_time - prev_event_time) > 1800000 THEN 1 ELSE 0 END) 
            OVER (PARTITION BY entity_id ORDER BY event_time ASC) AS session_id
    FROM ordered_events
),
session_steps AS (
    SELECT 
        entity_id,
        session_id,
        event_time,
        event_name,
        dt,
        ROW_NUMBER() OVER (PARTITION BY entity_id, session_id ORDER BY event_time ASC) AS step_in_session
    FROM sessionized
),
valid_sessions AS (
    SELECT 
        entity_id,
        session_id
    FROM session_steps
    WHERE step_in_session = 1 
      AND event_name = 'Launch'
),
path_nodes AS (
    SELECT 
        s.entity_id,
        s.session_id,
        s.event_time,
        s.event_name,
        s.dt,
        s.step_in_session
    FROM session_steps AS s
    INNER JOIN valid_sessions AS v 
        ON s.entity_id = v.entity_id 
        AND s.session_id = v.session_id
    WHERE s.step_in_session <= 10
),
edge_candidates AS (
    SELECT 
        entity_id,
        session_id,
        event_name AS path_source,
        LEAD(event_name) OVER (PARTITION BY entity_id, session_id ORDER BY step_in_session ASC) AS path_target,
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