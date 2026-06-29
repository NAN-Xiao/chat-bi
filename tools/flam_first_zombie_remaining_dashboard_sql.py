# -*- coding: utf-8 -*-
"""SQL definitions for remaining flam / first_zombie dashboard components."""

from __future__ import annotations

from dataclasses import dataclass

from flam_first_zombie_active_dashboard_sql import SQL_ACTIVE_BY_CHANNEL
from flam_first_zombie_dashboard_sql import CHANNEL_EXPR_U, DATASOURCE_ID, LOGIN_EVENTS, PAY_EVENTS, TENANT_ID


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


def _bounds(table: str, days: int = 29) -> str:
    return f"""
WITH obs AS (
    SELECT MAX(dt) AS max_dt FROM `{table}`
), bounds AS (
    SELECT CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST(max_dt AS CHAR), '%Y%m%d'), INTERVAL {days} DAY), '%Y%m%d') AS SIGNED) AS start_dt,
           max_dt
    FROM obs
)
""".strip()


def _metric_sql(table: str, metric_name: str, where_clause: str, value_expr: str = "COUNT(*)", days: int = 29) -> str:
    return f"""
{_bounds(table, days)}, daily AS (
    SELECT e.dt,
           {value_expr} AS value
    FROM `{table}` e
    JOIN bounds b ON TRUE
    WHERE e.dt BETWEEN b.start_dt AND b.max_dt
      AND {where_clause}
    GROUP BY e.dt
), metric_dt AS (
    SELECT MAX(dt) AS dt FROM daily
)
SELECT COALESCE(today.value, 0) AS `{metric_name}`,
       ROUND((COALESCE(today.value, 0) - COALESCE(yesterday.value, 0)) / NULLIF(yesterday.value, 0) * 100, 2) AS `日环比`,
       ROUND((COALESCE(today.value, 0) - COALESCE(last_week.value, 0)) / NULLIF(last_week.value, 0) * 100, 2) AS `周同比`
FROM metric_dt m
LEFT JOIN daily today ON today.dt = m.dt
LEFT JOIN daily yesterday ON yesterday.dt = CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST(m.dt AS CHAR), '%Y%m%d'), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
LEFT JOIN daily last_week ON last_week.dt = CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST(m.dt AS CHAR), '%Y%m%d'), INTERVAL 7 DAY), '%Y%m%d') AS SIGNED)
""".strip()


def _axis(field: str) -> dict[str, str]:
    return {"name": field, "value": field}


EXPEDITION_EVENTS = "'WorldMarch','WorldMarchRet','ActivityWorldBoss','ActivityAllianceBossBattleRet','honorExpedition','ArenaResults','TrainingArenaResults','multipleArena'"
ACTIVITY_EVENTS = "'ActivityAllianceBossBattleRet','ActivityAllianceBossChoose','ActivityAllianceBossDonation','ActivityAllianceBossReward','ActivityArmsRaceBoxOpen','ActivityArmsRaceGoalPoint','ActivityArmsRaceTask','ActivityChestCount','ActivityCommanderTask','ActivityWheelCount','ActivityWorldBoss','AllianceDuelAlliancePoint','AllianceDuelPersonalPoint','AllianceDuelBoxOpen'"
BUILDING_EVENTS = "'BuildingUpgrade','BuildingIdleUpgrade'"
TECH_EVENTS = "'BuildingIdleUpgrade','HeroSkillUpgrade','RadarUpgrade','AllianceTechnologyDonation'"
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
{_bounds("event", 29)}, daily AS (
    SELECT e.dt,
           AVG(COALESCE(CAST({_json_text('e', 'ext', 'combatPower')} AS DECIMAL(18,4)),
                        CAST({_json_text('e', 'ext', 'captainPower')} AS DECIMAL(18,4)))) AS value
    FROM `event` e
    JOIN bounds b ON TRUE
    WHERE e.dt BETWEEN b.start_dt AND b.max_dt
      AND e.event IN ({EXPEDITION_EVENTS})
    GROUP BY e.dt
), metric_dt AS (
    SELECT MAX(dt) AS dt FROM daily
)
SELECT ROUND(COALESCE(today.value, 0), 2) AS `竞技场/出征平均战力`,
       ROUND((COALESCE(today.value, 0) - COALESCE(yesterday.value, 0)) / NULLIF(yesterday.value, 0) * 100, 2) AS `日环比`,
       ROUND((COALESCE(today.value, 0) - COALESCE(last_week.value, 0)) / NULLIF(last_week.value, 0) * 100, 2) AS `周同比`
FROM metric_dt m
LEFT JOIN daily today ON today.dt = m.dt
LEFT JOIN daily yesterday ON yesterday.dt = CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST(m.dt AS CHAR), '%Y%m%d'), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
LEFT JOIN daily last_week ON last_week.dt = CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST(m.dt AS CHAR), '%Y%m%d'), INTERVAL 7 DAY), '%Y%m%d') AS SIGNED)
""".strip()

SQL_EXPEDITION_DETAIL = f"""
{_bounds("event", 29)}
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
       COUNT(*) AS `出征事件数`,
       ROUND(COUNT(*) / NULLIF(COUNT(DISTINCT e.uid), 0), 2) AS `人均事件数`,
       COUNT(DISTINCT e.uid) AS `参与用户数`
