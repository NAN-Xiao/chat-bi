"""Repair selected SLG BI Mock dashboard chart SQL and cached results.

This script updates dashboard chart configuration in the app system database.
It does not create aggregate tables, snapshots, analysis views, or modify BI
detail data. The repaired SQL keeps metrics computed from detail tables at
query time and aligns the affected charts with the datasource-scoped Data
Skills.
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

from core_system_db import core_system_db_config

from seed_slg_bi_acquisition_dashboard import ROI_SQL
from seed_slg_bi_payment_overview_dashboard import LTV_7D_SQL


BI_DB = {
    "host": "127.0.0.1",
    "port": 5432,
    "dbname": "slg_bi_mock",
    "user": "postgres",
    "password": "111111",
}
SYSTEM_DB = core_system_db_config()

DATASOURCE_ID = 1
UPDATE_BY = "7471612174524223488"
BACKUP_DIR = Path(".codex-runtime/backups")


SEVEN_DAY_RETENTION_TABLE_SQL = """
WITH obs AS (
  SELECT max(session_start::date) AS max_date
  FROM public.fact_sessions
), cohort AS (
  SELECT p.player_id,
         p.install_date
  FROM public.dim_player p
  CROSS JOIN obs
  WHERE p.install_date BETWEEN obs.max_date - 6 AND obs.max_date
), retained AS (
  SELECT c.install_date,
         count(DISTINCT c.player_id) AS new_users,
         count(DISTINCT s.player_id) FILTER (WHERE s.lifecycle_day = 1) AS d1_users,
         count(DISTINCT s.player_id) FILTER (WHERE s.lifecycle_day = 3) AS d3_users,
         count(DISTINCT s.player_id) FILTER (WHERE s.lifecycle_day = 7) AS d7_users
  FROM cohort c
  LEFT JOIN public.fact_sessions s
    ON s.player_id = c.player_id
   AND s.lifecycle_day IN (1, 3, 7)
  GROUP BY c.install_date
)
SELECT r.install_date,
       r.new_users,
       CASE WHEN r.install_date <= obs.max_date - 1
            THEN round(r.d1_users::numeric / nullif(r.new_users, 0) * 100, 2)
       END AS d1_retention_pct,
       CASE WHEN r.install_date <= obs.max_date - 3
            THEN round(r.d3_users::numeric / nullif(r.new_users, 0) * 100, 2)
       END AS d3_retention_pct,
       CASE WHEN r.install_date <= obs.max_date - 7
            THEN round(r.d7_users::numeric / nullif(r.new_users, 0) * 100, 2)
       END AS d7_retention_pct
FROM retained r
CROSS JOIN obs
ORDER BY r.install_date
LIMIT 1000
"""


SEVEN_DAY_RETENTION_TREND_SQL = """
WITH obs AS (
  SELECT max(session_start::date) AS max_date
  FROM public.fact_sessions
), cohort AS (
  SELECT p.player_id,
         p.install_date
  FROM public.dim_player p
  CROSS JOIN obs
  WHERE p.install_date BETWEEN obs.max_date - 6 AND obs.max_date
), retained AS (
  SELECT c.install_date,
         count(DISTINCT c.player_id) AS new_users,
         count(DISTINCT s.player_id) FILTER (WHERE s.lifecycle_day = 1) AS d1_users,
         count(DISTINCT s.player_id) FILTER (WHERE s.lifecycle_day = 3) AS d3_users,
         count(DISTINCT s.player_id) FILTER (WHERE s.lifecycle_day = 7) AS d7_users
  FROM cohort c
  LEFT JOIN public.fact_sessions s
    ON s.player_id = c.player_id
   AND s.lifecycle_day IN (1, 3, 7)
  GROUP BY c.install_date
)
SELECT install_date,
       'D1' AS retention_type,
       1 AS day_index,
       CASE WHEN install_date <= obs.max_date - 1
            THEN round(d1_users::numeric / nullif(new_users, 0) * 100, 2)
       END AS retention_pct
FROM retained
CROSS JOIN obs
UNION ALL
SELECT install_date,
       'D3',
       3,
       CASE WHEN install_date <= obs.max_date - 3
            THEN round(d3_users::numeric / nullif(new_users, 0) * 100, 2)
       END
FROM retained
CROSS JOIN obs
UNION ALL
SELECT install_date,
       'D7',
       7,
       CASE WHEN install_date <= obs.max_date - 7
            THEN round(d7_users::numeric / nullif(new_users, 0) * 100, 2)
       END
