"""Create the SLG BI Mock core dashboard report.

This script writes chart layout/configuration into the app system database
(`zhishu_bi` on 127.0.0.1:15432) and reads preview data from the detail-level
tracking database (`slg_bi_mock` on 127.0.0.1:5432).

It does not create aggregate tables, snapshot tables, or analysis views.
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


SYSTEM_DB = {
    "host": "10.1.5.28",
    "port": 5432,
    "dbname": "zhishu_bi",
    "user": "root",
    "password": "Password123@pg",
}
BI_DB = {
    "host": "10.1.5.28",
    "port": 5432,
    "dbname": "slg_bi_mock",
    "user": "root",
    "password": "Password123@pg",
}

DASHBOARD_ID = "5e16dcf469a7491780e48eed5086eb57"
DATASOURCE_ID = 1
UPDATE_BY = "7471612174524223488"
BACKUP_DIR = Path(".codex-runtime/backups")

BASE_BOUNDS = """
WITH bounds AS (
    SELECT max(session_start::date) AS end_date,
           max(session_start::date) - 29 AS start_date
    FROM public.fact_sessions
)
"""


def json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: json_value(value) for key, value in row.items()}


def axis(
    value: str,
    name: str | None = None,
    axis_type: str | None = None,
    multi: bool | None = None,
    hidden: bool | None = None,
    metric_type: str | None = None,
    pivot_aggregation: str | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {"value": value}
    if name and name != value:
        item["name"] = name
    if axis_type:
        item["type"] = axis_type
    if multi is not None:
        item["multi-quota"] = multi
    if hidden is not None:
        item["hidden"] = hidden
    if metric_type:
        item["metricType"] = metric_type
    if pivot_aggregation:
        item["pivotAggregation"] = pivot_aggregation
    return item


def chart(
    chart_id: str,
    title: str,
    chart_type: str,
    layout: tuple[int, int, int, int],
    sql: str,
    x_axis: list[dict[str, Any]] | None = None,
    y_axis: list[dict[str, Any]] | None = None,
    series: list[dict[str, Any]] | None = None,
    show_label: bool = False,
    pivot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": chart_id,
        "title": title,
        "type": chart_type,
        "layout": layout,
        "sql": sql,
        "x": x_axis or [],
        "y": y_axis or [],
        "series": series or [],
        "showLabel": show_label,
        "pivot": pivot or {"enabled": False},
    }


CHARTS = [
    chart(
        "2185000000000000001",
        "ARPU与ARPPU",
        "line",
        (1, 1, 36, 13),
        BASE_BOUNDS
        + """
, dates AS (
    SELECT generate_series(start_date, end_date, interval '1 day')::date AS dt
    FROM bounds
), daily_active AS (
    SELECT s.session_start::date AS dt,
           count(DISTINCT s.player_id) AS active_users
    FROM public.fact_sessions s, bounds b
    WHERE s.session_start::date BETWEEN b.start_date AND b.end_date
    GROUP BY 1
), daily_pay AS (
    SELECT p.event_date AS dt,
           count(DISTINCT p.player_id) AS payers,
           sum(p.net_revenue_usd) AS revenue
    FROM public.fact_payments p, bounds b
    WHERE p.payment_status = 'success'
      AND p.net_revenue_usd > 0
      AND p.event_date BETWEEN b.start_date AND b.end_date
    GROUP BY 1
)
SELECT d.dt AS "日期",
       coalesce(round(coalesce(p.revenue, 0)::numeric / nullif(a.active_users, 0), 2), 0) AS "ARPU",
       coalesce(round(coalesce(p.revenue, 0)::numeric / nullif(p.payers, 0), 2), 0) AS "ARPPU"
FROM dates d
LEFT JOIN daily_active a ON a.dt = d.dt
LEFT JOIN daily_pay p ON p.dt = d.dt
ORDER BY d.dt
""",
        [axis("日期", axis_type="x")],
        [
            axis("ARPU", axis_type="y", multi=True, metric_type="average", pivot_aggregation="avg"),
            axis("ARPPU", axis_type="y", multi=True, metric_type="average", pivot_aggregation="avg"),
        ],
    ),
    chart(
        "2185000000000000002",
        "日付费率",
        "line",
        (37, 1, 36, 13),
        BASE_BOUNDS
        + """