FROM `event` e
JOIN bounds b ON TRUE
WHERE e.dt BETWEEN b.start_dt AND b.max_dt
  AND e.event IN ({EXPEDITION_EVENTS})
GROUP BY e.dt
ORDER BY e.dt
""".strip()

SQL_ARMY_7D = f"""
{_bounds("event", 6)}
SELECT {ARMY_ID} AS `出征士兵兵种`,
       '兵种升级次数' AS `指标`,
       COUNT(*) AS `阶段汇总`
FROM `event` e
JOIN bounds b ON TRUE
WHERE e.dt BETWEEN b.start_dt AND b.max_dt
  AND e.event = 'ArmyUpgrade'
GROUP BY `出征士兵兵种`
ORDER BY `阶段汇总` DESC
LIMIT 50
""".strip()

SQL_HERO_EXPEDITION_COUNT = f"""
{_bounds("event", 29)}
SELECT {HERO_ID} AS `将领ID`,
       COUNT(*) AS `出征次数`
FROM `event` e
JOIN bounds b ON TRUE
WHERE e.dt BETWEEN b.start_dt AND b.max_dt
  AND e.event IN ({EXPEDITION_EVENTS})
GROUP BY `将领ID`
ORDER BY `出征次数` DESC
LIMIT 50
""".strip()

_WIN_EXPR = "COALESCE(" + _json_text("e", "ext", "battleResult") + ", " + _json_text("e", "ext", "expeditionDungeonResult") + ") IN ('win','success','1','胜利')"

SQL_LEVEL_WIN_RATE = f"""
{_bounds("event", 29)}
SELECT {CITY_LEVEL_E} AS `等级`,
       ROUND(AVG(CASE WHEN {_WIN_EXPR} THEN 1 ELSE 0 END) * 100, 2) AS `出征胜率`
FROM `event` e
JOIN bounds b ON TRUE
WHERE e.dt BETWEEN b.start_dt AND b.max_dt
  AND e.event IN ({EXPEDITION_EVENTS})
GROUP BY `等级`
ORDER BY CAST(`等级` AS SIGNED)
LIMIT 50
""".strip()

SQL_HERO_WIN_RATE = f"""
{_bounds("event", 29)}
SELECT {HERO_ID} AS `将领ID`,
       ROUND(AVG(CASE WHEN {_WIN_EXPR} THEN 1 ELSE 0 END) * 100, 2) AS `各将领出征胜率`
FROM `event` e
JOIN bounds b ON TRUE
WHERE e.dt BETWEEN b.start_dt AND b.max_dt
  AND e.event IN ({EXPEDITION_EVENTS})
GROUP BY `将领ID`
ORDER BY `各将领出征胜率` DESC
LIMIT 50
""".strip()

SQL_DRILL_BY_CITY_LEVEL = f"""
{_bounds("event", 29)}
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
       {CITY_LEVEL_E} AS `主城等级`,
       COUNT(*) AS `参与演习次数`
FROM `event` e
JOIN bounds b ON TRUE
WHERE e.dt BETWEEN b.start_dt AND b.max_dt
  AND e.event IN ({EXPEDITION_EVENTS})
GROUP BY e.dt, `主城等级`
ORDER BY e.dt, `主城等级`
LIMIT 300
""".strip()

SQL_WEEKLY_PAY_DISTRIBUTION = f"""
WITH obs AS (
    SELECT MAX(dt) AS max_dt FROM `user`
), weeks AS (
    SELECT DATE_SUB(STR_TO_DATE(CAST(max_dt AS CHAR), '%Y%m%d'), INTERVAL WEEKDAY(STR_TO_DATE(CAST(max_dt AS CHAR), '%Y%m%d')) DAY) AS latest_week_start
    FROM obs
), bounds AS (
    SELECT CAST(DATE_FORMAT(DATE_SUB(latest_week_start, INTERVAL 7 WEEK), '%Y%m%d') AS SIGNED) AS start_dt,
           max_dt
    FROM obs
    JOIN weeks ON TRUE
), user_week AS (
    SELECT DATE_SUB(STR_TO_DATE(CAST(u.dt AS CHAR), '%Y%m%d'), INTERVAL WEEKDAY(STR_TO_DATE(CAST(u.dt AS CHAR), '%Y%m%d')) DAY) AS week_start,
           u.uid,
           {CHANNEL_EXPR_U} AS channel,
           {_pay_value("u")} AS paytotal,
           ROW_NUMBER() OVER (
               PARTITION BY DATE_SUB(STR_TO_DATE(CAST(u.dt AS CHAR), '%Y%m%d'), INTERVAL WEEKDAY(STR_TO_DATE(CAST(u.dt AS CHAR), '%Y%m%d')) DAY), u.uid
               ORDER BY u.dt DESC
           ) AS rn
    FROM `user` u
    JOIN bounds b ON TRUE
    WHERE u.dt BETWEEN b.start_dt AND b.max_dt
)
SELECT week_start AS `事件发生时间`,
       channel AS `渠道`,
       COUNT(DISTINCT CASE WHEN paytotal > 0 THEN uid END) AS `全部用户`,
       COUNT(DISTINCT CASE WHEN paytotal > 0 AND paytotal < 500 THEN uid END) AS `(-∞, 500)`,
       COUNT(DISTINCT CASE WHEN paytotal >= 500 AND paytotal < 1000 THEN uid END) AS `[500, 1000)`,
       COUNT(DISTINCT CASE WHEN paytotal >= 1000 AND paytotal < 2000 THEN uid END) AS `[1000, 2000)`,
       COUNT(DISTINCT CASE WHEN paytotal >= 2000 THEN uid END) AS `[2000, +∞)`
