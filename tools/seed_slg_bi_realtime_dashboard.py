"""Seed realtime mock data and create the realtime dashboard report.

Targets:
- BI tracking database: 127.0.0.1:5432 / slg_bi_mock / postgres / 111111
- App system database: core SHUZHI_DB_* settings from the repo .env

The generated BI rows stay at detail level:
- fact_sessions rows model online sessions for 2026-07-01 and 2026-07-02;
- fact_events rows model purchase_start / purchase_success events;
- fact_payments rows model successful hourly orders.

No aggregate KPI tables, snapshot tables, or analysis views are created.
"""
from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import psycopg2
from psycopg2.extras import RealDictCursor

from core_system_db import core_system_db_config


TZ = ZoneInfo("Asia/Shanghai")

BI_DB = {
    "host": "127.0.0.1",
    "port": 5432,
    "dbname": "slg_bi_mock",
    "user": "postgres",
    "password": "111111",
}
SYSTEM_DB = core_system_db_config()

DASHBOARD_ID = "50f1a475ce1740959d5e83aea833ebbb"
DATASOURCE_ID = 1
UPDATE_BY = "7471612174524223488"
BACKUP_DIR = Path(".codex-runtime/backups")

START_DAY = date(2026, 7, 1)
TODAY = date(2026, 7, 2)
SESSION_ID_START = 20_000_000
SESSION_UID_PREFIX = "rt_live_mock"
EVENT_UID_PREFIX = "rt_live_mock_evt"
ORDER_ID_PREFIX = "RTLIVE"

RT_PRODUCT = (
    "rt_live_mock_realtime_pack",
    "实时活动礼包",
    "event_pack",
    Decimal("9999.00"),
    "hourly",
    1,
    False,
)

YESTERDAY_HOURLY_REVENUE = [
    Decimal("0"),
    Decimal("0"),
    Decimal("0"),
    Decimal("0"),
    Decimal("0"),
    Decimal("0"),
    Decimal("0"),
    Decimal("50"),
    Decimal("480"),
    Decimal("2600"),
    Decimal("1450"),
    Decimal("1120"),
    Decimal("900"),
    Decimal("680"),
    Decimal("1380"),
    Decimal("3170"),
    Decimal("2320"),
    Decimal("860"),
    Decimal("590"),
    Decimal("3400"),
    Decimal("3121"),
    Decimal("1660"),
    Decimal("1750"),
    Decimal("774"),
]

TODAY_HOURLY_REVENUE = [
    Decimal("0"),
    Decimal("0"),
    Decimal("0"),
    Decimal("0"),
    Decimal("0"),
    Decimal("0"),
    Decimal("0"),
    Decimal("120"),
    Decimal("600"),
    Decimal("2318"),
    Decimal("5400"),
    Decimal("3200"),
    Decimal("5100"),
    Decimal("2905"),
    Decimal("4180"),
    Decimal("5852"),
    Decimal("3792"),
    Decimal("4016"),
    Decimal("4200"),
    Decimal("7312"),
    Decimal("6033"),
    Decimal("1916"),
    Decimal("5398"),
    Decimal("5264"),
]


@dataclass(slots=True)
class Player:
    player_id: int
    account_id: str
    role_id: str
    device_id: str
    install_date: date
    country: str
    language: str
    platform: str
    channel: str
    campaign: str
    device_tier: str
    device_model: str
    os_version: str
    server_id: int
    current_level: int
    current_vip_level: int
    current_power: int


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
    return item


def day_start(day: date) -> datetime:
    return datetime.combine(day, dt_time(0, 0, 0), TZ)


def minute_dt(day: date, minute: int, second: int = 0) -> datetime:
    return day_start(day) + timedelta(minutes=minute, seconds=second)


