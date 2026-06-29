"""Seed acquisition fields and create the SLG BI Mock acquisition dashboard.

Targets:
- BI tracking database: 127.0.0.1:5432 / slg_bi_mock / postgres / 111111
- App system database: core ZHISHU_DB_* settings from the repo .env

The dataset remains detail-level. Acquisition cost is stored on dim_player as
player-level attribution fields and ROI is computed from fact_payments at query
time. No aggregate tables, snapshots, or analysis views are created.
"""
from __future__ import annotations

import json
import random
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from core_system_db import core_system_db_config


BI_DB = {
    "host": "127.0.0.1",
    "port": 5432,
    "dbname": "slg_bi_mock",
    "user": "postgres",
    "password": "111111",
}
SYSTEM_DB = core_system_db_config()

DASHBOARD_ID = "bf7f0accd27f45fc9915cbd2cc1c1511"
DATASOURCE_ID = 1
UPDATE_BY = "7471612174524223488"
BACKUP_DIR = Path(".codex-runtime/backups")
USD_TO_CNY = Decimal("7.15")

ORGANIC_CHANNELS = {"organic", "pre_register"}

FIXED_NETWORK_BY_CHANNEL = {
    "facebook_ads": "Facebook",
    "tiktok_ads": "Network_1",
    "google_ads": "Network_2",
    "app_store_search": "Network_3",
    "tap_tap": "Network_3",
    "influencer": "Network_5",
}

PAID_NETWORK_WEIGHTS = [
    ("Facebook", 18),
    ("Network_1", 17),
    ("Network_2", 16),
    ("Network_3", 14),
    ("Network_4", 14),
    ("Network_5", 12),
    ("Network_6", 9),
]

STORE_ACQUISITION_NETWORK_SEQUENCE = [
    "Organic",
    "Facebook",
    "Network_1",
    "Network_2",
    "Network_3",
    "Network_4",
    "Network_5",
    "Network_6",
    "Facebook",
    "Network_1",
    "Network_2",
    "Network_3",
    "Network_4",
    "Network_5",
]

BASE_CPI_USD = {
    "Facebook": Decimal("27.4"),
    "Network_1": Decimal("25.2"),
    "Network_2": Decimal("24.1"),
    "Network_3": Decimal("22.8"),
    "Network_4": Decimal("26.0"),
    "Network_5": Decimal("23.5"),
    "Network_6": Decimal("29.6"),
    "Organic": Decimal("0.00"),
}


def weighted_paid_network(rng: random.Random) -> str:
    total = sum(weight for _, weight in PAID_NETWORK_WEIGHTS)
    roll = rng.randint(1, total)
    running = 0
    for network, weight in PAID_NETWORK_WEIGHTS:
        running += weight
        if roll <= running:
            return network
    return PAID_NETWORK_WEIGHTS[-1][0]


def acquisition_network_for(channel: str, rng: random.Random) -> str:
    if channel in ORGANIC_CHANNELS:
        return "Organic"
    fixed_network = FIXED_NETWORK_BY_CHANNEL.get(channel)
    if fixed_network:
        return fixed_network
    return weighted_paid_network(rng)


