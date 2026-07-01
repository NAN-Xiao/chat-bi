# -*- coding: utf-8 -*-
"""SQL definitions for remaining flam / first_zombie dashboard components."""

from __future__ import annotations

from dataclasses import dataclass

from flam_first_zombie_active_dashboard_sql import SQL_ACTIVE_BY_CHANNEL
from flam_first_zombie_dashboard_sql import CHANNEL_EXPR_U, DATASOURCE_ID, LOGIN_EVENTS, PAY_EVENTS, PROD_ID, TENANT_ID


@dataclass(frozen=True)
class ViewSql:
    dashboard_name: str
    title: str
    chart_type: str
    fields: tuple[str, ...]
    x_axis: tuple[str, ...] = ()
    y_axis: tuple[str, ...] = ()
    columns: tuple[str, ...] = ()
    sql: str = ""


def _json_text(alias: str, obj: str, key: str) -> str:
    return f"NULLIF(JSON_UNQUOTE(JSON_EXTRACT({alias}.{obj}, '$.{key}')), '')"


def _json_num(alias: str, obj: str, key: str) -> str:
    return f"COALESCE(CAST({_json_text(alias, obj, key)} AS DECIMAL(18,4)), 0)"


def _pay_value(alias: str, field: str = "paytotal") -> str:
    return _json_num(alias, "pay", field)


def _date_expr(days_ago: int = 0) -> str:
    if days_ago <= 0:
        return "CAST(DATE_FORMAT(CURDATE(), '%Y%m%d') AS SIGNED)"
    return f"CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL {days_ago} DAY), '%Y%m%d') AS SIGNED)"


LATEST_WEEK_START = "DATE_SUB(DATE_SUB(CURDATE(), INTERVAL 1 DAY), INTERVAL WEEKDAY(DATE_SUB(CURDATE(), INTERVAL 1 DAY)) DAY)"


def _week_snapshot_dt_expr(weeks_ago: int) -> str:
    if weeks_ago <= 0:
        return _date_expr(1)
    return f"CAST(DATE_FORMAT(DATE_ADD(DATE_SUB({LATEST_WEEK_START}, INTERVAL {weeks_ago} WEEK), INTERVAL 6 DAY), '%Y%m%d') AS SIGNED)"


def _bounds(table: str, days: int = 29, end_days_ago: int = 0) -> str:
    del table
    start_days_ago = days + end_days_ago
    return f"""
WITH bounds AS (
    SELECT {_date_expr(start_days_ago)} AS start_dt,
           {_date_expr(end_days_ago)} AS max_dt
)
""".strip()


def _dt_between(alias: str, days: int = 29, end_days_ago: int = 0) -> str:
    start_days_ago = days + end_days_ago
    return f"{alias}.dt BETWEEN {_date_expr(start_days_ago)} AND {_date_expr(end_days_ago)}"


def _metric_sql(table: str, metric_name: str, where_clause: str, value_expr: str = "COUNT(*)", days: int = 29) -> str:
    del days
    prod_filter = f"\n             AND e.prod = {PROD_ID}" if table == "event" else ""
    today_dt = _date_expr(1)
    yesterday_dt = _date_expr(2)
    last_week_dt = _date_expr(8)
    return f"""
WITH metric AS (
    SELECT
        (SELECT {value_expr} FROM `{table}` e
         WHERE e.dt = {today_dt}
           AND {where_clause}{prod_filter}) AS today_value,
        (SELECT {value_expr} FROM `{table}` e
         WHERE e.dt = {yesterday_dt}
           AND {where_clause}{prod_filter}) AS yesterday_value,
        (SELECT {value_expr} FROM `{table}` e
         WHERE e.dt = {last_week_dt}
           AND {where_clause}{prod_filter}) AS last_week_value
)
SELECT COALESCE(today_value, 0) AS `{metric_name}`,
       ROUND((COALESCE(today_value, 0) - COALESCE(yesterday_value, 0)) / NULLIF(yesterday_value, 0) * 100, 2) AS `日环比`,
       ROUND((COALESCE(today_value, 0) - COALESCE(last_week_value, 0)) / NULLIF(last_week_value, 0) * 100, 2) AS `周同比`
FROM metric
""".strip()


def _axis(field: str) -> dict[str, str]:
    return {"name": field, "value": field}


EXPEDITION_EVENTS = "'WorldMarch','WorldMarchRet','ActivityWorldBoss','ActivityAllianceBossBattleRet','honorExpedition','ArenaResults','TrainingArenaResults','multipleArena'"
ACTIVITY_EVENTS = "'ActivityAllianceBossBattleRet','ActivityAllianceBossChoose','ActivityAllianceBossDonation','ActivityAllianceBossReward','ActivityArmsRaceBoxOpen','ActivityArmsRaceGoalPoint','ActivityArmsRaceTask','ActivityChestCount','ActivityCommanderTask','ActivityWheelCount','ActivityWorldBoss','AllianceDuelAlliancePoint','AllianceDuelPersonalPoint','AllianceDuelBoxOpen'"
BUILDING_EVENTS = "'BuildingUpgrade','BuildingIdleUpgrade'"
TECH_EVENTS = "'TechnologyDonation'"
HERO_EVENTS = "'HeroAcquisition','HeroLevelUp','HeroStarUp','HeroSkillUpgrade','HeroRecruit'"

HERO_ID = f"COALESCE({_json_text('e', 'ext', 'ed_heroId')}, {_json_text('e', 'ext', 'captainId')}, '未知')"
CITY_LEVEL_E = f"COALESCE({_json_text('e', 'ext', 'ed_mainBuildingLevel')}, '未知')"
ARMY_ID = f"COALESCE({_json_text('e', 'ext', 'ed_newArmyId')}, {_json_text('e', 'ext', 'ed_oldArmyId')}, '未知')"
PRODUCT_ID = (
    f"COALESCE({_json_text('e', 'ext', 'payId')}, {_json_text('e', 'ext', 'rechargeId')}, "
    f"{_json_text('e', 'ext', 'productId')}, {_json_text('e', 'ext', 'goodsId')}, e.event)"
)

SQL_EXPEDITION_COUNT = _metric_sql("event", "出征事件数", f"e.event IN ({EXPEDITION_EVENTS})")
SQL_ARMY_UPGRADE_COUNT = _metric_sql("event", "兵种升级事件数", "e.event = 'ArmyUpgrade'")
SQL_HONOR_EXPEDITION_COUNT = _metric_sql("event", "荣耀远征事件数", "e.event = 'honorExpedition'")