FROM retained
CROSS JOIN obs
ORDER BY install_date, day_index
LIMIT 1000
"""


MAY18_RETENTION_PAYMENT_TREND_SQL = """
WITH cohort_meta AS (
  SELECT date '2026-05-18' AS cohort_date
), obs AS (
  SELECT max(session_start::date) AS max_date
  FROM public.fact_sessions
), days AS (
  SELECT generate_series(0, greatest(obs.max_date - cohort_meta.cohort_date, 0))::int AS lifecycle_day
  FROM obs
  CROSS JOIN cohort_meta
), cohort AS (
  SELECT p.player_id
  FROM public.dim_player p
  CROSS JOIN cohort_meta
  WHERE p.install_date = cohort_meta.cohort_date
), cohort_size AS (
  SELECT count(DISTINCT player_id) AS cohort_size
  FROM cohort
), active AS (
  SELECT s.lifecycle_day,
         count(DISTINCT s.player_id) AS active_users
  FROM public.fact_sessions s
  JOIN cohort c ON c.player_id = s.player_id
  GROUP BY s.lifecycle_day
), pay AS (
  SELECT p.lifecycle_day,
         count(DISTINCT p.player_id) AS paying_users
  FROM public.fact_payments p
  JOIN cohort c ON c.player_id = p.player_id
  WHERE p.payment_status = 'success'
    AND p.net_revenue_usd > 0
  GROUP BY p.lifecycle_day
)
SELECT d.lifecycle_day,
       cs.cohort_size,
       coalesce(a.active_users, 0) AS active_users,
       coalesce(p.paying_users, 0) AS paying_users,
       round(coalesce(a.active_users, 0)::numeric * 100.0 / nullif(cs.cohort_size, 0), 2) AS retention_rate,
       round(coalesce(p.paying_users, 0)::numeric * 100.0 / nullif(cs.cohort_size, 0), 2) AS payment_rate
FROM days d
CROSS JOIN cohort_size cs
LEFT JOIN active a ON a.lifecycle_day = d.lifecycle_day
LEFT JOIN pay p ON p.lifecycle_day = d.lifecycle_day
ORDER BY d.lifecycle_day
LIMIT 1000
"""


MAY18_CHANNEL_RETENTION_SQL = """
SELECT p.channel AS channel,
       count(DISTINCT p.player_id) AS cohort_size,
       count(DISTINCT s.player_id) AS active_users,
       round(count(DISTINCT s.player_id)::numeric / nullif(count(DISTINCT p.player_id), 0) * 100, 2) AS retention_rate
FROM public.dim_player p
LEFT JOIN public.fact_sessions s
  ON s.player_id = p.player_id
 AND s.lifecycle_day = 1
WHERE p.install_date = date '2026-05-18'
GROUP BY p.channel
ORDER BY retention_rate DESC NULLS LAST, cohort_size DESC, p.channel
LIMIT 1000
"""


MAY18_CHANNEL_PAYMENT_PIE_SQL = """
SELECT p.channel AS channel,
       coalesce(round(sum(pay.net_revenue_usd), 2), 0) AS total_amount
FROM public.dim_player p
LEFT JOIN public.fact_payments pay
  ON p.player_id = pay.player_id
 AND pay.payment_status = 'success'
 AND pay.net_revenue_usd > 0
WHERE p.install_date = date '2026-05-18'
GROUP BY p.channel
ORDER BY total_amount DESC, p.channel
LIMIT 1000
"""


MAY18_CHANNEL_PAYMENT_TABLE_SQL = """
SELECT p.channel AS channel,
       count(DISTINCT pay.player_id) AS paying_users,
       count(DISTINCT p.player_id) AS total_users,
       coalesce(round(sum(pay.net_revenue_usd), 2), 0) AS total_amount,
       coalesce(round(sum(pay.net_revenue_usd) / nullif(count(DISTINCT pay.player_id), 0), 2), 0) AS avg_amount
FROM public.dim_player p
LEFT JOIN public.fact_payments pay
  ON p.player_id = pay.player_id
 AND pay.payment_status = 'success'
 AND pay.net_revenue_usd > 0
WHERE p.install_date = date '2026-05-18'
GROUP BY p.channel
ORDER BY total_amount DESC, p.channel
LIMIT 1000
"""


PAYMENT_CHANNEL_NET_REVENUE_SQL = """
SELECT p.payment_channel AS payment_channel,
       count(DISTINCT p.order_id) AS order_count,
       round(sum(p.net_revenue_usd), 2) AS total_revenue
FROM public.fact_payments p
WHERE p.payment_status = 'success'
  AND p.net_revenue_usd > 0
