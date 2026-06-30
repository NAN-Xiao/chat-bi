# -*- coding: utf-8 -*-
"""Datasource-scoped SQL definitions for remaining flam core dashboard components."""

from __future__ import annotations

from dataclasses import dataclass

from flam_first_zombie_active_dashboard_sql import SQL_DAU
from flam_first_zombie_dashboard_sql import VIEW_SQL as SHARED_VIEW_SQL


TENANT_ID = 7477202383789887488
DATASOURCE_ID = 3
DASHBOARD_ID = "6d50bd7dfc9f46ba961d636814c3294d"

PAY_EVENTS = (
    "'PayBuyRet','PayBuyRetBenifit','PayBuyRetSandBox','PayFinish',"
    "'ServerPayLog','ep_pay_purchase_finish','ep_pay_update_db_finish'"
)
PROD_ID = 110000038


def _date_expr(days_ago: int = 0) -> str:
    if days_ago <= 0:
        return "CAST(DATE_FORMAT(CURDATE(), '%Y%m%d') AS SIGNED)"
    return f"CAST(DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL {days_ago} DAY), '%Y%m%d') AS SIGNED)"


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


SQL_GIFT_PURCHASE = f"""
SELECT
    {_json_text("e", "personal", "productid")} AS `购买礼包ID`,
    COUNT(*) AS `购买次数`,
    COUNT(DISTINCT e.uid) AS `购买人数`
FROM `event` e
WHERE e.dt BETWEEN {_date_expr(30)} AND {_date_expr()}
  AND e.prod = {PROD_ID}
  AND e.event = 'ServerPayLog'
  AND {_json_text("e", "personal", "productid")} IS NOT NULL
GROUP BY `购买礼包ID`
ORDER BY `购买次数` DESC
LIMIT 1000;
""".strip()

SQL_ONBOARDING_FUNNEL = f"""
WITH cohort AS (
    SELECT u.uid,
           u.dt AS cohort_dt
    FROM `user` u
    WHERE u.dt BETWEEN {_date_expr(30)} AND {_date_expr(1)}
      AND u.prod = {PROD_ID}
      AND JSON_UNQUOTE(JSON_EXTRACT(u.userinfo, '$.regdate')) = CAST(u.dt AS CHAR)
), event_window AS (
    SELECT e.uid,
           e.event
    FROM `event` e
    WHERE e.dt BETWEEN {_date_expr(30)} AND {_date_expr(1)}
      AND e.event IN ('EnterGame','Login','UserLogin','NewUserGuideStart','DialogueStart','NewUserGuide','DialogueEnd','ChapterTaskReward','TaskReward')
      AND e.prod = {PROD_ID}
), step_users AS (
    SELECT 1 AS step_order, '账号注册' AS step_name, COUNT(DISTINCT c.uid) AS users
    FROM cohort c
    UNION ALL
    SELECT 2, '进入游戏', COUNT(DISTINCT c.uid)
    FROM cohort c
    JOIN event_window e ON e.uid = c.uid AND e.event IN ('EnterGame','Login','UserLogin')
    UNION ALL
    SELECT 3, '引导开始', COUNT(DISTINCT c.uid)
    FROM cohort c
    JOIN event_window e ON e.uid = c.uid AND e.event IN ('NewUserGuideStart','DialogueStart')
    UNION ALL
    SELECT 4, '引导完成', COUNT(DISTINCT c.uid)
    FROM cohort c
    JOIN event_window e ON e.uid = c.uid AND e.event IN ('NewUserGuide','DialogueEnd')
    UNION ALL
    SELECT 5, '章节/任务领奖', COUNT(DISTINCT c.uid)
    FROM cohort c
    JOIN event_window e ON e.uid = c.uid AND e.event IN ('ChapterTaskReward','TaskReward')
), calc AS (
    SELECT s.step_order,
           s.step_name,
           s.users,
           base.users AS start_users,
           COALESCE(prev.users, s.users) AS prev_users
    FROM step_users s
    LEFT JOIN step_users base ON base.step_order = 1
    LEFT JOIN step_users prev ON prev.step_order = s.step_order - 1
)
SELECT step_order,
       step_name AS `新手步骤`,
       users AS `用户数`,
       ROUND(users / NULLIF(start_users, 0) * 100, 2) AS `整体转化率`,
       ROUND(users / NULLIF(COALESCE(prev_users, users), 0) * 100, 2) AS `上步转化率`,
       GREATEST(COALESCE(prev_users, users) - users, 0) AS `流失人数`
FROM calc
ORDER BY step_order
""".strip()


