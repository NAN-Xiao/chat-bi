"""Seed city-construction detail events and create the SLG BI Mock dashboard.

Targets:
- BI tracking database: 127.0.0.1:5432 / slg_bi_mock / postgres / 111111
- App system database: 127.0.0.1:15432 / zhishu_bi / root / Password123@pg

This keeps the mock data at tracking/detail level:
- dim_player.current_city_level describes each player's current main-city level;
- fact_events rows model building upgrade finish events with construction fields.

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


TZ = ZoneInfo("Asia/Shanghai")

BI_DB = {
    "host": "127.0.0.1",
    "port": 5432,
    "dbname": "slg_bi_mock",
    "user": "postgres",
    "password": "111111",
}
SYSTEM_DB = {
    "host": "127.0.0.1",
    "port": 15432,
    "dbname": "zhishu_bi",
    "user": "root",
    "password": "Password123@pg",
}

DASHBOARD_ID = "5fde8f6a5cfb4194ad0680e9f925d57f"
DATASOURCE_ID = 1
UPDATE_BY = "7471612174524223488"
BACKUP_DIR = Path(".codex-runtime/backups")

START_DAY = date(2026, 6, 17)
END_DAY = date(2026, 6, 23)

BUILDINGS = [
    ("伐木场", "resource", 74),
    ("农田", "resource", 72),
    ("市集", "economy", 70),
    ("兵营", "military", 54),
    ("城墙", "defense", 52),
    ("医院", "support", 38),
    ("训练场", "military", 36),
    ("实验室", "research", 30),
    ("范围", "support", 26),
    ("马厩", "military", 24),
    ("采石场", "resource", 22),
    ("工坊", "craft", 20),
]

RESEARCHES = [
    ("粮食产量提升", "resource", 36),
    ("全军属性强化", "military", 34),
    ("将领攻击力", "hero", 33),
    ("士兵攻击力", "military", 32),
    ("木材产量提升", "resource", 28),
    ("士兵防御力", "military", 27),
    ("全军阵型强化", "military", 26),
    ("将领防御力", "hero", 25),
    ("士兵生命值", "military", 20),
    ("全军行军速度", "march", 18),
    ("建筑速度提升", "construction", 16),
    ("研究速度提升", "research", 15),
]

TROOPS = [
    ("老练步兵", "infantry", 28),
    ("老练弓兵", "archer", 27),
    ("轻步兵", "infantry", 24),
    ("老练骑兵", "cavalry", 22),
    ("轻骑兵", "cavalry", 20),
    ("重骑兵", "cavalry", 18),
    ("井阑", "siege", 16),
    ("轻弓兵", "archer", 14),
    ("弩车", "siege", 12),
    ("重步兵", "infantry", 10),
]

SPEEDUP_TYPES = [
    ("升级建筑加速", "building", 92),
    ("研究科技加速", "research", 34),
    ("招募士兵加速", "troop", 18),
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
    city_level: int


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
    factor = 1.0 + ((day.toordinal() % 7) - 3) * 0.045
    if day.weekday() in {4, 5}:
        factor += 0.18
    elif day.weekday() == 6:
        factor += 0.08
    if day in {date(2026, 6, 20), date(2026, 6, 21)}:
        factor += 0.28
    return max(0.72, factor)


def ensure_construction_columns(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO public.dim_event_name (
                event_name, event_category, event_cn_name, description, required_attrs
            ) VALUES
                (
                    'city_upgrade_finish',
                    'progression',
                    '主城升级完成',
                    '主城等级升级完成打点',
                    '{"city_level_before":"升级前主城等级","city_level_after":"升级后主城等级"}'::jsonb
                )
            ON CONFLICT (event_name) DO UPDATE SET
                event_category = EXCLUDED.event_category,
                event_cn_name = EXCLUDED.event_cn_name,
                description = EXCLUDED.description,
                required_attrs = EXCLUDED.required_attrs
            """
        )
        cur.execute(
            """
            ALTER TABLE public.fact_events
                ADD COLUMN IF NOT EXISTS construction_target_type text,
                ADD COLUMN IF NOT EXISTS construction_target_name text,
                ADD COLUMN IF NOT EXISTS construction_category text,
                ADD COLUMN IF NOT EXISTS construction_level_before integer,
                ADD COLUMN IF NOT EXISTS construction_level_after integer,
                ADD COLUMN IF NOT EXISTS construction_city_level integer,
                ADD COLUMN IF NOT EXISTS construction_queue_id text,
                ADD COLUMN IF NOT EXISTS construction_duration_seconds integer,
                ADD COLUMN IF NOT EXISTS construction_speedup_seconds integer,
                ADD COLUMN IF NOT EXISTS research_name text,
                ADD COLUMN IF NOT EXISTS research_category text,
                ADD COLUMN IF NOT EXISTS research_level_before integer,
                ADD COLUMN IF NOT EXISTS research_level_after integer,
                ADD COLUMN IF NOT EXISTS troop_type text,
                ADD COLUMN IF NOT EXISTS troop_tier text,
                ADD COLUMN IF NOT EXISTS troop_count integer,
                ADD COLUMN IF NOT EXISTS speedup_type text,
                ADD COLUMN IF NOT EXISTS speedup_target_type text,
                ADD COLUMN IF NOT EXISTS speedup_count integer,
                ADD COLUMN IF NOT EXISTS speedup_seconds integer
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
                   p.language, coalesce(p.current_city_level, 1) AS city_level
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
                city_level=row["city_level"],
            )
            rows_by_day.setdefault(candidate.session_start.date(), []).append(candidate)
    if not rows_by_day:
        raise RuntimeError("No sessions available for construction dashboard seeding")
    return rows_by_day


def build_upgrade_event_row(
    event_uid: str,
    candidate: SessionCandidate,
    event_time: datetime,
    building_name: str,
    building_category: str,
    level_before: int,
    level_after: int,
    speedup_seconds: int,
    sequence: int,
) -> tuple:
    duration_seconds = max(300, level_after * 900 + sequence * 23)
    attributes = {
        "source": "city_construction_mock_seed",
        "building_name": building_name,
        "building_category": building_category,
        "level_before": level_before,
        "level_after": level_after,
        "city_level": candidate.city_level,
        "speedup_seconds": speedup_seconds,
    }
    return (
        event_uid,
        f"city_build_mock_cli_{event_uid}",
        f"city_build_mock_trace_{candidate.session_id}_{sequence}",
        event_time,
        event_time,
        event_time + timedelta(milliseconds=280),
        event_time + timedelta(seconds=1),
        event_time.date(),
        candidate.player_id,
        candidate.account_id,
        candidate.role_id,
        candidate.device_id,
        candidate.server_id,
        candidate.session_id,
        "building_upgrade_finish",
        "construction",
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
        "building",
        building_name,
        building_category,
        level_before,
        level_after,
        candidate.city_level,
        f"city_build_queue_{candidate.server_id}_{candidate.player_id % 4}",
        duration_seconds,
        speedup_seconds,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )


def build_upgrade_events(rows_by_day: dict[date, list[SessionCandidate]]) -> list[tuple]:
    rng = random.Random(20260710)
    event_rows: list[tuple] = []
    event_no = 1
    for offset in range((END_DAY - START_DAY).days + 1):
        current_day = START_DAY + timedelta(days=offset)
        candidates = rows_by_day.get(current_day) or rows_by_day[max(rows_by_day)]
        for building_name, building_category, base_count in BUILDINGS:
            count = max(8, int(base_count * day_factor(current_day)))
            if building_category == "resource" and current_day.weekday() in {4, 5}:
                count += 18
            for index in range(count):
                candidate = candidates[(event_no * 17 + index * 5) % len(candidates)]
                level_after = min(20, max(2, candidate.city_level + rng.choice([-1, 0, 0, 1, 1, 2])))
                level_before = max(1, level_after - 1)
                event_time = dt_at(current_day, rng.randint(9, 23), rng.randint(0, 59), rng.randint(0, 45))
                speedup_seconds = 0
                if rng.random() < 0.48:
                    speedup_seconds = rng.choice([300, 900, 1800, 3600, 7200])
                event_rows.append(
                    build_upgrade_event_row(
                        f"city_build_mock_evt_{event_no:08d}",
                        candidate,
                        event_time,
                        building_name,
                        building_category,
                        level_before,
                        level_after,
                        speedup_seconds,
                        1 + (event_no % 8),
                    )
                )
                event_no += 1
    return event_rows


def build_domain_event_row(
    event_uid: str,
    candidate: SessionCandidate,
    event_time: datetime,
    event_name: str,
    event_category: str,
    attributes: dict[str, Any],
    sequence: int,
) -> tuple:
    return (
        event_uid,
        f"city_build_mock_cli_{event_uid}",
        f"city_build_mock_trace_{candidate.session_id}_{sequence}",
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
        event_category,
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
        attributes.get("construction_target_type"),
        attributes.get("construction_target_name"),
        attributes.get("construction_category"),
        attributes.get("construction_level_before"),
        attributes.get("construction_level_after"),
        attributes.get("construction_city_level"),
        attributes.get("construction_queue_id"),
        attributes.get("construction_duration_seconds"),
        attributes.get("construction_speedup_seconds"),
        attributes.get("research_name"),
        attributes.get("research_category"),
        attributes.get("research_level_before"),
        attributes.get("research_level_after"),
        attributes.get("troop_type"),
        attributes.get("troop_tier"),
        attributes.get("troop_count"),
        attributes.get("speedup_type"),
        attributes.get("speedup_target_type"),
        attributes.get("speedup_count"),
        attributes.get("speedup_seconds"),
    )


def build_city_level_events(rows_by_day: dict[date, list[SessionCandidate]]) -> list[tuple]:
    rng = random.Random(20260711)
    event_rows: list[tuple] = []
    event_no = 1
    for offset in range((END_DAY - START_DAY).days + 1):
        current_day = START_DAY + timedelta(days=offset)
        candidates = [item for item in (rows_by_day.get(current_day) or rows_by_day[max(rows_by_day)]) if item.city_level >= 2]
        if not candidates:
            continue
        base_count = max(130, int(210 * day_factor(current_day)))
        for index in range(base_count):
            candidate = candidates[(event_no * 23 + index * 11) % len(candidates)]
            level_after = min(10, max(2, candidate.city_level))
            if rng.random() < 0.32:
                level_after = max(2, level_after - 1)
            attributes = {
                "source": "city_construction_mock_seed",
                "construction_target_type": "main_city",
                "construction_target_name": "主城",
                "construction_category": "main_city",
                "construction_level_before": level_after - 1,
                "construction_level_after": level_after,
                "construction_city_level": level_after,
                "construction_queue_id": f"city_main_queue_{candidate.server_id}_{candidate.player_id % 4}",
                "construction_duration_seconds": level_after * 1800,
                "construction_speedup_seconds": rng.choice([0, 0, 600, 1800, 3600]),
            }
            event_rows.append(
                build_domain_event_row(
                    f"city_build_mock_city_evt_{event_no:08d}",
                    candidate,
                    dt_at(current_day, rng.randint(9, 23), rng.randint(0, 59), rng.randint(0, 45)),
                    "city_upgrade_finish",
                    "construction",
                    attributes,
                    1 + (event_no % 8),
                )
            )
            event_no += 1
    return event_rows


def build_research_events(rows_by_day: dict[date, list[SessionCandidate]]) -> list[tuple]:
    rng = random.Random(20260712)
    event_rows: list[tuple] = []
    event_no = 1
    for offset in range((END_DAY - START_DAY).days + 1):
        current_day = START_DAY + timedelta(days=offset)
        candidates = rows_by_day.get(current_day) or rows_by_day[max(rows_by_day)]
        for research_name, research_category, base_count in RESEARCHES:
            count = max(6, int(base_count * day_factor(current_day)))
            for index in range(count):
                candidate = candidates[(event_no * 19 + index * 7) % len(candidates)]
                level_after = min(10, max(1, candidate.city_level + rng.choice([-1, 0, 1])))
                attributes = {
                    "source": "city_construction_mock_seed",
                    "research_name": research_name,
                    "research_category": research_category,
                    "research_level_before": max(0, level_after - 1),
                    "research_level_after": level_after,
                    "speedup_seconds": rng.choice([0, 0, 300, 900, 1800]),
                }
                event_rows.append(
                    build_domain_event_row(
                        f"city_build_mock_research_evt_{event_no:08d}",
                        candidate,
                        dt_at(current_day, rng.randint(10, 23), rng.randint(0, 59), rng.randint(0, 45)),
                        "research_finish",
                        "research",
                        attributes,
                        1 + (event_no % 8),
                    )
                )
                event_no += 1
    return event_rows


def build_troop_events(rows_by_day: dict[date, list[SessionCandidate]]) -> list[tuple]:
    rng = random.Random(20260713)
    event_rows: list[tuple] = []
    event_no = 1
    for offset in range((END_DAY - START_DAY).days + 1):
        current_day = START_DAY + timedelta(days=offset)
        candidates = rows_by_day.get(current_day) or rows_by_day[max(rows_by_day)]
        for troop_name, troop_tier, base_count in TROOPS:
            count = max(4, int(base_count * day_factor(current_day)))
            for index in range(count):
                candidate = candidates[(event_no * 13 + index * 3) % len(candidates)]
                trained_count = rng.randint(45, 160) * max(1, min(candidate.city_level, 8))
                attributes = {
                    "source": "city_construction_mock_seed",
                    "troop_type": troop_name,
                    "troop_tier": troop_tier,
                    "troop_count": trained_count,
                }
                event_rows.append(
                    build_domain_event_row(
                        f"city_build_mock_troop_evt_{event_no:08d}",
                        candidate,
                        dt_at(current_day, rng.randint(9, 23), rng.randint(0, 59), rng.randint(0, 45)),
                        "troop_train_finish",
                        "army",
                        attributes,
                        1 + (event_no % 8),
                    )
                )
                event_no += 1
    return event_rows


def build_speedup_events(rows_by_day: dict[date, list[SessionCandidate]]) -> list[tuple]:
    rng = random.Random(20260714)
    event_rows: list[tuple] = []
    event_no = 1
    for offset in range((END_DAY - START_DAY).days + 1):
        current_day = START_DAY + timedelta(days=offset)
        candidates = rows_by_day.get(current_day) or rows_by_day[max(rows_by_day)]
        for speedup_type, target_type, base_count in SPEEDUP_TYPES:
            count = max(5, int(base_count * day_factor(current_day)))
            for index in range(count):
                candidate = candidates[(event_no * 29 + index * 5) % len(candidates)]
                use_count = rng.randint(1, 4) + (1 if candidate.city_level >= 5 else 0)
                seconds = use_count * rng.choice([300, 900, 1800, 3600])
                attributes = {
                    "source": "city_construction_mock_seed",
                    "speedup_type": speedup_type,
                    "speedup_target_type": target_type,
                    "speedup_count": use_count,
                    "speedup_seconds": seconds,
                }
                event_rows.append(
                    build_domain_event_row(
                        f"city_build_mock_speedup_evt_{event_no:08d}",
                        candidate,
                        dt_at(current_day, rng.randint(8, 23), rng.randint(0, 59), rng.randint(0, 45)),
                        "speedup_use",
                        "economy",
                        attributes,
                        1 + (event_no % 8),
                    )
                )
                event_no += 1
    return event_rows


def upsert_upgrade_events(conn: Any, event_rows: list[tuple]) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO public.fact_events (
                event_uid, client_event_id, trace_id, event_time, client_time, server_receive_time, ingest_time,
                event_date, player_id, account_id, role_id, device_id, server_id, session_id, event_name,
                event_category, lifecycle_day, player_level, vip_level, power, alliance_id, client_version,
                app_build, sdk_version, event_schema_version, platform, channel, campaign, country, ip_country,
                language, device_model, os_version, device_tier, network_type, event_source,
                sequence_in_session, attributes, construction_target_type, construction_target_name,
                construction_category, construction_level_before, construction_level_after,
                construction_city_level, construction_queue_id, construction_duration_seconds,
                construction_speedup_seconds, research_name, research_category, research_level_before,
                research_level_after, troop_type, troop_tier, troop_count, speedup_type,
                speedup_target_type, speedup_count, speedup_seconds
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (event_uid) DO UPDATE SET
                client_event_id = EXCLUDED.client_event_id,
                trace_id = EXCLUDED.trace_id,
                event_time = EXCLUDED.event_time,
                client_time = EXCLUDED.client_time,
                server_receive_time = EXCLUDED.server_receive_time,
                ingest_time = EXCLUDED.ingest_time,
                event_date = EXCLUDED.event_date,
                player_id = EXCLUDED.player_id,
                account_id = EXCLUDED.account_id,
                role_id = EXCLUDED.role_id,
                device_id = EXCLUDED.device_id,
                server_id = EXCLUDED.server_id,
                session_id = EXCLUDED.session_id,
                event_name = EXCLUDED.event_name,
                event_category = EXCLUDED.event_category,
                lifecycle_day = EXCLUDED.lifecycle_day,
                player_level = EXCLUDED.player_level,
                vip_level = EXCLUDED.vip_level,
                power = EXCLUDED.power,
                alliance_id = EXCLUDED.alliance_id,
                client_version = EXCLUDED.client_version,
                app_build = EXCLUDED.app_build,
                sdk_version = EXCLUDED.sdk_version,
                event_schema_version = EXCLUDED.event_schema_version,
                platform = EXCLUDED.platform,
                channel = EXCLUDED.channel,
                campaign = EXCLUDED.campaign,
                country = EXCLUDED.country,
                ip_country = EXCLUDED.ip_country,
                language = EXCLUDED.language,
                device_model = EXCLUDED.device_model,
                os_version = EXCLUDED.os_version,
                device_tier = EXCLUDED.device_tier,
                network_type = EXCLUDED.network_type,
                event_source = EXCLUDED.event_source,
                sequence_in_session = EXCLUDED.sequence_in_session,
                attributes = EXCLUDED.attributes,
                construction_target_type = EXCLUDED.construction_target_type,
                construction_target_name = EXCLUDED.construction_target_name,
                construction_category = EXCLUDED.construction_category,
                construction_level_before = EXCLUDED.construction_level_before,
                construction_level_after = EXCLUDED.construction_level_after,
                construction_city_level = EXCLUDED.construction_city_level,
                construction_queue_id = EXCLUDED.construction_queue_id,
                construction_duration_seconds = EXCLUDED.construction_duration_seconds,
                construction_speedup_seconds = EXCLUDED.construction_speedup_seconds,
                research_name = EXCLUDED.research_name,
                research_category = EXCLUDED.research_category,
                research_level_before = EXCLUDED.research_level_before,
                research_level_after = EXCLUDED.research_level_after,
                troop_type = EXCLUDED.troop_type,
                troop_tier = EXCLUDED.troop_tier,
                troop_count = EXCLUDED.troop_count,
                speedup_type = EXCLUDED.speedup_type,
                speedup_target_type = EXCLUDED.speedup_target_type,
                speedup_count = EXCLUDED.speedup_count,
                speedup_seconds = EXCLUDED.speedup_seconds
            """,
            event_rows,
        )
    conn.commit()
    print(f"upserted city construction events={len(event_rows)}")