SQL_EXPEDITION_AVG_POWER = f"""
WITH metric AS (
    SELECT
        (SELECT AVG(COALESCE(CAST({_json_text('e', 'ext', 'combatPower')} AS DECIMAL(18,4)),
                             CAST({_json_text('e', 'ext', 'captainPower')} AS DECIMAL(18,4))))
         FROM `event` e
         WHERE e.dt = {_date_expr(1)}
           AND e.event IN ({EXPEDITION_EVENTS})
           AND e.prod = {PROD_ID}) AS today_value,
        (SELECT AVG(COALESCE(CAST({_json_text('e', 'ext', 'combatPower')} AS DECIMAL(18,4)),
                             CAST({_json_text('e', 'ext', 'captainPower')} AS DECIMAL(18,4))))
         FROM `event` e
         WHERE e.dt = {_date_expr(2)}
           AND e.event IN ({EXPEDITION_EVENTS})
           AND e.prod = {PROD_ID}) AS yesterday_value,
        (SELECT AVG(COALESCE(CAST({_json_text('e', 'ext', 'combatPower')} AS DECIMAL(18,4)),
                             CAST({_json_text('e', 'ext', 'captainPower')} AS DECIMAL(18,4))))
         FROM `event` e
         WHERE e.dt = {_date_expr(8)}
           AND e.event IN ({EXPEDITION_EVENTS})
           AND e.prod = {PROD_ID}) AS last_week_value
)
SELECT ROUND(COALESCE(today_value, 0), 2) AS `竞技场/出征平均战力`,
       ROUND((COALESCE(today_value, 0) - COALESCE(yesterday_value, 0)) / NULLIF(yesterday_value, 0) * 100, 2) AS `日环比`,
       ROUND((COALESCE(today_value, 0) - COALESCE(last_week_value, 0)) / NULLIF(last_week_value, 0) * 100, 2) AS `周同比`
FROM metric
""".strip()

SQL_EXPEDITION_DETAIL = f"""
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
       COUNT(*) AS `出征事件数`,
       ROUND(COUNT(*) / NULLIF(COUNT(DISTINCT e.uid), 0), 2) AS `人均事件数`,
       COUNT(DISTINCT e.uid) AS `参与用户数`
FROM `event` e
WHERE {_dt_between("e", 6)}
  AND e.event IN ({EXPEDITION_EVENTS})
  AND e.prod = {PROD_ID}
GROUP BY e.dt
ORDER BY e.dt
""".strip()

SQL_ARMY_7D = f"""
SELECT
    STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
    COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_marchType')), ''), '未知') AS `出征类型`,
    COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_targetType')), ''), '未知') AS `目标类型`,
    COALESCE(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_mainBuildingLevel')), ''), '未知') AS `大本等级`,
    COUNT(*) AS `出征次数`,
    COUNT(DISTINCT e.uid) AS `出征用户数`,
    COUNT(DISTINCT NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_marchId')), '')) AS `出征ID数`,
    ROUND(COUNT(*) / NULLIF(COUNT(DISTINCT e.uid), 0), 2) AS `人均出征次数`,
    ROUND(AVG(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_estimatedSeconds')), '') AS DECIMAL(18,4))) / 60, 2) AS `平均预计耗时分钟`,
    ROUND(AVG(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_myTeamBattlePower')), '') AS DECIMAL(18,4))), 2) AS `平均出征战力`,
    ROUND(SUM(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_myTeamBattlePower')), '') AS DECIMAL(18,4))), 2) AS `出征总战力`
FROM `event` e
WHERE {_dt_between("e", 6)}
  AND e.event = 'WorldMarch'
  AND e.prod = {PROD_ID}
GROUP BY
    e.dt,
    `出征类型`,
    `目标类型`,
    `大本等级`
ORDER BY
    e.dt,
    `出征次数` DESC
LIMIT 1000;
""".strip()

SQL_HERO_EXPEDITION_COUNT = f"""
SELECT
    STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
    JSON_UNQUOTE(JSON_EXTRACT(e.personal, CONCAT('$.ed_myTeamHeroList[', n.n, '].heroId'))) AS `英雄ID`,
    COUNT(*) AS `出征次数`
FROM `event` e
JOIN (
    SELECT 0 AS n UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4
    UNION ALL SELECT 5 UNION ALL SELECT 6 UNION ALL SELECT 7 UNION ALL SELECT 8 UNION ALL SELECT 9
) n
  ON JSON_EXTRACT(e.personal, CONCAT('$.ed_myTeamHeroList[', n.n, '].heroId')) IS NOT NULL
WHERE {_dt_between("e", 6)}
  AND e.event = 'WorldMarch'
  AND e.prod = {PROD_ID}
GROUP BY
    e.dt,
    `英雄ID`
ORDER BY
    e.dt,
    `出征次数` DESC
LIMIT 1000;
""".strip()

_WIN_EXPR = "COALESCE(" + _json_text("e", "ext", "battleResult") + ", " + _json_text("e", "ext", "expeditionDungeonResult") + ") IN ('win','success','1','胜利')"

SQL_LEVEL_WIN_RATE = f"""
SELECT
    COALESCE(
        NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_mainBuildingLevel')), ''),
        '未知'
    ) AS `等级`,
    COALESCE(
        NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_targetType')), ''),
        '未知'
    ) AS `目标类型`,
    COUNT(*) AS `出征结果次数`,
    COUNT(DISTINCT e.uid) AS `出征用户数`,
    SUM(
        CASE
            WHEN COALESCE(
                NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_result')), ''),
                NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_battleResult')), '')
            ) IN ('4', 'win', 'success', '1', '胜利') THEN 1
            ELSE 0
        END
    ) AS `胜利次数`,
    ROUND(
        SUM(
            CASE
                WHEN COALESCE(
                    NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_result')), ''),
                    NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_battleResult')), '')
                ) IN ('4', 'win', 'success', '1', '胜利') THEN 1
                ELSE 0
            END
        ) / NULLIF(COUNT(*), 0) * 100,
        2
    ) AS `出征胜率`
FROM `event` e
WHERE {_dt_between("e", 6)}
  AND e.event = 'WorldMarchRet'
  AND e.prod = {PROD_ID}
GROUP BY
    `等级`,
    `目标类型`
ORDER BY
    CAST(`等级` AS SIGNED),
    `出征结果次数` DESC
LIMIT 1000;
""".strip()

SQL_HERO_WIN_RATE = f"""
WITH bounds AS (
    SELECT
        CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 6 DAY), '%Y%m%d') AS SIGNED) AS start_dt,
        CAST(DATE_FORMAT(CURDATE(), '%Y%m%d') AS SIGNED) AS end_dt
),
march_heroes AS (
    SELECT DISTINCT
        e.uid,
        JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_marchId')) AS march_id,
        JSON_UNQUOTE(
            JSON_EXTRACT(
                e.personal,
                CONCAT('$.ed_myTeamHeroList[', n.n, '].heroId')
            )
        ) AS hero_id
    FROM `event` e
    JOIN bounds b ON TRUE
    JOIN (
        SELECT 0 AS n UNION ALL SELECT 1 UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4
        UNION ALL SELECT 5 UNION ALL SELECT 6 UNION ALL SELECT 7 UNION ALL SELECT 8 UNION ALL SELECT 9
    ) n
      ON JSON_EXTRACT(e.personal, CONCAT('$.ed_myTeamHeroList[', n.n, ']')) IS NOT NULL
    WHERE e.dt BETWEEN b.start_dt AND b.end_dt
      AND e.prod = {PROD_ID}
      AND e.event = 'WorldMarch'
      AND JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_marchId')) IS NOT NULL
),
march_results AS (
    SELECT
        e.uid,
        JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_marchId')) AS march_id,
        MAX(
            CASE
                WHEN COALESCE(
                    NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_result')), ''),
                    NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_battleResult')), '')
                ) IN ('4', 'win', 'success', '1', '胜利') THEN 1
                ELSE 0
            END
        ) AS is_win
    FROM `event` e
    JOIN bounds b ON TRUE
    WHERE e.dt BETWEEN b.start_dt AND b.end_dt
      AND e.prod = {PROD_ID}
      AND e.event = 'WorldMarchRet'
      AND JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_marchId')) IS NOT NULL
    GROUP BY
        e.uid,
        JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_marchId'))
)
SELECT
    mh.hero_id AS `英雄ID`,
    COUNT(*) AS `出征次数`,
    SUM(mr.is_win) AS `胜利次数`,
    ROUND(SUM(mr.is_win) / NULLIF(COUNT(*), 0) * 100, 2) AS `出征胜率`
FROM march_results mr
JOIN march_heroes mh
  ON mh.uid = mr.uid
 AND mh.march_id = mr.march_id
WHERE mh.hero_id IS NOT NULL
  AND mh.hero_id <> ''
GROUP BY mh.hero_id
ORDER BY `出征次数` DESC, `出征胜率` DESC
LIMIT 1000
""".strip()

