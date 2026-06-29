# -*- coding: utf-8 -*-
"""Datasource-scoped SQL definitions for the flam / first_zombie dashboards."""

from __future__ import annotations

from dataclasses import dataclass


TENANT_ID = 7477202383789887488
DATASOURCE_ID = 3

PAY_EVENTS = (
    "'PayBuyRet','PayBuyRetBenifit','PayBuyRetSandBox','PayFinish',"
    "'ServerPayLog','ep_pay_purchase_finish','ep_pay_update_db_finish'"
)
ACTIVE_EVENT = 'UserActive'
LOGIN_EVENTS = f"'{ACTIVE_EVENT}'"
REGISTER_EVENT = 'UserRegister'
PROD_ID = 110000038


def _date_window_start_expr(days: int) -> str:
    return f"CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL {days} DAY), '%Y%m%d') AS SIGNED)"


def _date_window_end_expr() -> str:
    return "CAST(DATE_FORMAT(CURDATE(), '%Y%m%d') AS SIGNED)"


def _bounds_cte(start_days: int = 30, alias: str = "bounds") -> str:
    return (
        f"WITH {alias} AS (\n"
        f"    SELECT {_date_window_start_expr(start_days)} AS start_dt,\n"
        f"           {_date_window_end_expr()} AS end_dt\n"
        f")"
    )


def _dt_between(alias: str, start_days: int = 30) -> str:
    return f"{alias}.dt BETWEEN {_date_window_start_expr(start_days)} AND {_date_window_end_expr()}"


def _dt_between_until_yesterday(alias: str, start_days: int = 30) -> str:
    return f"{alias}.dt BETWEEN {_date_window_start_expr(start_days)} AND {_date_window_start_expr(1)}"


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


DISPLAY_NAMES = {
    "cohort_date": "日期",
    "new_users": "新增用户数",
    "d1_retained_users": "次日留存用户数",
    "d1_retention_pct": "次日留存率",
}


def _pay_value(alias: str, field: str = "paytotal") -> str:
    return (
        "COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT("
        f"{alias}.pay, '$.{field}'"
        ")), '') AS DECIMAL(18,4)), 0)"
    )


def _json_text(alias: str, obj: str, key: str) -> str:
    return f"NULLIF(JSON_UNQUOTE(JSON_EXTRACT({alias}.{obj}, '$.{key}')), '')"


CHANNEL_EXPR_U = (
    "COALESCE("
    + _json_text("u", "adinfo", "mediaSource")
    + ", "
    + _json_text("u", "adinfo", "campaignName")
    + ", '未知')"
)
CHANNEL_EXPR_E = (
    "COALESCE("
    + _json_text("e", "adinfo", "mediaSource")
    + ", "
    + _json_text("e", "adinfo", "campaignName")
    + ", '未知')"
)
PLATFORM_EXPR_U = (
    "COALESCE("
    + _json_text("u", "deviceinfo", "_platform")
    + ", "
    + _json_text("u", "userinfo", "_platformType")
    + ", '未知')"
)
PLATFORM_EXPR_E = (
    "COALESCE("
    + _json_text("e", "deviceinfo", "_platform")
    + ", "
    + _json_text("e", "userinfo", "_platformType")
    + ", '未知')"
)


SQL_NEW_USERS_DAILY = f"""
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
       COUNT(DISTINCT e.uid) AS `新增用户数`
FROM `event` e
WHERE {_dt_between("e", 30)}
  AND e.prod = {PROD_ID}
  AND e.event = '{REGISTER_EVENT}'
GROUP BY e.dt
ORDER BY e.dt
""".strip()

SQL_NEW_USERS_BY_CHANNEL = f"""
WITH registers AS (
    SELECT e.dt,
           e.uid,
           {CHANNEL_EXPR_E} AS channel
    FROM `event` e
    WHERE {_dt_between("e", 30)}
      AND e.prod = {PROD_ID}
      AND e.event = '{REGISTER_EVENT}'
)
SELECT STR_TO_DATE(CAST(dt AS CHAR), '%Y%m%d') AS `日期`,
       channel AS `渠道`,
       COUNT(DISTINCT uid) AS `新增用户数`
FROM registers
GROUP BY dt, channel
ORDER BY dt, channel
LIMIT 300
""".strip()