CITY_LEVEL_PLAYERS_SQL = """
WITH levels AS (
    SELECT generate_series(1, 10) AS city_level
), players AS (
    SELECT CASE
             WHEN coalesce(current_city_level, 1) >= 10 THEN 10
             ELSE greatest(coalesce(current_city_level, 1), 1)
           END AS city_level,
           player_id
    FROM public.dim_player
)
SELECT l.city_level::text AS "主城等级",
       coalesce(count(p.player_id), 0) AS "玩家数"
FROM levels l
LEFT JOIN players p ON p.city_level = l.city_level
GROUP BY l.city_level
ORDER BY l.city_level
"""

BUILDING_UPGRADES_SQL = """
WITH obs AS (
    SELECT max(event_date) AS max_date
    FROM public.fact_events
    WHERE event_uid LIKE 'city_build_mock_evt_%'
), days AS (
    SELECT generate_series(max_date - 6, max_date, interval '1 day')::date AS dt
    FROM obs
), buildings AS (
    SELECT *
    FROM (VALUES
        ('伐木场', 1), ('农田', 2), ('市集', 3), ('兵营', 4),
        ('城墙', 5), ('医院', 6), ('训练场', 7), ('实验室', 8),
        ('范围', 9), ('马厩', 10), ('采石场', 11), ('工坊', 12)
    ) AS t(building_name, sort_no)
), daily AS (
    SELECT event_date AS dt,
           construction_target_name AS building_name,
           count(*) AS upgrade_count
    FROM public.fact_events, obs
    WHERE event_name = 'building_upgrade_finish'
      AND construction_target_type = 'building'
      AND event_uid LIKE 'city_build_mock_evt_%'
      AND event_date BETWEEN obs.max_date - 6 AND obs.max_date
    GROUP BY event_date, construction_target_name
)
SELECT d.dt AS "日期",
       b.building_name AS "建筑名称",
       coalesce(daily.upgrade_count, 0) AS "升级次数"
FROM days d
CROSS JOIN buildings b
LEFT JOIN daily ON daily.dt = d.dt AND daily.building_name = b.building_name
ORDER BY d.dt, b.sort_no
"""