SQL_DRILL_BY_CITY_LEVEL = f"""
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
       {CITY_LEVEL_E} AS `主城等级`,
       COUNT(*) AS `参与演习次数`
FROM `event` e
WHERE {_dt_between("e", 6)}
  AND e.event IN ({EXPEDITION_EVENTS})
  AND e.prod = {PROD_ID}
GROUP BY e.dt, `主城等级`
ORDER BY e.dt, `主城等级`
LIMIT 300
""".strip()

SQL_WEEKLY_PAY_DISTRIBUTION = f"""
WITH user_week AS (
    SELECT w.week_start,
           u.uid,
           u.channel,
           u.paytotal
    FROM (
        SELECT u.uid,
               u.dt,
               {CHANNEL_EXPR_U} AS channel,
               {_pay_value("u")} AS paytotal
        FROM `user` u
        WHERE u.dt IN ({", ".join(_week_snapshot_dt_expr(i) for i in range(7, -1, -1))})
          AND u.prod = {PROD_ID}
    ) u
    JOIN (
        SELECT DATE_SUB({LATEST_WEEK_START}, INTERVAL 7 WEEK) AS week_start, {_week_snapshot_dt_expr(7)} AS snapshot_dt
        UNION ALL SELECT DATE_SUB({LATEST_WEEK_START}, INTERVAL 6 WEEK), {_week_snapshot_dt_expr(6)}
        UNION ALL SELECT DATE_SUB({LATEST_WEEK_START}, INTERVAL 5 WEEK), {_week_snapshot_dt_expr(5)}
        UNION ALL SELECT DATE_SUB({LATEST_WEEK_START}, INTERVAL 4 WEEK), {_week_snapshot_dt_expr(4)}
        UNION ALL SELECT DATE_SUB({LATEST_WEEK_START}, INTERVAL 3 WEEK), {_week_snapshot_dt_expr(3)}
        UNION ALL SELECT DATE_SUB({LATEST_WEEK_START}, INTERVAL 2 WEEK), {_week_snapshot_dt_expr(2)}
        UNION ALL SELECT DATE_SUB({LATEST_WEEK_START}, INTERVAL 1 WEEK), {_week_snapshot_dt_expr(1)}
        UNION ALL SELECT {LATEST_WEEK_START}, {_week_snapshot_dt_expr(0)}
    ) w ON w.snapshot_dt = u.dt
)
SELECT week_start AS `事件发生时间`,
       channel AS `渠道`,
       COUNT(DISTINCT CASE WHEN paytotal > 0 THEN uid END) AS `全部用户`,
       COUNT(DISTINCT CASE WHEN paytotal > 0 AND paytotal < 500 THEN uid END) AS `(-∞, 500)`,
       COUNT(DISTINCT CASE WHEN paytotal >= 500 AND paytotal < 1000 THEN uid END) AS `[500, 1000)`,
       COUNT(DISTINCT CASE WHEN paytotal >= 1000 AND paytotal < 2000 THEN uid END) AS `[1000, 2000)`,
       COUNT(DISTINCT CASE WHEN paytotal >= 2000 THEN uid END) AS `[2000, +∞)`
FROM user_week
GROUP BY week_start, channel
ORDER BY week_start, channel
LIMIT 300
""".strip()

SQL_PAY_EVENT_DISTRIBUTION = f"""
WITH pay_events AS (
    SELECT {PRODUCT_ID} AS gift_name
    FROM `event` e
    WHERE {_dt_between("e", 29)}
      AND e.event IN ({PAY_EVENTS})
      AND e.prod = {PROD_ID}
)
SELECT gift_name AS `购买礼包名`,
       COUNT(*) AS `购买次数`
FROM pay_events
GROUP BY gift_name
ORDER BY `购买次数` DESC
LIMIT 50
""".strip()

SQL_ACQUISITION_CHANNEL_PAY = f"""
WITH bounds AS (
    SELECT {_date_expr(30)} AS start_dt,
           {_date_expr(1)} AS max_dt
), cohort AS (
    SELECT u.dt AS cohort_dt,
           u.uid,
           {CHANNEL_EXPR_U} AS channel,
           {_pay_value("u", "pay1")} AS pay1,
           CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(u.dt AS CHAR), '%Y%m%d'), INTERVAL 6 DAY), '%Y%m%d') AS SIGNED) AS d7_dt,
           b.max_dt
    FROM `user` u
    JOIN bounds b ON u.dt BETWEEN b.start_dt AND b.max_dt
    WHERE u.prod = {PROD_ID}
      AND JSON_UNQUOTE(JSON_EXTRACT(u.userinfo, '$.regdate')) = CAST(u.dt AS CHAR)
)
SELECT STR_TO_DATE(CAST(cohort_dt AS CHAR), '%Y%m%d') AS `日期`,
       channel AS `渠道`,
       COUNT(DISTINCT c.uid) AS `账号注册用户数`,
       ROUND(SUM(c.pay1), 2) AS `首日付费金额`,
       ROUND(SUM(CASE WHEN d7.dt IS NOT NULL THEN {_pay_value("d7", "pay7")} END), 2) AS `7日累计付费金额`,
       ROUND(SUM({_pay_value("latest")}), 2) AS `累计付费金额`
FROM cohort c
LEFT JOIN `user` d7
  ON d7.uid = c.uid
 AND d7.prod = {PROD_ID}
 AND d7.dt = c.d7_dt
LEFT JOIN `user` latest
  ON latest.uid = c.uid
 AND latest.prod = {PROD_ID}
 AND latest.dt = c.max_dt
GROUP BY cohort_dt, channel
ORDER BY cohort_dt DESC, `累计付费金额` DESC
LIMIT 300
""".strip()

SQL_ACTIVITY_PARTICIPATION_RATE = f"""
WITH dau AS (
    SELECT e.dt, COUNT(DISTINCT e.uid) AS dau
    FROM `event` e
    WHERE {_dt_between("e", 29)}
      AND e.event IN ({LOGIN_EVENTS})
      AND e.prod = {PROD_ID}
    GROUP BY e.dt
), act AS (
    SELECT e.dt, e.event, COUNT(DISTINCT e.uid) AS users
    FROM `event` e
    WHERE {_dt_between("e", 29)}
      AND e.event IN ({ACTIVITY_EVENTS})
      AND e.prod = {PROD_ID}
    GROUP BY e.dt, e.event
)
SELECT STR_TO_DATE(CAST(act.dt AS CHAR), '%Y%m%d') AS `日期`,
       act.event AS `活动类型`,
       ROUND(act.users / NULLIF(dau.dau, 0) * 100, 2) AS `活动参与率`
FROM act
JOIN dau ON dau.dt = act.dt
ORDER BY act.dt, act.event
LIMIT 300
""".strip()