FROM user_week
WHERE rn = 1
GROUP BY week_start, channel
ORDER BY week_start, channel
LIMIT 300
""".strip()

SQL_PAY_EVENT_DISTRIBUTION = f"""
{_bounds("event", 29)}, pay_events AS (
    SELECT {PRODUCT_ID} AS gift_name
    FROM `event` e
    JOIN bounds b ON TRUE
    WHERE e.dt BETWEEN b.start_dt AND b.max_dt
      AND e.event IN ({PAY_EVENTS})
)
SELECT gift_name AS `购买礼包名`,
       COUNT(*) AS `购买次数`
FROM pay_events
GROUP BY gift_name
ORDER BY `购买次数` DESC
LIMIT 50
""".strip()

SQL_ACQUISITION_CHANNEL_PAY = f"""
WITH obs AS (
    SELECT MAX(dt) AS max_dt FROM `user`
), cohort AS (
    SELECT u.dt AS cohort_dt,
           u.uid,
           {CHANNEL_EXPR_U} AS channel,
           {_pay_value("u", "pay1")} AS pay1,
           {_pay_value("u", "pay7")} AS pay7,
           {_pay_value("u")} AS paytotal
    FROM `user` u
    JOIN obs ON TRUE
    WHERE u.dt BETWEEN CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST(obs.max_dt AS CHAR), '%Y%m%d'), INTERVAL 29 DAY), '%Y%m%d') AS SIGNED)
                   AND obs.max_dt
      AND JSON_UNQUOTE(JSON_EXTRACT(u.userinfo, '$.regdate')) = CAST(u.dt AS CHAR)
)
SELECT STR_TO_DATE(CAST(cohort_dt AS CHAR), '%Y%m%d') AS `日期`,
       channel AS `渠道`,
       COUNT(DISTINCT uid) AS `账号注册用户数`,
       ROUND(SUM(pay1), 2) AS `首日付费金额`,
       ROUND(SUM(pay7), 2) AS `7日累计付费金额`,
       ROUND(SUM(paytotal), 2) AS `累计付费金额`
FROM cohort
GROUP BY cohort_dt, channel
ORDER BY cohort_dt DESC, `累计付费金额` DESC
LIMIT 300
""".strip()

SQL_ACTIVITY_PARTICIPATION_RATE = f"""
{_bounds("event", 29)}, dau AS (
    SELECT e.dt, COUNT(DISTINCT e.uid) AS dau
    FROM `event` e
    JOIN bounds b ON TRUE
    WHERE e.dt BETWEEN b.start_dt AND b.max_dt
      AND e.event IN ({LOGIN_EVENTS})
    GROUP BY e.dt
), act AS (
    SELECT e.dt, e.event, COUNT(DISTINCT e.uid) AS users
    FROM `event` e
    JOIN bounds b ON TRUE
    WHERE e.dt BETWEEN b.start_dt AND b.max_dt
      AND e.event IN ({ACTIVITY_EVENTS})
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
{_bounds("event", 29)}
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
       e.event AS `活动类型`,
       ROUND(COUNT(*) / NULLIF(COUNT(DISTINCT e.uid), 0), 2) AS `人均参与次数`
FROM `event` e
JOIN bounds b ON TRUE
WHERE e.dt BETWEEN b.start_dt AND b.max_dt
  AND e.event IN ({ACTIVITY_EVENTS})
GROUP BY e.dt, e.event
ORDER BY e.dt, e.event
LIMIT 300
""".strip()

SQL_ACTIVITY_LEVEL = f"""
{_bounds("event", 29)}
SELECT CASE
         WHEN COALESCE(CAST({_json_text('e', 'ext', 'ed_mainBuildingLevel')} AS DECIMAL(18,4)), 0) < 10 THEN '0-9'
         WHEN COALESCE(CAST({_json_text('e', 'ext', 'ed_mainBuildingLevel')} AS DECIMAL(18,4)), 0) < 20 THEN '10-19'
         WHEN COALESCE(CAST({_json_text('e', 'ext', 'ed_mainBuildingLevel')} AS DECIMAL(18,4)), 0) < 30 THEN '20-29'
         ELSE '30+'
       END AS `阶段`,
       COUNT(DISTINCT e.uid) AS `参与人数`
FROM `event` e
JOIN bounds b ON TRUE
WHERE e.dt BETWEEN b.start_dt AND b.max_dt
  AND e.event IN ({ACTIVITY_EVENTS})
GROUP BY `阶段`
ORDER BY MIN(COALESCE(CAST({_json_text('e', 'ext', 'ed_mainBuildingLevel')} AS DECIMAL(18,4)), 0))
""".strip()

SQL_WEEKLY_ACTIVITY_DISTRIBUTION = f"""
{_bounds("event", 29)}, user_week AS (
    SELECT DATE_SUB(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'), INTERVAL WEEKDAY(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d')) DAY) AS week_start,
           e.uid,
           COUNT(*) AS participate_count
    FROM `event` e
    JOIN bounds b ON TRUE
    WHERE e.dt BETWEEN b.start_dt AND b.max_dt
      AND e.event IN ({ACTIVITY_EVENTS})
    GROUP BY week_start, e.uid
)
SELECT week_start AS `周`,
       CASE
         WHEN participate_count = 1 THEN '1次'
         WHEN participate_count BETWEEN 2 AND 3 THEN '2-3次'
         WHEN participate_count BETWEEN 4 AND 7 THEN '4-7次'
         ELSE '8次+'
       END AS `参与次数段`,
       COUNT(DISTINCT uid) AS `人数`