, dates AS (
    SELECT generate_series(start_date, end_date, interval '1 day')::date AS dt
    FROM bounds
), daily_active AS (
    SELECT s.session_start::date AS dt,
           count(DISTINCT s.player_id) AS active_users
    FROM public.fact_sessions s, bounds b
    WHERE s.session_start::date BETWEEN b.start_date AND b.end_date
    GROUP BY 1
), daily_pay AS (
    SELECT p.event_date AS dt,
           count(DISTINCT p.player_id) AS payers
    FROM public.fact_payments p, bounds b
    WHERE p.payment_status = 'success'
      AND p.net_revenue_usd > 0
      AND p.event_date BETWEEN b.start_date AND b.end_date
    GROUP BY 1
)
SELECT d.dt AS "日期",
       coalesce(round(coalesce(p.payers, 0)::numeric / nullif(a.active_users, 0) * 100, 2), 0) AS "付费率"
FROM dates d
LEFT JOIN daily_active a ON a.dt = d.dt
LEFT JOIN daily_pay p ON p.dt = d.dt
ORDER BY d.dt
""",
        [axis("日期", axis_type="x")],
        [axis("付费率", axis_type="y", metric_type="ratio", pivot_aggregation="avg")],
        pivot={
            "enabled": True,
            "time_field": "日期",
            "metric_field": "付费率",
            "metric_fields": ["付费率"],
            "metric_aggregations": {"付费率": "avg"},
            "group_field": "",
            "group_enabled": False,
            "range_enabled": True,
            "granularity": "day",
            "range": "source",
            "custom_start": "",
            "custom_end": "",
            "aggregation": "avg",
        },
    ),
    chart(
        "2185000000000000003",
        "DAU趋势",
        "line",
        (1, 14, 36, 13),
        BASE_BOUNDS
        + """
, dates AS (
    SELECT generate_series(start_date, end_date, interval '1 day')::date AS dt
    FROM bounds
), dau AS (
    SELECT s.session_start::date AS dt,
           count(DISTINCT s.player_id) AS dau
    FROM public.fact_sessions s, bounds b
    WHERE s.session_start::date BETWEEN b.start_date AND b.end_date
    GROUP BY 1
)
SELECT d.dt AS "日期",
       coalesce(dau.dau, 0) AS "DAU"
FROM dates d
LEFT JOIN dau ON dau.dt = d.dt
ORDER BY d.dt
""",
        [axis("日期", axis_type="x")],
        [axis("DAU", axis_type="y", metric_type="snapshot", pivot_aggregation="avg")],
    ),
    chart(
        "2185000000000000004",
        "新增用户趋势",
        "column",
        (37, 14, 36, 13),
        BASE_BOUNDS
        + """
, dates AS (
    SELECT generate_series(start_date, end_date, interval '1 day')::date AS dt
    FROM bounds
), installs AS (
    SELECT p.install_date AS dt,
           count(*) AS new_users
    FROM public.dim_player p, bounds b
    WHERE p.install_date BETWEEN b.start_date AND b.end_date
    GROUP BY 1
)
SELECT d.dt AS "日期",
       coalesce(i.new_users, 0) AS "新增用户数"
FROM dates d
LEFT JOIN installs i ON i.dt = d.dt
ORDER BY d.dt
""",
        [axis("日期", axis_type="x")],
        [axis("新增用户数", axis_type="y", metric_type="additive", pivot_aggregation="sum")],
    ),
    chart(
        "2185000000000000005",
        "收入趋势",
        "line",
        (1, 27, 36, 13),
        BASE_BOUNDS
        + """
, dates AS (
    SELECT generate_series(start_date, end_date, interval '1 day')::date AS dt
    FROM bounds
), revenue AS (
    SELECT p.event_date AS dt,
           round(sum(p.net_revenue_usd), 2) AS net_revenue
    FROM public.fact_payments p, bounds b
    WHERE p.payment_status = 'success'
      AND p.net_revenue_usd > 0
      AND p.event_date BETWEEN b.start_date AND b.end_date
    GROUP BY 1
)
SELECT d.dt AS "日期",
       coalesce(r.net_revenue, 0) AS "净收入"
FROM dates d
LEFT JOIN revenue r ON r.dt = d.dt
ORDER BY d.dt
""",
        [axis("日期", axis_type="x")],
        [axis("净收入", axis_type="y", metric_type="additive", pivot_aggregation="sum")],
    ),
    chart(
        "2185000000000000006",
        "付费人数趋势",
        "line",
        (37, 27, 36, 13),
        BASE_BOUNDS
        + """