SQL_ACTIVITY_AVG_TIMES = f"""
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
       e.event AS `活动类型`,
       ROUND(COUNT(*) / NULLIF(COUNT(DISTINCT e.uid), 0), 2) AS `人均参与次数`
FROM `event` e
WHERE {_dt_between("e", 29)}
  AND e.event IN ({ACTIVITY_EVENTS})
  AND e.prod = {PROD_ID}
GROUP BY e.dt, e.event
ORDER BY e.dt, e.event
LIMIT 300
""".strip()

SQL_ACTIVITY_LEVEL = f"""
SELECT
    CASE
        WHEN main_level BETWEEN 1 AND 3 THEN '1-3'
        WHEN main_level BETWEEN 4 AND 6 THEN '4-6'
        WHEN main_level BETWEEN 7 AND 9 THEN '7-9'
        WHEN main_level BETWEEN 10 AND 12 THEN '10-12'
        WHEN main_level BETWEEN 13 AND 15 THEN '13-15'
        WHEN main_level BETWEEN 16 AND 18 THEN '16-18'
        WHEN main_level BETWEEN 19 AND 21 THEN '19-21'
        WHEN main_level BETWEEN 22 AND 24 THEN '22-24'
        WHEN main_level BETWEEN 25 AND 27 THEN '25-27'
        WHEN main_level BETWEEN 28 AND 30 THEN '28-30'
        WHEN main_level = 31 THEN '31'
    END AS `等级段`,
    COUNT(DISTINCT uid) AS `参与人数`
FROM (
    SELECT
        e.uid,
        CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_mainBuildingLevel')), '') AS SIGNED) AS main_level
    FROM `event` e
    WHERE {_dt_between("e", 29)}
      AND e.prod = {PROD_ID}
      AND e.event IN ({ACTIVITY_EVENTS})
) t
WHERE main_level BETWEEN 1 AND 31
GROUP BY `等级段`
ORDER BY
    CASE `等级段`
        WHEN '1-3' THEN 1
        WHEN '4-6' THEN 4
        WHEN '7-9' THEN 7
        WHEN '10-12' THEN 10
        WHEN '13-15' THEN 13
        WHEN '16-18' THEN 16
        WHEN '19-21' THEN 19
        WHEN '22-24' THEN 22
        WHEN '25-27' THEN 25
        WHEN '28-30' THEN 28
        WHEN '31' THEN 31
        ELSE 999
    END
LIMIT 1000
""".strip()

SQL_WEEKLY_ACTIVITY_DISTRIBUTION = f"""
SELECT
    e.event AS `活动类型`,
    COUNT(*) AS `参与次数`,
    COUNT(DISTINCT e.uid) AS `参与人数`,
    ROUND(COUNT(*) / NULLIF(COUNT(DISTINCT e.uid), 0), 2) AS `人均参与次数`
FROM `event` e
WHERE {_dt_between("e", 6)}
  AND e.prod = {PROD_ID}
  AND e.event IN ({ACTIVITY_EVENTS})
GROUP BY e.event
ORDER BY `参与次数` DESC
LIMIT 1000
""".strip()

SQL_NEWBIE_ACTIVITY_RETENTION = f"""
WITH participants AS (
    SELECT e.uid, MIN(e.dt) AS participate_dt
    FROM `event` e
    WHERE {_dt_between("e", 35)}
      AND e.event IN ('ActivityCommanderTask','ActivityArmsRaceTask','ActivityChestCount')
      AND e.prod = {PROD_ID}
    GROUP BY e.uid
), retained AS (
    SELECT p.participate_dt,
           COUNT(DISTINCT p.uid) AS participants,
           COUNT(DISTINCT CASE WHEN u.dt = CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(p.participate_dt AS CHAR), '%Y%m%d'), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
                                AND JSON_UNQUOTE(JSON_EXTRACT(u.remain, '$.remain1')) = '1' THEN p.uid END) AS r1,
           COUNT(DISTINCT CASE WHEN u.dt = CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(p.participate_dt AS CHAR), '%Y%m%d'), INTERVAL 7 DAY), '%Y%m%d') AS SIGNED)
                                AND JSON_UNQUOTE(JSON_EXTRACT(u.remain, '$.remain7')) = '1' THEN p.uid END) AS r7
    FROM participants p
    LEFT JOIN `user` u
      ON u.uid = p.uid
     AND u.dt BETWEEN p.participate_dt AND {_date_expr(1)}
     AND u.prod = {PROD_ID}
    WHERE p.participate_dt <= {_date_expr(8)}
    GROUP BY p.participate_dt
)
SELECT STR_TO_DATE(CAST(participate_dt AS CHAR), '%Y%m%d') AS `日期`,
       participants AS `参与新手活动用户数`,
       ROUND(r1 / NULLIF(participants, 0) * 100, 2) AS `第1日`,
       ROUND(r7 / NULLIF(participants, 0) * 100, 2) AS `第7日`
FROM retained
ORDER BY participate_dt
""".strip()

SQL_FESTIVAL_PAY_RETENTION = f"""
WITH participants AS (
    SELECT e.uid, MIN(e.dt) AS participate_dt
    FROM `event` e
    WHERE {_dt_between("e", 35)}
      AND e.event IN ('ActivityAllianceBossBattleRet','ActivityAllianceBossChoose','ActivityAllianceBossDonation','ActivityAllianceBossReward','ActivityWorldBoss','AllianceDuelAlliancePoint','AllianceDuelPersonalPoint','AllianceDuelBoxOpen')
      AND e.prod = {PROD_ID}
    GROUP BY e.uid
), user_pay AS (
    SELECT p.participate_dt,
           COUNT(DISTINCT p.uid) AS participants,
           COUNT(DISTINCT CASE WHEN {_pay_value('u', 'pay1')} > 0 THEN p.uid END) AS pay0,
           COUNT(DISTINCT CASE WHEN {_pay_value('u', 'pay7')} > 0 THEN p.uid END) AS pay7
    FROM participants p
    LEFT JOIN `user` u ON u.uid = p.uid AND u.dt = p.participate_dt AND u.prod = {PROD_ID}
    WHERE p.participate_dt <= {_date_expr(8)}
    GROUP BY p.participate_dt
)
SELECT STR_TO_DATE(CAST(participate_dt AS CHAR), '%Y%m%d') AS `日期`,
       participants AS `参与节日活动用户数`,
       ROUND(pay0 / NULLIF(participants, 0) * 100, 2) AS `当日`,
       ROUND(pay7 / NULLIF(participants, 0) * 100, 2) AS `第7日`
FROM user_pay
ORDER BY participate_dt
""".strip()

GOLD_FREE_DELTA = _json_num("e", "personal", "ed_changeFree")
GOLD_PAID_DELTA = _json_num("e", "personal", "ed_changePaid")
GOLD_DELTA = f"{GOLD_FREE_DELTA} + {GOLD_PAID_DELTA}"
GOLD_ROUTE = f"COALESCE({_json_text('e', 'personal', 'ed_route')}, {_json_text('e', 'personal', 'ed_detailReason')}, '未知')"

