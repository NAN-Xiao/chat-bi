"""Seed active-session detail rows and create the SLG BI Mock active dashboard.

Targets:
- BI tracking database: 127.0.0.1:5432 / slg_bi_mock / postgres / 111111
- App system database: core SHUZHI_DB_* settings from the repo .env

The generated data remains detail-level session data. DAU, WAU, MAU, lifecycle
composition, channel/system active users, and weekly login-day distribution are
computed from fact_sessions and dim_player at query time. No aggregate tables,
snapshot tables, or analysis views are created.
"""
from __future__ import annotations

import json
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

DASHBOARD_ID = "19ff0c0f909944a596278aa7509ba000"
DATASOURCE_ID = 1
UPDATE_BY = "7471612174524223488"
BACKUP_DIR = Path(".codex-runtime/backups")

START_DAY = date(2026, 5, 25)
END_DAY = date(2026, 6, 23)
SESSION_ID_START = 9_800_000

REGISTRATION_CHANNELS = [
    "app store",
    "华为应用商城",
    "应用宝",
    "小米应用商城",
    "Google Play",
    "360手机助手",
    "百度手机助手",
    "豌豆荚",
]

LIFECYCLE_SEGMENTS = [
    ("新增期", 1),
    ("成长期", 2),
    ("稳定期", 3),
    ("成熟期", 4),
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
    registration_channel: str
    device_tier: str
    device_model: str
    os_version: str
    server_id: int
    current_level: int
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


def axis(value: str, name: str | None = None, axis_type: str | None = None, multi: bool | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"value": value}
    if name and name != value:
        item["name"] = name
    if axis_type:
        item["type"] = axis_type
    if multi is not None:
        item["multi-quota"] = multi
    return item


def dt_at(day: date, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime.combine(day, dt_time(hour, minute, second), TZ)


def lifecycle_day(player: Player, current_day: date) -> int:
    return max(0, (current_day - player.install_date).days)


def lifecycle_segment(lifecycle: int) -> str:
    if lifecycle <= 6:
        return "新增期"
    if lifecycle <= 13:
        return "成长期"
    if lifecycle <= 30:
        return "稳定期"
    return "成熟期"


def target_dau(current_day: date) -> int:
    base = 1460 + ((current_day.toordinal() % 7) - 3) * 18
    if current_day.weekday() in {4, 5}:
        base += 430
    elif current_day.weekday() == 6:
        base += 150
    if current_day == END_DAY:
        base = 1687
    return base


def ensure_active_columns(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            ALTER TABLE public.dim_player
                ADD COLUMN IF NOT EXISTS registration_channel text
            """
        )
        cur.execute(
            """
            UPDATE public.dim_player
               SET registration_channel = CASE
                   WHEN lower(platform) = 'ios' THEN 'app store'
                   WHEN channel = 'huawei_store' THEN '华为应用商城'
                   WHEN channel = 'google_play' THEN 'Google Play'
                   WHEN player_id % 7 = 0 THEN '应用宝'
                   WHEN player_id % 7 = 1 THEN '小米应用商城'
                   WHEN player_id % 7 = 2 THEN '360手机助手'
                   WHEN player_id % 7 = 3 THEN '百度手机助手'
                   WHEN player_id % 7 = 4 THEN '豌豆荚'
                   WHEN player_id % 7 = 5 THEN '华为应用商城'
                   ELSE '应用宝'
               END
             WHERE registration_channel IS NULL
            """
        )
        cur.execute(
            """
            ALTER TABLE public.fact_sessions
                ADD COLUMN IF NOT EXISTS registration_channel text,
                ADD COLUMN IF NOT EXISTS active_lifecycle_segment text
            """
        )
        cur.execute(
            """
            UPDATE public.fact_sessions s
               SET registration_channel = coalesce(p.registration_channel, p.channel),
                   active_lifecycle_segment = CASE
                       WHEN s.lifecycle_day <= 6 THEN '新增期'
                       WHEN s.lifecycle_day <= 13 THEN '成长期'
                       WHEN s.lifecycle_day <= 30 THEN '稳定期'
                       ELSE '成熟期'
                   END
              FROM public.dim_player p
             WHERE p.player_id = s.player_id
               AND (s.registration_channel IS NULL OR s.active_lifecycle_segment IS NULL)
            """
        )
    conn.commit()


def cleanup(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) AS existing_rows
            FROM public.fact_sessions
            WHERE session_uid LIKE 'active_mock_%'
            """
        )
        existing_rows = cur.fetchone()[0]
    conn.commit()
    print(f"retained active sessions={existing_rows}")


def load_players(conn: Any) -> list[Player]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT player_id, account_id, role_id, device_id, install_date, country, language,
                   platform, channel, campaign, coalesce(registration_channel, channel) AS registration_channel,
                   device_tier, device_model, os_version, register_server_id AS server_id,
                   current_level, current_power
            FROM public.dim_player
            WHERE install_date <= %s
              AND lower(platform) IN ('ios', 'android')
            ORDER BY player_id
            """,
            (END_DAY,),
        )
        return [Player(**dict(row)) for row in cur.fetchall()]


def load_existing_active_users(conn: Any) -> dict[date, set[int]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT session_start::date AS dt,
                   player_id
            FROM public.fact_sessions
            WHERE session_start::date BETWEEN %s AND %s
            GROUP BY session_start::date, player_id
            """,
            (START_DAY, END_DAY),
        )
        rows = cur.fetchall()
    active_by_day: dict[date, set[int]] = {}
    for row in rows:
        active_by_day.setdefault(row["dt"], set()).add(row["player_id"])
    return active_by_day


def build_session_row(session_id: int, player: Player, current_day: date, rng: random.Random) -> tuple:
    start_at = dt_at(current_day, rng.randint(8, 23), rng.randint(0, 59), rng.randint(0, 45))
    duration_minutes = rng.randint(18, 64)
    end_at = min(start_at + timedelta(minutes=duration_minutes), dt_at(current_day, 23, 59, 30))
    lifecycle = lifecycle_day(player, current_day)
    level_end = max(player.current_level, 1)
    power_end = max(player.current_power, 800)
    return (
        session_id,
        f"active_mock_sess_{session_id}",
        player.player_id,
        player.account_id,
        player.role_id,
        player.device_id,
        player.server_id,
        start_at,
        end_at,
        max(60, int((end_at - start_at).total_seconds())),
        lifecycle,
        max(1, level_end - 1),
        level_end,
        max(500, power_end - rng.randint(80, 240)),
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
        player.registration_channel,
        lifecycle_segment(lifecycle),
    )


def build_active_sessions(conn: Any, players: list[Player]) -> list[tuple]:
    rng = random.Random(20260626)
    player_by_id = {player.player_id: player for player in players}
    existing_by_day = load_existing_active_users(conn)
    session_rows: list[tuple] = []
    session_id = SESSION_ID_START

    for day_offset in range((END_DAY - START_DAY).days + 1):
        current_day = START_DAY + timedelta(days=day_offset)
        existing_users = existing_by_day.get(current_day, set())
        eligible = [
            player
            for player in players
            if player.install_date <= current_day and player.player_id not in existing_users
        ]
        rng.shuffle(eligible)
        need = max(0, target_dau(current_day) - len(existing_users))
        for player in eligible[:need]:
            session_rows.append(build_session_row(session_id, player, current_day, rng))
            session_id += 1
        inserted_users = {row[2] for row in session_rows if row[7].date() == current_day}
        existing_by_day[current_day] = existing_users | inserted_users

        # Keep the loop honest if the available pool is unexpectedly small.
        if need > len(eligible):
            missing = need - len(eligible)
            print(f"warning: {current_day} active pool short by {missing} users")

    # Re-sort for deterministic, human-readable inserts after daily shuffling.
    session_rows.sort(key=lambda row: (row[7], row[0]))
    return session_rows


def insert_active_sessions(conn: Any, session_rows: list[tuple]) -> None:
    if not session_rows:
        print("seeded active sessions=0")
        return
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO public.fact_sessions (
                session_id, session_uid, player_id, account_id, role_id, device_id, server_id,
                session_start, session_end, duration_seconds, lifecycle_day, player_level_start,
                player_level_end, power_start, power_end, platform, channel, campaign,
                client_version, app_build, sdk_version, device_tier, device_model, os_version,
                network_type, country, ip_country, registration_channel, active_lifecycle_segment
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (session_id) DO UPDATE SET
                session_uid = EXCLUDED.session_uid,
                player_id = EXCLUDED.player_id,
                account_id = EXCLUDED.account_id,
                role_id = EXCLUDED.role_id,
                device_id = EXCLUDED.device_id,
                server_id = EXCLUDED.server_id,
                session_start = EXCLUDED.session_start,
                session_end = EXCLUDED.session_end,
                duration_seconds = EXCLUDED.duration_seconds,
                lifecycle_day = EXCLUDED.lifecycle_day,
                player_level_start = EXCLUDED.player_level_start,
                player_level_end = EXCLUDED.player_level_end,
                power_start = EXCLUDED.power_start,
                power_end = EXCLUDED.power_end,
                platform = EXCLUDED.platform,
                channel = EXCLUDED.channel,
                campaign = EXCLUDED.campaign,
                client_version = EXCLUDED.client_version,
                app_build = EXCLUDED.app_build,
                sdk_version = EXCLUDED.sdk_version,
                device_tier = EXCLUDED.device_tier,
                device_model = EXCLUDED.device_model,
                os_version = EXCLUDED.os_version,
                network_type = EXCLUDED.network_type,
                country = EXCLUDED.country,
                ip_country = EXCLUDED.ip_country,
                registration_channel = EXCLUDED.registration_channel,
                active_lifecycle_segment = EXCLUDED.active_lifecycle_segment
            """,
            session_rows,
        )
    conn.commit()
    print(f"seeded active sessions={len(session_rows)}")


DAU_SQL = """
WITH obs AS (
    SELECT max(install_date) AS max_date FROM public.dim_player
), days AS (
    SELECT generate_series(max_date - 29, max_date, interval '1 day')::date AS dt
    FROM obs
), daily_active AS (
    SELECT s.session_start::date AS dt,
           count(DISTINCT s.player_id) AS dau
    FROM public.fact_sessions s, obs
    WHERE s.session_start::date BETWEEN obs.max_date - 29 AND obs.max_date
    GROUP BY s.session_start::date
)
SELECT d.dt AS "日期",
       coalesce(a.dau, 0) AS "DAU"
FROM days d
LEFT JOIN daily_active a ON a.dt = d.dt
ORDER BY d.dt
"""

WAU_SQL = """
WITH obs AS (
    SELECT max(install_date) AS max_date FROM public.dim_player
), weeks AS (
    SELECT generate_series(
        date_trunc('week', obs.max_date - 29)::date,
        date_trunc('week', obs.max_date)::date,
        interval '1 week'
    )::date AS week_start,
    obs.max_date
    FROM obs
), weekly_active AS (
    SELECT w.week_start,
           count(DISTINCT s.player_id) AS wau
    FROM weeks w
    LEFT JOIN public.fact_sessions s
      ON s.session_start::date BETWEEN w.week_start AND least(w.week_start + 6, w.max_date)
    GROUP BY w.week_start
)
SELECT to_char(week_start, 'YYYY-MM-DD') || '当周' AS "周",
       wau AS "WAU"
FROM weekly_active
ORDER BY week_start
"""

MAU_SQL = """
WITH obs AS (
    SELECT max(install_date) AS max_date FROM public.dim_player
), months AS (
    SELECT generate_series(
        date_trunc('month', obs.max_date - 74)::date,
        date_trunc('month', obs.max_date)::date,
        interval '1 month'
    )::date AS month_start,
    obs.max_date
    FROM obs
), monthly_active AS (
    SELECT m.month_start,
           count(DISTINCT s.player_id) AS mau
    FROM months m
    LEFT JOIN public.fact_sessions s
      ON s.session_start::date BETWEEN greatest(m.month_start, m.max_date - 74)
                                  AND least((m.month_start + interval '1 month - 1 day')::date, m.max_date)
    GROUP BY m.month_start
)
SELECT to_char(month_start, 'YYYY-MM') || '月' AS "月份",
       mau AS "MAU"
FROM monthly_active
ORDER BY month_start
"""

LIFECYCLE_COMPOSITION_SQL = """
WITH obs AS (
    SELECT max(install_date) AS max_date FROM public.dim_player
), days AS (
    SELECT generate_series(max_date - 29, max_date, interval '1 day')::date AS dt
    FROM obs
), segments AS (
    SELECT *
    FROM (VALUES
        ('新增期', 1),
        ('成长期', 2),
        ('稳定期', 3),
        ('成熟期', 4)
    ) AS t(segment, sort_no)
), active_segment AS (
    SELECT s.session_start::date AS dt,
           coalesce(
               s.active_lifecycle_segment,
               CASE
                   WHEN s.lifecycle_day <= 6 THEN '新增期'
                   WHEN s.lifecycle_day <= 13 THEN '成长期'
                   WHEN s.lifecycle_day <= 30 THEN '稳定期'
                   ELSE '成熟期'
               END
           ) AS segment,
           count(DISTINCT s.player_id) AS active_users
    FROM public.fact_sessions s, obs
    WHERE s.session_start::date BETWEEN obs.max_date - 29 AND obs.max_date
    GROUP BY s.session_start::date, coalesce(
        s.active_lifecycle_segment,
        CASE
            WHEN s.lifecycle_day <= 6 THEN '新增期'
            WHEN s.lifecycle_day <= 13 THEN '成长期'
            WHEN s.lifecycle_day <= 30 THEN '稳定期'
            ELSE '成熟期'
        END
    )
)
SELECT d.dt AS "日期",
       seg.segment AS "生命周期",
       coalesce(a.active_users, 0) AS "活跃用户数"
FROM days d
CROSS JOIN segments seg
LEFT JOIN active_segment a
  ON a.dt = d.dt
 AND a.segment = seg.segment
ORDER BY d.dt, seg.sort_no
"""

ACTIVE_BY_CHANNEL_SQL = """
WITH obs AS (
    SELECT max(install_date) AS max_date FROM public.dim_player
), days AS (
    SELECT generate_series(max_date - 29, max_date, interval '1 day')::date AS dt
    FROM obs
), channels AS (
    SELECT *
    FROM (VALUES
        ('app store', 1),
        ('华为应用商城', 2),
        ('应用宝', 3),
        ('小米应用商城', 4),
        ('Google Play', 5),
        ('360手机助手', 6),
        ('百度手机助手', 7),
        ('豌豆荚', 8)
    ) AS t(registration_channel, sort_no)
), daily_channel AS (
    SELECT s.session_start::date AS dt,
           coalesce(s.registration_channel, p.registration_channel, p.channel) AS registration_channel,
           count(DISTINCT s.player_id) AS active_users
    FROM public.fact_sessions s
    JOIN public.dim_player p ON p.player_id = s.player_id
    JOIN obs ON true
    WHERE s.session_start::date BETWEEN obs.max_date - 29 AND obs.max_date
    GROUP BY s.session_start::date, coalesce(s.registration_channel, p.registration_channel, p.channel)
)
SELECT d.dt AS "日期",
       c.registration_channel AS "渠道",
       coalesce(dc.active_users, 0) AS "活跃用户数"
FROM days d
CROSS JOIN channels c
LEFT JOIN daily_channel dc
  ON dc.dt = d.dt
 AND dc.registration_channel = c.registration_channel
ORDER BY d.dt, c.sort_no
"""

ACTIVE_BY_SYSTEM_SQL = """
WITH obs AS (
    SELECT max(install_date) AS max_date FROM public.dim_player
), days AS (
    SELECT generate_series(max_date - 29, max_date, interval '1 day')::date AS dt
    FROM obs
), systems AS (
    SELECT * FROM (VALUES ('iOS', 1), ('Android', 2)) AS t(os_name, sort_no)
), daily_system AS (
    SELECT s.session_start::date AS dt,
           CASE WHEN lower(s.platform) = 'ios' THEN 'iOS' ELSE 'Android' END AS os_name,
           count(DISTINCT s.player_id) AS active_users
    FROM public.fact_sessions s, obs
    WHERE s.session_start::date BETWEEN obs.max_date - 29 AND obs.max_date
      AND lower(s.platform) IN ('ios', 'android')
    GROUP BY s.session_start::date, CASE WHEN lower(s.platform) = 'ios' THEN 'iOS' ELSE 'Android' END
)
SELECT d.dt AS "日期",
       s.os_name AS "系统",
       coalesce(ds.active_users, 0) AS "活跃用户数"
FROM days d
CROSS JOIN systems s
LEFT JOIN daily_system ds
  ON ds.dt = d.dt
 AND ds.os_name = s.os_name
ORDER BY d.dt, s.sort_no
"""

WEEKLY_LOGIN_DAYS_SQL = """
WITH obs AS (
    SELECT max(install_date) AS max_date FROM public.dim_player
), weeks AS (
    SELECT generate_series(
        date_trunc('week', obs.max_date - 29)::date,
        date_trunc('week', obs.max_date)::date,
        interval '1 week'
    )::date AS week_start,
    obs.max_date
    FROM obs
), player_week AS (
    SELECT w.week_start,
           s.player_id,
           count(DISTINCT s.session_start::date) AS login_days
    FROM weeks w
    JOIN public.fact_sessions s
      ON s.session_start::date BETWEEN w.week_start AND least(w.week_start + 6, w.max_date)
    GROUP BY w.week_start, s.player_id
), summary AS (
    SELECT week_start,
           count(*) AS all_users,
           count(*) FILTER (WHERE login_days = 1) AS d1,
           count(*) FILTER (WHERE login_days = 2) AS d2,
           count(*) FILTER (WHERE login_days = 3) AS d3,
           count(*) FILTER (WHERE login_days = 4) AS d4,
           count(*) FILTER (WHERE login_days = 5) AS d5,
           count(*) FILTER (WHERE login_days = 6) AS d6,
           count(*) FILTER (WHERE login_days >= 7) AS d7
    FROM player_week
    GROUP BY week_start
)
SELECT to_char(week_start, 'YYYY-MM-DD') || '当周' AS "事件发生时间",
       all_users AS "全部用户",
       d1::text || chr(10) || round(d1::numeric / nullif(all_users, 0) * 100, 2)::text || '%' AS "1天",
       d2::text || chr(10) || round(d2::numeric / nullif(all_users, 0) * 100, 2)::text || '%' AS "2天",
       d3::text || chr(10) || round(d3::numeric / nullif(all_users, 0) * 100, 2)::text || '%' AS "3天",
       d4::text || chr(10) || round(d4::numeric / nullif(all_users, 0) * 100, 2)::text || '%' AS "4天",
       d5::text || chr(10) || round(d5::numeric / nullif(all_users, 0) * 100, 2)::text || '%' AS "5天",
       d6::text || chr(10) || round(d6::numeric / nullif(all_users, 0) * 100, 2)::text || '%' AS "6天",
       d7::text || chr(10) || round(d7::numeric / nullif(all_users, 0) * 100, 2)::text || '%' AS "7天"
FROM summary
ORDER BY week_start
"""


CHARTS = [
    {
        "id": "2190000000000000001",
        "title": "DAU",
        "type": "line",
        "layout": (1, 1, 36, 16),
        "sql": DAU_SQL,
        "x": [axis("日期", axis_type="x")],
        "y": [axis("DAU", axis_type="y")],
        "series": [],
    },
    {
        "id": "2190000000000000002",
        "title": "WAU",
        "type": "line",
        "layout": (37, 1, 36, 16),
        "sql": WAU_SQL,
        "x": [axis("周", axis_type="x")],
        "y": [axis("WAU", axis_type="y")],
        "series": [],
    },
    {
        "id": "2190000000000000003",
        "title": "MAU",
        "type": "line",
        "layout": (1, 17, 36, 16),
        "sql": MAU_SQL,
        "x": [axis("月份", axis_type="x")],
        "y": [axis("MAU", axis_type="y")],
        "series": [],
    },
    {
        "id": "2190000000000000004",
        "title": "活跃用户生命周期构成",
        "type": "line",
        "layout": (37, 17, 36, 16),
        "sql": LIFECYCLE_COMPOSITION_SQL,
        "x": [axis("日期", axis_type="x")],
        "y": [axis("活跃用户数", axis_type="y")],
        "series": [axis("生命周期", axis_type="series")],
    },
    {
        "id": "2190000000000000005",
        "title": "活跃用户数（按渠道）",
        "type": "line",
        "layout": (1, 33, 72, 17),
        "sql": ACTIVE_BY_CHANNEL_SQL,
        "x": [axis("日期", axis_type="x")],
        "y": [axis("活跃用户数", axis_type="y")],
        "series": [axis("渠道", axis_type="series")],
    },
    {
        "id": "2190000000000000006",
        "title": "活跃用户数（按系统）",
        "type": "line",
        "layout": (1, 50, 72, 17),
        "sql": ACTIVE_BY_SYSTEM_SQL,
        "x": [axis("日期", axis_type="x")],
        "y": [axis("活跃用户数", axis_type="y")],
        "series": [axis("系统", axis_type="series")],
    },
    {
        "id": "2190000000000000007",
        "title": "周登录天数分布",
        "type": "table",
        "layout": (1, 67, 72, 16),
        "sql": WEEKLY_LOGIN_DAYS_SQL,
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
    backup_path = BACKUP_DIR / f"active_dashboard_{DASHBOARD_ID}_{int(time.time())}.json"
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
                raise RuntimeError(f"Active dashboard does not exist: {DASHBOARD_ID}")
            if dashboard["datasource"] != DATASOURCE_ID:
                raise RuntimeError(f"Active dashboard datasource={dashboard['datasource']}, expected {DATASOURCE_ID}")

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
            SELECT count(*) FILTER (WHERE session_uid LIKE 'active_mock_%') AS active_mock_sessions,
                   min(session_start::date) FILTER (WHERE session_uid LIKE 'active_mock_%') AS min_date,
                   max(session_start::date) FILTER (WHERE session_uid LIKE 'active_mock_%') AS max_date,
                   count(DISTINCT player_id) FILTER (WHERE session_uid LIKE 'active_mock_%') AS players
            FROM public.fact_sessions
            """
        )
        print("verify_sessions=" + json.dumps(normalize_row(dict(cur.fetchone())), ensure_ascii=False))
        cur.execute(
            """
            SELECT count(*) FILTER (WHERE registration_channel IS NOT NULL) AS session_channel_rows,
                   count(*) FILTER (WHERE active_lifecycle_segment IS NOT NULL) AS session_lifecycle_rows
            FROM public.fact_sessions
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


def seed_bi_data(conn: Any) -> None:
    ensure_active_columns(conn)
    cleanup(conn)
    players = load_players(conn)
    if not players:
        raise RuntimeError("No eligible players for active dashboard seed")
    session_rows = build_active_sessions(conn, players)
    insert_active_sessions(conn, session_rows)
    ensure_active_columns(conn)


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