def load_players(conn: Any) -> list[Player]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT player_id, account_id, role_id, device_id, install_date, country, language,
                   platform, channel, campaign, device_tier, device_model, os_version,
                   register_server_id AS server_id, current_level, current_vip_level,
                   current_power
            FROM public.dim_player
            WHERE install_date <= %s
            ORDER BY player_id
            LIMIT 1800
            """,
            (START_DAY,),
        )
        rows = cur.fetchall()
    return [Player(**dict(row)) for row in rows]


def cleanup(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM public.fact_payments WHERE order_id LIKE %s", (f"{ORDER_ID_PREFIX}%",))
        cur.execute("DELETE FROM public.fact_events WHERE event_uid LIKE %s", (f"{EVENT_UID_PREFIX}_%",))
        cur.execute("DELETE FROM public.fact_sessions WHERE session_uid LIKE %s", (f"{SESSION_UID_PREFIX}_pay_sess_%",))
        cur.execute("DELETE FROM public.dim_product WHERE product_id = %s", (RT_PRODUCT[0],))
    conn.commit()


def seed_product(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO public.dim_product (
                product_id, product_name, product_type, price_usd, limit_type,
                unlock_level, is_first_pay_pack
            ) VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (product_id) DO UPDATE SET
                product_name = excluded.product_name,
                product_type = excluded.product_type,
                price_usd = excluded.price_usd,
                limit_type = excluded.limit_type,
                unlock_level = excluded.unlock_level,
                is_first_pay_pack = excluded.is_first_pay_pack
            """,
            RT_PRODUCT,
        )
    conn.commit()


def sample_start_minute(rng: random.Random) -> int:
    roll = rng.random()
    if roll < 0.34:
        minute = int(rng.gauss(185, 85))
    elif roll < 0.58:
        minute = int(rng.gauss(575, 150))
    elif roll < 0.88:
        minute = int(rng.gauss(1080, 95))
    else:
        minute = rng.randint(0, 1439)
    return max(0, min(1439, minute))


def lifecycle_day(player: Player, current_day: date) -> int:
    return max(0, (current_day - player.install_date).days)


def build_session_row(
    session_id: int,
    session_uid: str,
    player: Player,
    start_at: datetime,
    duration_minutes: int,
) -> tuple:
    current_day = start_at.date()
    end_at = min(start_at + timedelta(minutes=duration_minutes), day_start(current_day) + timedelta(days=1, seconds=-1))
    duration_seconds = max(60, int((end_at - start_at).total_seconds()))
    level_start = max(1, player.current_level - 1)
    level_end = max(level_start, player.current_level)
    power_start = max(500, player.current_power - 120)
    power_end = max(power_start, player.current_power)
    return (
        session_id,
        session_uid,
        player.player_id,
        player.account_id,
        player.role_id,
        player.device_id,
        player.server_id,
        start_at,
        end_at,
        duration_seconds,
        lifecycle_day(player, current_day),
        level_start,
        level_end,
        power_start,
        power_end,
        player.platform,
        player.channel,
        player.campaign,
        "1.2.1",
        102100,
        "slg-sdk-4.1.0",
        player.device_tier,
        player.device_model,
        player.os_version,
        "wifi",
        player.country,
        player.country,
    )


def build_online_sessions(players: list[Player]) -> tuple[list[tuple], int]:
    rng = random.Random(20260624)
    session_rows: list[tuple] = []
    session_id = SESSION_ID_START
    player_index = 0
    for current_day, session_count in [(START_DAY, 940), (TODAY, 930)]:
        for _ in range(session_count):
            player = players[player_index % len(players)]
            player_index += 1
            start_minute = sample_start_minute(rng)
            start_at = minute_dt(current_day, start_minute, rng.randint(0, 45))
            duration = int(max(45, min(520, rng.gauss(285, 95))))
            session_uid = f"{SESSION_UID_PREFIX}_online_sess_{session_id}"
            session_rows.append(build_session_row(session_id, session_uid, player, start_at, duration))
            session_id += 1
    return session_rows, session_id