, dates AS (
    SELECT generate_series(start_date, end_date, interval '1 day')::date AS dt
    FROM bounds
), pay AS (
    SELECT p.event_date AS dt,
           count(DISTINCT p.player_id) AS payers,
           count(*) AS payment_orders
    FROM public.fact_payments p, bounds b
    WHERE p.payment_status = 'success'
      AND p.net_revenue_usd > 0
      AND p.event_date BETWEEN b.start_date AND b.end_date
    GROUP BY 1
)
SELECT d.dt AS "日期",
       coalesce(p.payers, 0) AS "付费人数",
       coalesce(p.payment_orders, 0) AS "付费次数"
FROM dates d
LEFT JOIN pay p ON p.dt = d.dt
ORDER BY d.dt
""",
        [axis("日期", axis_type="x")],
        [
            axis("付费人数", axis_type="y", multi=True, metric_type="snapshot", pivot_aggregation="avg"),
            axis("付费次数", axis_type="y", multi=True, metric_type="additive", pivot_aggregation="sum"),
        ],
    ),
    chart(
        "2185000000000000007",
        "渠道新增用户数",
        "line",
        (1, 40, 36, 13),
        BASE_BOUNDS
        + """
, top_channels AS (
    SELECT channel_name
    FROM (
        SELECT CASE
                 WHEN nullif(trim(p.bi_channel_name), '') IS NOT NULL THEN p.bi_channel_name
                 WHEN nullif(trim(p.registration_channel), '') IS NOT NULL THEN p.registration_channel
                 WHEN p.channel = 'iOS,app store' THEN 'app store'
                 WHEN p.channel = 'huawei_store' THEN '华为应用商城'
                 WHEN p.channel = 'yingyongbao' THEN '应用宝'
                 WHEN p.channel = 'xiaomi_store' THEN '小米应用商城'
                 WHEN p.channel = 'google_play' THEN 'Google Play'
                 WHEN p.channel = 'qihu_360' THEN '360手机助手'
                 WHEN p.channel = 'baidu_store' THEN '百度手机助手'
                 WHEN p.channel = 'wandoujia' THEN '豌豆荚'
                 ELSE coalesce(nullif(trim(p.channel), ''), '未知')
               END AS channel_name
        FROM public.dim_player p, bounds b
        WHERE p.install_date BETWEEN b.start_date AND b.end_date
    ) n
    GROUP BY channel_name
    ORDER BY count(*) DESC
    LIMIT 6
), normalized_installs AS (
    SELECT p.install_date AS dt,
           CASE
             WHEN nullif(trim(p.bi_channel_name), '') IS NOT NULL THEN p.bi_channel_name
             WHEN nullif(trim(p.registration_channel), '') IS NOT NULL THEN p.registration_channel
             WHEN p.channel = 'iOS,app store' THEN 'app store'
             WHEN p.channel = 'huawei_store' THEN '华为应用商城'
             WHEN p.channel = 'yingyongbao' THEN '应用宝'
             WHEN p.channel = 'xiaomi_store' THEN '小米应用商城'
             WHEN p.channel = 'google_play' THEN 'Google Play'
             WHEN p.channel = 'qihu_360' THEN '360手机助手'
             WHEN p.channel = 'baidu_store' THEN '百度手机助手'
             WHEN p.channel = 'wandoujia' THEN '豌豆荚'
             ELSE coalesce(nullif(trim(p.channel), ''), '未知')
           END AS channel_name
    FROM public.dim_player p, bounds b
    WHERE p.install_date BETWEEN b.start_date AND b.end_date
), channel_installs AS (
    SELECT dt,
           CASE WHEN channel_name IN (SELECT channel_name FROM top_channels) THEN channel_name ELSE '其他' END AS channel_group,
           count(*) AS new_users
    FROM normalized_installs
    GROUP BY 1, 2
)
SELECT dt AS "日期",
       channel_group AS "渠道",
       new_users AS "新增用户数"
FROM channel_installs
ORDER BY dt, new_users DESC, channel_group
""",
        [axis("日期", axis_type="x")],
        [axis("新增用户数", axis_type="y", metric_type="additive", pivot_aggregation="sum")],
        [axis("渠道", axis_type="series")],
    ),
    chart(
        "2185000000000000008",
        "渠道收入排行",
        "bar",
        (37, 40, 36, 13),
        BASE_BOUNDS
        + """
SELECT dp.channel AS "渠道",
       round(sum(fp.net_revenue_usd), 2) AS "净收入",
       count(DISTINCT fp.player_id) AS "付费人数"