SQL_NEW_USERS_BY_PLATFORM = f"""
WITH registers AS (
    SELECT e.dt,
           e.uid,
           {PLATFORM_EXPR_E} AS platform_name
    FROM `event` e
    WHERE {_dt_between("e", 30)}
      AND e.prod = {PROD_ID}
      AND e.event = '{REGISTER_EVENT}'
)
SELECT STR_TO_DATE(CAST(dt AS CHAR), '%Y%m%d') AS `日期`,
       platform_name AS `系统`,
       COUNT(DISTINCT uid) AS `新增用户数`
FROM registers
GROUP BY dt, platform_name
ORDER BY dt, platform_name
LIMIT 300
""".strip()

SQL_D1_RETENTION = f"""
WITH bounds AS (
    SELECT {_date_window_start_expr(29)} AS start_dt,
           {_date_window_start_expr(2)} AS end_dt
), cohort AS (
    SELECT e.dt AS cohort_dt,
           CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED) AS d1_dt,
           e.uid
    FROM `event` e
    JOIN bounds b ON e.dt BETWEEN b.start_dt AND b.end_dt
    WHERE e.prod = {PROD_ID}
      AND e.event = '{REGISTER_EVENT}'
), active AS (
    SELECT e.dt,
           e.uid
    FROM `event` e
    WHERE e.dt BETWEEN {_date_window_start_expr(28)} AND {_date_window_start_expr(1)}
      AND e.prod = {PROD_ID}
      AND e.event = '{ACTIVE_EVENT}'
    GROUP BY e.dt, e.uid
), retained AS (
    SELECT c.cohort_dt,
           COUNT(DISTINCT c.uid) AS d1_retained_users
    FROM cohort c
    JOIN active a ON a.uid = c.uid AND a.dt = c.d1_dt
    GROUP BY c.cohort_dt
)
SELECT STR_TO_DATE(CAST(c.cohort_dt AS CHAR), '%Y%m%d') AS cohort_date,
       COUNT(DISTINCT c.uid) AS new_users,
       COALESCE(r.d1_retained_users, 0) AS d1_retained_users,
       ROUND(COALESCE(r.d1_retained_users, 0) / NULLIF(COUNT(DISTINCT c.uid), 0) * 100, 2) AS d1_retention_pct
FROM cohort c
LEFT JOIN retained r ON r.cohort_dt = c.cohort_dt
GROUP BY c.cohort_dt, r.d1_retained_users
ORDER BY c.cohort_dt
""".strip()

SQL_NEW_USERS_FIRST_DAY_PAY = f"""
WITH bounds AS (
    SELECT {_date_window_start_expr(30)} AS start_dt,
           {_date_window_start_expr(1)} AS end_dt
), cohort AS (
    SELECT e.dt AS cohort_dt,
           e.uid,
           {_pay_value("u", "pay1")} AS pay1
    FROM `event` e
    JOIN bounds b ON e.dt BETWEEN b.start_dt AND b.end_dt
    JOIN `user` u
      ON u.uid = e.uid
     AND u.dt = e.dt
     AND u.prod = {PROD_ID}
    WHERE e.prod = {PROD_ID}
      AND e.event = '{REGISTER_EVENT}'
)
SELECT STR_TO_DATE(CAST(cohort_dt AS CHAR), '%Y%m%d') AS `日期`,
       ROUND(SUM(pay1), 2) AS `新增首日付费金额`
FROM cohort
GROUP BY cohort_dt
ORDER BY cohort_dt
""".strip()