SQL_GOLD_CHANGE = f"""
SELECT
    STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
    ROUND(SUM(GREATEST({GOLD_FREE_DELTA}, 0)), 2) AS `免费钻石获取量`,
    ROUND(ABS(SUM(LEAST({GOLD_FREE_DELTA}, 0))), 2) AS `免费钻石消耗量`,
    ROUND(SUM({GOLD_FREE_DELTA}), 2) AS `免费钻石存量变化`,
    ROUND(SUM(GREATEST({GOLD_PAID_DELTA}, 0)), 2) AS `付费钻石获取量`,
    ROUND(ABS(SUM(LEAST({GOLD_PAID_DELTA}, 0))), 2) AS `付费钻石消耗量`,
    ROUND(SUM({GOLD_PAID_DELTA}), 2) AS `付费钻石存量变化`
FROM `event` e
WHERE {_dt_between("e", 29)}
  AND e.event = 'GoldChange'
  AND e.prod = {PROD_ID}
GROUP BY e.dt
ORDER BY e.dt
LIMIT 1000
""".strip()

SQL_GOLD_SOURCE = f"""
SELECT
    {GOLD_ROUTE} AS `获取途径`,
    ROUND(SUM({GOLD_FREE_DELTA}), 2) AS `免费钻石获取量`
FROM `event` e
WHERE {_dt_between("e", 29)}
  AND e.event = 'GoldChange'
  AND e.prod = {PROD_ID}
  AND {GOLD_FREE_DELTA} > 0
GROUP BY `获取途径`
ORDER BY `免费钻石获取量` DESC
LIMIT 1000
""".strip()

SQL_GOLD_SINK = f"""
SELECT
    {GOLD_ROUTE} AS `消耗途径`,
    ROUND(ABS(SUM(LEAST({GOLD_FREE_DELTA}, 0))), 2) AS `免费钻石消耗量`,
    ROUND(ABS(SUM(LEAST({GOLD_PAID_DELTA}, 0))), 2) AS `付费钻石消耗量`
FROM `event` e
WHERE {_dt_between("e", 29)}
  AND e.event = 'GoldChange'
  AND e.prod = {PROD_ID}
  AND ({GOLD_FREE_DELTA} < 0 OR {GOLD_PAID_DELTA} < 0)
GROUP BY `消耗途径`
ORDER BY (`免费钻石消耗量` + `付费钻石消耗量`) DESC
LIMIT 1000
""".strip()

SQL_STARTER_PACK_REPURCHASE = f"""
WITH pay_events AS (
    SELECT
        e.uid,
        e.dt,
        JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.orderId')) AS order_id,
        JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.productid')) AS product_id
    FROM `event` e
    WHERE {_dt_between("e", 36)}
      AND e.prod = {PROD_ID}
      AND e.event = 'ServerPayLog'
      AND JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.productid')) IS NOT NULL
), first_buy AS (
    SELECT
        uid,
        MIN(dt) AS first_buy_dt
    FROM pay_events
    WHERE product_id IN ('85003')
    GROUP BY uid
), repurchase AS (
    SELECT
        s.uid,
        s.first_buy_dt,
        MAX(
            CASE
                WHEN p.dt > s.first_buy_dt
                 AND p.dt <= CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(s.first_buy_dt AS CHAR), '%Y%m%d'), INTERVAL 7 DAY), '%Y%m%d') AS SIGNED)
                THEN 1
                ELSE 0
            END
        ) AS has_repurchase_7d
    FROM first_buy s
    LEFT JOIN pay_events p
      ON p.uid = s.uid
     AND p.dt > s.first_buy_dt
     AND p.dt <= CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(s.first_buy_dt AS CHAR), '%Y%m%d'), INTERVAL 7 DAY), '%Y%m%d') AS SIGNED)
    WHERE s.first_buy_dt <= {_date_expr(7)}
    GROUP BY s.uid, s.first_buy_dt
)
SELECT
    STR_TO_DATE(CAST(first_buy_dt AS CHAR), '%Y%m%d') AS `首购日期`,
    COUNT(*) AS `购买新手礼包用户数`,
    SUM(has_repurchase_7d) AS `7日内复购用户数`,
    ROUND(SUM(has_repurchase_7d) / NULLIF(COUNT(*), 0) * 100, 2) AS `7日内复购率`
FROM repurchase
GROUP BY first_buy_dt
ORDER BY first_buy_dt
LIMIT 1000
""".strip()

SQL_MONTH_CARD_RETENTION = f"""
WITH pay_events AS (
    SELECT e.uid, MIN(e.dt) AS buy_dt
    FROM `event` e
    WHERE e.dt BETWEEN {_date_expr(61)} AND {_date_expr(31)}
      AND e.prod = {PROD_ID}
      AND e.event IN ({PAY_EVENTS})
      AND (LOWER({PRODUCT_ID}) LIKE '%month%' OR {PRODUCT_ID} LIKE '%月卡%')
    GROUP BY e.uid
), active_events AS (
    SELECT e.dt,
           e.uid
    FROM `event` e
    WHERE e.dt BETWEEN {_date_expr(60)} AND {_date_expr(1)}
      AND e.event IN ({LOGIN_EVENTS})
      AND e.prod = {PROD_ID}
    GROUP BY e.dt, e.uid
), login_events AS (
    SELECT p.uid,
           DATEDIFF(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'), STR_TO_DATE(CAST(p.buy_dt AS CHAR), '%Y%m%d')) AS retain_day
    FROM pay_events p
    JOIN active_events e ON e.uid = p.uid
    WHERE e.dt BETWEEN p.buy_dt AND CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(p.buy_dt AS CHAR), '%Y%m%d'), INTERVAL 30 DAY), '%Y%m%d') AS SIGNED)
)
SELECT CONCAT('第', d.retain_day, '日') AS `留存日`,
       ROUND(COUNT(DISTINCT l.uid) / NULLIF((SELECT COUNT(DISTINCT uid) FROM pay_events), 0) * 100, 2) AS `留存率`
FROM (
    SELECT 1 AS retain_day UNION ALL SELECT 7 UNION ALL SELECT 14 UNION ALL SELECT 30
) d
LEFT JOIN login_events l ON l.retain_day = d.retain_day
GROUP BY d.retain_day
ORDER BY d.retain_day
""".strip()

SQL_HERO_GROWTH = f"""
SELECT
    JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_heroId')) AS `将领ID`,
    COUNT(CASE WHEN e.event = 'HeroStarUp' THEN 1 END) AS `升星次数`,
    COUNT(DISTINCT CASE WHEN e.event = 'HeroStarUp' THEN e.uid END) AS `升星用户数`,
    COUNT(CASE WHEN e.event = 'HeroLevelUp' THEN 1 END) AS `升级次数`,
    COUNT(DISTINCT CASE WHEN e.event = 'HeroLevelUp' THEN e.uid END) AS `升级用户数`
FROM `event` e
WHERE {_dt_between("e", 29)}
  AND e.event IN ('HeroLevelUp', 'HeroStarUp')
  AND NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_heroId')), '') IS NOT NULL
GROUP BY `将领ID`
ORDER BY (`升星次数` + `升级次数`) DESC
LIMIT 1000;
""".strip()

