# -*- coding: utf-8 -*-
"""Datasource-scoped SQL definitions for the flam active dashboard."""

from __future__ import annotations

from dataclasses import dataclass


TENANT_ID = 7477202383789887488
DATASOURCE_ID = 3
DASHBOARD_ID = "8c93878ee7af41b9b3832547856d25e6"

ACTIVE_EVENT = 'UserActive'
LOGIN_EVENTS = f"'{ACTIVE_EVENT}'"
PROD_ID = 110000038


def _active_start_dt_expr(days: int = 29) -> str:
    return f"CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL {days} DAY), '%Y%m%d') AS SIGNED)"


def _active_end_dt_expr() -> str:
    return "CAST(DATE_FORMAT(CURDATE(), '%Y%m%d') AS SIGNED)"


@dataclass(frozen=True)
class ViewSql:
    title: str
    chart_type: str
    fields: tuple[str, ...]
    x_axis: tuple[str, ...] = ()
    y_axis: tuple[str, ...] = ()
    columns: tuple[str, ...] = ()
    sql: str = ""


def _json_text(alias: str, obj: str, key: str) -> str:
    return f"NULLIF(JSON_UNQUOTE(JSON_EXTRACT({alias}.{obj}, '$.{key}')), '')"


CHANNEL_EXPR_E = (
    "COALESCE("
    + _json_text("e", "adinfo", "mediaSource")
    + ", "
    + _json_text("e", "adinfo", "campaignName")
    + ", '未知')"
)
PLATFORM_EXPR_E = (
    "COALESCE("
    + _json_text("e", "deviceinfo", "_platform")
    + ", "
    + _json_text("e", "userinfo", "_platformType")
    + ", '未知')"
)


SQL_DAU = f"""
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
       COUNT(DISTINCT e.uid) AS `DAU`
FROM `event` e
WHERE e.dt BETWEEN {_active_start_dt_expr(30)}
               AND {_active_end_dt_expr()}
  AND e.event IN ({LOGIN_EVENTS})
  AND e.prod = {PROD_ID}
GROUP BY e.dt
ORDER BY e.dt
""".strip()

SQL_WAU = f"""
WITH weeks AS (
    SELECT DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY) AS latest_week_start
), bounds AS (
    SELECT CAST(DATE_FORMAT(DATE_SUB(latest_week_start, INTERVAL 11 WEEK), '%Y%m%d') AS SIGNED) AS start_dt,
           CAST(DATE_FORMAT(DATE_ADD(latest_week_start, INTERVAL 6 DAY), '%Y%m%d') AS SIGNED) AS end_dt
    FROM weeks
)
SELECT DATE_SUB(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'), INTERVAL WEEKDAY(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d')) DAY) AS `周`,
       COUNT(DISTINCT e.uid) AS `WAU`
FROM `event` e
JOIN bounds b ON TRUE
WHERE e.dt BETWEEN b.start_dt AND b.end_dt
  AND e.event IN ({LOGIN_EVENTS})
  AND e.prod = {PROD_ID}
GROUP BY `周`
ORDER BY `周`
""".strip()

SQL_MAU = f"""
WITH months AS (
    SELECT DATE_FORMAT(CURDATE(), '%Y-%m-01') AS latest_month_start
), bounds AS (
    SELECT CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(latest_month_start, '%Y-%m-%d'), INTERVAL 11 MONTH), '%Y%m%d') AS SIGNED) AS start_dt,
           CAST(DATE_FORMAT(LAST_DAY(STR_TO_DATE(latest_month_start, '%Y-%m-%d')), '%Y%m%d') AS SIGNED) AS end_dt
    FROM months
)
SELECT DATE_FORMAT(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'), '%Y-%m') AS `月份`,
       COUNT(DISTINCT e.uid) AS `MAU`
FROM `event` e
JOIN bounds b ON TRUE
WHERE e.dt BETWEEN b.start_dt AND b.end_dt
  AND e.event IN ({LOGIN_EVENTS})
  AND e.prod = {PROD_ID}
GROUP BY `月份`
ORDER BY `月份`
""".strip()

SQL_LIFECYCLE = f"""
WITH active_uid AS (
    SELECT e.dt, e.uid
    FROM `event` e
    WHERE e.dt BETWEEN {_active_start_dt_expr(30)}
                   AND {_active_end_dt_expr()}
      AND e.event IN ({LOGIN_EVENTS})
      AND e.prod = {PROD_ID}
    GROUP BY e.dt, e.uid
), active_snapshot AS (
    SELECT a.dt,
           a.uid,
           COALESCE(CAST({_json_text("u", "lastinfo", "regnday")} AS DECIMAL(18,4)), 0) AS regnday
    FROM active_uid a
    LEFT JOIN `user` u
      ON u.uid = a.uid
     AND u.dt = a.dt
     AND u.prod = {PROD_ID}
)
SELECT STR_TO_DATE(CAST(dt AS CHAR), '%Y%m%d') AS `日期`,
       CASE
         WHEN regnday <= 1 THEN '新增期'
         WHEN regnday <= 7 THEN '成长期'
         WHEN regnday <= 30 THEN '稳定期'
         ELSE '成熟期'
       END AS `生命周期`,
       COUNT(DISTINCT uid) AS `活跃用户数`
FROM active_snapshot
GROUP BY dt, `生命周期`
ORDER BY dt, `生命周期`
""".strip()