FROM public.fact_payments fp
JOIN public.dim_player dp ON dp.player_id = fp.player_id
JOIN bounds b ON fp.event_date BETWEEN b.start_date AND b.end_date
WHERE fp.payment_status = 'success'
  AND fp.net_revenue_usd > 0
GROUP BY dp.channel
ORDER BY "净收入" DESC
LIMIT 10
""",
        [axis("渠道", axis_type="x")],
        [axis("净收入", axis_type="y", metric_type="additive", pivot_aggregation="sum")],
    ),
    chart(
        "2185000000000000009",
        "礼包购买情况",
        "table",
        (1, 53, 36, 16),
        """
SELECT fp.product_name AS "购买礼包名",
       count(*) AS "购买次数",
       count(DISTINCT fp.player_id) AS "购买人数",
       round(sum(fp.net_revenue_usd), 2) AS "购买总金额"
FROM public.fact_payments fp
WHERE fp.event_date = (SELECT max(event_date) FROM public.fact_payments)
  AND fp.payment_status = 'success'
  AND fp.net_revenue_usd > 0
GROUP BY fp.product_name
ORDER BY count(*) DESC, sum(fp.net_revenue_usd) DESC
LIMIT 20
""",
    ),
    chart(
        "2185000000000000010",
        "当前等级分布",
        "column",
        (37, 53, 36, 16),
        """
WITH bucketed AS (
    SELECT CASE
             WHEN current_level >= 0 AND current_level < 9 THEN '[0, 9)'
             WHEN current_level >= 9 AND current_level < 18 THEN '[9, 18)'
             WHEN current_level >= 18 AND current_level < 27 THEN '[18, 27)'
             WHEN current_level >= 27 AND current_level < 36 THEN '[27, 36)'
             WHEN current_level >= 36 AND current_level < 45 THEN '[36, 45)'
             WHEN current_level >= 45 AND current_level < 54 THEN '[45, 54)'
             WHEN current_level >= 54 AND current_level < 63 THEN '[54, 63)'
             ELSE '[63, 72)'
           END AS level_bucket,
           CASE
             WHEN current_level >= 0 AND current_level < 9 THEN 1
             WHEN current_level >= 9 AND current_level < 18 THEN 2
             WHEN current_level >= 18 AND current_level < 27 THEN 3
             WHEN current_level >= 27 AND current_level < 36 THEN 4
             WHEN current_level >= 36 AND current_level < 45 THEN 5
             WHEN current_level >= 45 AND current_level < 54 THEN 6
             WHEN current_level >= 54 AND current_level < 63 THEN 7
             ELSE 8
           END AS bucket_sort
    FROM public.dim_player
)
SELECT level_bucket AS "等级区间",
       count(*) AS "用户数"
FROM bucketed
GROUP BY level_bucket, bucket_sort
ORDER BY bucket_sort
""",
        [axis("等级区间", axis_type="x")],
        [axis("用户数", axis_type="y", metric_type="snapshot", pivot_aggregation="avg")],
    ),
    chart(
        "2185000000000000011",
        "新手引导漏斗转化",
        "funnel",
        (1, 69, 72, 15),
        BASE_BOUNDS
        + """
, cohort_players AS (
    SELECT p.player_id
    FROM public.dim_player p, bounds b
    WHERE p.install_date BETWEEN b.start_date AND b.end_date
), tutorial_steps AS (
    SELECT jsonb_extract_path_text(e.attributes, 'step')::int AS tutorial_step,
           count(DISTINCT e.player_id) AS users
    FROM public.fact_events e
    JOIN cohort_players c ON c.player_id = e.player_id
    JOIN bounds b ON e.event_date BETWEEN b.start_date AND b.end_date
    WHERE e.event_name = 'tutorial_step'
      AND jsonb_extract_path_text(e.attributes, 'step') IS NOT NULL
    GROUP BY 1
), funnel_steps AS (
    SELECT 1 AS display_order,
           '步骤1: 账号注册' AS step_name,
           count(*) AS users
    FROM cohort_players
    UNION ALL
    SELECT tutorial_step + 1 AS display_order,
           '步骤' || (tutorial_step + 1)::text || ': 新手引导' AS step_name,
           users
    FROM tutorial_steps
    WHERE tutorial_step BETWEEN 1 AND 9
), base AS (
    SELECT users AS base_users
    FROM funnel_steps
    WHERE display_order = 1
)
SELECT step_name AS "新手步骤",
       users AS "用户数",
       round(users::numeric / nullif(base_users, 0) * 100, 2) AS "转化率"