CITY_UPGRADE_FUNNEL_SQL = """
WITH obs AS (
    SELECT max(install_date) AS max_date FROM public.dim_player
), cohort AS (
    SELECT player_id, greatest(coalesce(current_city_level, 1), 1) AS city_level
    FROM public.dim_player, obs
    WHERE install_date BETWEEN obs.max_date - 59 AND obs.max_date
), steps AS (
    SELECT *
    FROM (VALUES
        (1, '步骤1：用户注册'),
        (2, '步骤2：主城2级'),
        (3, '步骤3：主城3级'),
        (4, '步骤4：主城4级'),
        (5, '步骤5：主城5级'),
        (6, '步骤6：主城6级'),
        (7, '步骤7：主城7级'),
        (8, '步骤8：主城8级'),
        (9, '步骤9：主城9级'),
        (10, '步骤10：主城10级')
    ) AS t(step_level, step_name)
), funnel AS (
    SELECT s.step_level,
           s.step_name,
           count(*) FILTER (WHERE c.city_level >= s.step_level) AS users
    FROM steps s
    CROSS JOIN cohort c
    GROUP BY s.step_level, s.step_name
), base AS (
    SELECT users AS base_users FROM funnel WHERE step_level = 1
)
SELECT step_name AS "主城升级步骤",
       users AS "用户数",
       round(users::numeric / nullif(base_users, 0) * 100, 2) AS "转化率"
FROM funnel
CROSS JOIN base
ORDER BY step_level
"""