SQL_SSR_HERO_LEVEL = f"""
WITH base AS (
    SELECT
        e.uid,
        e.dt,
        e.time,
        JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_heroId')) AS hero_id,
        NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_heroStar')), '') AS hero_star_levelup,
        NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_newStar')), '') AS hero_star_starup,
        CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_currentLevel')), '') AS DECIMAL(18,4)) AS current_level,
        CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_heroLevel')), '') AS DECIMAL(18,4)) AS event_hero_level
    FROM `event` e
    WHERE {_dt_between("e", 29)}
      AND e.event IN ('HeroLevelUp', 'HeroStarUp')
      AND e.prod = {PROD_ID}
),
ranked AS (
    SELECT
        uid,
        hero_id,
        COALESCE(hero_star_levelup, hero_star_starup, '未知') AS hero_star,
        COALESCE(current_level, event_hero_level, 0) AS hero_level,
        ROW_NUMBER() OVER (
            PARTITION BY uid, hero_id
            ORDER BY dt DESC, time DESC
        ) AS rn
    FROM base
    WHERE NULLIF(hero_id, '') IS NOT NULL
)
SELECT
    hero_id AS `将领ID`,
    hero_star AS `英雄星级`,
    COUNT(*) AS `全部用户`,
    SUM(CASE WHEN hero_level BETWEEN 1 AND 10 THEN 1 ELSE 0 END) AS `1-10`,
    SUM(CASE WHEN hero_level BETWEEN 11 AND 20 THEN 1 ELSE 0 END) AS `11-20`,
    SUM(CASE WHEN hero_level >= 21 THEN 1 ELSE 0 END) AS `21+`
FROM ranked
WHERE rn = 1
GROUP BY hero_id, hero_star
ORDER BY `全部用户` DESC
LIMIT 1000;
""".strip()

SQL_CITY_AVG_LEVEL = f"""
SELECT ROUND(AVG(COALESCE(CAST({_json_text('u', 'lastinfo', 'blevel')} AS DECIMAL(18,4)), 0)), 2) AS `主城平均等级`
FROM `user` u
WHERE u.dt = {_date_expr(1)}
  AND u.prod = {PROD_ID}
""".strip()

SQL_CITY_UPGRADE_METRIC = _metric_sql("event", "当日主城升级次数", f"e.event IN ({BUILDING_EVENTS})")
SQL_BUILDING_UPGRADE_METRIC = _metric_sql("event", "当日建筑升级次数", "e.event = 'BuildingUpgrade'")
SQL_TECH_UPGRADE_METRIC = _metric_sql("event", "当日科技升级次数", f"e.event IN ({TECH_EVENTS})")

SQL_CITY_LEVEL_USERS = f"""
SELECT COALESCE(CAST(CAST({_json_text('u', 'lastinfo', 'blevel')} AS DECIMAL(18,4)) AS CHAR), '未知') AS `主城等级`,
       COUNT(DISTINCT u.uid) AS `玩家数`
FROM `user` u
WHERE u.dt = {_date_expr(1)}
  AND u.prod = {PROD_ID}
GROUP BY `主城等级`
ORDER BY CAST(`主城等级` AS SIGNED)
LIMIT 50
""".strip()

BUILDING_ID = f"COALESCE({_json_text('e', 'ext', 'ed_buildingId')}, {_json_text('e', 'ext', 'ed_metaId')}, e.event)"

SQL_BUILDING_BY_TYPE = f"""
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
       {BUILDING_ID} AS `建筑`,
       COUNT(*) AS `升级次数`
FROM `event` e
WHERE {_dt_between("e", 29)}
  AND e.event IN ({BUILDING_EVENTS})
  AND e.prod = {PROD_ID}
GROUP BY e.dt, `建筑`
ORDER BY e.dt, `建筑`
LIMIT 300
""".strip()

SQL_BUILDING_BY_CITY = f"""
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
       {CITY_LEVEL_E} AS `主城等级`,
       COUNT(*) AS `建筑升级次数`
FROM `event` e
WHERE {_dt_between("e", 29)}
  AND e.event IN ({BUILDING_EVENTS})
  AND e.prod = {PROD_ID}
GROUP BY e.dt, `主城等级`
ORDER BY e.dt, `主城等级`
LIMIT 300
""".strip()

SQL_TECH_BY_TYPE = f"""
SELECT e.event AS `科技名称`,
       COUNT(*) AS `升级科技.总次数`
FROM `event` e
WHERE {_dt_between("e", 29)}
  AND e.event IN ({TECH_EVENTS})
  AND e.prod = {PROD_ID}
GROUP BY e.event
ORDER BY `升级科技.总次数` DESC
LIMIT 50
""".strip()

SQL_TECH_BY_CITY = f"""
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
       {CITY_LEVEL_E} AS `主城等级`,
       COUNT(*) AS `科技升级次数`
FROM `event` e
WHERE {_dt_between("e", 29)}
  AND e.event IN ({TECH_EVENTS})
  AND e.prod = {PROD_ID}
GROUP BY e.dt, `主城等级`
ORDER BY e.dt, `主城等级`
LIMIT 300
""".strip()

SQL_ARMY_RECRUIT = f"""
SELECT COALESCE(
           NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_cardType')), ''),
           '未知'
       ) AS `招募池ID`,
       CASE COALESCE(
           NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.personal, '$.ed_recruitNumType')), ''),
           '未知'
       )
           WHEN 'ONE' THEN '单抽'
           WHEN 'TEN' THEN '十连抽'
           ELSE '未知'
       END AS `招募方式`,
       COUNT(*) AS `招募次数`,
       COUNT(DISTINCT e.uid) AS `招募用户数`
FROM `event` e
WHERE {_dt_between("e", 29)}
  AND e.event = 'HeroRecruit'
  AND e.prod = {PROD_ID}
GROUP BY `招募池ID`, `招募方式`
ORDER BY `招募池ID`, `招募方式`
LIMIT 100;
""".strip()

SPEEDUP_TYPE = f"COALESCE({_json_text('e', 'ext', 'ed_detailReason')}, {_json_text('e', 'ext', 'ed_route')}, e.event)"

SQL_SPEEDUP = f"""
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
       {SPEEDUP_TYPE} AS `加速类型`,
       COUNT(*) AS `使用加速次数`,
       COUNT(DISTINCT e.uid) AS `使用加速人数`,
       ROUND(COUNT(*) / NULLIF(COUNT(DISTINCT e.uid), 0), 2) AS `人均使用加速次数`
FROM `event` e
WHERE {_dt_between("e", 29)}
  AND e.event IN ('BuildingUpgrade','BuildingIdleUpgrade','ArmyUpgrade')
  AND e.prod = {PROD_ID}
GROUP BY e.dt, `加速类型`
ORDER BY e.dt, `使用加速次数` DESC
LIMIT 300
""".strip()