SQL_CHANNEL_RETENTION = f"""
WITH bounds AS (
    SELECT {_date_window_start_expr(36)} AS start_dt,
           {_date_window_start_expr(8)} AS end_dt,
           {_date_window_start_expr(1)} AS data_end_dt
), cohort AS (
    SELECT e.dt AS cohort_dt,
           CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED) AS d1_dt,
           CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'), INTERVAL 3 DAY), '%Y%m%d') AS SIGNED) AS d3_dt,
           CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'), INTERVAL 7 DAY), '%Y%m%d') AS SIGNED) AS d7_dt,
           e.uid,
           {CHANNEL_EXPR_E} AS channel
    FROM `event` e
    JOIN bounds b ON e.dt BETWEEN b.start_dt AND b.end_dt
    WHERE e.prod = {PROD_ID}
      AND e.event = '{REGISTER_EVENT}'
), active AS (
    SELECT e.dt,
           e.uid
    FROM `event` e
    JOIN bounds b ON e.dt BETWEEN CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(b.start_dt AS CHAR), '%Y%m%d'), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED) AND b.data_end_dt
    WHERE e.prod = {PROD_ID}
      AND e.event = '{ACTIVE_EVENT}'
    GROUP BY e.dt, e.uid
)
SELECT STR_TO_DATE(CAST(c.cohort_dt AS CHAR), '%Y%m%d') AS `日期`,
       c.channel AS `渠道`,
       COUNT(DISTINCT c.uid) AS `用户注册用户数`,
       ROUND(COUNT(DISTINCT CASE WHEN a.dt = c.d1_dt THEN c.uid END) / NULLIF(COUNT(DISTINCT c.uid), 0) * 100, 2) AS `第1日`,
       ROUND(COUNT(DISTINCT CASE WHEN a.dt = c.d3_dt THEN c.uid END) / NULLIF(COUNT(DISTINCT c.uid), 0) * 100, 2) AS `第3日`,
       ROUND(COUNT(DISTINCT CASE WHEN a.dt = c.d7_dt THEN c.uid END) / NULLIF(COUNT(DISTINCT c.uid), 0) * 100, 2) AS `第7日`
FROM cohort c
LEFT JOIN active a
  ON a.uid = c.uid
 AND a.dt IN (c.d1_dt, c.d3_dt, c.d7_dt)
GROUP BY c.cohort_dt, c.channel
ORDER BY c.cohort_dt, c.channel
LIMIT 300
""".strip()

SQL_LTV_7D = f"""
WITH bounds AS (
    SELECT {_date_window_start_expr(36)} AS start_dt,
           {_date_window_start_expr(8)} AS end_dt
), cohort AS (
    SELECT u.dt AS cohort_dt,
           u.uid,
           {_pay_value("u", "pay1")} AS pay1,
           {_pay_value("u", "pay2")} AS pay2,
           {_pay_value("u", "pay3")} AS pay3,
           {_pay_value("u", "pay7")} AS pay7
    FROM `user` u
    JOIN bounds b ON u.dt BETWEEN b.start_dt AND b.end_dt
    WHERE u.prod = {PROD_ID}
      AND JSON_UNQUOTE(JSON_EXTRACT(u.userinfo, '$.regdate')) = CAST(u.dt AS CHAR)
)
SELECT STR_TO_DATE(CAST(cohort_dt AS CHAR), '%Y%m%d') AS `日期`,
       COUNT(DISTINCT uid) AS `用户注册用户数`,
       ROUND(SUM(pay1) / NULLIF(COUNT(DISTINCT uid), 0), 2) AS `当日`,
       ROUND(SUM(pay2) / NULLIF(COUNT(DISTINCT uid), 0), 2) AS `第1日`,
       ROUND(SUM(pay3) / NULLIF(COUNT(DISTINCT uid), 0), 2) AS `第2日`,
       ROUND(SUM(pay7) / NULLIF(COUNT(DISTINCT uid), 0), 2) AS `第7日`
FROM cohort
GROUP BY cohort_dt
ORDER BY cohort_dt
""".strip()