AVG_CITY_LEVEL_METRIC_SQL = """
SELECT round(avg(greatest(coalesce(current_city_level, 1), 1))::numeric, 3) AS "主城平均等级"
FROM public.dim_player
"""

DAILY_CITY_UPGRADE_METRIC_SQL = """
WITH obs AS (
    SELECT max(event_date) AS max_date
    FROM public.fact_events
    WHERE event_uid LIKE 'city_build_mock_city_evt_%'
), daily AS (
    SELECT event_date,
           count(*) AS upgrades
    FROM public.fact_events, obs
    WHERE event_uid LIKE 'city_build_mock_city_evt_%'
      AND event_date IN (obs.max_date, obs.max_date - 1, obs.max_date - 7)
    GROUP BY event_date
)
SELECT coalesce(today.upgrades, 0) AS "当日主城升级次数",
       round((coalesce(today.upgrades, 0) - coalesce(yesterday.upgrades, 0))::numeric / nullif(yesterday.upgrades, 0) * 100, 2) AS "日环比",
       round((coalesce(today.upgrades, 0) - coalesce(last_week.upgrades, 0))::numeric / nullif(last_week.upgrades, 0) * 100, 2) AS "周同比"
FROM obs
LEFT JOIN daily today ON today.event_date = obs.max_date
LEFT JOIN daily yesterday ON yesterday.event_date = obs.max_date - 1
LEFT JOIN daily last_week ON last_week.event_date = obs.max_date - 7
"""