FROM user_week
GROUP BY week_start, `参与次数段`
ORDER BY week_start, `参与次数段`
""".strip()

SQL_NEWBIE_ACTIVITY_RETENTION = f"""
{_bounds("event", 35)}, participants AS (
    SELECT e.uid, MIN(e.dt) AS participate_dt
    FROM `event` e
    JOIN bounds b ON TRUE
    WHERE e.dt BETWEEN b.start_dt AND b.max_dt
      AND e.event IN ('ActivityCommanderTask','ActivityArmsRaceTask','ActivityChestCount')
    GROUP BY e.uid
), retained AS (
    SELECT p.participate_dt,
           COUNT(DISTINCT p.uid) AS participants,
           COUNT(DISTINCT CASE WHEN u.dt = CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(p.participate_dt AS CHAR), '%Y%m%d'), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
                                AND JSON_UNQUOTE(JSON_EXTRACT(u.remain, '$.remain1')) = '1' THEN p.uid END) AS r1,
           COUNT(DISTINCT CASE WHEN u.dt = CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(p.participate_dt AS CHAR), '%Y%m%d'), INTERVAL 7 DAY), '%Y%m%d') AS SIGNED)
                                AND JSON_UNQUOTE(JSON_EXTRACT(u.remain, '$.remain7')) = '1' THEN p.uid END) AS r7
    FROM participants p
    JOIN bounds b ON TRUE
    LEFT JOIN `user` u ON u.uid = p.uid AND u.dt BETWEEN p.participate_dt AND b.max_dt
    WHERE p.participate_dt <= CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST(b.max_dt AS CHAR), '%Y%m%d'), INTERVAL 7 DAY), '%Y%m%d') AS SIGNED)
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
{_bounds("event", 35)}, participants AS (
    SELECT e.uid, MIN(e.dt) AS participate_dt
    FROM `event` e
    JOIN bounds b ON TRUE
    WHERE e.dt BETWEEN b.start_dt AND b.max_dt
      AND e.event IN ('ActivityAllianceBossBattleRet','ActivityAllianceBossChoose','ActivityAllianceBossDonation','ActivityAllianceBossReward','ActivityWorldBoss','AllianceDuelAlliancePoint','AllianceDuelPersonalPoint','AllianceDuelBoxOpen')
    GROUP BY e.uid
), user_pay AS (
    SELECT p.participate_dt,
           COUNT(DISTINCT p.uid) AS participants,
           COUNT(DISTINCT CASE WHEN {_pay_value('u', 'pay1')} > 0 THEN p.uid END) AS pay0,
           COUNT(DISTINCT CASE WHEN {_pay_value('u', 'pay7')} > 0 THEN p.uid END) AS pay7
    FROM participants p
    JOIN bounds b ON TRUE
    LEFT JOIN `user` u ON u.uid = p.uid AND u.dt = p.participate_dt
    WHERE p.participate_dt <= CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST(b.max_dt AS CHAR), '%Y%m%d'), INTERVAL 7 DAY), '%Y%m%d') AS SIGNED)
    GROUP BY p.participate_dt
)
SELECT STR_TO_DATE(CAST(participate_dt AS CHAR), '%Y%m%d') AS `日期`,
       participants AS `参与节日活动用户数`,
       ROUND(pay0 / NULLIF(participants, 0) * 100, 2) AS `当日`,
       ROUND(pay7 / NULLIF(participants, 0) * 100, 2) AS `第7日`
FROM user_pay
ORDER BY participate_dt
""".strip()

GOLD_DELTA = f"{_json_num('e', 'ext', 'ed_changeFree')} + {_json_num('e', 'ext', 'ed_changePaid')}"
GOLD_ROUTE = f"COALESCE({_json_text('e', 'ext', 'ed_route')}, {_json_text('e', 'ext', 'ed_detailReason')}, '未知')"

SQL_GOLD_CHANGE = f"""
{_bounds("event", 29)}
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
       ROUND(SUM(GREATEST({GOLD_DELTA}, 0)), 2) AS `钻石获取量`,
       ROUND(ABS(SUM(LEAST({GOLD_DELTA}, 0))), 2) AS `钻石消耗量`,
       ROUND(SUM({GOLD_DELTA}), 2) AS `钻石存量变化`