def build_event_row(
    event_uid: str,
    player: Player,
    session_id: int,
    event_time: datetime,
    event_name: str,
    sequence: int,
    attributes: dict[str, Any],
    event_source: str,
) -> tuple:
    current_day = event_time.date()
    return (
        event_uid,
        f"{SESSION_UID_PREFIX}_cli_{event_uid}",
        f"{SESSION_UID_PREFIX}_trace_{session_id}_{sequence}",
        event_time,
        event_time,
        event_time + timedelta(milliseconds=350),
        event_time + timedelta(seconds=1),
        current_day,
        player.player_id,
        player.account_id,
        player.role_id,
        player.device_id,
        player.server_id,
        session_id,
        event_name,
        "monetization",
        lifecycle_day(player, current_day),
        player.current_level,
        player.current_vip_level,
        player.current_power,
        None,
        "1.2.1",
        102100,
        "slg-sdk-4.1.0",
        "slg_event_v4",
        player.platform,
        player.channel,
        player.campaign,
        player.country,
        player.country,
        player.language,
        player.device_model,
        player.os_version,
        player.device_tier,
        "wifi",
        event_source,
        sequence,
        json.dumps(attributes, ensure_ascii=False),
    )


def build_payment_rows(players: list[Player], next_session_id: int) -> tuple[list[tuple], list[tuple], list[tuple]]:
    session_rows: list[tuple] = []
    event_rows: list[tuple] = []
    payment_rows: list[tuple] = []
    event_no = 1
    order_no = 1
    player_index = 280

    revenue_by_day = {
        START_DAY: YESTERDAY_HOURLY_REVENUE,
        TODAY: TODAY_HOURLY_REVENUE,
    }

    for current_day, revenues in revenue_by_day.items():
        for hour, amount in enumerate(revenues):
            if amount <= 0:
                continue
            player = players[player_index % len(players)]
            player_index += 17
            pay_time = day_start(current_day) + timedelta(hours=hour, minutes=8 + (hour % 5), seconds=11)
            session_id = next_session_id
            next_session_id += 1
            session_uid = f"{SESSION_UID_PREFIX}_pay_sess_{session_id}"
            session_rows.append(build_session_row(session_id, session_uid, player, pay_time - timedelta(minutes=8), 36))

            order_id = f"{ORDER_ID_PREFIX}{current_day:%Y%m%d}{order_no:05d}"
            order_no += 1
            product_id, product_name = RT_PRODUCT[0], RT_PRODUCT[1]
            start_uid = f"{EVENT_UID_PREFIX}_{event_no:08d}"
            event_no += 1
            final_uid = f"{EVENT_UID_PREFIX}_{event_no:08d}"
            event_no += 1

            event_rows.append(
                build_event_row(
                    start_uid,
                    player,
                    session_id,
                    pay_time,
                    "purchase_start",
                    1,
                    {"order_id": order_id, "product_id": product_id, "price_usd": str(amount)},
                    "client",
                )
            )
            event_rows.append(
                build_event_row(
                    final_uid,
                    player,
                    session_id,
                    pay_time + timedelta(seconds=6),
                    "purchase_success",
                    2,
                    {"order_id": order_id, "product_id": product_id, "amount_usd": str(amount), "is_first_pay": False},
                    "server",
                )
            )
            payment_rows.append(
                (
                    order_id,
                    start_uid,
                    final_uid,
                    pay_time + timedelta(seconds=6),
                    current_day,
                    player.player_id,
                    player.server_id,
                    session_id,
                    product_id,
                    product_name,
                    amount,
                    amount,
                    Decimal("0.00"),
                    amount,
                    "CNY",
                    "app_store" if player.platform == "ios" else "google_play",
                    "success",
                    None,
                    None,
                    False,
                    1,
                    lifecycle_day(player, current_day),
                    max(player.current_vip_level, 1),
                    player.current_level,
                    "whale" if amount >= Decimal("5000") else "mid",
                    json.dumps({"source": "rt_live_mock_seed", "hour": hour}, ensure_ascii=False),
                )
            )
    return session_rows, event_rows, payment_rows