FROM funnel_steps
CROSS JOIN base
ORDER BY display_order
""",
        [axis("新手步骤", axis_type="x")],
        [axis("用户数", axis_type="y", metric_type="snapshot", pivot_aggregation="avg")],
        show_label=True,
    ),
    chart(
        "2185000000000000012",
        "各渠道新增留存",
        "heatmap",
        (1, 84, 72, 18),
        """
WITH bounds AS (
    SELECT max(session_start::date) AS end_date
    FROM public.fact_sessions
), normalized_cohorts AS (
    SELECT p.install_date,
           p.player_id,
           CASE
             WHEN nullif(trim(p.bi_channel_name), '') IS NOT NULL THEN p.bi_channel_name
             WHEN nullif(trim(p.registration_channel), '') IS NOT NULL THEN p.registration_channel
             WHEN p.channel = 'iOS,app store' THEN 'app store'
             WHEN p.channel = 'huawei_store' THEN '华为应用商城'
             WHEN p.channel = 'yingyongbao' THEN '应用宝'
             WHEN p.channel = 'xiaomi_store' THEN '小米应用商城'
             WHEN p.channel = 'google_play' THEN 'Google Play'
             WHEN p.channel = 'qihu_360' THEN '360手机助手'
             WHEN p.channel = 'baidu_store' THEN '百度手机助手'
             WHEN p.channel = 'wandoujia' THEN '豌豆荚'
             ELSE coalesce(nullif(trim(p.channel), ''), '未知')
           END AS channel_name
    FROM public.dim_player p, bounds b
    WHERE p.install_date BETWEEN b.end_date - 13 AND b.end_date - 7
), top_channels AS (
    SELECT channel_name
    FROM normalized_cohorts
    GROUP BY channel_name
    ORDER BY count(*) DESC
    LIMIT 5
), cohorts AS (
    SELECT install_date,
           CASE WHEN channel_name IN (SELECT channel_name FROM top_channels) THEN channel_name ELSE '其他' END AS channel_group,
           player_id
    FROM normalized_cohorts
), active AS (
    SELECT DISTINCT s.player_id,
           s.lifecycle_day
    FROM public.fact_sessions s
    WHERE s.lifecycle_day BETWEEN 0 AND 7
), retention AS (
    SELECT c.install_date,
           c.channel_group,
           gs.day AS lifecycle_day,
           count(DISTINCT c.player_id) AS cohort_users,
           count(DISTINCT c.player_id) FILTER (WHERE a.lifecycle_day = gs.day) AS retained_users
    FROM cohorts c
    CROSS JOIN generate_series(0, 7) AS gs(day)
    LEFT JOIN active a ON a.player_id = c.player_id AND a.lifecycle_day = gs.day
    GROUP BY c.install_date, c.channel_group, gs.day
)
SELECT install_date AS "日期",
       channel_group || ' / ' ||
         CASE WHEN lifecycle_day = 0 THEN '当日' ELSE '第' || lifecycle_day::text || '日' END AS "渠道留存日",
       round(retained_users::numeric / nullif(cohort_users, 0) * 100, 2) AS "留存率",
       retained_users AS "留存人数",
       cohort_users AS "新增用户数"