FROM `event` e
JOIN bounds b ON TRUE
WHERE e.dt BETWEEN b.start_dt AND b.max_dt
  AND e.event = 'GoldChange'
GROUP BY e.dt
ORDER BY e.dt
""".strip()

SQL_GOLD_SOURCE = f"""
{_bounds("event", 29)}
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
       {GOLD_ROUTE} AS `获取途径`,
       ROUND(SUM(GREATEST({GOLD_DELTA}, 0)), 2) AS `钻石获取量`
FROM `event` e
JOIN bounds b ON TRUE
WHERE e.dt BETWEEN b.start_dt AND b.max_dt
  AND e.event = 'GoldChange'
GROUP BY e.dt, `获取途径`
HAVING `钻石获取量` > 0
ORDER BY e.dt, `获取途径`
LIMIT 300
""".strip()

SQL_GOLD_SINK = f"""
{_bounds("event", 29)}
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
       {GOLD_ROUTE} AS `消耗途径`,
       ROUND(ABS(SUM(LEAST({GOLD_DELTA}, 0))), 2) AS `钻石消耗量`
FROM `event` e
JOIN bounds b ON TRUE
WHERE e.dt BETWEEN b.start_dt AND b.max_dt
  AND e.event = 'GoldChange'
GROUP BY e.dt, `消耗途径`
HAVING `钻石消耗量` > 0
ORDER BY e.dt, `消耗途径`
LIMIT 300
""".strip()

SQL_STARTER_PACK_REPURCHASE = f"""
{_bounds("event", 29)}, pay_events AS (
    SELECT e.uid, e.dt, {PRODUCT_ID} AS product_id
    FROM `event` e
    JOIN bounds b ON TRUE
    WHERE e.dt BETWEEN b.start_dt AND b.max_dt
      AND e.event IN ({PAY_EVENTS})
), first_buy AS (
    SELECT uid, MIN(dt) AS first_dt
    FROM pay_events
    WHERE LOWER(product_id) LIKE '%new%' OR LOWER(product_id) LIKE '%starter%' OR product_id LIKE '%新手%' OR product_id LIKE '%首充%'
    GROUP BY uid
), repurchase AS (
    SELECT f.first_dt,
           COUNT(DISTINCT f.uid) AS buyers,
           COUNT(DISTINCT CASE WHEN p.dt BETWEEN f.first_dt AND CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(f.first_dt AS CHAR), '%Y%m%d'), INTERVAL 6 DAY), '%Y%m%d') AS SIGNED) AND p.dt > f.first_dt THEN f.uid END) AS w0,
           COUNT(DISTINCT CASE WHEN p.dt BETWEEN CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(f.first_dt AS CHAR), '%Y%m%d'), INTERVAL 7 DAY), '%Y%m%d') AS SIGNED) AND CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(f.first_dt AS CHAR), '%Y%m%d'), INTERVAL 13 DAY), '%Y%m%d') AS SIGNED) THEN f.uid END) AS w1,
           COUNT(DISTINCT CASE WHEN p.dt BETWEEN CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(f.first_dt AS CHAR), '%Y%m%d'), INTERVAL 14 DAY), '%Y%m%d') AS SIGNED) AND CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(f.first_dt AS CHAR), '%Y%m%d'), INTERVAL 20 DAY), '%Y%m%d') AS SIGNED) THEN f.uid END) AS w2
    FROM first_buy f
    LEFT JOIN pay_events p ON p.uid = f.uid
    GROUP BY f.first_dt
)
SELECT STR_TO_DATE(CAST(first_dt AS CHAR), '%Y%m%d') AS `日期`,
       buyers AS `购买新手礼包用户数`,
       ROUND(w0 / NULLIF(buyers, 0) * 100, 2) AS `当周`,
       ROUND(w1 / NULLIF(buyers, 0) * 100, 2) AS `第1周`,
       ROUND(w2 / NULLIF(buyers, 0) * 100, 2) AS `第2周`
