"""Seed hero-growth detail events and create the SLG BI Mock growth dashboard.

Targets:
- BI tracking database: 127.0.0.1:5432 / slg_bi_mock / postgres / 111111
- App system database: core SHUZHI_DB_* settings from the repo .env

This follows the BI tracking strategy:
- dim_hero describes hero/card metadata;
- fact_events rows model hero level-up and star-up tracking events.

No aggregate KPI tables, result tables, snapshots, or analysis views are
created. Dashboard metrics are computed from detail rows at query time.
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

DASHBOARD_ID = "d7e9ed45eb77480694e7a49191039ed0"
DATASOURCE_ID = 1
UPDATE_BY = "7471612174524223488"
BACKUP_DIR = Path(".codex-runtime/backups")

START_DAY = date(2026, 5, 25)
END_DAY = date(2026, 6, 23)

HEROES = [
    (10, "SR", "战士", 46),
    (11, "SR", "战士", 24),
    (47, "SR", "牧师", 23),
    (23, "SR", "法师", 23),
    (46, "SR", "牧师", 22),
    (36, "SR", "射手", 22),
    (22, "SR", "法师", 21),
    (26, "SSR", "法师", 21),
    (50, "SR", "牧师", 20),
    (52, "SSR", "牧师", 20),
    (25, "SSR", "法师", 19),
    (12, "SSR", "战士", 19),
    (39, "SSR", "射手", 18),
    (18, "SSR", "牧师", 17),
    (41, "SSR", "战士", 17),
    (7, "SSR", "法师", 16),
    (32, "SSR", "射手", 16),
    (55, "SSR", "战士", 15),
    (60, "SSR", "牧师", 15),
    (63, "SSR", "法师", 14),
    (2, "SR", "战士", 18),
    (3, "SR", "射手", 17),
    (4, "SR", "法师", 17),
    (5, "SR", "牧师", 16),
    (6, "SR", "战士", 16),
    (8, "SR", "射手", 15),
    (9, "SR", "法师", 15),
    (13, "SR", "牧师", 14),
    (14, "SR", "战士", 14),
    (15, "SR", "射手", 14),
    (16, "SR", "法师", 13),
    (17, "SR", "牧师", 13),
    (19, "SR", "战士", 13),
    (20, "SR", "射手", 12),
    (21, "SR", "法师", 12),
    (24, "SR", "牧师", 12),
    (27, "R", "战士", 10),
    (28, "R", "射手", 10),
    (29, "R", "法师", 9),
    (30, "R", "牧师", 9),
    (31, "R", "战士", 8),
    (33, "R", "射手", 8),
    (34, "R", "法师", 8),
    (35, "R", "牧师", 8),
    (37, "R", "战士", 7),
    (38, "R", "射手", 7),
    (40, "R", "法师", 7),
    (42, "R", "牧师", 7),
]

EVENT_COLUMNS = [
    "event_uid",
    "client_event_id",
    "trace_id",
    "event_time",
    "client_time",
    "server_receive_time",
    "ingest_time",
    "event_date",
    "player_id",
    "account_id",
    "role_id",
    "device_id",
    "server_id",
    "session_id",
    "event_name",
    "event_category",
    "lifecycle_day",
    "player_level",
    "vip_level",
    "power",
    "alliance_id",
    "client_version",
    "app_build",
    "sdk_version",
    "event_schema_version",
    "platform",
    "channel",
    "campaign",
    "country",
    "ip_country",
    "language",
    "device_model",
    "os_version",
    "device_tier",
    "network_type",
    "event_source",
    "sequence_in_session",
    "attributes",
    "hero_id",
    "hero_name",
    "hero_quality",
    "hero_type",
    "hero_action",
    "hero_level_before",
    "hero_level_after",
    "hero_star_before",
    "hero_star_after",
]


@dataclass(slots=True)
class SessionCandidate:
    session_id: int
    player_id: int
    account_id: str
    role_id: str
    device_id: str
    server_id: int
    session_start: datetime
    lifecycle_day: int
    player_level: int
    vip_level: int
    power: int
    platform: str
    channel: str
    campaign: str
    client_version: str
    app_build: int
    sdk_version: str
    device_tier: str
    device_model: str
    os_version: str
    network_type: str
    country: str
    ip_country: str
    language: str


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


def day_factor(day: date) -> float:
    factor = 1.0 + ((day.toordinal() % 7) - 3) * 0.035
    if day.weekday() in {4, 5}:
        factor += 0.18
    elif day.weekday() == 6:
        factor += 0.06
    if day >= date(2026, 6, 20):
        factor += 0.12
    return max(0.72, factor)


def hero_quality_factor(quality: str) -> float:
    if quality == "SSR":
        return 1.12
    if quality == "SR":
        return 1.0
    return 0.62


def ensure_growth_schema(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS public.dim_hero (
                hero_id integer PRIMARY KEY,
                hero_name text NOT NULL,
                hero_quality text NOT NULL,
                hero_type text NOT NULL,
                release_date date,
                default_star integer
            )
            """
        )
        cur.executemany(
            """
            INSERT INTO public.dim_hero (
                hero_id, hero_name, hero_quality, hero_type, release_date, default_star
            ) VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (hero_id) DO UPDATE SET
                hero_name = EXCLUDED.hero_name,
                hero_quality = EXCLUDED.hero_quality,
                hero_type = EXCLUDED.hero_type,
                release_date = EXCLUDED.release_date,
                default_star = EXCLUDED.default_star
            """,
            [
                (
                    hero_id,
                    f"将领{hero_id}",
                    quality,
                    hero_type,
                    date(2025, 10, 1) + timedelta(days=hero_id % 280),
                    3 if quality == "SSR" else (2 if quality == "SR" else 1),
                )
                for hero_id, quality, hero_type, _weight in HEROES
            ],
        )
        cur.executemany(
            """
            INSERT INTO public.dim_event_name (
                event_name, event_category, event_cn_name, description, required_attrs
            ) VALUES (%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT (event_name) DO UPDATE SET
                event_category = EXCLUDED.event_category,
                event_cn_name = EXCLUDED.event_cn_name,
                description = EXCLUDED.description,
                required_attrs = EXCLUDED.required_attrs
            """,
            [
                (
                    "hero_level_up",
                    "progression",
                    "英雄升级",
                    "英雄等级提升打点",
                    '{"hero_id":"英雄ID","hero_level_before":"升级前等级","hero_level_after":"升级后等级"}',
                ),
                (
                    "hero_star_up",
                    "progression",
                    "英雄升星",
                    "英雄星级提升打点",
                    '{"hero_id":"英雄ID","hero_star_before":"升星前星级","hero_star_after":"升星后星级"}',
                ),
            ],
        )
        cur.execute(
            """
            ALTER TABLE public.fact_events
                ADD COLUMN IF NOT EXISTS hero_id integer,
                ADD COLUMN IF NOT EXISTS hero_name text,
                ADD COLUMN IF NOT EXISTS hero_quality text,
                ADD COLUMN IF NOT EXISTS hero_type text,
                ADD COLUMN IF NOT EXISTS hero_action text,
                ADD COLUMN IF NOT EXISTS hero_level_before integer,
                ADD COLUMN IF NOT EXISTS hero_level_after integer,
                ADD COLUMN IF NOT EXISTS hero_star_before integer,
                ADD COLUMN IF NOT EXISTS hero_star_after integer
            """
        )
    conn.commit()