SQL_ACTIVE_BY_CHANNEL = f"""
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
       {CHANNEL_EXPR_E} AS `渠道`,
       COUNT(DISTINCT e.uid) AS `活跃用户数`
FROM `event` e
WHERE e.dt BETWEEN {_active_start_dt_expr(30)}
               AND {_active_end_dt_expr()}
  AND e.event IN ({LOGIN_EVENTS})
  AND e.prod = {PROD_ID}
GROUP BY e.dt, `渠道`
ORDER BY e.dt, `渠道`
LIMIT 300
""".strip()

SQL_ACTIVE_BY_PLATFORM = f"""
SELECT STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d') AS `日期`,
       {PLATFORM_EXPR_E} AS `系统`,
       COUNT(DISTINCT e.uid) AS `活跃用户数`
FROM `event` e
WHERE e.dt BETWEEN {_active_start_dt_expr(30)}
               AND {_active_end_dt_expr()}
  AND e.event IN ({LOGIN_EVENTS})
  AND e.prod = {PROD_ID}
GROUP BY e.dt, `系统`
ORDER BY e.dt, `系统`
LIMIT 300
""".strip()

SQL_WEEKLY_LOGIN_DAYS = f"""
WITH weeks AS (
    SELECT DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY) AS latest_week_start
), bounds AS (
    SELECT CAST(DATE_FORMAT(DATE_SUB(latest_week_start, INTERVAL 11 WEEK), '%Y%m%d') AS SIGNED) AS start_dt,
           CAST(DATE_FORMAT(DATE_ADD(latest_week_start, INTERVAL 6 DAY), '%Y%m%d') AS SIGNED) AS end_dt
    FROM weeks
), user_week AS (
    SELECT DATE_SUB(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'), INTERVAL WEEKDAY(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d')) DAY) AS week_start,
           e.uid,
           COUNT(DISTINCT e.dt) AS login_days
    FROM `event` e
    JOIN bounds b ON TRUE
    WHERE e.dt BETWEEN b.start_dt AND b.end_dt
      AND e.event IN ({LOGIN_EVENTS})
      AND e.prod = {PROD_ID}
    GROUP BY week_start, e.uid
)
SELECT week_start AS `周`,
       COUNT(DISTINCT uid) AS `全部用户`,
       SUM(CASE WHEN login_days = 1 THEN 1 ELSE 0 END) AS `1天`,
       SUM(CASE WHEN login_days = 2 THEN 1 ELSE 0 END) AS `2天`,
       SUM(CASE WHEN login_days = 3 THEN 1 ELSE 0 END) AS `3天`,
       SUM(CASE WHEN login_days = 4 THEN 1 ELSE 0 END) AS `4天`,
       SUM(CASE WHEN login_days = 5 THEN 1 ELSE 0 END) AS `5天`,
       SUM(CASE WHEN login_days = 6 THEN 1 ELSE 0 END) AS `6天`,
       SUM(CASE WHEN login_days >= 7 THEN 1 ELSE 0 END) AS `7天`
FROM user_week
GROUP BY week_start
ORDER BY week_start
""".strip()


VIEW_SQL: dict[str, ViewSql] = {
    "a7a7e09c7289414999a25657fa95d527": ViewSql("DAU", "line", ("日期", "DAU"), ("日期",), ("DAU",), sql=SQL_DAU),
    "e3e716d42d654e61ab80c62c1915d0e8": ViewSql("DAU趋势", "line", ("日期", "DAU"), ("日期",), ("DAU",), sql=SQL_DAU),
    "839ce2cab673467ab22fe508bf822d61": ViewSql("WAU", "line", ("周", "WAU"), ("周",), ("WAU",), sql=SQL_WAU),
    "77aa7f9c7c2c4eb38d821d10379978e7": ViewSql("MAU", "line", ("月份", "MAU"), ("月份",), ("MAU",), sql=SQL_MAU),
    "3ea113a229784c6f9c04b2a7b91d65b6": ViewSql("活跃用户生命周期构成", "line", ("日期", "生命周期", "活跃用户数"), ("日期",), ("活跃用户数",), sql=SQL_LIFECYCLE),
    "03c44a9f89f2403ea7a9b168da0a13e8": ViewSql("活跃用户数（按渠道）", "line", ("日期", "渠道", "活跃用户数"), ("日期",), ("活跃用户数",), sql=SQL_ACTIVE_BY_CHANNEL),
    "8b3e5b7179af442e8fded00ae25a0245": ViewSql("活跃用户数（按渠道）", "line", ("日期", "渠道", "活跃用户数"), ("日期",), ("活跃用户数",), sql=SQL_ACTIVE_BY_CHANNEL),
    "38a1356c04aa4bd2817a0ec9d396d8b6": ViewSql("活跃用户数（按系统）", "line", ("日期", "系统", "活跃用户数"), ("日期",), ("活跃用户数",), sql=SQL_ACTIVE_BY_PLATFORM),
    "f0793fb6af7845c8be2b39e2d7ea523f": ViewSql("周登录天数分布", "table", ("周", "全部用户", "1天", "2天", "3天", "4天", "5天", "6天", "7天"), columns=("周", "全部用户", "1天", "2天", "3天", "4天", "5天", "6天", "7天"), sql=SQL_WEEKLY_LOGIN_DAYS),
}


def axis(field: str) -> dict[str, str]:
    return {"name": field, "value": field}


def sql_blocks_markdown(view_ids: list[str] | tuple[str, ...] | None = None) -> str:
    blocks: list[str] = []
    for view_id in view_ids or tuple(VIEW_SQL):
        view = VIEW_SQL[view_id]
        blocks.append(f"<!-- dashboard-sql:{view_id} -->\n```sql\n{view.sql.strip()}\n```")
    return "\n\n".join(blocks)