SQL_DAILY_REVENUE_BASE = f"""
WITH pay_event_users AS (
    SELECT e.dt,
           e.uid
    FROM `event` e
    WHERE {_dt_between("e", 30)}
      AND e.event IN ({PAY_EVENTS})
      AND e.prod = {PROD_ID}
    GROUP BY e.dt, e.uid
), user_pay_delta AS (
    SELECT pe.dt,
           pe.uid,
           GREATEST({_pay_value("u")} - COALESCE({_pay_value("p")}, 0), 0) AS pay_amount
    FROM pay_event_users pe
    JOIN `user` u
      ON u.dt = pe.dt
     AND u.uid = pe.uid
     AND u.prod = {PROD_ID}
    LEFT JOIN `user` p
      ON p.uid = pe.uid
     AND p.dt = CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST(pe.dt AS CHAR), '%Y%m%d'), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
     AND p.prod = {PROD_ID}
), daily_pay AS (
    SELECT dt,
           ROUND(SUM(pay_amount), 2) AS pay_amount,
           COUNT(DISTINCT CASE WHEN pay_amount > 0 THEN uid END) AS pay_users
    FROM user_pay_delta
    GROUP BY dt
), daily_active AS (
    SELECT e.dt,
           COUNT(DISTINCT e.uid) AS active_users
    FROM `event` e
    WHERE {_dt_between("e", 30)}
      AND e.event IN ({LOGIN_EVENTS})
      AND e.prod = {PROD_ID}
    GROUP BY e.dt
)
""".strip()

SQL_ARPU_ARPPU = f"""
{SQL_DAILY_REVENUE_BASE}
SELECT STR_TO_DATE(CAST(d.dt AS CHAR), '%Y%m%d') AS `日期`,
       ROUND(COALESCE(p.pay_amount, 0) / NULLIF(d.active_users, 0), 2) AS `ARPU`,
       ROUND(COALESCE(p.pay_amount, 0) / NULLIF(p.pay_users, 0), 2) AS `ARPPU`
FROM daily_active d
LEFT JOIN daily_pay p ON p.dt = d.dt
ORDER BY d.dt
""".strip()

SQL_PAYMENT_OVERVIEW = f"""
{SQL_DAILY_REVENUE_BASE}
SELECT STR_TO_DATE(CAST(d.dt AS CHAR), '%Y%m%d') AS `日期`,
       COALESCE(p.pay_users, 0) AS `付费用户数`,
       COALESCE(p.pay_amount, 0) AS `付费总额`,
       ROUND(COALESCE(p.pay_amount, 0) / NULLIF(d.active_users, 0), 2) AS `ARPU`,
       ROUND(COALESCE(p.pay_amount, 0) / NULLIF(p.pay_users, 0), 2) AS `ARPPU`,
       ROUND(COALESCE(p.pay_users, 0) / NULLIF(d.active_users, 0) * 100, 2) AS `付费渗透率`
FROM daily_active d
LEFT JOIN daily_pay p ON p.dt = d.dt
ORDER BY d.dt
""".strip()

SQL_DAILY_PAY_EVENT_COUNT = f"""
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
       COUNT(*) AS `充值次数`
FROM `event` e
WHERE {_dt_between("e", 30)}
  AND e.event IN ({PAY_EVENTS})
  AND e.prod = {PROD_ID}
GROUP BY e.dt
ORDER BY e.dt
""".strip()

SQL_DAILY_PAY_USERS = f"""
WITH pay_users AS (
    SELECT e.dt, e.uid
    FROM `event` e
    WHERE {_dt_between("e", 30)}
      AND e.event IN ({PAY_EVENTS})
      AND e.prod = {PROD_ID}
    GROUP BY e.dt, e.uid
), first_pay AS (
    SELECT e.uid, MIN(e.dt) AS first_pay_dt
    FROM `event` e
    WHERE {_dt_between("e", 30)}
      AND e.event IN ({PAY_EVENTS})
      AND e.prod = {PROD_ID}
    GROUP BY e.uid
)
SELECT STR_TO_DATE(CAST(p.dt AS CHAR), '%Y%m%d') AS `日期`,
       COUNT(DISTINCT p.uid) AS `日充值用户数`,
       COUNT(DISTINCT CASE WHEN f.first_pay_dt = p.dt THEN p.uid END) AS `日新增充值用户数`
FROM pay_users p
LEFT JOIN first_pay f ON f.uid = p.uid
GROUP BY p.dt
ORDER BY p.dt
""".strip()