def insert_detail_rows(conn: Any, session_rows: list[tuple], event_rows: list[tuple], payment_rows: list[tuple]) -> None:
    with conn.cursor() as cur:
        if session_rows:
            cur.executemany(
                """
                INSERT INTO public.fact_sessions (
                    session_id, session_uid, player_id, account_id, role_id, device_id, server_id, session_start,
                    session_end, duration_seconds, lifecycle_day, player_level_start, player_level_end, power_start,
                    power_end, platform, channel, campaign, client_version, app_build, sdk_version, device_tier,
                    device_model, os_version, network_type, country, ip_country
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (session_uid) DO NOTHING
                """,
                session_rows,
            )
        if event_rows:
            cur.executemany(
                """
                INSERT INTO public.fact_events (
                    event_uid, client_event_id, trace_id, event_time, client_time, server_receive_time, ingest_time,
                    event_date, player_id, account_id, role_id, device_id, server_id, session_id, event_name,
                    event_category, lifecycle_day, player_level, vip_level, power, alliance_id, client_version,
                    app_build, sdk_version, event_schema_version, platform, channel, campaign, country, ip_country,
                    language, device_model, os_version, device_tier, network_type, event_source,
                    sequence_in_session, attributes
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                event_rows,
            )
        if payment_rows:
            cur.executemany(
                """
                INSERT INTO public.fact_payments (
                    order_id, start_event_uid, final_event_uid, event_time, event_date, player_id, server_id,
                    session_id, product_id, product_name, amount_usd, gross_revenue_usd, refund_amount_usd,
                    net_revenue_usd, local_currency, payment_channel, payment_status, fail_reason, refund_reason,
                    is_first_pay, pay_sequence, lifecycle_day, vip_level_after, player_level, revenue_tier, attributes
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                payment_rows,
            )
    conn.commit()


ONLINE_SQL = """
WITH obs AS (
    SELECT max(session_start::date) AS today
    FROM public.fact_sessions
    WHERE session_uid LIKE 'rt_live_mock_%'
), days AS (
    SELECT today AS day_date FROM obs
    UNION ALL
    SELECT today - 1 AS day_date FROM obs
), minute_buckets AS (
    SELECT d.day_date,
           generate_series(
               d.day_date::timestamp,
               d.day_date::timestamp + interval '23 hours 59 minutes',
               interval '1 minute'
           ) AT TIME ZONE 'Asia/Shanghai' AS bucket_time
    FROM days d
)
SELECT to_char(bucket_time, 'HH24') || chr(58) || to_char(bucket_time, 'MI') AS "时间",
       to_char(day_date, 'YYYY-MM-DD') AS "日期",
       count(DISTINCT s.player_id) AS "实时在线人数"
FROM minute_buckets mb
LEFT JOIN public.fact_sessions s
  ON s.session_start <= mb.bucket_time
 AND s.session_end > mb.bucket_time
 AND s.session_start::date BETWEEN (SELECT today - 1 FROM obs) AND (SELECT today FROM obs)
 AND s.session_uid LIKE 'rt_live_mock_%'
GROUP BY day_date, bucket_time
ORDER BY day_date, bucket_time
"""

HOURLY_PAYMENT_SQL = """
WITH obs AS (
    SELECT max(event_date) AS today
    FROM public.fact_payments
    WHERE order_id LIKE 'RTLIVE%'
), days AS (
    SELECT today AS day_date FROM obs
    UNION ALL
    SELECT today - 1 AS day_date FROM obs
), hours AS (
    SELECT d.day_date, gs.hour_index
    FROM days d
    CROSS JOIN generate_series(0, 23) AS gs(hour_index)
), hourly AS (
    SELECT p.event_date AS day_date,
           extract(hour FROM p.event_time)::int AS hour_index,
           round(sum(p.net_revenue_usd), 2) AS revenue
    FROM public.fact_payments p, obs
    WHERE p.payment_status = 'success'
      AND p.net_revenue_usd > 0
      AND p.order_id LIKE 'RTLIVE%'
      AND p.event_date BETWEEN obs.today - 1 AND obs.today
    GROUP BY p.event_date, extract(hour FROM p.event_time)::int
)
SELECT lpad(h.hour_index::text, 2, '0') || chr(58) || '00' AS "小时",
       to_char(h.day_date, 'YYYY-MM-DD') AS "日期",
       coalesce(hourly.revenue, 0) AS "实时付费金额"
FROM hours h
LEFT JOIN hourly
  ON hourly.day_date = h.day_date
 AND hourly.hour_index = h.hour_index
ORDER BY h.day_date, h.hour_index
"""

CUMULATIVE_PAYMENT_SQL = """
WITH obs AS (
    SELECT max(event_date) AS today,
           extract(hour FROM max(event_time))::int AS current_hour
    FROM public.fact_payments
    WHERE order_id LIKE 'RTLIVE%'
), days AS (
    SELECT today AS day_date,
           23 AS max_hour
    FROM obs
    UNION ALL
    SELECT today - 1 AS day_date,
           23 AS max_hour
    FROM obs
), hours AS (
    SELECT d.day_date, gs.hour_index
    FROM days d
    CROSS JOIN LATERAL generate_series(0, d.max_hour) AS gs(hour_index)
), hourly AS (
    SELECT p.event_date AS day_date,
           extract(hour FROM p.event_time)::int AS hour_index,
           round(sum(p.net_revenue_usd), 2) AS revenue
    FROM public.fact_payments p, obs
    WHERE p.payment_status = 'success'
      AND p.net_revenue_usd > 0
      AND p.order_id LIKE 'RTLIVE%'
      AND p.event_date BETWEEN obs.today - 1 AND obs.today
    GROUP BY p.event_date, extract(hour FROM p.event_time)::int
), filled AS (
    SELECT h.day_date,
           h.hour_index,
           coalesce(hourly.revenue, 0) AS revenue
    FROM hours h
    LEFT JOIN hourly
      ON hourly.day_date = h.day_date
     AND hourly.hour_index = h.hour_index
)
SELECT lpad(hour_index::text, 2, '0') || chr(58) || '00' AS "小时",
       to_char(day_date, 'YYYY-MM-DD') AS "日期",
       sum(revenue) OVER (PARTITION BY day_date ORDER BY hour_index) AS "累计付费金额"
FROM filled
ORDER BY day_date, hour_index
"""


CHARTS = [
    {
        "id": "2186000000000000001",
        "title": "实时在线人数",
        "type": "line",
        "layout": (1, 1, 72, 18),
        "sql": ONLINE_SQL,
        "x": [axis("时间", axis_type="x")],
        "y": [axis("实时在线人数", axis_type="y")],
        "series": [axis("日期", axis_type="series")],
    },
    {
        "id": "2186000000000000002",
        "title": "实时付费金额",
        "type": "line",
        "layout": (1, 19, 36, 16),
        "sql": HOURLY_PAYMENT_SQL,
        "x": [axis("小时", axis_type="x")],
        "y": [axis("实时付费金额", axis_type="y")],
        "series": [axis("日期", axis_type="series")],
    },
    {
        "id": "2186000000000000003",
        "title": "累计付费金额",
        "type": "line",
        "layout": (37, 19, 36, 16),
        "sql": CUMULATIVE_PAYMENT_SQL,
        "x": [axis("小时", axis_type="x")],
        "y": [axis("累计付费金额", axis_type="y")],
        "series": [axis("日期", axis_type="series")],
    },
]


def run_chart_sql(conn: Any, chart_info: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(chart_info["sql"])
        rows = cur.fetchall()
        fields = [desc.name for desc in cur.description]
    return fields, [normalize_row(dict(row)) for row in rows]


def backup_dashboard_row(row: dict[str, Any]) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"realtime_dashboard_{DASHBOARD_ID}_{int(time.time())}.json"
    backup_path.write_text(
        json.dumps(normalize_row(dict(row)), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return backup_path


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
                "columns": [],
            },
            "sourceId": "",
            "status": "success",
            "message": "",
            "fields": fields,
        }
        print(f"{chart_info['title']}: rows={len(rows)} fields={fields}")

    return component_data, canvas_view_info


def update_dashboard(system_conn: Any, component_data: list[dict[str, Any]], canvas_view_info: dict[str, Any]) -> None:
    component_json = json.dumps(component_data, ensure_ascii=False, separators=(",", ":"))
    view_json = json.dumps(canvas_view_info, ensure_ascii=False, separators=(",", ":"))

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
                raise RuntimeError(f"Realtime dashboard does not exist: {DASHBOARD_ID}")
            if dashboard["datasource"] != DATASOURCE_ID:
                raise RuntimeError(f"Realtime dashboard datasource={dashboard['datasource']}, expected {DATASOURCE_ID}")

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
                (component_json, view_json, int(time.time()), UPDATE_BY, DASHBOARD_ID),
            )
            print(f"updated rows={cur.rowcount}")
            print(f"backup={backup_path}")


def verify(system_conn: Any, bi_conn: Any) -> None:
    with bi_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT count(*) FILTER (WHERE session_uid LIKE 'rt_live_mock_%') AS rt_sessions,
                   min(session_start) FILTER (WHERE session_uid LIKE 'rt_live_mock_%') AS min_session,
                   max(session_start) FILTER (WHERE session_uid LIKE 'rt_live_mock_%') AS max_session
            FROM public.fact_sessions
            """
        )
        print("verify_sessions=" + json.dumps(normalize_row(dict(cur.fetchone())), ensure_ascii=False))
        cur.execute(
            """
            SELECT count(*) FILTER (WHERE order_id LIKE 'RTLIVE%') AS rt_payments,
                   round(sum(net_revenue_usd) FILTER (WHERE order_id LIKE 'RTLIVE%'), 2) AS rt_revenue,
                   min(event_time) FILTER (WHERE order_id LIKE 'RTLIVE%') AS min_payment,
                   max(event_time) FILTER (WHERE order_id LIKE 'RTLIVE%') AS max_payment
            FROM public.fact_payments
            """
        )
        print("verify_payments=" + json.dumps(normalize_row(dict(cur.fetchone())), ensure_ascii=False))

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


def seed_bi_data(conn: Any) -> None:
    cleanup(conn)
    seed_product(conn)
    players = load_players(conn)
    if len(players) < 100:
        raise RuntimeError("Not enough players in dim_player to build realtime detail rows")
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT count(*) AS online_sessions,
                   coalesce(max(session_id), %s - 1) + 1 AS next_session_id
            FROM public.fact_sessions
            WHERE session_uid LIKE %s
            """,
            (SESSION_ID_START, f"{SESSION_UID_PREFIX}_%"),
        )
        realtime_state = dict(cur.fetchone())

    if realtime_state["online_sessions"] > 0:
        online_sessions = []
        next_session_id = int(realtime_state["next_session_id"])
    else:
        online_sessions, next_session_id = build_online_sessions(players)

    payment_sessions, payment_events, payment_rows = build_payment_rows(players, next_session_id)
    all_sessions = online_sessions + payment_sessions
    insert_detail_rows(conn, all_sessions, payment_events, payment_rows)
    print(
        f"seeded realtime detail rows: sessions={len(all_sessions)}, "
        f"events={len(payment_events)}, payments={len(payment_rows)}"
    )


def main() -> None:
    bi_conn = psycopg2.connect(**BI_DB)
    system_conn = psycopg2.connect(**SYSTEM_DB)
    try:
        seed_bi_data(bi_conn)
        component_data, canvas_view_info = build_dashboard_payload(bi_conn)
        update_dashboard(system_conn, component_data, canvas_view_info)
        verify(system_conn, bi_conn)
    finally:
        bi_conn.close()
        system_conn.close()


if __name__ == "__main__":
    main()