DAILY_BUILDING_UPGRADE_METRIC_SQL = """
WITH obs AS (
    SELECT max(event_date) AS max_date
    FROM public.fact_events
    WHERE event_uid LIKE 'city_build_mock_evt_%'
), daily AS (
    SELECT event_date,
           count(*) AS upgrades
    FROM public.fact_events, obs
    WHERE event_uid LIKE 'city_build_mock_evt_%'
      AND event_date IN (obs.max_date, obs.max_date - 1, obs.max_date - 7)
    GROUP BY event_date
)
SELECT coalesce(today.upgrades, 0) AS "当日建筑升级次数",
       round((coalesce(today.upgrades, 0) - coalesce(yesterday.upgrades, 0))::numeric / nullif(yesterday.upgrades, 0) * 100, 2) AS "日环比",
       round((coalesce(today.upgrades, 0) - coalesce(last_week.upgrades, 0))::numeric / nullif(last_week.upgrades, 0) * 100, 2) AS "周同比"
FROM obs
LEFT JOIN daily today ON today.event_date = obs.max_date
LEFT JOIN daily yesterday ON yesterday.event_date = obs.max_date - 1
LEFT JOIN daily last_week ON last_week.event_date = obs.max_date - 7
"""

DAILY_RESEARCH_UPGRADE_METRIC_SQL = """
WITH obs AS (
    SELECT max(event_date) AS max_date
    FROM public.fact_events
    WHERE event_uid LIKE 'city_build_mock_research_evt_%'
), daily AS (
    SELECT event_date,
           count(*) AS upgrades
    FROM public.fact_events, obs
    WHERE event_uid LIKE 'city_build_mock_research_evt_%'
      AND event_date IN (obs.max_date, obs.max_date - 1, obs.max_date - 7)
    GROUP BY event_date
)
SELECT coalesce(today.upgrades, 0) AS "当日科技升级次数",
       round((coalesce(today.upgrades, 0) - coalesce(yesterday.upgrades, 0))::numeric / nullif(yesterday.upgrades, 0) * 100, 2) AS "日环比",
       round((coalesce(today.upgrades, 0) - coalesce(last_week.upgrades, 0))::numeric / nullif(last_week.upgrades, 0) * 100, 2) AS "周同比"
FROM obs
LEFT JOIN daily today ON today.event_date = obs.max_date
LEFT JOIN daily yesterday ON yesterday.event_date = obs.max_date - 1
LEFT JOIN daily last_week ON last_week.event_date = obs.max_date - 7
"""