FROM repurchase
ORDER BY first_dt
""".strip()

SQL_MONTH_CARD_RETENTION = f"""
WITH obs AS (
    SELECT MAX(dt) AS max_dt FROM `event`
), pay_events AS (
    SELECT e.uid, MIN(e.dt) AS buy_dt
    FROM `event` e
    JOIN obs ON TRUE
    WHERE e.dt BETWEEN CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST(obs.max_dt AS CHAR), '%Y%m%d'), INTERVAL 60 DAY), '%Y%m%d') AS SIGNED)
                   AND CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST(obs.max_dt AS CHAR), '%Y%m%d'), INTERVAL 30 DAY), '%Y%m%d') AS SIGNED)
      AND e.event IN ({PAY_EVENTS})
      AND (LOWER({PRODUCT_ID}) LIKE '%month%' OR {PRODUCT_ID} LIKE '%月卡%')
    GROUP BY e.uid
), login_events AS (
    SELECT p.uid,
           DATEDIFF(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'), STR_TO_DATE(CAST(p.buy_dt AS CHAR), '%Y%m%d')) AS retain_day
    FROM pay_events p
    JOIN `event` e ON e.uid = p.uid
    WHERE e.dt BETWEEN p.buy_dt AND CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(p.buy_dt AS CHAR), '%Y%m%d'), INTERVAL 30 DAY), '%Y%m%d') AS SIGNED)
      AND e.event IN ({LOGIN_EVENTS})
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
{_bounds("event", 29)}
SELECT {HERO_ID} AS `将领ID`,
       COUNT(CASE WHEN e.event = 'HeroStarUp' THEN 1 END) AS `升星次数`,
       COUNT(DISTINCT CASE WHEN e.event = 'HeroStarUp' THEN e.uid END) AS `升星用户数`,
       COUNT(CASE WHEN e.event = 'HeroLevelUp' THEN 1 END) AS `升级次数`,
       COUNT(DISTINCT CASE WHEN e.event = 'HeroLevelUp' THEN e.uid END) AS `升级用户数`
FROM `event` e
JOIN bounds b ON TRUE
WHERE e.dt BETWEEN b.start_dt AND b.max_dt
  AND e.event IN ({HERO_EVENTS})
GROUP BY `将领ID`
ORDER BY (`升星次数` + `升级次数`) DESC
LIMIT 50
""".strip()

HERO_LEVEL = f"COALESCE(CAST({_json_text('e', 'ext', 'ed_currentLevel')} AS DECIMAL(18,4)), CAST({_json_text('e', 'ext', 'ed_heroLevel')} AS DECIMAL(18,4)), 0)"
HERO_STAR = f"COALESCE({_json_text('e', 'ext', 'ed_heroStar')}, {_json_text('e', 'ext', 'ed_newStar')}, '未知')"

SQL_SSR_HERO_LEVEL = f"""
{_bounds("event", 29)}, latest AS (
    SELECT e.uid,
           {HERO_ID} AS hero_id,
           {HERO_STAR} AS hero_star,
           {HERO_LEVEL} AS hero_level,
           ROW_NUMBER() OVER (PARTITION BY e.uid, {HERO_ID} ORDER BY e.dt DESC, e.time DESC) AS rn
    FROM `event` e
    JOIN bounds b ON TRUE
    WHERE e.dt BETWEEN b.start_dt AND b.max_dt
      AND e.event IN ('HeroLevelUp','HeroStarUp')
)
SELECT hero_id AS `将领ID`,
       hero_star AS `英雄星级`,
       COUNT(DISTINCT uid) AS `全部用户`,
       COUNT(DISTINCT CASE WHEN hero_level BETWEEN 1 AND 10 THEN uid END) AS `1-10`,
       COUNT(DISTINCT CASE WHEN hero_level BETWEEN 11 AND 20 THEN uid END) AS `11-20`,
       COUNT(DISTINCT CASE WHEN hero_level >= 21 THEN uid END) AS `21+`
FROM latest
WHERE rn = 1
GROUP BY hero_id, hero_star
ORDER BY `全部用户` DESC
LIMIT 50
""".strip()

SQL_CITY_AVG_LEVEL = f"""
SELECT ROUND(AVG(COALESCE(CAST({_json_text('u', 'lastinfo', 'blevel')} AS DECIMAL(18,4)), 0)), 2) AS `主城平均等级`
FROM `user` u
WHERE u.dt = (SELECT MAX(dt) FROM `user`)
""".strip()

SQL_CITY_UPGRADE_METRIC = _metric_sql("event", "当日主城升级次数", f"e.event IN ({BUILDING_EVENTS})")
SQL_BUILDING_UPGRADE_METRIC = _metric_sql("event", "当日建筑升级次数", "e.event = 'BuildingUpgrade'")
SQL_TECH_UPGRADE_METRIC = _metric_sql("event", "当日科技升级次数", f"e.event IN ({TECH_EVENTS})")

SQL_CITY_LEVEL_USERS = f"""
SELECT COALESCE(CAST(CAST({_json_text('u', 'lastinfo', 'blevel')} AS DECIMAL(18,4)) AS CHAR), '未知') AS `主城等级`,
       COUNT(DISTINCT u.uid) AS `玩家数`
FROM `user` u
WHERE u.dt = (SELECT MAX(dt) FROM `user`)
GROUP BY `主城等级`
ORDER BY CAST(`主城等级` AS SIGNED)
LIMIT 50
""".strip()

BUILDING_ID = f"COALESCE({_json_text('e', 'ext', 'ed_buildingId')}, {_json_text('e', 'ext', 'ed_metaId')}, e.event)"

SQL_BUILDING_BY_TYPE = f"""
{_bounds("event", 29)}
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
       {BUILDING_ID} AS `建筑`,
       COUNT(*) AS `升级次数`