GROUP BY p.payment_channel
ORDER BY total_revenue DESC
LIMIT 1000
"""


REPAIRS: list[tuple[str, str, str]] = [
    ("bf7f0accd27f45fc9915cbd2cc1c1511", "2187000000000000003", ROI_SQL),
    ("0be8392e17674666b75c2126c42cce9d", "2187000000000000003", ROI_SQL),
    ("62616b33e94b4877a61ebc8750f79042", "2191000000000000005", LTV_7D_SQL),
    ("7546d482aaa74925b1debf08dbd86c33", "2183875603168665600", SEVEN_DAY_RETENTION_TABLE_SQL),
    ("7546d482aaa74925b1debf08dbd86c33", "2183893235888463872", SEVEN_DAY_RETENTION_TREND_SQL),
    ("9d2c326d544b4b72a816c928a30fe2d6", "2181649692499288064", MAY18_RETENTION_PAYMENT_TREND_SQL),
    ("9d2c326d544b4b72a816c928a30fe2d6", "2181681342360756224", MAY18_CHANNEL_RETENTION_SQL),
    ("9d2c326d544b4b72a816c928a30fe2d6", "2181684008998576128", MAY18_CHANNEL_PAYMENT_PIE_SQL),
    ("9d2c326d544b4b72a816c928a30fe2d6", "2181687520713154560", MAY18_CHANNEL_PAYMENT_TABLE_SQL),
    ("slg_mock_payment_dashboard", "2181674560993271808", PAYMENT_CHANNEL_NET_REVENUE_SQL),
]


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


def axis(value: str) -> dict[str, Any]:
    return {"value": value}


def run_chart_sql(conn: Any, sql: str) -> tuple[list[str], list[dict[str, Any]]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql)
        rows = cur.fetchall()
        fields = [desc.name for desc in cur.description]
    return fields, [normalize_row(dict(row)) for row in rows]


def backup_dashboard(row: dict[str, Any]) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f"repair_slg_bi_dashboard_{row['id']}_{int(time.time())}.json"
    path.write_text(json.dumps(normalize_row(dict(row)), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def repair_dashboard(system_conn: Any, bi_conn: Any, dashboard_id: str, repairs: list[tuple[str, str]]) -> None:
    with system_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, name, datasource, canvas_view_info, component_data
            FROM public.core_dashboard
            WHERE id = %s
              AND COALESCE(delete_flag, 0) = 0
            FOR UPDATE
            """,
            (dashboard_id,),
        )
        dashboard = cur.fetchone()
        if not dashboard:
            raise RuntimeError(f"Dashboard not found: {dashboard_id}")
        if dashboard["datasource"] != DATASOURCE_ID:
            raise RuntimeError(f"Dashboard {dashboard_id} datasource={dashboard['datasource']}, expected {DATASOURCE_ID}")

        canvas_view_info = json.loads(dashboard["canvas_view_info"] or "{}")
        backup_path = backup_dashboard(dict(dashboard))
        print(f"backup={backup_path}")

        for view_id, sql in repairs:
            if view_id not in canvas_view_info:
                raise RuntimeError(f"View {view_id} not found in dashboard {dashboard_id}")
            fields, rows = run_chart_sql(bi_conn, sql)
            view = canvas_view_info[view_id]
            chart = view.setdefault("chart", {})
            chart_type = chart.get("type")
            if chart_type in {"table", "metric"}:
                chart["columns"] = [axis(field) for field in fields]
            view["sql"] = sql.strip()
            view["data"] = {"fields": fields, "data": rows}
            view["fields"] = fields
            view["status"] = "success"
            view["message"] = ""
            print(
                json.dumps(
                    {
                        "dashboard": dashboard["name"],
                        "dashboard_id": dashboard_id,
                        "view_id": view_id,
                        "title": chart.get("title"),
                        "rows": len(rows),
                        "fields": fields,
                    },
                    ensure_ascii=False,
                )
            )

        cur.execute(
            """
            UPDATE public.core_dashboard
               SET canvas_view_info = %s,
                   update_time = %s,
                   update_by = %s
             WHERE id = %s
            """,
            (
                json.dumps(canvas_view_info, ensure_ascii=False, separators=(",", ":")),
                int(time.time()),
                UPDATE_BY,
                dashboard_id,
            ),
        )
        print(f"updated_dashboard={dashboard_id} rows={cur.rowcount}")


def main() -> None:
    grouped: dict[str, list[tuple[str, str]]] = {}
    for dashboard_id, view_id, sql in REPAIRS:
        grouped.setdefault(dashboard_id, []).append((view_id, sql))

    bi_conn = psycopg2.connect(**BI_DB)
    system_conn = psycopg2.connect(**SYSTEM_DB)
    try:
        with system_conn:
            for dashboard_id, repairs in grouped.items():
                repair_dashboard(system_conn, bi_conn, dashboard_id, repairs)
    finally:
        bi_conn.close()
        system_conn.close()


if __name__ == "__main__":
    main()