def load_session_candidates(conn: Any) -> dict[date, list[SessionCandidate]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT s.session_id, s.player_id, s.account_id, s.role_id, s.device_id,
                   s.server_id, s.session_start, s.lifecycle_day,
                   s.player_level_end AS player_level,
                   coalesce(p.current_vip_level, 0) AS vip_level,
                   s.power_end AS power, s.platform, s.channel, s.campaign,
                   s.client_version, s.app_build, s.sdk_version, s.device_tier,
                   s.device_model, s.os_version, s.network_type, s.country, s.ip_country,
                   p.language
            FROM public.fact_sessions s
            JOIN public.dim_player p ON p.player_id = s.player_id
            WHERE s.session_start::date BETWEEN %s AND %s
            ORDER BY s.session_start, s.session_id
            """,
            (START_DAY, END_DAY),
        )
        rows_by_day: dict[date, list[SessionCandidate]] = {}
        for row in cur.fetchall():
            candidate = SessionCandidate(
                session_id=row["session_id"],
                player_id=row["player_id"],
                account_id=row["account_id"],
                role_id=row["role_id"],
                device_id=row["device_id"],
                server_id=row["server_id"],
                session_start=row["session_start"],
                lifecycle_day=row["lifecycle_day"],
                player_level=row["player_level"],
                vip_level=row["vip_level"],
                power=row["power"],
                platform=row["platform"],
                channel=row["channel"],
                campaign=row["campaign"],
                client_version=row["client_version"],
                app_build=row["app_build"],
                sdk_version=row["sdk_version"],
                device_tier=row["device_tier"],
                device_model=row["device_model"],
                os_version=row["os_version"],
                network_type=row["network_type"],
                country=row["country"],
                ip_country=row["ip_country"],
                language=row["language"],
            )
            rows_by_day.setdefault(candidate.session_start.date(), []).append(candidate)
    if not rows_by_day:
        raise RuntimeError("No sessions available for growth dashboard seeding")
    return rows_by_day


def weighted_level(rng: random.Random, quality: str) -> int:
    if quality == "SSR":
        levels = [2, 3, 4, 5, 6, 7, 8, 9, 10]
        weights = [6, 7, 7, 58, 8, 6, 6, 1, 1]
    elif quality == "SR":
        levels = [1, 2, 3, 4, 5, 6, 7, 8]
        weights = [9, 12, 16, 22, 28, 7, 4, 2]
    else:
        levels = [1, 2, 3, 4, 5]
        weights = [18, 28, 28, 18, 8]
    return rng.choices(levels, weights=weights, k=1)[0]


def build_event_row(
    event_uid: str,
    candidate: SessionCandidate,
    event_time: datetime,
    event_name: str,
    hero_id: int,
    hero_quality: str,
    hero_type: str,
    hero_action: str,
    sequence: int,
    hero_level_before: int | None = None,
    hero_level_after: int | None = None,
    hero_star_before: int | None = None,
    hero_star_after: int | None = None,
) -> tuple:
    attributes = {
        "source": "growth_mock_seed",
        "hero_id": hero_id,
        "hero_quality": hero_quality,
        "hero_type": hero_type,
        "hero_action": hero_action,
    }
    if hero_level_after is not None:
        attributes["hero_level_before"] = hero_level_before
        attributes["hero_level_after"] = hero_level_after
    if hero_star_after is not None:
        attributes["hero_star_before"] = hero_star_before
        attributes["hero_star_after"] = hero_star_after
    return (
        event_uid,
        f"growth_mock_cli_{event_uid}",
        f"growth_mock_trace_{candidate.session_id}_{sequence}",
        event_time,
        event_time,
        event_time + timedelta(milliseconds=260),
        event_time + timedelta(seconds=1),
        event_time.date(),
        candidate.player_id,
        candidate.account_id,
        candidate.role_id,
        candidate.device_id,
        candidate.server_id,
        candidate.session_id,
        event_name,
        "progression",
        candidate.lifecycle_day,
        candidate.player_level,
        candidate.vip_level,
        candidate.power,
        None,
        candidate.client_version,
        candidate.app_build,
        candidate.sdk_version,
        "slg_event_v4",
        candidate.platform,
        candidate.channel,
        candidate.campaign,
        candidate.country,
        candidate.ip_country,
        candidate.language,
        candidate.device_model,
        candidate.os_version,
        candidate.device_tier,
        candidate.network_type,
        "server",
        sequence,
        json.dumps(attributes, ensure_ascii=False),
        hero_id,
        f"将领{hero_id}",
        hero_quality,
        hero_type,
        hero_action,
        hero_level_before,
        hero_level_after,
        hero_star_before,
        hero_star_after,
    )


def build_growth_events(rows_by_day: dict[date, list[SessionCandidate]]) -> list[tuple]:
    rng = random.Random(20260720)
    event_rows: list[tuple] = []
    level_no = 1
    star_no = 1
    for offset in range((END_DAY - START_DAY).days + 1):
        current_day = START_DAY + timedelta(days=offset)
        candidates = rows_by_day.get(current_day) or rows_by_day[max(rows_by_day)]
        for hero_id, quality, hero_type, weight in HEROES:
            factor = day_factor(current_day) * hero_quality_factor(quality)
            level_count = max(2, int(weight * factor * 1.22))
            star_count = max(1, int(weight * factor * (0.34 if quality != "R" else 0.18)))
            for index in range(level_count):
                candidate = candidates[(level_no * 17 + hero_id * 11 + index * 5) % len(candidates)]
                level_after = weighted_level(rng, quality)
                event_time = dt_at(current_day, rng.randint(9, 23), rng.randint(0, 59), rng.randint(0, 45))
                event_rows.append(
                    build_event_row(
                        f"growth_hero_level_evt_{level_no:08d}",
                        candidate,
                        event_time,
                        "hero_level_up",
                        hero_id,
                        quality,
                        hero_type,
                        "level_up",
                        1 + (level_no % 8),
                        max(1, level_after - 1),
                        level_after,
                        None,
                        None,
                    )
                )
                level_no += 1
            for index in range(star_count):
                candidate = candidates[(star_no * 23 + hero_id * 7 + index * 3) % len(candidates)]
                star_after = min(6, max(2, rng.choices([2, 3, 4, 5, 6], weights=[30, 38, 20, 10, 2], k=1)[0]))
                event_time = dt_at(current_day, rng.randint(10, 23), rng.randint(0, 59), rng.randint(0, 45))
                event_rows.append(
                    build_event_row(
                        f"growth_hero_star_evt_{star_no:08d}",
                        candidate,
                        event_time,
                        "hero_star_up",
                        hero_id,
                        quality,
                        hero_type,
                        "star_up",
                        1 + (star_no % 8),
                        None,
                        None,
                        max(1, star_after - 1),
                        star_after,
                    )
                )
                star_no += 1
    return event_rows


def upsert_growth_events(conn: Any, event_rows: list[tuple]) -> None:
    placeholders = ",".join(["%s"] * len(EVENT_COLUMNS))
    update_set = ",\n                ".join(
        f"{column} = EXCLUDED.{column}" for column in EVENT_COLUMNS if column != "event_uid"
    )
    with conn.cursor() as cur:
        cur.executemany(
            f"""
            INSERT INTO public.fact_events (
                {", ".join(EVENT_COLUMNS)}
            ) VALUES ({placeholders})
            ON CONFLICT (event_uid) DO UPDATE SET
                {update_set}
            """,
            event_rows,
        )
    conn.commit()
    print(f"upserted growth hero events={len(event_rows)}")


HERO_GROWTH_SQL = """
WITH obs AS (
    SELECT max(event_date) AS max_date
    FROM public.fact_events
    WHERE event_uid LIKE 'growth_hero_%_evt_%'
), star_stats AS (
    SELECT hero_id,
           count(*) AS star_up_count,
           count(DISTINCT player_id) AS star_up_users
    FROM public.fact_events, obs
    WHERE event_uid LIKE 'growth_hero_star_evt_%'
      AND event_date BETWEEN obs.max_date - 29 AND obs.max_date
    GROUP BY hero_id
), level_stats AS (
    SELECT hero_id,
           count(*) AS level_up_count,
           count(DISTINCT player_id) AS level_up_users
    FROM public.fact_events, obs
    WHERE event_uid LIKE 'growth_hero_level_evt_%'
      AND event_date BETWEEN obs.max_date - 29 AND obs.max_date
    GROUP BY hero_id
)
SELECT h.hero_id AS "将领ID",
       h.hero_quality AS "card_list@hero_quality",
       h.hero_type AS "card_list@hero_type",
       coalesce(star_stats.star_up_count, 0) AS "升星次数",
       coalesce(star_stats.star_up_users, 0) AS "升星用户数",
       coalesce(level_stats.level_up_count, 0) AS "升级次数",
       coalesce(level_stats.level_up_users, 0) AS "升级用户数"
FROM public.dim_hero h
LEFT JOIN star_stats ON star_stats.hero_id = h.hero_id
LEFT JOIN level_stats ON level_stats.hero_id = h.hero_id
WHERE coalesce(star_stats.star_up_count, 0) + coalesce(level_stats.level_up_count, 0) > 0
ORDER BY "升星次数" DESC, "升级次数" DESC, h.hero_id
"""

SSR_LEVEL_DISTRIBUTION_SQL = """
WITH latest AS (
    SELECT e.player_id,
           e.hero_id,
           max(e.hero_level_after) AS hero_level
    FROM public.fact_events e
    JOIN public.dim_hero h ON h.hero_id = e.hero_id
    WHERE e.event_uid LIKE 'growth_hero_level_evt_%'
      AND h.hero_quality = 'SSR'
      AND e.hero_level_after IS NOT NULL
    GROUP BY e.player_id, e.hero_id
), summary AS (
    SELECT h.hero_id::text AS hero_id_text,
           h.hero_quality,
           h.hero_type,
           count(*) AS all_users,
           count(*) FILTER (WHERE latest.hero_level = 2) AS l2,
           count(*) FILTER (WHERE latest.hero_level = 3) AS l3,
           count(*) FILTER (WHERE latest.hero_level = 4) AS l4,
           count(*) FILTER (WHERE latest.hero_level = 5) AS l5,
           count(*) FILTER (WHERE latest.hero_level = 6) AS l6,
           count(*) FILTER (WHERE latest.hero_level = 7) AS l7,
           count(*) FILTER (WHERE latest.hero_level = 8) AS l8,
           count(*) FILTER (WHERE latest.hero_level = 9) AS l9,
           count(*) FILTER (WHERE latest.hero_level >= 10) AS l10,
           1 AS sort_group,
           h.hero_id AS sort_no
    FROM latest
    JOIN public.dim_hero h ON h.hero_id = latest.hero_id
    GROUP BY h.hero_id, h.hero_quality, h.hero_type
), total AS (
    SELECT '合计' AS hero_id_text,
           '合计' AS hero_quality,
           '合计' AS hero_type,
           sum(all_users) AS all_users,
           sum(l2) AS l2,
           sum(l3) AS l3,
           sum(l4) AS l4,
           sum(l5) AS l5,
           sum(l6) AS l6,
           sum(l7) AS l7,
           sum(l8) AS l8,
           sum(l9) AS l9,
           sum(l10) AS l10,
           0 AS sort_group,
           0 AS sort_no
    FROM summary
), rows AS (
    SELECT * FROM total
    UNION ALL
    SELECT * FROM summary
)
SELECT hero_id_text AS "将领ID",
       hero_quality AS "card_list@hero_quality",
       hero_type AS "card_list@hero_type",
       all_users AS "全部用户",
       l2::text || chr(10) || round(l2::numeric / nullif(all_users, 0) * 100, 2)::text || '%' AS "2",
       l3::text || chr(10) || round(l3::numeric / nullif(all_users, 0) * 100, 2)::text || '%' AS "3",
       l4::text || chr(10) || round(l4::numeric / nullif(all_users, 0) * 100, 2)::text || '%' AS "4",
       l5::text || chr(10) || round(l5::numeric / nullif(all_users, 0) * 100, 2)::text || '%' AS "5",
       l6::text || chr(10) || round(l6::numeric / nullif(all_users, 0) * 100, 2)::text || '%' AS "6",
       l7::text || chr(10) || round(l7::numeric / nullif(all_users, 0) * 100, 2)::text || '%' AS "7",
       l8::text || chr(10) || round(l8::numeric / nullif(all_users, 0) * 100, 2)::text || '%' AS "8",
       l9::text || chr(10) || round(l9::numeric / nullif(all_users, 0) * 100, 2)::text || '%' AS "9",
       l10::text || chr(10) || round(l10::numeric / nullif(all_users, 0) * 100, 2)::text || '%' AS "10"
FROM rows
ORDER BY sort_group, all_users DESC, sort_no
"""


CHARTS = [
    {
        "id": "2197000000000000001",
        "title": "英雄养成情况",
        "type": "table",
        "layout": (1, 1, 72, 17),
        "sql": HERO_GROWTH_SQL,
        "x": [],
        "y": [],
        "series": [],
    },
    {
        "id": "2197000000000000002",
        "title": "SSR英雄的等级分布",
        "type": "table",
        "layout": (1, 18, 72, 17),
        "sql": SSR_LEVEL_DISTRIBUTION_SQL,
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
                "columns": [axis(field) for field in fields],
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
    backup_path = BACKUP_DIR / f"growth_dashboard_{DASHBOARD_ID}_{int(time.time())}.json"
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
                raise RuntimeError(f"Growth dashboard does not exist: {DASHBOARD_ID}")
            if dashboard["datasource"] != DATASOURCE_ID:
                raise RuntimeError(f"Growth dashboard datasource={dashboard['datasource']}, expected {DATASOURCE_ID}")

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
            SELECT count(*) FILTER (WHERE event_uid LIKE 'growth_hero_%_evt_%') AS growth_events,
                   count(*) FILTER (WHERE event_uid LIKE 'growth_hero_level_evt_%') AS level_events,
                   count(*) FILTER (WHERE event_uid LIKE 'growth_hero_star_evt_%') AS star_events,
                   min(event_date) FILTER (WHERE event_uid LIKE 'growth_hero_%_evt_%') AS min_date,
                   max(event_date) FILTER (WHERE event_uid LIKE 'growth_hero_%_evt_%') AS max_date,
                   count(DISTINCT hero_id) FILTER (WHERE event_uid LIKE 'growth_hero_%_evt_%') AS heroes
            FROM public.fact_events
            """
        )
        print("verify_events=" + json.dumps(normalize_row(dict(cur.fetchone())), ensure_ascii=False))

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
    ensure_growth_schema(conn)
    rows_by_day = load_session_candidates(conn)
    event_rows = build_growth_events(rows_by_day)
    upsert_growth_events(conn, event_rows)


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