FROM `event` e
JOIN bounds b ON TRUE
WHERE e.dt BETWEEN b.start_dt AND b.max_dt
  AND e.event IN ({BUILDING_EVENTS})
GROUP BY e.dt, `建筑`
ORDER BY e.dt, `建筑`
LIMIT 300
""".strip()

SQL_BUILDING_BY_CITY = f"""
{_bounds("event", 29)}
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
       {CITY_LEVEL_E} AS `主城等级`,
       COUNT(*) AS `建筑升级次数`
FROM `event` e
JOIN bounds b ON TRUE
WHERE e.dt BETWEEN b.start_dt AND b.max_dt
  AND e.event IN ({BUILDING_EVENTS})
GROUP BY e.dt, `主城等级`
ORDER BY e.dt, `主城等级`
LIMIT 300
""".strip()

SQL_TECH_BY_TYPE = f"""
{_bounds("event", 29)}
SELECT e.event AS `科技名称`,
       COUNT(*) AS `升级科技.总次数`
FROM `event` e
JOIN bounds b ON TRUE
WHERE e.dt BETWEEN b.start_dt AND b.max_dt
  AND e.event IN ({TECH_EVENTS})
GROUP BY e.event
ORDER BY `升级科技.总次数` DESC
LIMIT 50
""".strip()

SQL_TECH_BY_CITY = f"""
{_bounds("event", 29)}
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
       {CITY_LEVEL_E} AS `主城等级`,
       COUNT(*) AS `科技升级次数`
FROM `event` e
JOIN bounds b ON TRUE
WHERE e.dt BETWEEN b.start_dt AND b.max_dt
  AND e.event IN ({TECH_EVENTS})
GROUP BY e.dt, `主城等级`
ORDER BY e.dt, `主城等级`
LIMIT 300
""".strip()

SQL_ARMY_RECRUIT = f"""
{_bounds("event", 29)}
SELECT {ARMY_ID} AS `士兵兵种`,
       COUNT(*) AS `招募总次数`,
       ROUND(COUNT(*) / NULLIF(COUNT(DISTINCT e.uid), 0), 2) AS `人均招募次数`,
       ROUND(SUM({_json_num('e', 'ext', 'ed_count')}), 2) AS `招募总数量`
FROM `event` e
JOIN bounds b ON TRUE
WHERE e.dt BETWEEN b.start_dt AND b.max_dt
  AND e.event = 'ArmyUpgrade'
GROUP BY `士兵兵种`
ORDER BY `招募总次数` DESC
LIMIT 50
""".strip()

SPEEDUP_TYPE = f"COALESCE({_json_text('e', 'ext', 'ed_detailReason')}, {_json_text('e', 'ext', 'ed_route')}, e.event)"

SQL_SPEEDUP = f"""
{_bounds("event", 29)}
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
       {SPEEDUP_TYPE} AS `加速类型`,
       COUNT(*) AS `使用加速次数`,
       COUNT(DISTINCT e.uid) AS `使用加速人数`,
       ROUND(COUNT(*) / NULLIF(COUNT(DISTINCT e.uid), 0), 2) AS `人均使用加速次数`
FROM `event` e
JOIN bounds b ON TRUE
WHERE e.dt BETWEEN b.start_dt AND b.max_dt
  AND e.event IN ('BuildingUpgrade','BuildingIdleUpgrade','ArmyUpgrade')