FROM retention
ORDER BY install_date, channel_group, lifecycle_day
""",
        [axis("日期", axis_type="x")],
        [axis("留存率", axis_type="y", metric_type="ratio", pivot_aggregation="avg")],
        [axis("渠道留存日", axis_type="series")],
        show_label=True,
    ),
]


def run_chart_sql(conn: Any, chart_info: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(chart_info["sql"])
        raw_rows = cur.fetchall()
        fields = [desc.name for desc in cur.description]
    return fields, [normalize_row(dict(row)) for row in raw_rows]


def build_dashboard_payload(bi_conn: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    component_data: list[dict[str, Any]] = []
    canvas_view_info: dict[str, Any] = {}

    for chart_info in CHARTS:
        fields, rows = run_chart_sql(bi_conn, chart_info)
        if not rows:
            raise RuntimeError(f"Chart has no data: {chart_info['title']}")

        x, y, size_x, size_y = chart_info["layout"]
        component_data.append(
            {
                "id": chart_info["id"],
                "component": "SQView",
                "name": "new-view",
                "propValue": "&nbsp;",
                "icon": "icon_graphical",
                "innerType": "bar",
                "locked": False,
                "editing": False,
                "x": x,
                "y": y,
                "sizeX": size_x,
                "sizeY": size_y,
                "style": {},
                "_dragId": chart_info["id"],
                "show": True,
            }
        )

        chart_config: dict[str, Any] = {
            "type": chart_info["type"],
            "sourceType": chart_info["type"],
            "title": chart_info["title"],
            "id": chart_info["id"],
            "xAxis": chart_info["x"],
            "yAxis": chart_info["y"],
            "series": chart_info["series"],
            "columns": [axis(field) for field in fields]
            if chart_info["type"] in {"table", "metric"}
            else [],
        }
        if chart_info.get("showLabel"):
            chart_config["showLabel"] = True
        if sum(1 for item in chart_info["y"] if item.get("multi-quota")) > 1:
            chart_config["multiQuotaName"] = "指标类型"

        canvas_view_info[chart_info["id"]] = {
            "id": chart_info["id"],
            "sql": chart_info["sql"].strip(),
            "datasource": DATASOURCE_ID,
            "data": {"fields": fields, "data": rows},
            "chart": chart_config,
            "sourceId": "",
            "status": "success",
            "message": "",
            "fields": fields,
            "pivot": chart_info.get("pivot") or {"enabled": False},
        }
        print(f"{chart_info['title']}: rows={len(rows)} fields={fields}")

    return component_data, canvas_view_info


def backup_dashboard_row(row: dict[str, Any]) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"core_dashboard_{DASHBOARD_ID}_{int(time.time())}.json"
    backup_path.write_text(
        json.dumps(normalize_row(dict(row)), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return backup_path


def main() -> None:
    bi_conn = psycopg2.connect(**BI_DB)
    sys_conn = psycopg2.connect(**SYSTEM_DB)
    try:
        component_data, canvas_view_info = build_dashboard_payload(bi_conn)
        component_json = json.dumps(component_data, ensure_ascii=False, separators=(",", ":"))
        style_json = "{}"
        view_json = json.dumps(canvas_view_info, ensure_ascii=False, separators=(",", ":"))

        with sys_conn:
            with sys_conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, name, datasource, create_by, update_by,
                           component_data, canvas_style_data, canvas_view_info, update_time
                    FROM public.core_dashboard
                    WHERE id = %s
                    FOR UPDATE
                    """,
                    (DASHBOARD_ID,),
                )
                dashboard = cur.fetchone()
                if not dashboard:
                    raise RuntimeError(f"Core dashboard does not exist: {DASHBOARD_ID}")
                if dashboard["datasource"] != DATASOURCE_ID:
                    raise RuntimeError(
                        f"Core dashboard datasource={dashboard['datasource']}, expected {DATASOURCE_ID}"
                    )

                backup_path = backup_dashboard_row(dict(dashboard))
                cur.execute(
                    """
                    UPDATE public.core_dashboard
                       SET component_data = %s,
                           canvas_style_data = %s,
                           canvas_view_info = %s,
                           update_time = %s,
                           update_by = %s
                     WHERE id = %s
                    """,
                    (component_json, style_json, view_json, int(time.time()), UPDATE_BY, DASHBOARD_ID),
                )
                print(f"updated rows={cur.rowcount}")
                print(f"backup={backup_path}")

        with sys_conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, name, datasource,
                       jsonb_array_length(component_data::jsonb) AS component_count,
                       (SELECT count(*) FROM jsonb_each(canvas_view_info::jsonb)) AS view_count,
                       update_time
                FROM public.core_dashboard
                WHERE id = %s
                """,
                (DASHBOARD_ID,),
            )
            print("verify_dashboard=" + json.dumps(normalize_row(dict(cur.fetchone())), ensure_ascii=False))
            cur.execute(
                """
                SELECT value->'chart'->>'title' AS title,
                       value->'chart'->>'type' AS chart_type,
                       jsonb_array_length(value->'data'->'data') AS row_count
                FROM public.core_dashboard d,
                     jsonb_each(d.canvas_view_info::jsonb) AS e(key, value)
                WHERE d.id = %s
                ORDER BY key
                """,
                (DASHBOARD_ID,),
            )
            print("verify_charts=")
            for row in cur.fetchall():
                print(json.dumps(normalize_row(dict(row)), ensure_ascii=False))
    finally:
        bi_conn.close()
        sys_conn.close()


if __name__ == "__main__":
    main()