CITY_LEVEL_BUILDING_UPGRADES_SQL = """
WITH obs AS (
    SELECT max(event_date) AS max_date
    FROM public.fact_events
    WHERE event_uid LIKE 'city_build_mock_evt_%'
), days AS (
    SELECT generate_series(max_date - 6, max_date, interval '1 day')::date AS dt
    FROM obs
), levels AS (
    SELECT generate_series(1, 8) AS city_level
), daily AS (
    SELECT event_date AS dt,
           least(greatest(coalesce(construction_city_level, 1), 1), 8) AS city_level,
           count(*) AS upgrade_count
    FROM public.fact_events, obs
    WHERE event_uid LIKE 'city_build_mock_evt_%'
      AND event_date BETWEEN obs.max_date - 6 AND obs.max_date
    GROUP BY event_date, least(greatest(coalesce(construction_city_level, 1), 1), 8)
)
SELECT d.dt AS "日期",
       l.city_level::text AS "主城等级",
       coalesce(daily.upgrade_count, 0) AS "建筑升级次数"
FROM days d
CROSS JOIN levels l
LEFT JOIN daily ON daily.dt = d.dt AND daily.city_level = l.city_level
ORDER BY d.dt, l.city_level
"""

RESEARCH_UPGRADES_TABLE_SQL = """
WITH obs AS (
    SELECT max(event_date) AS max_date
    FROM public.fact_events
    WHERE event_uid LIKE 'city_build_mock_research_evt_%'
)
SELECT research_name AS "科技名称",
       count(*) AS "升级科技.总次数"
FROM public.fact_events, obs
WHERE event_uid LIKE 'city_build_mock_research_evt_%'
  AND event_date BETWEEN obs.max_date - 29 AND obs.max_date
GROUP BY research_name
ORDER BY count(*) DESC, research_name
"""