CORE_ONLY_VIEW_SQL: dict[str, ViewSql] = {
    "551d465e59fa454ba97ff9ef0ad0dd2a": ViewSql(
        "礼包购买情况",
        "table",
        ("购买礼包ID", "购买次数", "购买人数"),
        columns=("购买礼包ID", "购买次数", "购买人数"),
        sql=SQL_GIFT_PURCHASE,
    ),
    "73cfeb49a58a44799e5a91371fbe296d": ViewSql(
        "新手引导漏斗转化",
        "funnel",
        ("step_order", "新手步骤", "用户数", "整体转化率", "上步转化率", "流失人数"),
        ("新手步骤",),
        ("用户数",),
        ("step_order", "新手步骤", "用户数", "整体转化率", "上步转化率", "流失人数"),
        SQL_ONBOARDING_FUNNEL,
    ),
}

CORE_DASHBOARD_VIEW_IDS = (
    "6fce0cfb227b47828b41fd3c5cc736d5",
    "e300602c05804ecc93123625f9bafa3a",
    "e3e716d42d654e61ab80c62c1915d0e8",
    "22f0761ab59449189707aca09323810e",
    "65f52e391c5a430b8c8d2575195082f4",
    "b9043b8bca964589949a11c198154af4",
    "ba48ea6e38e748ee9990b59324459b64",
    "89d495c3733a441799b032cd7407df01",
    "551d465e59fa454ba97ff9ef0ad0dd2a",
    "de17a15e36b14e79826a86637c576514",
    "73cfeb49a58a44799e5a91371fbe296d",
    "f39bac6b01784ca5b92c60ffe4348756",
)

CORE_DASHBOARD_VIEW_SQL: dict[str, ViewSql] = {
    "6fce0cfb227b47828b41fd3c5cc736d5": SHARED_VIEW_SQL["6fce0cfb227b47828b41fd3c5cc736d5"],
    "e300602c05804ecc93123625f9bafa3a": SHARED_VIEW_SQL["e300602c05804ecc93123625f9bafa3a"],
    "e3e716d42d654e61ab80c62c1915d0e8": ViewSql("DAU趋势", "line", ("日期", "DAU"), ("日期",), ("DAU",), sql=SQL_DAU),
    "22f0761ab59449189707aca09323810e": SHARED_VIEW_SQL["22f0761ab59449189707aca09323810e"],
    "65f52e391c5a430b8c8d2575195082f4": SHARED_VIEW_SQL["65f52e391c5a430b8c8d2575195082f4"],
    "b9043b8bca964589949a11c198154af4": SHARED_VIEW_SQL["b9043b8bca964589949a11c198154af4"],
    "ba48ea6e38e748ee9990b59324459b64": SHARED_VIEW_SQL["ba48ea6e38e748ee9990b59324459b64"],
    "89d495c3733a441799b032cd7407df01": SHARED_VIEW_SQL["89d495c3733a441799b032cd7407df01"],
    "551d465e59fa454ba97ff9ef0ad0dd2a": CORE_ONLY_VIEW_SQL["551d465e59fa454ba97ff9ef0ad0dd2a"],
    "de17a15e36b14e79826a86637c576514": SHARED_VIEW_SQL["de17a15e36b14e79826a86637c576514"],
    "73cfeb49a58a44799e5a91371fbe296d": CORE_ONLY_VIEW_SQL["73cfeb49a58a44799e5a91371fbe296d"],
    "f39bac6b01784ca5b92c60ffe4348756": SHARED_VIEW_SQL["f39bac6b01784ca5b92c60ffe4348756"],
}


def axis(field: str) -> dict[str, str]:
    return {"name": field, "value": field}


def sql_blocks_markdown(view_ids: list[str] | tuple[str, ...] | None = None) -> str:
    blocks: list[str] = []
    for view_id in view_ids or tuple(CORE_ONLY_VIEW_SQL):
        view = CORE_ONLY_VIEW_SQL[view_id]
        blocks.append(f"<!-- dashboard-sql:{view_id} -->\n```sql\n{view.sql.strip()}\n```")
    return "\n\n".join(blocks)