GROUP BY e.dt, `加速类型`
ORDER BY e.dt, `使用加速次数` DESC
LIMIT 300
""".strip()

SQL_CITY_FUNNEL = f"""
WITH latest AS (
    SELECT u.uid,
           COALESCE(CAST({_json_text('u', 'lastinfo', 'blevel')} AS DECIMAL(18,4)), 0) AS blevel
    FROM `user` u
    WHERE u.dt = (SELECT MAX(dt) FROM `user`)
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
    "e02bdbafdd364d3cba9f991f94896c86": ViewSql("出征数据", "过去7日各兵种出征情况", "table", ("出征士兵兵种", "指标", "阶段汇总"), columns=("出征士兵兵种", "指标", "阶段汇总"), sql=SQL_ARMY_7D),
    "59a8dfd8d6e341988edfbf1666872aae": ViewSql("出征数据", "各将领出征量分布", "table", ("将领ID", "出征次数"), columns=("将领ID", "出征次数"), sql=SQL_HERO_EXPEDITION_COUNT),
    "848927b0833443d39a93797c3507368e": ViewSql("出征数据", "各等级出征胜率", "column", ("等级", "出征胜率"), ("等级",), ("出征胜率",), sql=SQL_LEVEL_WIN_RATE),
    "344c936b561f44f6bc29cc2663f3f651": ViewSql("出征数据", "各将领出征胜率", "table", ("将领ID", "各将领出征胜率"), columns=("将领ID", "各将领出征胜率"), sql=SQL_HERO_WIN_RATE),
    "61c21b5974844638a3d7370971de58c9": ViewSql("出征数据", "各主城等级参与演习次数", "line", ("日期", "主城等级", "参与演习次数"), ("日期",), ("参与演习次数",), sql=SQL_DRILL_BY_CITY_LEVEL),
    "f6ca362eb4274830b3298b0227a8ab88": ViewSql("付费概览", "充值用户周累充分布", "table", ("事件发生时间", "渠道", "全部用户", "(-∞, 500)", "[500, 1000)", "[1000, 2000)", "[2000, +∞)"), columns=("事件发生时间", "渠道", "全部用户", "(-∞, 500)", "[500, 1000)", "[1000, 2000)", "[2000, +∞)"), sql=SQL_WEEKLY_PAY_DISTRIBUTION),
    "4045ede9004f48de9fb8b8aed5f79287": ViewSql("渠道分析", "各渠道充值用户周累充分布", "table", ("事件发生时间", "渠道", "全部用户", "(-∞, 500)", "[500, 1000)", "[1000, 2000)", "[2000, +∞)"), columns=("事件发生时间", "渠道", "全部用户", "(-∞, 500)", "[500, 1000)", "[1000, 2000)", "[2000, +∞)"), sql=SQL_WEEKLY_PAY_DISTRIBUTION),
    "fdb8f135e2644bcb80b7634882809f7e": ViewSql("付费概览", "付费事件分布", "column", ("购买礼包名", "购买次数"), ("购买礼包名",), ("购买次数",), sql=SQL_PAY_EVENT_DISTRIBUTION),
    "531012d01f104a509da2d1926692ee1d": ViewSql("投放看板", "各渠道注册与付费", "table", ("日期", "渠道", "账号注册用户数", "首日付费金额", "7日累计付费金额", "累计付费金额"), columns=("日期", "渠道", "账号注册用户数", "首日付费金额", "7日累计付费金额", "累计付费金额"), sql=SQL_ACQUISITION_CHANNEL_PAY),
    "c794f6521d8b44d39f78eabdf109896b": ViewSql("活动分析", "各类活动参与率", "line", ("日期", "活动类型", "活动参与率"), ("日期",), ("活动参与率",), sql=SQL_ACTIVITY_PARTICIPATION_RATE),
    "6266951d0e1842e2b259121ab06f7a61": ViewSql("活动分析", "各类活动人均参与次数", "line", ("日期", "活动类型", "人均参与次数"), ("日期",), ("人均参与次数",), sql=SQL_ACTIVITY_AVG_TIMES),
    "13d554014c854e508ff016d93a6f3899": ViewSql("活动分析", "各等级段参与日常活动的人数分布", "column", ("阶段", "参与人数"), ("阶段",), ("参与人数",), sql=SQL_ACTIVITY_LEVEL),
    "161fd0d2996a49a29e82606e6db7d95b": ViewSql("活动分析", "每周活动参与次数分布", "column", ("周", "参与次数段", "人数"), ("参与次数段",), ("人数",), columns=("周", "参与次数段", "人数"), sql=SQL_WEEKLY_ACTIVITY_DISTRIBUTION),
    "9684a569ed034fb0b8a106a9817effaa": ViewSql("活动分析", "参与新手活动的后续7日留存率", "table", ("日期", "参与新手活动用户数", "第1日", "第7日"), columns=("日期", "参与新手活动用户数", "第1日", "第7日"), sql=SQL_NEWBIE_ACTIVITY_RETENTION),
    "095b1cf41cd64844b1f78f07ceccb7bf": ViewSql("活动分析", "参与节日活动的后续7日付费留存率", "table", ("日期", "参与节日活动用户数", "当日", "第7日"), columns=("日期", "参与节日活动用户数", "当日", "第7日"), sql=SQL_FESTIVAL_PAY_RETENTION),
    "4cc60cadf26e4b2f945c672f2648d205": ViewSql("经济系统", "钻石消耗获取情况", "line", ("日期", "钻石获取量", "钻石消耗量", "钻石存量变化"), ("日期",), ("钻石获取量", "钻石消耗量", "钻石存量变化"), sql=SQL_GOLD_CHANGE),
    "df837cb59810483f84fb0e7cd420646a": ViewSql("经济系统", "钻石获取途径分布", "line", ("日期", "获取途径", "钻石获取量"), ("日期",), ("钻石获取量",), sql=SQL_GOLD_SOURCE),
    "fda6854e188c44c4b35e75c9af6d9854": ViewSql("经济系统", "钻石消耗途径分布", "line", ("日期", "消耗途径", "钻石消耗量"), ("日期",), ("钻石消耗量",), sql=SQL_GOLD_SINK),
    "15da41b65ee64aba854e2de701a728bc": ViewSql("礼包付费概览", "购买新手礼包用户复购率", "table", ("日期", "购买新手礼包用户数", "当周", "第1周", "第2周"), columns=("日期", "购买新手礼包用户数", "当周", "第1周", "第2周"), sql=SQL_STARTER_PACK_REPURCHASE),
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
    "1e41ffdca6b041a6abea363fcb1b8cd2": ViewSql("主城建设", "各兵种招募情况", "table", ("士兵兵种", "招募总次数", "人均招募次数", "招募总数量"), columns=("士兵兵种", "招募总次数", "人均招募次数", "招募总数量"), sql=SQL_ARMY_RECRUIT),
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