CITY_LEVEL_RESEARCH_UPGRADES_SQL = """
WITH obs AS (
    SELECT max(event_date) AS max_date
    FROM public.fact_events
    WHERE event_uid LIKE 'city_build_mock_research_evt_%'
), days AS (
    SELECT generate_series(max_date - 6, max_date, interval '1 day')::date AS dt
    FROM obs
), levels AS (
    SELECT generate_series(1, 9) AS city_level
), daily AS (
    SELECT event_date AS dt,
           least(greatest(coalesce(construction_city_level, player_level, 1), 1), 9) AS city_level,
           count(*) AS upgrade_count
    FROM public.fact_events, obs
    WHERE event_uid LIKE 'city_build_mock_research_evt_%'
      AND event_date BETWEEN obs.max_date - 6 AND obs.max_date
    GROUP BY event_date, least(greatest(coalesce(construction_city_level, player_level, 1), 1), 9)
)
SELECT d.dt AS "日期",
       l.city_level::text AS "主城等级",
       coalesce(daily.upgrade_count, 0) AS "科技升级次数"
FROM days d
CROSS JOIN levels l
LEFT JOIN daily ON daily.dt = d.dt AND daily.city_level = l.city_level
ORDER BY d.dt, l.city_level
"""

TROOP_RECRUITMENT_TABLE_SQL = """
WITH obs AS (
    SELECT max(event_date) AS max_date
    FROM public.fact_events
    WHERE event_uid LIKE 'city_build_mock_troop_evt_%'
)
SELECT troop_type AS "士兵兵种",
       count(*) AS "招募总次数",
       round(count(*)::numeric / nullif(count(DISTINCT player_id), 0), 2) AS "人均招募次数",
       coalesce(sum(troop_count), 0) AS "招募总数量"
FROM public.fact_events, obs
WHERE event_uid LIKE 'city_build_mock_troop_evt_%'
  AND event_date BETWEEN obs.max_date - 29 AND obs.max_date
GROUP BY troop_type
ORDER BY "招募总次数" DESC, troop_type
"""

SPEEDUP_USAGE_TABLE_SQL = """
WITH obs AS (
    SELECT max(event_date) AS max_date
    FROM public.fact_events
    WHERE event_uid LIKE 'city_build_mock_speedup_evt_%'
)
SELECT event_date AS "日期",
       speedup_type AS "加速类型",
       coalesce(sum(speedup_count), 0) AS "使用加速次数",
       count(DISTINCT player_id) AS "使用加速人数",
       round(coalesce(sum(speedup_count), 0)::numeric / nullif(count(DISTINCT player_id), 0), 2) AS "人均使用加速次数",
       coalesce(sum(speedup_seconds), 0) AS "加速总时长"
FROM public.fact_events, obs
WHERE event_uid LIKE 'city_build_mock_speedup_evt_%'
  AND event_date BETWEEN obs.max_date - 29 AND obs.max_date
GROUP BY event_date, speedup_type
ORDER BY event_date DESC, speedup_type
"""