SQL_7D_PAY_RANK = f"""
WITH pay_users AS (
    SELECT e.uid
    FROM `event` e
    WHERE e.dt BETWEEN {_date_window_start_expr(8)} AND {_date_window_start_expr(1)}
      AND e.event IN ({PAY_EVENTS})
      AND e.prod = {PROD_ID}
    GROUP BY e.uid
), latest AS (
    SELECT u.uid,
           {CHANNEL_EXPR_U} AS channel_name,
           COALESCE({_json_text("u", "userinfo", "_serverId")}, {_json_text("u", "lastinfo", "_serverId")}, '未知') AS server_id,
           {_pay_value("u")} AS paytotal
    FROM `user` u
    JOIN pay_users pu ON pu.uid = u.uid
    WHERE u.dt = {_date_window_start_expr(1)}
      AND u.prod = {PROD_ID}
), baseline AS (
    SELECT u.uid,
           {_pay_value("u")} AS paytotal
    FROM `user` u
    JOIN pay_users pu ON pu.uid = u.uid
    WHERE u.dt = {_date_window_start_expr(8)}
      AND u.prod = {PROD_ID}
), ranked AS (
    SELECT l.uid,
           l.channel_name,
           l.server_id,
           ROUND(GREATEST(l.paytotal - COALESCE(b.paytotal, 0), 0), 2) AS pay_amount
    FROM latest l
    LEFT JOIN baseline b ON b.uid = l.uid
    WHERE GREATEST(l.paytotal - COALESCE(b.paytotal, 0), 0) > 0
)
SELECT uid AS `账号ID`,
       channel_name AS `来源渠道`,
       server_id AS `区服ID`,
       pay_amount AS `付费总额`
FROM ranked
ORDER BY pay_amount DESC
LIMIT 100
""".strip()

SQL_CHANNEL_PAY_AMOUNT = f"""
WITH pay_event_users AS (
    SELECT e.dt,
           e.uid
    FROM `event` e
    WHERE {_dt_between("e", 30)}
      AND e.event IN ({PAY_EVENTS})
      AND e.prod = {PROD_ID}
    GROUP BY e.dt, e.uid
), user_pay_delta AS (
    SELECT pe.dt,
           pe.uid,
           {CHANNEL_EXPR_U} AS channel,
           GREATEST({_pay_value("u")} - COALESCE({_pay_value("p")}, 0), 0) AS pay_amount
    FROM pay_event_users pe
    JOIN `user` u
      ON u.dt = pe.dt
     AND u.uid = pe.uid
     AND u.prod = {PROD_ID}
    LEFT JOIN `user` p
      ON p.uid = pe.uid
     AND p.dt = CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST(pe.dt AS CHAR), '%Y%m%d'), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
     AND p.prod = {PROD_ID}
)
SELECT STR_TO_DATE(CAST(dt AS CHAR), '%Y%m%d') AS `日期`,
       channel AS `渠道`,
       ROUND(SUM(pay_amount), 2) AS `付费金额`
FROM user_pay_delta
GROUP BY dt, channel
ORDER BY dt, channel
LIMIT 300
""".strip()

SQL_CHANNEL_PAY_USERS = SQL_CHANNEL_PAY_AMOUNT.replace(
    "ROUND(SUM(pay_amount), 2) AS `付费金额`",
    "COUNT(DISTINCT CASE WHEN pay_amount > 0 THEN uid END) AS `付费用户数`",
)