SQL_CITY_FUNNEL = f"""
WITH latest AS (
    SELECT u.uid,
           COALESCE(CAST({_json_text('u', 'lastinfo', 'blevel')} AS DECIMAL(18,4)), 0) AS blevel
    FROM `user` u
    WHERE u.dt = {_date_expr(1)}
      AND u.prod = {PROD_ID}
), steps AS (
    SELECT 1 AS step_order, '主城1级+' AS step_name, 1 AS min_level UNION ALL
    SELECT 2, '主城5级+', 5 UNION ALL
    SELECT 3, '主城10级+', 10 UNION ALL
    SELECT 4, '主城15级+', 15 UNION ALL
    SELECT 5, '主城20级+', 20
)
SELECT step_name AS `主城升级步骤`,
       COUNT(DISTINCT CASE WHEN latest.blevel >= steps.min_level THEN latest.uid END) AS `用户数`
FROM steps
CROSS JOIN latest
GROUP BY step_order, step_name
ORDER BY step_order
""".strip()

REMAINING_VIEW_SQL: dict[str, ViewSql] = {
    "9d4add7a8be048ea9c7beb62a43e50cc": ViewSql("出征数据", "出征事件数", "metric", ("出征事件数", "日环比", "周同比"), y_axis=("出征事件数", "日环比", "周同比"), sql=SQL_EXPEDITION_COUNT),
    "9325211a9f594376bf818cec639aa103": ViewSql("出征数据", "兵种升级事件数", "metric", ("兵种升级事件数", "日环比", "周同比"), y_axis=("兵种升级事件数", "日环比", "周同比"), sql=SQL_ARMY_UPGRADE_COUNT),
    "440303dfdf39408ba86ffb222f3334f2": ViewSql("出征数据", "竞技场/出征平均战力", "metric", ("竞技场/出征平均战力", "日环比", "周同比"), y_axis=("竞技场/出征平均战力", "日环比", "周同比"), sql=SQL_EXPEDITION_AVG_POWER),
    "0b849c96c0a3480c9e940b92995d5e3e": ViewSql("出征数据", "荣耀远征事件数", "metric", ("荣耀远征事件数", "日环比", "周同比"), y_axis=("荣耀远征事件数", "日环比", "周同比"), sql=SQL_HONOR_EXPEDITION_COUNT),
    "f2be189bf85f4181bc7191cd5138561f": ViewSql("出征数据", "出征相关明细", "table", ("日期", "出征事件数", "人均事件数", "参与用户数"), columns=("日期", "出征事件数", "人均事件数", "参与用户数"), sql=SQL_EXPEDITION_DETAIL),
    "e02bdbafdd364d3cba9f991f94896c86": ViewSql("出征数据", "过去7日各兵种出征情况", "table", ("日期", "出征类型", "目标类型", "大本等级", "出征次数", "出征用户数", "出征ID数", "人均出征次数", "平均预计耗时分钟", "平均出征战力", "出征总战力"), columns=("日期", "出征类型", "目标类型", "大本等级", "出征次数", "出征用户数", "出征ID数", "人均出征次数", "平均预计耗时分钟", "平均出征战力", "出征总战力"), sql=SQL_ARMY_7D),
    "59a8dfd8d6e341988edfbf1666872aae": ViewSql("出征数据", "近七天英雄出征量分布", "table", ("日期", "英雄ID", "出征次数"), columns=("日期", "英雄ID", "出征次数"), sql=SQL_HERO_EXPEDITION_COUNT),
    "848927b0833443d39a93797c3507368e": ViewSql("出征数据", "各等级出征胜率", "table", ("等级", "目标类型", "出征结果次数", "出征用户数", "胜利次数", "出征胜率"), columns=("等级", "目标类型", "出征结果次数", "出征用户数", "胜利次数", "出征胜率"), sql=SQL_LEVEL_WIN_RATE),
    "344c936b561f44f6bc29cc2663f3f651": ViewSql("出征数据", "各英雄出征胜率", "table", ("英雄ID", "出征次数", "胜利次数", "出征胜率"), columns=("英雄ID", "出征次数", "胜利次数", "出征胜率"), sql=SQL_HERO_WIN_RATE),
    "61c21b5974844638a3d7370971de58c9": ViewSql("出征数据", "各主城等级参与演习次数", "line", ("日期", "主城等级", "参与演习次数"), ("日期",), ("参与演习次数",), sql=SQL_DRILL_BY_CITY_LEVEL),
    "f6ca362eb4274830b3298b0227a8ab88": ViewSql("付费概览", "充值用户周累充分布", "table", ("事件发生时间", "渠道", "全部用户", "(-∞, 500)", "[500, 1000)", "[1000, 2000)", "[2000, +∞)"), columns=("事件发生时间", "渠道", "全部用户", "(-∞, 500)", "[500, 1000)", "[1000, 2000)", "[2000, +∞)"), sql=SQL_WEEKLY_PAY_DISTRIBUTION),
    "4045ede9004f48de9fb8b8aed5f79287": ViewSql("渠道分析", "各渠道充值用户周累充分布", "table", ("事件发生时间", "渠道", "全部用户", "(-∞, 500)", "[500, 1000)", "[1000, 2000)", "[2000, +∞)"), columns=("事件发生时间", "渠道", "全部用户", "(-∞, 500)", "[500, 1000)", "[1000, 2000)", "[2000, +∞)"), sql=SQL_WEEKLY_PAY_DISTRIBUTION),
    "fdb8f135e2644bcb80b7634882809f7e": ViewSql("付费概览", "付费事件分布", "column", ("购买礼包名", "购买次数"), ("购买礼包名",), ("购买次数",), sql=SQL_PAY_EVENT_DISTRIBUTION),
    "531012d01f104a509da2d1926692ee1d": ViewSql("投放看板", "各渠道注册与付费", "table", ("日期", "渠道", "账号注册用户数", "首日付费金额", "7日累计付费金额", "累计付费金额"), columns=("日期", "渠道", "账号注册用户数", "首日付费金额", "7日累计付费金额", "累计付费金额"), sql=SQL_ACQUISITION_CHANNEL_PAY),
    "c794f6521d8b44d39f78eabdf109896b": ViewSql("活动分析", "各类活动参与率", "line", ("日期", "活动类型", "活动参与率"), ("日期",), ("活动参与率",), sql=SQL_ACTIVITY_PARTICIPATION_RATE),
    "6266951d0e1842e2b259121ab06f7a61": ViewSql("活动分析", "各类活动人均参与次数", "line", ("日期", "活动类型", "人均参与次数"), ("日期",), ("人均参与次数",), sql=SQL_ACTIVITY_AVG_TIMES),
    "13d554014c854e508ff016d93a6f3899": ViewSql("活动分析", "各等级段参与日常活动的人数分布", "column", ("等级段", "参与人数"), ("等级段",), ("参与人数",), columns=("等级段", "参与人数"), sql=SQL_ACTIVITY_LEVEL),
    "161fd0d2996a49a29e82606e6db7d95b": ViewSql("活动分析", "每周活动参与次数分布", "column", ("活动类型", "参与次数", "参与人数", "人均参与次数"), ("活动类型",), ("参与次数",), columns=("活动类型", "参与次数", "参与人数", "人均参与次数"), sql=SQL_WEEKLY_ACTIVITY_DISTRIBUTION),
    "9684a569ed034fb0b8a106a9817effaa": ViewSql("活动分析", "参与新手活动的后续7日留存率", "table", ("日期", "参与新手活动用户数", "第1日", "第7日"), columns=("日期", "参与新手活动用户数", "第1日", "第7日"), sql=SQL_NEWBIE_ACTIVITY_RETENTION),
    "095b1cf41cd64844b1f78f07ceccb7bf": ViewSql("活动分析", "参与节日活动的后续7日付费留存率", "table", ("日期", "参与节日活动用户数", "当日", "第7日"), columns=("日期", "参与节日活动用户数", "当日", "第7日"), sql=SQL_FESTIVAL_PAY_RETENTION),
    "4cc60cadf26e4b2f945c672f2648d205": ViewSql("经济系统", "钻石消耗获取情况", "line", ("日期", "免费钻石获取量", "免费钻石消耗量", "免费钻石存量变化", "付费钻石获取量", "付费钻石消耗量", "付费钻石存量变化"), ("日期",), ("免费钻石获取量", "免费钻石消耗量", "免费钻石存量变化", "付费钻石获取量", "付费钻石消耗量", "付费钻石存量变化"), sql=SQL_GOLD_CHANGE),
    "df837cb59810483f84fb0e7cd420646a": ViewSql("经济系统", "免费钻石获取途径分布", "column", ("获取途径", "免费钻石获取量"), ("获取途径",), ("免费钻石获取量",), columns=("获取途径", "免费钻石获取量"), sql=SQL_GOLD_SOURCE),
    "fda6854e188c44c4b35e75c9af6d9854": ViewSql("经济系统", "钻石消耗途径分布", "column", ("消耗途径", "免费钻石消耗量", "付费钻石消耗量"), ("消耗途径",), ("免费钻石消耗量", "付费钻石消耗量"), columns=("消耗途径", "免费钻石消耗量", "付费钻石消耗量"), sql=SQL_GOLD_SINK),
    "15da41b65ee64aba854e2de701a728bc": ViewSql("礼包付费概览", "购买新手礼包用户复购率", "line", ("首购日期", "购买新手礼包用户数", "7日内复购用户数", "7日内复购率"), ("首购日期",), ("7日内复购率",), columns=("首购日期", "购买新手礼包用户数", "7日内复购用户数", "7日内复购率"), sql=SQL_STARTER_PACK_REPURCHASE),
    "f113ac14e8994d12814452040b702424": ViewSql("礼包付费概览", "购买月卡用户的30日留存", "line", ("留存日", "留存率"), ("留存日",), ("留存率",), sql=SQL_MONTH_CARD_RETENTION),
    "8b3e5b7179af442e8fded00ae25a0245": ViewSql("渠道分析", "活跃用户数（按渠道）", "line", ("日期", "渠道", "活跃用户数"), ("日期",), ("活跃用户数",), sql=SQL_ACTIVE_BY_CHANNEL),
    "e13ce279fb3d432da20336b1f93eaf4f": ViewSql("养成看板", "英雄养成情况", "table", ("将领ID", "升星次数", "升星用户数", "升级次数", "升级用户数"), columns=("将领ID", "升星次数", "升星用户数", "升级次数", "升级用户数"), sql=SQL_HERO_GROWTH),
    "78ddbc37336844b1852ddeaef72f7ecc": ViewSql("养成看板", "SSR英雄的等级分布", "table", ("将领ID", "英雄星级", "全部用户", "1-10", "11-20", "21+"), columns=("将领ID", "英雄星级", "全部用户", "1-10", "11-20", "21+"), sql=SQL_SSR_HERO_LEVEL),
    "4608fb0831cd4845ba881678fb778b2f": ViewSql("主城建设", "主城平均等级", "metric", ("主城平均等级",), y_axis=("主城平均等级",), sql=SQL_CITY_AVG_LEVEL),
    "dbc481fea69d4314af8535600fa4f8c8": ViewSql("主城建设", "当日主城升级次数", "metric", ("当日主城升级次数", "日环比", "周同比"), y_axis=("当日主城升级次数", "日环比", "周同比"), sql=SQL_CITY_UPGRADE_METRIC),
    "48f02edf9a364e1082cd67008cd60b2b": ViewSql("主城建设", "当日建筑升级次数", "metric", ("当日建筑升级次数", "日环比", "周同比"), y_axis=("当日建筑升级次数", "日环比", "周同比"), sql=SQL_BUILDING_UPGRADE_METRIC),
    "8f6dcec8cfdb40b4a7c02139b7d35f56": ViewSql("主城建设", "当日科技升级次数", "metric", ("当日科技升级次数", "日环比", "周同比"), y_axis=("当日科技升级次数", "日环比", "周同比"), sql=SQL_TECH_UPGRADE_METRIC),
    "1b9eb5aac8224dee9ccdf839d5a3988c": ViewSql("主城建设", "各主城等级玩家数", "column", ("主城等级", "玩家数"), ("主城等级",), ("玩家数",), sql=SQL_CITY_LEVEL_USERS),
    "82f560ee39f2409485e7270d2c9db26c": ViewSql("主城建设", "各建筑升级次数", "line", ("日期", "建筑", "升级次数"), ("日期",), ("升级次数",), sql=SQL_BUILDING_BY_TYPE),
    "3a46d6c112284ee98373dbe53baa6290": ViewSql("主城建设", "各主城等级建筑升级次数", "line", ("日期", "主城等级", "建筑升级次数"), ("日期",), ("建筑升级次数",), sql=SQL_BUILDING_BY_CITY),
    "697c622479fb4ab0b768e02c360e6c6f": ViewSql("主城建设", "各科技升级次数", "table", ("科技名称", "升级科技.总次数"), columns=("科技名称", "升级科技.总次数"), sql=SQL_TECH_BY_TYPE),
    "725f639c5ed24cc6a13d6e1fa2430c8a": ViewSql("主城建设", "各主城等级用户科技升级情况", "line", ("日期", "主城等级", "科技升级次数"), ("日期",), ("科技升级次数",), sql=SQL_TECH_BY_CITY),
    "1e41ffdca6b041a6abea363fcb1b8cd2": ViewSql("主城建设", "招募情况", "table", ("招募池ID", "招募方式", "招募次数", "招募用户数"), columns=("招募池ID", "招募方式", "招募次数", "招募用户数"), sql=SQL_ARMY_RECRUIT),
    "1c5f7aa5ae6f47ecb3dcfab37ee5e34e": ViewSql("主城建设", "各类型加速情况", "table", ("日期", "加速类型", "使用加速次数", "使用加速人数", "人均使用加速次数"), columns=("日期", "加速类型", "使用加速次数", "使用加速人数", "人均使用加速次数"), sql=SQL_SPEEDUP),
    "a547eb9c1a1a4f4eba00191abbd9ac62": ViewSql("主城建设", "主城升级漏斗", "funnel", ("主城升级步骤", "用户数"), ("主城升级步骤",), ("用户数",), ("主城升级步骤", "用户数"), sql=SQL_CITY_FUNNEL),
}


REMAINING_VIEW_IDS = tuple(REMAINING_VIEW_SQL)


def axis(field: str) -> dict[str, str]:
    return _axis(field)


def sql_blocks_markdown(view_ids: list[str] | tuple[str, ...] | None = None) -> str:
    blocks: list[str] = []
    for view_id in view_ids or REMAINING_VIEW_IDS:
        view = REMAINING_VIEW_SQL[view_id]
        blocks.append(f"<!-- dashboard-sql:{view_id} -->\n```sql\n{view.sql.strip()}\n```")
    return "\n\n".join(blocks)