CHARTS = [
    {
        "id": "2196000000000000001",
        "title": "主城平均等级",
        "type": "metric",
        "layout": (1, 1, 18, 8),
        "sql": AVG_CITY_LEVEL_METRIC_SQL,
        "x": [],
        "y": [axis("主城平均等级", axis_type="y")],
        "series": [],
    },
    {
        "id": "2196000000000000002",
        "title": "当日主城升级次数",
        "type": "metric",
        "layout": (19, 1, 18, 8),
        "sql": DAILY_CITY_UPGRADE_METRIC_SQL,
        "x": [],
        "y": [axis("当日主城升级次数", axis_type="y"), axis("日环比", axis_type="y"), axis("周同比", axis_type="y")],
        "series": [],
    },
    {
        "id": "2196000000000000003",
        "title": "当日建筑升级次数",
        "type": "metric",
        "layout": (37, 1, 18, 8),
        "sql": DAILY_BUILDING_UPGRADE_METRIC_SQL,
        "x": [],
        "y": [axis("当日建筑升级次数", axis_type="y"), axis("日环比", axis_type="y"), axis("周同比", axis_type="y")],
        "series": [],
    },
    {
        "id": "2196000000000000004",
        "title": "当日科技升级次数",
        "type": "metric",
        "layout": (55, 1, 18, 8),
        "sql": DAILY_RESEARCH_UPGRADE_METRIC_SQL,
        "x": [],
        "y": [axis("当日科技升级次数", axis_type="y"), axis("日环比", axis_type="y"), axis("周同比", axis_type="y")],
        "series": [],
    },
    {
        "id": "2196000000000000005",
        "title": "各主城等级玩家数",
        "type": "column",
        "layout": (1, 9, 36, 18),
        "sql": CITY_LEVEL_PLAYERS_SQL,
        "x": [axis("主城等级", axis_type="x")],
        "y": [axis("玩家数", axis_type="y")],
        "series": [],
    },
    {
        "id": "2196000000000000006",
        "title": "各建筑升级次数",
        "type": "line",
        "layout": (37, 9, 36, 18),
        "sql": BUILDING_UPGRADES_SQL,
        "x": [axis("日期", axis_type="x")],
        "y": [axis("升级次数", axis_type="y")],
        "series": [axis("建筑名称", axis_type="series")],
    },
    {
        "id": "2196000000000000007",
        "title": "各主城等级建筑升级次数",
        "type": "line",
        "layout": (1, 27, 36, 18),
        "sql": CITY_LEVEL_BUILDING_UPGRADES_SQL,
        "x": [axis("日期", axis_type="x")],
        "y": [axis("建筑升级次数", axis_type="y")],
        "series": [axis("主城等级", axis_type="series")],
    },
    {
        "id": "2196000000000000008",
        "title": "各科技升级次数",
        "type": "table",
        "layout": (37, 27, 36, 18),
        "sql": RESEARCH_UPGRADES_TABLE_SQL,
        "x": [],
        "y": [],
        "series": [],
    },
    {
        "id": "2196000000000000009",
        "title": "各主城等级用户科技升级情况",
        "type": "line",
        "layout": (1, 45, 36, 18),
        "sql": CITY_LEVEL_RESEARCH_UPGRADES_SQL,
        "x": [axis("日期", axis_type="x")],
        "y": [axis("科技升级次数", axis_type="y")],
        "series": [axis("主城等级", axis_type="series")],
    },
    {
        "id": "2196000000000000010",
        "title": "各兵种招募情况",
        "type": "table",
        "layout": (37, 45, 36, 18),
        "sql": TROOP_RECRUITMENT_TABLE_SQL,
        "x": [],
        "y": [],
        "series": [],
    },
    {
        "id": "2196000000000000011",
        "title": "各类型加速情况",
        "type": "table",
        "layout": (1, 63, 72, 16),
        "sql": SPEEDUP_USAGE_TABLE_SQL,
        "x": [],
        "y": [],
        "series": [],
    },
    {
        "id": "2196000000000000012",
        "title": "主城升级漏斗",
        "type": "funnel",
        "layout": (1, 79, 72, 20),
        "sql": CITY_UPGRADE_FUNNEL_SQL,
        "x": [axis("主城升级步骤", axis_type="x")],
        "y": [axis("用户数", axis_type="y")],
        "series": [],
        "showLabel": True,
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
        chart_config = {
            "type": chart_info["type"],
            "sourceType": chart_info["type"],
            "title": chart_info["title"],
            "id": chart_info["id"],
            "xAxis": chart_info["x"],
            "yAxis": chart_info["y"],
            "series": chart_info["series"],
            "columns": [axis(field) for field in fields] if chart_info["type"] in {"table", "metric"} else [],
        }
        if chart_info.get("showLabel"):
            chart_config["showLabel"] = True
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
        }
        print(f"{chart_info['title']}: rows={len(rows)} fields={fields}")

    return component_data, canvas_view_info


def backup_dashboard_row(row: dict[str, Any]) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"city_construction_dashboard_{DASHBOARD_ID}_{int(time.time())}.json"
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
                raise RuntimeError(f"City construction dashboard does not exist: {DASHBOARD_ID}")
            if dashboard["datasource"] != DATASOURCE_ID:
                raise RuntimeError(f"City construction dashboard datasource={dashboard['datasource']}, expected {DATASOURCE_ID}")

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
            SELECT count(*) FILTER (WHERE event_uid LIKE 'city_build_mock_%') AS city_mock_events,
                   count(*) FILTER (WHERE event_uid LIKE 'city_build_mock_evt_%') AS building_events,
                   count(*) FILTER (WHERE event_uid LIKE 'city_build_mock_city_evt_%') AS city_upgrade_events,
                   count(*) FILTER (WHERE event_uid LIKE 'city_build_mock_research_evt_%') AS research_events,
                   count(*) FILTER (WHERE event_uid LIKE 'city_build_mock_troop_evt_%') AS troop_events,
                   count(*) FILTER (WHERE event_uid LIKE 'city_build_mock_speedup_evt_%') AS speedup_events,
                   min(event_date) FILTER (WHERE event_uid LIKE 'city_build_mock_%') AS min_date,
                   max(event_date) FILTER (WHERE event_uid LIKE 'city_build_mock_%') AS max_date,
                   count(DISTINCT construction_target_name) FILTER (WHERE event_uid LIKE 'city_build_mock_evt_%') AS buildings
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
    ensure_construction_columns(conn)
    rows_by_day = load_session_candidates(conn)
    event_rows = []
    event_rows.extend(build_upgrade_events(rows_by_day))
    event_rows.extend(build_city_level_events(rows_by_day))
    event_rows.extend(build_research_events(rows_by_day))
    event_rows.extend(build_troop_events(rows_by_day))
    event_rows.extend(build_speedup_events(rows_by_day))
    upsert_upgrade_events(conn, event_rows)


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