SQL_CHANNEL_CUMULATIVE_PAY_RANK = f"""
SELECT {CHANNEL_EXPR_U} AS `渠道`,
       ROUND(SUM({_pay_value("u")}), 2) AS `累计付费金额`,
       COUNT(DISTINCT CASE WHEN {_pay_value("u")} > 0 THEN u.uid END) AS `累计付费用户数`
FROM `user` u
WHERE u.dt = {_date_window_start_expr(1)}
  AND u.prod = {PROD_ID}
GROUP BY `渠道`
ORDER BY `累计付费金额` DESC
LIMIT 20
""".strip()

SQL_CUMULATIVE_PAY_AMOUNT = f"""
WITH bounds AS (
    SELECT {_date_window_start_expr(30)} AS start_dt,
           {_date_window_start_expr(1)} AS max_dt
)
SELECT STR_TO_DATE(CAST(u.dt AS CHAR), '%Y%m%d') AS `日期`,
       ROUND(SUM({_pay_value("u")}), 2) AS `累计付费金额`
FROM `user` u
JOIN bounds b ON u.dt BETWEEN b.start_dt AND b.max_dt
WHERE u.prod = {PROD_ID}
GROUP BY u.dt
ORDER BY u.dt
""".strip()

SQL_CUMULATIVE_PAY_USERS = SQL_CUMULATIVE_PAY_AMOUNT.replace(
    "ROUND(SUM(" + _pay_value("u") + "), 2) AS `累计付费金额`",
    "COUNT(DISTINCT CASE WHEN " + _pay_value("u") + " > 0 THEN u.uid END) AS `累计付费用户数`",
)

SQL_CUMULATIVE_PAY_RATE = SQL_CUMULATIVE_PAY_AMOUNT.replace(
    "ROUND(SUM(" + _pay_value("u") + "), 2) AS `累计付费金额`",
    "ROUND(COUNT(DISTINCT CASE WHEN " + _pay_value("u") + " > 0 THEN u.uid END) / NULLIF(COUNT(DISTINCT u.uid), 0) * 100, 2) AS `累计付费率`",
)

SQL_LEVEL_PAY_AMOUNT = f"""
SELECT CASE
         WHEN COALESCE(CAST({_json_text("u", "lastinfo", "level")} AS DECIMAL(18,4)), 0) < 10 THEN '0-9'
         WHEN COALESCE(CAST({_json_text("u", "lastinfo", "level")} AS DECIMAL(18,4)), 0) < 20 THEN '10-19'
         WHEN COALESCE(CAST({_json_text("u", "lastinfo", "level")} AS DECIMAL(18,4)), 0) < 30 THEN '20-29'
         ELSE '30+'
       END AS `等级段`,
       ROUND(SUM({_pay_value("u")}) / NULLIF(COUNT(DISTINCT u.uid), 0), 2) AS `人均付费金额`
FROM `user` u
WHERE u.dt = {_date_window_start_expr(1)}
  AND u.prod = {PROD_ID}
GROUP BY `等级段`
ORDER BY MIN(COALESCE(CAST({_json_text("u", "lastinfo", "level")} AS DECIMAL(18,4)), 0))
""".strip()

SQL_CURRENT_LEVEL_DISTRIBUTION = f"""
SELECT CASE
         WHEN COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.lastinfo, '$.level')), '') AS DECIMAL(18,4)), 0) < 10 THEN '0-9'
         WHEN COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.lastinfo, '$.level')), '') AS DECIMAL(18,4)), 0) < 20 THEN '10-19'
         WHEN COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.lastinfo, '$.level')), '') AS DECIMAL(18,4)), 0) < 30 THEN '20-29'
         ELSE '30+'
       END AS `等级区间`,
       COUNT(DISTINCT u.uid) AS `用户数`
FROM `user` u
WHERE u.dt = {_date_window_start_expr(1)}
  AND u.prod = {PROD_ID}
GROUP BY `等级区间`
ORDER BY MIN(COALESCE(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(u.lastinfo, '$.level')), '') AS DECIMAL(18,4)), 0))
""".strip()