def store_acquisition_network_for(install_day: date, sequence_index: int) -> str:
    offset = install_day.toordinal() % len(STORE_ACQUISITION_NETWORK_SEQUENCE)
    return STORE_ACQUISITION_NETWORK_SEQUENCE[
        (sequence_index + offset) % len(STORE_ACQUISITION_NETWORK_SEQUENCE)
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


def axis(value: str, name: str | None = None, axis_type: str | None = None, multi: bool | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"value": value}
    if name and name != value:
        item["name"] = name
    if axis_type:
        item["type"] = axis_type
    if multi is not None:
        item["multi-quota"] = multi
    return item


def ensure_acquisition_columns(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            ALTER TABLE public.dim_player
                ADD COLUMN IF NOT EXISTS acquisition_network text,
                ADD COLUMN IF NOT EXISTS acquisition_cost_usd numeric(12, 2),
                ADD COLUMN IF NOT EXISTS acquisition_cost_cny numeric(12, 2)
            """
        )
    conn.commit()


def seed_acquisition_fields(conn: Any) -> None:
    rng = random.Random(20260624)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT player_id, channel, install_date
            FROM public.dim_player
            WHERE install_date >= (
                SELECT max(install_date) - 89 FROM public.dim_player
            )
            ORDER BY install_date, player_id
            """
        )
        rows = cur.fetchall()

    updates: list[tuple[Decimal, Decimal, str, int]] = []
    daily_store_counts: dict[date, int] = {}
    for row in rows:
        channel = row["channel"]
        if channel in ORGANIC_CHANNELS or channel in FIXED_NETWORK_BY_CHANNEL:
            network = acquisition_network_for(channel, rng)
        else:
            install_day = row["install_date"]
            sequence_index = daily_store_counts.get(install_day, 0)
            daily_store_counts[install_day] = sequence_index + 1
            network = store_acquisition_network_for(install_day, sequence_index)
        base_cpi = BASE_CPI_USD[network]
        if base_cpi == 0:
            cost_usd = Decimal("0.00")
        else:
            weekday = row["install_date"].weekday()
            weekend_boost = Decimal("1.18") if weekday in {4, 5, 6} else Decimal("1.00")
            wave = Decimal(str(0.92 + 0.16 * rng.random()))
            cost_usd = (base_cpi * weekend_boost * wave).quantize(Decimal("0.01"))
        cost_cny = (cost_usd * USD_TO_CNY).quantize(Decimal("0.01"))
        updates.append((cost_usd, cost_cny, network, row["player_id"]))

    with conn.cursor() as cur:
        cur.executemany(
            """
            UPDATE public.dim_player
               SET acquisition_cost_usd = %s,
                   acquisition_cost_cny = %s,
                   acquisition_network = %s
             WHERE player_id = %s
            """,
            updates,
        )
    conn.commit()
    print(f"seeded acquisition fields for players={len(updates)}")


DAILY_COST_SQL = """
WITH obs AS (
    SELECT max(install_date) AS max_date FROM public.dim_player
), cohort AS (
    SELECT p.install_date,
           coalesce(p.acquisition_network, p.channel) AS network,
           coalesce(p.acquisition_cost_cny, 0) AS cost_cny
    FROM public.dim_player p, obs
    WHERE p.install_date BETWEEN obs.max_date - 29 AND obs.max_date
), network_daily AS (
    SELECT install_date,
           network,
           round(sum(cost_cny), 2) AS network_cost
    FROM cohort
    GROUP BY install_date, network
)
SELECT install_date AS "日期",
       '渠道成本（元）.' || network AS "投放系列",
       network_cost AS "买量成本"
FROM network_daily
ORDER BY "日期", "投放系列"
"""

CPA_SQL = """
WITH obs AS (
    SELECT max(install_date) AS max_date FROM public.dim_player
), cohort AS (
    SELECT p.install_date,
           coalesce(p.acquisition_network, p.channel) AS network,
           count(*) AS registered_users,
           round(sum(coalesce(p.acquisition_cost_cny, 0)), 2) AS cost_cny
    FROM public.dim_player p, obs
    WHERE p.install_date BETWEEN obs.max_date - 29 AND obs.max_date
    GROUP BY p.install_date, coalesce(p.acquisition_network, p.channel)
)
SELECT install_date AS "日期",
       network AS "投放渠道",
       round(cost_cny / nullif(registered_users, 0), 2) AS "单用户买量成本"
FROM cohort
ORDER BY install_date, network
"""

ROI_SQL = """
WITH obs AS (
    SELECT max(install_date) AS max_date FROM public.dim_player
), cohort AS (
    SELECT p.install_date,
           p.player_id,
           coalesce(p.acquisition_cost_cny, 0) AS cost_cny
    FROM public.dim_player p, obs
    WHERE p.install_date BETWEEN obs.max_date - 60 AND obs.max_date
), payment_revenue AS (
    SELECT c.install_date,
           c.player_id,
           p.lifecycle_day,
           p.net_revenue_usd * 7.15 AS net_revenue_cny
    FROM cohort c
    JOIN public.fact_payments p
      ON p.player_id = c.player_id
     AND p.payment_status = 'success'
     AND p.net_revenue_usd > 0
     AND p.lifecycle_day BETWEEN 0 AND 60
), cohort_daily AS (
    SELECT c.install_date,
           round(sum(c.cost_cny), 2) AS spend_cny,
           count(DISTINCT c.player_id) AS registered_users
    FROM cohort c
    GROUP BY c.install_date
), revenue_daily AS (
    SELECT c.install_date,
           round(sum(pr.net_revenue_cny) FILTER (WHERE pr.lifecycle_day <= 0), 2) AS d0_revenue,
           round(sum(pr.net_revenue_cny) FILTER (WHERE pr.lifecycle_day <= 1), 2) AS d1_revenue,
           round(sum(pr.net_revenue_cny) FILTER (WHERE pr.lifecycle_day <= 7), 2) AS d7_revenue,
           round(sum(pr.net_revenue_cny) FILTER (WHERE pr.lifecycle_day <= 14), 2) AS d14_revenue,
           round(sum(pr.net_revenue_cny) FILTER (WHERE pr.lifecycle_day <= 30), 2) AS d30_revenue,
           round(sum(pr.net_revenue_cny) FILTER (WHERE pr.lifecycle_day <= 45), 2) AS d45_revenue,
           round(sum(pr.net_revenue_cny) FILTER (WHERE pr.lifecycle_day <= 60), 2) AS d60_revenue
    FROM cohort c
    LEFT JOIN payment_revenue pr ON pr.player_id = c.player_id AND pr.install_date = c.install_date
    GROUP BY c.install_date
)
SELECT cd.install_date AS "日期",
       cd.spend_cny AS "买量支出（元）",
       cd.registered_users AS "账号注册用户数",
       CASE WHEN cd.spend_cny > 0 THEN round(coalesce(rd.d0_revenue, 0) / cd.spend_cny * 100, 2)::text || '%' ELSE '-' END AS "当日",
       CASE WHEN cd.spend_cny > 0 THEN round(coalesce(rd.d1_revenue, 0) / cd.spend_cny * 100, 2)::text || '%' ELSE '-' END AS "第1日",
       CASE WHEN cd.spend_cny > 0 AND cd.install_date <= (SELECT max_date - 7 FROM obs)
            THEN round(coalesce(rd.d7_revenue, 0) / cd.spend_cny * 100, 2)::text || '%'
            ELSE '-' END AS "第7日",
       CASE WHEN cd.spend_cny > 0 AND cd.install_date <= (SELECT max_date - 14 FROM obs)
            THEN round(coalesce(rd.d14_revenue, 0) / cd.spend_cny * 100, 2)::text || '%'
            ELSE '-' END AS "第14日",
       CASE WHEN cd.spend_cny > 0 AND cd.install_date <= (SELECT max_date - 30 FROM obs)
            THEN round(coalesce(rd.d30_revenue, 0) / cd.spend_cny * 100, 2)::text || '%'
            ELSE '-' END AS "第30日",
       CASE WHEN cd.spend_cny > 0 AND cd.install_date <= (SELECT max_date - 45 FROM obs)
            THEN round(coalesce(rd.d45_revenue, 0) / cd.spend_cny * 100, 2)::text || '%'
            ELSE '-' END AS "第45日",
       CASE WHEN cd.spend_cny > 0 AND cd.install_date <= (SELECT max_date - 60 FROM obs)
            THEN round(coalesce(rd.d60_revenue, 0) / cd.spend_cny * 100, 2)::text || '%'
            ELSE '-' END AS "第60日"
FROM cohort_daily cd
LEFT JOIN revenue_daily rd ON rd.install_date = cd.install_date
ORDER BY cd.install_date
"""


CHARTS = [
    {
        "id": "2187000000000000001",
        "title": "每日买量成本",
        "type": "area",
        "layout": (1, 1, 72, 17),
        "sql": DAILY_COST_SQL,
        "x": [axis("日期", axis_type="x")],
        "y": [axis("买量成本", axis_type="y")],
        "series": [axis("投放系列", axis_type="series")],
    },
    {
        "id": "2187000000000000002",
        "title": "单用户买量成本",
        "type": "area",
        "layout": (1, 18, 72, 17),
        "sql": CPA_SQL,
        "x": [axis("日期", axis_type="x")],
        "y": [axis("单用户买量成本", axis_type="y")],
        "series": [axis("投放渠道", axis_type="series")],
    },
    {
        "id": "2187000000000000003",
        "title": "各渠道ROI",
        "type": "table",
        "layout": (1, 35, 72, 18),
        "sql": ROI_SQL,
        "x": [],
        "y": [],
        "series": [],
    },
]


def run_chart_sql(conn: Any, chart_info: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(chart_info["sql"])
        rows = cur.fetchall()
        fields = [desc.name for desc in cur.description]
    return fields, [normalize_row(dict(row)) for row in rows]


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
        canvas_view_info[chart_info["id"]] = {
            "id": chart_info["id"],
            "sql": chart_info["sql"].strip(),
            "datasource": DATASOURCE_ID,
            "data": {"fields": fields, "data": rows},
            "chart": {
                "type": chart_info["type"],
                "sourceType": chart_info["type"],
                "title": chart_info["title"],
                "id": chart_info["id"],
                "xAxis": chart_info["x"],
                "yAxis": chart_info["y"],
                "series": chart_info["series"],
                "columns": [axis(field) for field in fields] if chart_info["type"] == "table" else [],
            },
            "sourceId": "",
            "status": "success",
            "message": "",
            "fields": fields,
        }
        print(f"{chart_info['title']}: rows={len(rows)} fields={fields}")

    return component_data, canvas_view_info


def backup_dashboard_row(row: dict[str, Any]) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"acquisition_dashboard_{DASHBOARD_ID}_{int(time.time())}.json"
    backup_path.write_text(
        json.dumps(normalize_row(dict(row)), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return backup_path


def update_dashboard(system_conn: Any, component_data: list[dict[str, Any]], canvas_view_info: dict[str, Any]) -> None:
    with system_conn:
        with system_conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, name, datasource, tenant_id, create_by, update_by,
                       component_data, canvas_style_data, canvas_view_info, update_time
                FROM public.core_dashboard
                WHERE id = %s
                FOR UPDATE
                """,
                (DASHBOARD_ID,),
            )
            dashboard = cur.fetchone()
            if not dashboard:
                raise RuntimeError(f"Acquisition dashboard does not exist: {DASHBOARD_ID}")
            if dashboard["datasource"] != DATASOURCE_ID:
                raise RuntimeError(f"Acquisition dashboard datasource={dashboard['datasource']}, expected {DATASOURCE_ID}")

            backup_path = backup_dashboard_row(dict(dashboard))
            cur.execute(
                """
                UPDATE public.core_dashboard
                   SET component_data = %s,
                       canvas_style_data = '{}',
                       canvas_view_info = %s,
                       update_time = %s,
                       update_by = %s
                 WHERE id = %s
                """,
                (
                    json.dumps(component_data, ensure_ascii=False, separators=(",", ":")),
                    json.dumps(canvas_view_info, ensure_ascii=False, separators=(",", ":")),
                    int(time.time()),
                    UPDATE_BY,
                    DASHBOARD_ID,
                ),
            )
            print(f"updated rows={cur.rowcount}")
            print(f"backup={backup_path}")


def verify(system_conn: Any, bi_conn: Any) -> None:
    with bi_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT count(*) FILTER (WHERE acquisition_network IS NOT NULL) AS attributed_players,
                   min(install_date) FILTER (WHERE acquisition_network IS NOT NULL) AS min_install,
                   max(install_date) FILTER (WHERE acquisition_network IS NOT NULL) AS max_install,
                   round(sum(acquisition_cost_cny) FILTER (WHERE acquisition_network IS NOT NULL), 2) AS total_cost
            FROM public.dim_player
            """
        )
        print("verify_fields=" + json.dumps(normalize_row(dict(cur.fetchone())), ensure_ascii=False))
    with system_conn.cursor(cursor_factory=RealDictCursor) as cur:
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


def main() -> None:
    bi_conn = psycopg2.connect(**BI_DB)
    system_conn = psycopg2.connect(**SYSTEM_DB)
    try:
        ensure_acquisition_columns(bi_conn)
        seed_acquisition_fields(bi_conn)
        component_data, canvas_view_info = build_dashboard_payload(bi_conn)
        update_dashboard(system_conn, component_data, canvas_view_info)
        verify(system_conn, bi_conn)
    finally:
        bi_conn.close()
        system_conn.close()


if __name__ == "__main__":
    main()