VIEW_SQL: dict[str, ViewSql] = {
    "22f0761ab59449189707aca09323810e": ViewSql("核心看板", "新增用户趋势", "column", ("日期", "新增用户数"), ("日期",), ("新增用户数",), sql=SQL_NEW_USERS_DAILY),
    "29055a5fcfd74169a12373b3f0d9a412": ViewSql("新增看板", "新增用户数", "line", ("日期", "新增用户数"), ("日期",), ("新增用户数",), sql=SQL_NEW_USERS_DAILY),
    "ba48ea6e38e748ee9990b59324459b64": ViewSql("核心看板", "每日渠道新增用户", "line", ("日期", "渠道", "新增用户数"), ("日期",), ("新增用户数",), sql=SQL_NEW_USERS_BY_CHANNEL),
    "b64cc15b6dde4833ac1f8830038f673f": ViewSql("渠道分析", "每日渠道新增用户", "line", ("日期", "渠道", "新增用户数"), ("日期",), ("新增用户数",), sql=SQL_NEW_USERS_BY_CHANNEL),
    "cdf17cb957bb40499914a3ef790a79ef": ViewSql("新增看板", "每日渠道新增用户", "line", ("日期", "渠道", "新增用户数"), ("日期",), ("新增用户数",), sql=SQL_NEW_USERS_BY_CHANNEL),
    "1f099cfb059a469ebedb5d040ff84de2": ViewSql("投放看板", "每日渠道新增用户", "area", ("日期", "渠道", "新增用户数"), ("日期",), ("新增用户数",), sql=SQL_NEW_USERS_BY_CHANNEL),
    "4d8bfb37698843aab0031c74dbbf8489": ViewSql("投放看板", "单渠道新增用户", "area", ("日期", "渠道", "新增用户数"), ("日期",), ("新增用户数",), sql=SQL_NEW_USERS_BY_CHANNEL),
    "db1d8ef987724e68a1e0c9fe8b073ed1": ViewSql("新增看板", "新增用户数（按系统）", "line", ("日期", "系统", "新增用户数"), ("日期",), ("新增用户数",), sql=SQL_NEW_USERS_BY_PLATFORM),
    "f0d759307a304043883a23499a281b97": ViewSql("新增看板", "新增用户次日留存", "line", ("cohort_date", "new_users", "d1_retained_users", "d1_retention_pct"), ("cohort_date",), ("d1_retention_pct",), ("cohort_date", "new_users", "d1_retained_users", "d1_retention_pct"), SQL_D1_RETENTION),
    "f784452553f1426ea5097b092deb818a": ViewSql("新增看板", "新增首日付费金额", "line", ("日期", "新增首日付费金额"), ("日期",), ("新增首日付费金额",), sql=SQL_NEW_USERS_FIRST_DAY_PAY),
    "f39bac6b01784ca5b92c60ffe4348756": ViewSql("核心看板", "各渠道新增留存", "table", ("日期", "渠道", "用户注册用户数", "第1日", "第3日", "第7日"), columns=("日期", "渠道", "用户注册用户数", "第1日", "第3日", "第7日"), sql=SQL_CHANNEL_RETENTION),
    "63e03c7e2ad34ad58321892998497a85": ViewSql("渠道分析", "各渠道新增留存", "table", ("日期", "渠道", "用户注册用户数", "第1日", "第3日", "第7日"), columns=("日期", "渠道", "用户注册用户数", "第1日", "第3日", "第7日"), sql=SQL_CHANNEL_RETENTION),
    "6391d385e5084c0f86351ae088d3c336": ViewSql("付费概览", "7日LTV", "table", ("日期", "用户注册用户数", "当日", "第1日", "第2日", "第7日"), columns=("日期", "用户注册用户数", "当日", "第1日", "第2日", "第7日"), sql=SQL_LTV_7D),
    "6fce0cfb227b47828b41fd3c5cc736d5": ViewSql("核心看板", "ARPU与ARPPU", "line", ("日期", "ARPU", "ARPPU"), ("日期",), ("ARPU", "ARPPU"), sql=SQL_ARPU_ARPPU),
    "f75122a83c84441381fe77a551f69a28": ViewSql("付费概览", "付费情况", "table", ("日期", "付费用户数", "付费总额", "ARPU", "ARPPU", "付费渗透率"), columns=("日期", "付费用户数", "付费总额", "ARPU", "ARPPU", "付费渗透率"), sql=SQL_PAYMENT_OVERVIEW),
    "20a42bea9bcf4bc5b1bddfff187a874d": ViewSql("付费概览", "日充值总次数", "line", ("日期", "充值次数"), ("日期",), ("充值次数",), sql=SQL_DAILY_PAY_EVENT_COUNT),
    "01b402cb5b5f4c95bc457cf505a2ecc7": ViewSql("付费概览", "日充值用户数", "line", ("日期", "日充值用户数", "日新增充值用户数"), ("日期",), ("日充值用户数", "日新增充值用户数"), sql=SQL_DAILY_PAY_USERS),
    "bb9fbc7502af455cbea246821e180c72": ViewSql("付费概览", "近7日累充排名", "table", ("账号ID", "来源渠道", "区服ID", "付费总额"), columns=("账号ID", "来源渠道", "区服ID", "付费总额"), sql=SQL_7D_PAY_RANK),
    "24a51da63ed84379adbec45927500dce": ViewSql("渠道分析", "付费用户数（按渠道）", "line", ("日期", "渠道", "付费用户数"), ("日期",), ("付费用户数",), sql=SQL_CHANNEL_PAY_USERS),
    "8b1c7fa28da041afaf91d4a834a9a84a": ViewSql("渠道分析", "付费金额（按渠道）", "line", ("日期", "渠道", "付费金额"), ("日期",), ("付费金额",), sql=SQL_CHANNEL_PAY_AMOUNT),
    "89d495c3733a441799b032cd7407df01": ViewSql("核心看板", "渠道累计付费排行", "bar", ("渠道", "累计付费金额", "累计付费用户数"), ("渠道",), ("累计付费金额",), sql=SQL_CHANNEL_CUMULATIVE_PAY_RANK),
    "65f52e391c5a430b8c8d2575195082f4": ViewSql("核心看板", "累计付费金额趋势", "line", ("日期", "累计付费金额"), ("日期",), ("累计付费金额",), sql=SQL_CUMULATIVE_PAY_AMOUNT),
    "b9043b8bca964589949a11c198154af4": ViewSql("核心看板", "累计付费用户趋势", "line", ("日期", "累计付费用户数"), ("日期",), ("累计付费用户数",), sql=SQL_CUMULATIVE_PAY_USERS),
    "e300602c05804ecc93123625f9bafa3a": ViewSql("核心看板", "累计付费率", "line", ("日期", "累计付费率"), ("日期",), ("累计付费率",), sql=SQL_CUMULATIVE_PAY_RATE),
    "eabf5e30333342ed8bf47dfcd0898278": ViewSql("付费概览", "各等级段人均付费金额", "column", ("等级段", "人均付费金额"), ("等级段",), ("人均付费金额",), sql=SQL_LEVEL_PAY_AMOUNT),
    "de17a15e36b14e79826a86637c576514": ViewSql("核心看板", "当前等级分布", "column", ("等级区间", "用户数"), ("等级区间",), ("用户数",), sql=SQL_CURRENT_LEVEL_DISTRIBUTION),
}


def axis(field: str) -> dict[str, str]:
    return {"name": DISPLAY_NAMES.get(field, field), "value": field}


def sql_blocks_markdown(view_ids: list[str] | tuple[str, ...]) -> str:
    blocks: list[str] = []
    for view_id in view_ids:
        view = VIEW_SQL[view_id]
        blocks.append(
            f"<!-- dashboard-sql:{view_id} -->\n```sql\n{view.sql.strip()}\n```"
        )
    return "\n\n".join(blocks)
