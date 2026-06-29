"""Seed expedition detail rows and create the SLG BI Mock expedition dashboard.

Targets:
- BI tracking database: 127.0.0.1:5432 / slg_bi_mock / postgres / 111111
- App system database: core ZHISHU_DB_* settings from the repo .env

This keeps the mock data at event/detail level. The new fact_expeditions table
stores one row per expedition, traceable to player/session/event time. No
aggregate KPI tables, result tables, snapshots, or analysis views are created.
Dashboard metrics are computed from detail rows at query time.
"""
from __future__ import annotations

import builtins
import csv
import io
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

b_float = builtins.float
b_int = builtins.int
b_str = builtins.str
b_len = builtins.len
b_max = builtins.max
b_min = builtins.min
b_sum = builtins.sum
b_range = builtins.range
b_zip = builtins.zip
b_list = builtins.list

BI_DB = {
    "host": "127.0.0.1",
    "port": 5432,
    "dbname": "slg_bi_mock",
    "user": "postgres",
    "password": "111111",
}
SYSTEM_DB = core_system_db_config()

DASHBOARD_ID = "f2b49b69927740e8bd4c51f38ecf6f7a"
DASHBOARD_NAME = "出征数据"
TENANT_NAME = "slg_bi_mock"
DATASOURCE_NAME = "SLG BI Mock"
EXPEDITION_TABLE_NAME = "fact_expeditions"
EXPEDITION_TABLE_COMMENT = "出征事实表，一行代表一次玩家出征，记录兵种、将领、队伍战力、出征耗时、结果和剩余士兵等明细。"
FALLBACK_TENANT_ID = 7473600346187632640
FALLBACK_DATASOURCE_ID = 1
FALLBACK_UPDATE_BY = "7471612174524223488"
BACKUP_DIR = Path(".codex-runtime/backups")

OBSERVED_DAY = date(2026, 6, 26)
DATA_START_DAY = date(2026, 5, 27)
DATA_END_DAY = date(2026, 7, 2)
EXPEDITION_ID_BASE = 880_000_000_000_000
INSERT_PAGE_SIZE = 10_000


@dataclass(slots=True)
class SessionCandidate:
    session_id: int
    player_id: int
    server_id: int
    session_start: datetime
    session_end: datetime
    duration_seconds: int
    lifecycle_day: int
    player_level: int
    vip_level: int
    power: int
    city_level: int


@dataclass(slots=True)
class Hero:
    hero_id: int
    hero_name: str
    quality: str
    hero_type: str
    weight: float


TROOPS = [
    ("轻步兵", 1, 1.00, 0.160),
    ("轻弓兵", 1, 0.98, 0.155),
    ("重步兵", 2, 0.91, 0.150),
    ("重弓兵", 2, 0.93, 0.140),
    ("轻骑兵", 1, 1.05, 0.125),
    ("重骑兵", 3, 1.08, 0.110),
    ("枪兵", 2, 0.97, 0.080),
    ("弩车", 3, 1.12, 0.055),
    ("投石车", 4, 1.18, 0.025),
]

EXPEDITION_TYPES = [
    ("drill", "演习", "npc", 0.46),
    ("world_monster", "野怪", "monster", 0.24),
    ("resource_tile", "资源点", "npc", 0.16),
    ("pve_chapter", "主线", "npc", 0.09),
    ("pvp", "玩家对战", "player", 0.05),
]

CITY_LEVEL_WIN_BASE = {
    1: 0.770,
    2: 0.795,
    3: 0.820,
    4: 0.845,
    5: 0.865,
    6: 0.882,
    7: 0.897,
    8: 0.910,
    9: 0.923,
}

EXPEDITION_TYPE_WIN_MODIFIER = {
    "drill": 0.016,
    "resource_tile": 0.006,
    "world_monster": -0.014,
    "pve_chapter": -0.024,
    "pvp": -0.085,
}

EXPEDITION_FIELD_COMMENTS = {
    "expedition_id": "出征记录ID",
    "expedition_uid": "出征唯一标识",
    "source_battle_id": "来源战斗ID",
    "source_event_uid": "来源事件唯一标识",
    "march_start_event_uid": "出征开始事件唯一标识",
    "march_finish_event_uid": "出征结束事件唯一标识",
    "event_time": "出征完成时间",
    "event_date": "出征日期",
    "player_id": "玩家ID",
    "server_id": "服务器ID",
    "session_id": "会话ID",
    "expedition_type": "出征类型",
    "drill_type": "演习/玩法类型",
    "target_type": "目标类型",
    "result": "出征结果",
    "troop_type": "出征士兵兵种",
    "troop_tier": "士兵阶级",
    "troops_sent": "出征士兵数量",
    "troops_lost": "损失士兵数量",
    "wounded": "受伤士兵数量",
    "troops_remaining": "剩余士兵数量",
    "team_power": "出征队伍战斗力",
    "duration_seconds": "出征耗时秒数",
    "hero_id": "将领ID",
    "hero_name": "将领名称",
    "hero_level": "将领等级",
    "city_level": "主城等级",
    "stamina_spent": "消耗体力",
    "resource_looted": "掠夺资源量",
    "map_x": "地图X坐标",
    "map_y": "地图Y坐标",
    "attributes": "出征扩展属性",
}

HERO_PRIORITY = [
    10,
    15,
    5,
    42,
    17,
    19,
    14,
    41,
    32,
    22,
    35,
    47,
    49,
    36,
    21,
    50,
    8,
    9,
    12,
    28,
]

FIXED_DAILY_TARGETS: dict[date, dict[str, float]] = {
    date(2026, 6, 17): {
        "count": 10452,
        "avg_per": 6.64,
        "avg_troops": 597.24,
        "avg_power": 5719.87,
        "avg_duration": 299.63,
        "win_rate": 85.41,
    },
    date(2026, 6, 18): {
        "count": 10164,
        "avg_per": 6.42,
        "avg_troops": 568.50,
        "avg_power": 5597.00,
        "avg_duration": 297.87,
        "win_rate": 85.85,
    },
    date(2026, 6, 19): {
        "count": 11620,
        "avg_per": 6.21,
        "avg_troops": 533.02,
        "avg_power": 5340.08,
        "avg_duration": 293.57,
        "win_rate": 84.90,
    },
    date(2026, 6, 20): {
        "count": 14180,
        "avg_per": 6.07,
        "avg_troops": 501.49,
        "avg_power": 5110.35,
        "avg_duration": 288.14,
        "win_rate": 84.96,
    },
    date(2026, 6, 21): {
        "count": 14241,
        "avg_per": 6.22,
        "avg_troops": 506.07,
        "avg_power": 5108.24,
        "avg_duration": 287.90,
        "win_rate": 84.85,
    },
    date(2026, 6, 22): {
        "count": 11650,
        "avg_per": 6.81,
        "avg_troops": 552.20,
        "avg_power": 5312.66,
        "avg_duration": 292.42,
        "win_rate": 86.10,
    },
    date(2026, 6, 23): {
        "count": 11101,
        "avg_per": 6.62,
        "avg_troops": 572.37,
        "avg_power": 5559.87,
        "avg_duration": 294.33,
        "win_rate": 85.71,
    },
    date(2026, 6, 24): {
        "count": 10839,
        "avg_per": 6.61,
        "avg_troops": 589.68,
        "avg_power": 5666.87,
        "avg_duration": 298.41,
        "win_rate": 85.69,
    },
    date(2026, 6, 25): {
        "count": 9978,
        "avg_per": 6.23,
        "avg_troops": 570.86,
        "avg_power": 5531.21,
        "avg_duration": 295.11,
        "win_rate": 85.56,
    },
    date(2026, 6, 26): {
        "count": 11936,
        "avg_per": 6.39,
        "avg_troops": 579.42,
        "avg_power": 5604.18,
        "avg_duration": 296.26,
        "win_rate": 85.93,
    },
}


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


def choose_weighted(items: list[tuple[Any, float]], rng: random.Random) -> Any:
    total = 0.0
    for weighted_item in items:
        raw_weight = weighted_item[1]
        weight = b_float(raw_weight)
        if weight < 0.0:
            weight = 0.0
        total += weight
    if total <= 0:
        return items[0][0]
    marker = rng.random() * total
    running = 0.0
    fallback = items[-1][0]
    for weighted_item in items:
        chosen_item = weighted_item[0]
        weight = b_float(weighted_item[1])
        if weight < 0.0:
            weight = 0.0
        running += weight
        if marker <= running:
            return chosen_item
    return fallback


def choose_troop(rng: random.Random) -> tuple[str, int, float]:
    total = 0.0
    for troop_row in TROOPS:
        total += b_float(troop_row[3])
    marker = rng.random() * total
    running = 0.0
    selected_troop = TROOPS[-1]
    for troop_row in TROOPS:
        running += b_float(troop_row[3])
        if marker <= running:
            selected_troop = troop_row
            break
    troop_name, troop_tier, troop_modifier, _weight = selected_troop
    return b_str(troop_name), b_int(troop_tier), b_float(troop_modifier)


def choose_expedition_type(rng: random.Random) -> tuple[str, str, str]:
    total = 0.0
    for type_row in EXPEDITION_TYPES:
        total += b_float(type_row[3])
    marker = rng.random() * total
    running = 0.0
    selected_type = EXPEDITION_TYPES[-1]
    for type_row in EXPEDITION_TYPES:
        running += b_float(type_row[3])
        if marker <= running:
            selected_type = type_row
            break
    expedition_type, drill_type, target_type, _weight = selected_type
    return b_str(expedition_type), b_str(drill_type), b_str(target_type)


def choose_hero(heroes: list[Hero], rng: random.Random) -> Hero:
    hero_pool = [hero_row for hero_row in heroes if isinstance(hero_row, Hero)]
    if not hero_pool:
        raise RuntimeError("No valid dim_hero rows available for expedition dashboard seeding")
    total = 0.0
    for hero_row in hero_pool:
        total += b_float(hero_row.weight)
    marker = rng.random() * total
    running = 0.0
    selected_hero = hero_pool[-1]
    for hero_row in hero_pool:
        running += b_float(hero_row.weight)
        if marker <= running:
            selected_hero = hero_row
            break
    return selected_hero


def city_level_win_base(city_level: int) -> float:
    if city_level in CITY_LEVEL_WIN_BASE:
        return CITY_LEVEL_WIN_BASE[city_level]
    if city_level < 1:
        return CITY_LEVEL_WIN_BASE[1] - 0.025
    return min(0.945, CITY_LEVEL_WIN_BASE[9] + min(city_level - 9, 6) * 0.004)


def expedition_win_probability(
    target: dict[str, float],
    candidate: SessionCandidate,
    selected_hero: Hero,
    troop_tier: int,
    expedition_type: str,
) -> float:
    day_modifier = (target["win_rate"] - 85.5) / 100.0 * 0.28
    hero_modifier = 0.012 if selected_hero.quality == "SSR" else 0.004 if selected_hero.quality == "SR" else -0.004
    tier_modifier = (troop_tier - 2) * 0.006
    vip_modifier = min(candidate.vip_level, 8) * 0.002
    player_level_modifier = min(max(candidate.player_level - candidate.city_level * 2, -6), 10) * 0.0012
    type_modifier = EXPEDITION_TYPE_WIN_MODIFIER.get(expedition_type, 0.0)
    probability = (
        city_level_win_base(candidate.city_level)
        + day_modifier
        + hero_modifier
        + tier_modifier
        + vip_modifier
        + player_level_modifier
        + type_modifier
    )
    return min(0.965, max(0.58, probability))


def weekday_cn_sql(field: str) -> str:
    return (
        f"CASE EXTRACT(ISODOW FROM {field})::int "
        "WHEN 1 THEN '一' WHEN 2 THEN '二' WHEN 3 THEN '三' WHEN 4 THEN '四' "
        "WHEN 5 THEN '五' WHEN 6 THEN '六' ELSE '日' END"
    )


def dashboard_day_label_sql(field: str) -> str:
    return f"to_char({field}, 'YYYY-MM-DD') || '(' || {weekday_cn_sql(field)} || ')'"


def daily_target(day: date, eligible_count: int) -> dict[str, float]:
    fixed = FIXED_DAILY_TARGETS.get(day)
    if fixed:
        return dict(fixed)

    phase = math.sin((day - DATA_START_DAY).days / 3.2)
    weekend_boost = 1.22 if day.weekday() in {4, 5} else 1.08 if day.weekday() == 6 else 1.0
    future_softener = 0.96 if day > OBSERVED_DAY else 1.0
    avg_per = (5.72 + 0.34 * phase) * weekend_boost * future_softener
    count = max(2200, int(max(eligible_count, 320) * avg_per))
    return {
        "count": float(count),
        "avg_per": avg_per,
        "avg_troops": 548.0 + 34.0 * math.sin(day.toordinal() / 2.7),
        "avg_power": 5400.0 + 320.0 * math.sin(day.toordinal() / 3.6),
        "avg_duration": 293.0 + 6.0 * math.cos(day.toordinal() / 4.2),
        "win_rate": 85.2 + 0.8 * math.sin(day.toordinal() / 5.3),
    }


def ensure_expedition_table(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS public.fact_expeditions (
                expedition_id bigint PRIMARY KEY,
                expedition_uid text NOT NULL UNIQUE,
                source_battle_id bigint,
                source_event_uid text,
                march_start_event_uid text,
                march_finish_event_uid text,
                event_time timestamptz NOT NULL,
                event_date date NOT NULL,
                player_id integer NOT NULL REFERENCES public.dim_player(player_id),
                server_id integer NOT NULL REFERENCES public.dim_server(server_id),
                session_id bigint NOT NULL REFERENCES public.fact_sessions(session_id),
                expedition_type text NOT NULL,
                drill_type text NOT NULL,
                target_type text NOT NULL,
                result text NOT NULL,
                troop_type text NOT NULL,
                troop_tier integer NOT NULL,
                troops_sent integer NOT NULL,
                troops_lost integer NOT NULL,
                wounded integer NOT NULL,
                troops_remaining integer NOT NULL,
                team_power integer NOT NULL,
                duration_seconds integer NOT NULL,
                hero_id integer NOT NULL,
                hero_name text NOT NULL,
                hero_level integer NOT NULL,
                city_level integer NOT NULL,
                stamina_spent integer NOT NULL,
                resource_looted integer NOT NULL,
                map_x integer NOT NULL,
                map_y integer NOT NULL,
                attributes jsonb NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_fact_expeditions_event_date
                ON public.fact_expeditions(event_date)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_fact_expeditions_player_date
                ON public.fact_expeditions(player_id, event_date)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_fact_expeditions_troop_date
                ON public.fact_expeditions(troop_type, event_date)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_fact_expeditions_hero_date
                ON public.fact_expeditions(hero_id, event_date)
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_fact_expeditions_city_date
                ON public.fact_expeditions(city_level, event_date)
            """
        )
    conn.commit()


def load_physical_columns(conn: Any, table_name: str) -> list[dict[str, Any]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT a.attname AS field_name,
                   pg_catalog.format_type(a.atttypid, a.atttypmod) AS field_type,
                   coalesce(col_description(c.oid, a.attnum), '') AS field_comment,
                   a.attnum AS field_index
            FROM pg_catalog.pg_attribute a
            JOIN pg_catalog.pg_class c ON a.attrelid = c.oid
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname = %s
              AND a.attnum > 0
              AND NOT a.attisdropped
            ORDER BY a.attnum
            """,
            (table_name,),
        )
        return [dict(row) for row in cur.fetchall()]


def sync_expedition_metadata(system_conn: Any, bi_conn: Any, datasource_id: int) -> int:
    physical_fields = load_physical_columns(bi_conn, EXPEDITION_TABLE_NAME)
    if not physical_fields:
        raise RuntimeError(f"Physical table public.{EXPEDITION_TABLE_NAME} was not found")

    added_fields: list[str] = []
    updated_fields = 0
    with system_conn:
        with system_conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id
                FROM public.core_table
                WHERE ds_id = %s AND table_name = %s
                LIMIT 1
                """,
                (datasource_id, EXPEDITION_TABLE_NAME),
            )
            table = cur.fetchone()
            if table:
                table_id = int(table["id"])
                cur.execute(
                    """
                    UPDATE public.core_table
                       SET checked = true,
                           table_comment = %s,
                           custom_comment = %s
                     WHERE id = %s
                    """,
                    (EXPEDITION_TABLE_COMMENT, EXPEDITION_TABLE_COMMENT, table_id),
                )
                print(f"updated_metadata_table id={table_id} rows={cur.rowcount}")
            else:
                cur.execute(
                    """
                    INSERT INTO public.core_table
                        (ds_id, checked, table_name, table_comment, custom_comment, embedding)
                    VALUES
                        (%s, true, %s, %s, %s, NULL)
                    RETURNING id
                    """,
                    (
                        datasource_id,
                        EXPEDITION_TABLE_NAME,
                        EXPEDITION_TABLE_COMMENT,
                        EXPEDITION_TABLE_COMMENT,
                    ),
                )
                table_id = int(cur.fetchone()["id"])
                print(f"inserted_metadata_table id={table_id}")

            cur.execute(
                """
                SELECT id, field_name
                FROM public.core_field
                WHERE ds_id = %s AND table_id = %s
                """,
                (datasource_id, table_id),
            )
            existing_by_name = {row["field_name"]: int(row["id"]) for row in cur.fetchall()}

            for index, field in enumerate(physical_fields):
                field_name = field["field_name"]
                comment = EXPEDITION_FIELD_COMMENTS.get(field_name) or field["field_comment"] or field_name
                field_id = existing_by_name.get(field_name)
                if field_id:
                    cur.execute(
                        """
                        UPDATE public.core_field
                           SET checked = true,
                               field_type = %s,
                               field_comment = %s,
                               custom_comment = %s,
                               field_index = %s
                         WHERE id = %s
                        """,
                        (field["field_type"], comment, comment, index, field_id),
                    )
                    updated_fields += cur.rowcount
                else:
                    cur.execute(
                        """
                        INSERT INTO public.core_field
                            (ds_id, table_id, checked, field_name, field_type,
                             field_comment, custom_comment, field_index)
                        VALUES
                            (%s, %s, true, %s, %s, %s, %s, %s)
                        """,
                        (
                            datasource_id,
                            table_id,
                            field_name,
                            field["field_type"],
                            comment,
                            comment,
                            index,
                        ),
                    )
                    added_fields.append(field_name)

    print(
        "synced_expedition_metadata="
        + json.dumps(
            {
                "datasource_id": datasource_id,
                "table_id": table_id,
                "field_count": len(physical_fields),
                "updated_fields": updated_fields,
                "added_fields": added_fields,
            },
            ensure_ascii=False,
        )
    )
    return table_id


def load_sessions(conn: Any) -> dict[date, list[SessionCandidate]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT s.session_id, s.player_id, s.server_id, s.session_start, s.session_end,
                   s.duration_seconds, s.lifecycle_day,
                   s.player_level_end AS player_level,
                   coalesce(p.current_vip_level, 0) AS vip_level,
                   greatest(s.power_end, p.current_power) AS power,
                   coalesce(p.current_city_level, 1) AS city_level
            FROM public.fact_sessions s
            JOIN public.dim_player p ON p.player_id = s.player_id
            WHERE s.session_start::date BETWEEN %s AND %s
            ORDER BY s.session_start, s.session_id
            """,
            (DATA_START_DAY, DATA_END_DAY),
        )
        rows_by_day: dict[date, list[SessionCandidate]] = {}
        seen_by_day: set[tuple[date, int]] = set()
        for row in cur.fetchall():
            session_day = row["session_start"].date()
            key = (session_day, row["player_id"])
            if key in seen_by_day:
                continue
            seen_by_day.add(key)
            candidate = SessionCandidate(
                session_id=row["session_id"],
                player_id=row["player_id"],
                server_id=row["server_id"],
                session_start=row["session_start"],
                session_end=row["session_end"],
                duration_seconds=row["duration_seconds"],
                lifecycle_day=row["lifecycle_day"],
                player_level=row["player_level"],
                vip_level=row["vip_level"],
                power=int(row["power"]),
                city_level=row["city_level"],
            )
            rows_by_day.setdefault(session_day, []).append(candidate)
    if not rows_by_day:
        raise RuntimeError("No sessions available for expedition dashboard seeding")
    return rows_by_day


def load_heroes(conn: Any) -> list[Hero]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT hero_id, hero_name, hero_quality, hero_type
            FROM public.dim_hero
            ORDER BY hero_id
            """
        )
        rows = cur.fetchall()
    if not rows:
        raise RuntimeError("No dim_hero rows available for expedition dashboard seeding")

    priority_rank = {hero_id: index for index, hero_id in enumerate(HERO_PRIORITY)}
    heroes: list[Hero] = []
    for row in rows:
        hero_id = row["hero_id"]
        quality_weight = 1.18 if row["hero_quality"] == "SSR" else 1.0
        priority_weight = 1.0
        if hero_id in priority_rank:
            priority_weight = 4.2 - min(priority_rank[hero_id], 18) * 0.15
        heroes.append(
            Hero(
                hero_id=hero_id,
                hero_name=row["hero_name"],
                quality=row["hero_quality"],
                hero_type=row["hero_type"],
                weight=max(0.35, priority_weight * quality_weight),
            )
        )
    return heroes


def allocate_counts(total: int, candidates: list[SessionCandidate], rng: random.Random) -> list[int]:
    if not candidates:
        return []
    if total < len(candidates):
        selected = set(rng.sample(range(len(candidates)), total))
        return [1 if index in selected else 0 for index in range(len(candidates))]

    weights = []
    for candidate in candidates:
        activity_weight = 1.0 + min(candidate.city_level, 12) * 0.025 + min(candidate.vip_level, 8) * 0.018
        weights.append(max(0.1, rng.lognormvariate(0.0, 0.23) * activity_weight))
    weight_sum = sum(weights)
    counts = [max(1, int(total * weight / weight_sum)) for weight in weights]
    diff = total - sum(counts)
    order = sorted(range(len(candidates)), key=lambda i: weights[i], reverse=diff > 0)
    cursor = 0
    while diff != 0 and order:
        index = order[cursor % len(order)]
        if diff > 0:
            counts[index] += 1
            diff -= 1
        elif counts[index] > 1:
            counts[index] -= 1
            diff += 1
        cursor += 1
    return counts


def event_time_for(candidate: SessionCandidate, expedition_index: int, rng: random.Random) -> datetime:
    if candidate.duration_seconds > 240:
        latest_offset = max(180, min(candidate.duration_seconds - 60, 7200))
        offset = rng.randint(90, latest_offset)
        return candidate.session_start + timedelta(seconds=offset + expedition_index * rng.randint(23, 91))

    base = datetime.combine(candidate.session_start.date(), dt_time(rng.randint(8, 23), rng.randint(0, 59)), TZ)
    return base + timedelta(seconds=rng.randint(0, 59))


def build_expedition_rows(
    rows_by_day: dict[date, list[SessionCandidate]],
    heroes: list[Hero],
) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    expedition_id = EXPEDITION_ID_BASE
    for offset in range((DATA_END_DAY - DATA_START_DAY).days + 1):
        current_day = DATA_START_DAY + timedelta(days=offset)
        day_sessions = rows_by_day.get(current_day, [])
        if not day_sessions:
            continue

        eligible = [item for item in day_sessions if item.player_level >= 4]
        if len(eligible) < 80:
            eligible = day_sessions

        target = daily_target(current_day, len(eligible))
        rng = random.Random(2026062600 + current_day.toordinal())
        total_count = int(target["count"])
        target_players = int(total_count / max(1.0, target["avg_per"]))
        participant_count = min(len(eligible), max(1, target_players))
        participants = rng.sample(eligible, participant_count) if participant_count < len(eligible) else list(eligible)
        counts = allocate_counts(total_count, participants, rng)

        for candidate, personal_count in zip(participants, counts):
            for personal_index in range(personal_count):
                troop_name, troop_tier, troop_modifier = choose_troop(rng)
                selected_hero = choose_hero(heroes, rng)
                expedition_type, drill_type, target_type = choose_expedition_type(rng)

                city_modifier = 0.92 + min(candidate.city_level, 12) * 0.012
                troops_sent = max(
                    80,
                    int(rng.gauss(target["avg_troops"] * troop_modifier * city_modifier, target["avg_troops"] * 0.13)),
                )
                team_power = max(
                    800,
                    int(
                        rng.gauss(target["avg_power"] * 0.972, target["avg_power"] * 0.12)
                        + (selected_hero.hero_id % 9) * 28
                        + min(candidate.city_level, 15) * 10
                    ),
                )
                duration_seconds = max(45, int(rng.gauss(target["avg_duration"], 31)))
                win_probability = expedition_win_probability(
                    target=target,
                    candidate=candidate,
                    selected_hero=selected_hero,
                    troop_tier=troop_tier,
                    expedition_type=expedition_type,
                )
                result = "win" if rng.random() < win_probability else "lose"
                loss_ratio = rng.uniform(0.010, 0.045) if result == "win" else rng.uniform(0.060, 0.135)
                troops_lost = min(troops_sent, max(0, int(troops_sent * loss_ratio)))
                wounded = min(troops_sent - troops_lost, int(troops_sent * loss_ratio * rng.uniform(0.65, 1.35)))
                troops_remaining = max(0, troops_sent - troops_lost)
                stamina_spent = 10 if expedition_type == "pvp" else 6 if expedition_type in {"world_monster", "pve_chapter"} else 4
                resource_looted = (
                    int(rng.randint(300, 5200) * max(1.0, candidate.city_level / 4.0))
                    if result == "win" and expedition_type in {"resource_tile", "world_monster", "pve_chapter"}
                    else 0
                )
                event_time = event_time_for(candidate, personal_index, rng)
                sequence = expedition_id - EXPEDITION_ID_BASE + 1
                expedition_uid = f"exp_mock_{current_day.strftime('%Y%m%d')}_{sequence:09d}"
                attributes = {
                    "source": "expedition_mock_seed",
                    "observed_day": str(OBSERVED_DAY.isoformat()),
                    "target_avg_troops": float(round(float(target["avg_troops"]), 2)),
                    "target_avg_power": float(round(float(target["avg_power"]), 2)),
                    "target_win_rate_pct": float(round(float(target["win_rate"]), 2)),
                }
                rows.append(
                    (
                        expedition_id,
                        expedition_uid,
                        None,
                        None,
                        f"exp_mock_march_start_{expedition_id}",
                        f"exp_mock_march_finish_{expedition_id}",
                        event_time,
                        current_day,
                        candidate.player_id,
                        candidate.server_id,
                        candidate.session_id,
                        expedition_type,
                        drill_type,
                        target_type,
                        result,
                        troop_name,
                        troop_tier,
                        troops_sent,
                        troops_lost,
                        wounded,
                        troops_remaining,
                        team_power,
                        duration_seconds,
                        selected_hero.hero_id,
                        selected_hero.hero_name,
                        max(1, min(80, candidate.player_level * 2 + selected_hero.hero_id % 11 + rng.randint(-2, 3))),
                        candidate.city_level,
                        stamina_spent,
                        resource_looted,
                        rng.randint(1, 1200),
                        rng.randint(1, 1200),
                        json.dumps(attributes, ensure_ascii=False),
                    )
                )
                expedition_id += 1

    return rows


def insert_expedition_rows(conn: Any, rows: list[tuple[Any, ...]]) -> None:
    columns = (
        "expedition_id",
        "expedition_uid",
        "source_battle_id",
        "source_event_uid",
        "march_start_event_uid",
        "march_finish_event_uid",
        "event_time",
        "event_date",
        "player_id",
        "server_id",
        "session_id",
        "expedition_type",
        "drill_type",
        "target_type",
        "result",
        "troop_type",
        "troop_tier",
        "troops_sent",
        "troops_lost",
        "wounded",
        "troops_remaining",
        "team_power",
        "duration_seconds",
        "hero_id",
        "hero_name",
        "hero_level",
        "city_level",
        "stamina_spent",
        "resource_looted",
        "map_x",
        "map_y",
        "attributes",
    )
    with conn.cursor() as cur:
        cur.execute("DELETE FROM public.fact_expeditions WHERE expedition_uid LIKE 'exp_mock_%'")
        conn.commit()
        for offset in range(0, len(rows), INSERT_PAGE_SIZE):
            buffer = io.StringIO()
            writer = csv.writer(buffer, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
            for row in rows[offset : offset + INSERT_PAGE_SIZE]:
                writer.writerow(["\\N" if value is None else value for value in row])
            buffer.seek(0)
            column_sql = ", ".join(columns)
            cur.copy_expert(
                f"""
                COPY public.fact_expeditions ({column_sql})
                FROM STDIN WITH (FORMAT CSV, DELIMITER E'\\t', NULL '\\N')
                """,
                buffer,
            )
            conn.commit()
            print(f"inserted_expeditions={min(offset + INSERT_PAGE_SIZE, len(rows))}/{len(rows)}")


def seed_bi_data(conn: Any) -> None:
    ensure_expedition_table(conn)
    rows_by_day = load_sessions(conn)
    heroes = load_heroes(conn)
    rows = build_expedition_rows(rows_by_day, heroes)
    if not rows:
        raise RuntimeError("No expedition rows generated")
    insert_expedition_rows(conn, rows)


OBS = f"DATE '{OBSERVED_DAY.isoformat()}'"
OBS_MINUS_1 = f"DATE '{(OBSERVED_DAY - timedelta(days=1)).isoformat()}'"
OBS_MINUS_7 = f"DATE '{(OBSERVED_DAY - timedelta(days=7)).isoformat()}'"
OBS_7_START = f"DATE '{(OBSERVED_DAY - timedelta(days=6)).isoformat()}'"
OBS_14_START = f"DATE '{(OBSERVED_DAY - timedelta(days=13)).isoformat()}'"
OBS_30_START = f"DATE '{(OBSERVED_DAY - timedelta(days=29)).isoformat()}'"

DAILY_BASE_SQL = f"""
WITH params AS (SELECT {OBS} AS obs_day),
daily AS (
    SELECT event_date,
           count(*)::numeric AS expedition_count,
           sum(troops_sent)::numeric AS troops_sent,
           avg(team_power)::numeric AS avg_power,
           avg(duration_seconds)::numeric AS avg_duration
    FROM public.fact_expeditions, params
    WHERE event_date IN (params.obs_day, params.obs_day - 1, params.obs_day - 7)
    GROUP BY event_date
)
"""

TOTAL_EXPEDITIONS_METRIC_SQL = DAILY_BASE_SQL + """
SELECT to_char(params.obs_day, 'YYYY-MM-DD') AS "日期",
       coalesce(curr.expedition_count, 0)::bigint AS "出征总量",
       round((curr.expedition_count - prev.expedition_count) / nullif(prev.expedition_count, 0) * 100, 2) AS "日环比",
       round((curr.expedition_count - week.expedition_count) / nullif(week.expedition_count, 0) * 100, 2) AS "周同比"
FROM params
LEFT JOIN daily curr ON curr.event_date = params.obs_day
LEFT JOIN daily prev ON prev.event_date = params.obs_day - 1
LEFT JOIN daily week ON week.event_date = params.obs_day - 7
"""

TOTAL_TROOPS_METRIC_SQL = DAILY_BASE_SQL + """
SELECT to_char(params.obs_day, 'YYYY-MM-DD') AS "日期",
       round(coalesce(curr.troops_sent, 0) / 10000.0, 2) AS "出征士兵总量",
       round((curr.troops_sent - prev.troops_sent) / nullif(prev.troops_sent, 0) * 100, 2) AS "日环比",
       round((curr.troops_sent - week.troops_sent) / nullif(week.troops_sent, 0) * 100, 2) AS "周同比"
FROM params
LEFT JOIN daily curr ON curr.event_date = params.obs_day
LEFT JOIN daily prev ON prev.event_date = params.obs_day - 1
LEFT JOIN daily week ON week.event_date = params.obs_day - 7
"""

AVG_POWER_METRIC_SQL = DAILY_BASE_SQL + """
SELECT to_char(params.obs_day, 'YYYY-MM-DD') AS "日期",
       round(coalesce(curr.avg_power, 0), 2) AS "出征平均战斗力",
       round((curr.avg_power - prev.avg_power) / nullif(prev.avg_power, 0) * 100, 2) AS "日环比",
       round((curr.avg_power - week.avg_power) / nullif(week.avg_power, 0) * 100, 2) AS "周同比"
FROM params
LEFT JOIN daily curr ON curr.event_date = params.obs_day
LEFT JOIN daily prev ON prev.event_date = params.obs_day - 1
LEFT JOIN daily week ON week.event_date = params.obs_day - 7
"""

AVG_DURATION_METRIC_SQL = DAILY_BASE_SQL + """
SELECT to_char(params.obs_day, 'YYYY-MM-DD') AS "日期",
       round(coalesce(curr.avg_duration, 0), 2) AS "出征总耗时",
       round((curr.avg_duration - prev.avg_duration) / nullif(prev.avg_duration, 0) * 100, 2) AS "日环比",
       round((curr.avg_duration - week.avg_duration) / nullif(week.avg_duration, 0) * 100, 2) AS "周同比"
FROM params
LEFT JOIN daily curr ON curr.event_date = params.obs_day
LEFT JOIN daily prev ON prev.event_date = params.obs_day - 1
LEFT JOIN daily week ON week.event_date = params.obs_day - 7
"""

EXPEDITION_DETAIL_TABLE_SQL = f"""
WITH params AS (SELECT {OBS} AS obs_day),
days AS (
    SELECT generate_series(params.obs_day - 13, params.obs_day, interval '1 day')::date AS stat_date
    FROM params
),
daily_exp AS (
    SELECT event_date,
           count(*)::numeric AS expedition_count,
           count(DISTINCT player_id)::numeric AS expedition_players,
           avg(troops_sent)::numeric AS avg_troops,
           avg(team_power)::numeric AS avg_power,
           avg(duration_seconds)::numeric AS avg_duration,
           avg(CASE WHEN result = 'win' THEN 1 ELSE 0 END)::numeric * 100 AS win_rate,
           avg(troops_remaining)::numeric AS avg_remaining
    FROM public.fact_expeditions, params
    WHERE event_date BETWEEN params.obs_day - 13 AND params.obs_day
    GROUP BY event_date
),
active AS (
    SELECT s.session_start::date AS stat_date,
           count(DISTINCT s.player_id)::numeric AS active_players
    FROM public.fact_sessions s
    JOIN public.dim_player p ON p.player_id = s.player_id,
         params
    WHERE s.session_start::date BETWEEN params.obs_day - 13 AND params.obs_day
      AND p.current_level >= 4
    GROUP BY s.session_start::date
),
combined AS (
    SELECT d.stat_date,
           coalesce(e.expedition_count, 0) AS expedition_count,
           coalesce(e.expedition_players, 0) AS expedition_players,
           coalesce(a.active_players, 0) AS active_players,
           e.avg_troops,
           e.avg_power,
           e.avg_duration,
           e.win_rate,
           e.avg_remaining
    FROM days d
    LEFT JOIN daily_exp e ON e.event_date = d.stat_date
    LEFT JOIN active a ON a.stat_date = d.stat_date
),
stage AS (
    SELECT NULL::date AS stat_date,
           sum(expedition_count) AS expedition_count,
           sum(expedition_count) / nullif(sum(expedition_players), 0) AS avg_per_player,
           sum(expedition_players) / nullif(sum(active_players), 0) * 100 AS participation_rate,
           avg(avg_troops) AS avg_troops,
           avg(avg_power) AS avg_power,
           avg(avg_duration) AS avg_duration,
           avg(win_rate) AS win_rate,
           avg(avg_remaining) AS avg_remaining,
           0 AS sort_key
    FROM combined
),
daily AS (
    SELECT stat_date,
           expedition_count,
           expedition_count / nullif(expedition_players, 0) AS avg_per_player,
           expedition_players / nullif(active_players, 0) * 100 AS participation_rate,
           avg_troops,
           avg_power,
           avg_duration,
           win_rate,
           avg_remaining,
           1 AS sort_key
    FROM combined
)
SELECT CASE WHEN stat_date IS NULL THEN '阶段汇总' ELSE {dashboard_day_label_sql('stat_date')} END AS "日期",
       expedition_count::bigint AS "出征总量",
       round(avg_per_player, 2) AS "人均出征数",
       round(participation_rate, 2)::text || '%' AS "出征参与率",
       round(avg_troops, 2) AS "平均出征士兵量",
       round(avg_power, 2) AS "平均队伍战斗力",
       round(avg_duration, 2) AS "平均出征耗时",
       round(win_rate, 2)::text || '%' AS "出征平均胜率",
       round(avg_remaining, 2) AS "平均剩余士兵量"
FROM (
    SELECT * FROM stage
    UNION ALL
    SELECT * FROM daily
) t
ORDER BY sort_key, stat_date DESC NULLS FIRST
"""

TROOP_PIVOT_TABLE_SQL = f"""
WITH base AS (
    SELECT troop_type,
           event_date,
           count(*)::numeric AS expedition_count,
           sum(troops_sent)::numeric AS troop_count,
           avg(troops_sent)::numeric AS avg_troops
    FROM public.fact_expeditions
    WHERE event_date BETWEEN {OBS_7_START} AND {OBS}
    GROUP BY troop_type, event_date
),
metrics AS (
    SELECT troop_type, '出征次数' AS metric_name, event_date, expedition_count AS metric_value, 1 AS metric_sort FROM base
    UNION ALL
    SELECT troop_type, '出征士兵数' AS metric_name, event_date, troop_count AS metric_value, 2 AS metric_sort FROM base
    UNION ALL
    SELECT troop_type, '平均每次出征士兵数' AS metric_name, event_date, avg_troops AS metric_value, 3 AS metric_sort FROM base
)
SELECT troop_type AS "出征士兵兵种",
       metric_name AS "指标",
       round(sum(metric_value), CASE WHEN metric_name LIKE '平均%' THEN 2 ELSE 0 END) AS "阶段汇总",
       round(sum(metric_value) FILTER (WHERE event_date = DATE '2026-06-20'), CASE WHEN metric_name LIKE '平均%' THEN 2 ELSE 0 END) AS "2026-06-20(六)",
       round(sum(metric_value) FILTER (WHERE event_date = DATE '2026-06-21'), CASE WHEN metric_name LIKE '平均%' THEN 2 ELSE 0 END) AS "2026-06-21(日)",
       round(sum(metric_value) FILTER (WHERE event_date = DATE '2026-06-22'), CASE WHEN metric_name LIKE '平均%' THEN 2 ELSE 0 END) AS "2026-06-22(一)",
       round(sum(metric_value) FILTER (WHERE event_date = DATE '2026-06-23'), CASE WHEN metric_name LIKE '平均%' THEN 2 ELSE 0 END) AS "2026-06-23(二)",
       round(sum(metric_value) FILTER (WHERE event_date = DATE '2026-06-24'), CASE WHEN metric_name LIKE '平均%' THEN 2 ELSE 0 END) AS "2026-06-24(三)",
       round(sum(metric_value) FILTER (WHERE event_date = DATE '2026-06-25'), CASE WHEN metric_name LIKE '平均%' THEN 2 ELSE 0 END) AS "2026-06-25(四)",
       round(sum(metric_value) FILTER (WHERE event_date = DATE '2026-06-26'), CASE WHEN metric_name LIKE '平均%' THEN 2 ELSE 0 END) AS "2026-06-26(五)"
FROM metrics
GROUP BY troop_type, metric_name, metric_sort
ORDER BY CASE troop_type
             WHEN '轻步兵' THEN 1 WHEN '轻弓兵' THEN 2 WHEN '重步兵' THEN 3
             WHEN '重弓兵' THEN 4 WHEN '轻骑兵' THEN 5 WHEN '重骑兵' THEN 6
             WHEN '枪兵' THEN 7 WHEN '弩车' THEN 8 WHEN '投石车' THEN 9 ELSE 99
         END,
         metric_sort
"""

HERO_DISTRIBUTION_TABLE_SQL = f"""
SELECT hero_id AS "将领ID",
       count(*) AS "出征次数"
FROM public.fact_expeditions
WHERE event_date BETWEEN {OBS_30_START} AND {OBS}
GROUP BY hero_id
ORDER BY "出征次数" DESC, hero_id
LIMIT 50
"""

LEVEL_WIN_RATE_SQL = f"""
SELECT city_level::text AS "等级",
       round(avg(CASE WHEN result = 'win' THEN 1 ELSE 0 END)::numeric * 100, 2) AS "出征胜率"
FROM public.fact_expeditions
WHERE event_date BETWEEN {OBS_30_START} AND {OBS}
  AND city_level BETWEEN 1 AND 9
GROUP BY city_level
ORDER BY city_level
"""

HERO_WIN_RATE_TABLE_SQL = f"""
SELECT hero_id AS "将领ID",
       round(avg(CASE WHEN result = 'win' THEN 1 ELSE 0 END)::numeric * 100, 2)::text || '%' AS "各将领出征胜率"
FROM public.fact_expeditions
WHERE event_date BETWEEN {OBS_30_START} AND {OBS}
GROUP BY hero_id
HAVING count(*) >= 20
ORDER BY hero_id
LIMIT 60
"""

CITY_LEVEL_DRILL_TREND_SQL = f"""
SELECT event_date AS "日期",
       city_level::text AS "主城等级",
       count(*) AS "参与演习次数"
FROM public.fact_expeditions
WHERE event_date BETWEEN {OBS_30_START} AND {OBS}
  AND drill_type = '演习'
  AND city_level BETWEEN 1 AND 8
GROUP BY event_date, city_level
ORDER BY event_date, city_level
"""


CHARTS = [
    {
        "id": "2296000000000000001",
        "title": "出征总量",
        "type": "metric",
        "layout": (1, 1, 18, 8),
        "sql": TOTAL_EXPEDITIONS_METRIC_SQL,
        "x": [],
        "y": [axis("出征总量", axis_type="y"), axis("日环比", axis_type="y"), axis("周同比", axis_type="y")],
        "series": [],
    },
    {
        "id": "2296000000000000002",
        "title": "出征士兵总量",
        "type": "metric",
        "layout": (19, 1, 18, 8),
        "sql": TOTAL_TROOPS_METRIC_SQL,
        "x": [],
        "y": [axis("出征士兵总量", axis_type="y"), axis("日环比", axis_type="y"), axis("周同比", axis_type="y")],
        "series": [],
    },
    {
        "id": "2296000000000000003",
        "title": "出征平均战斗力",
        "type": "metric",
        "layout": (37, 1, 18, 8),
        "sql": AVG_POWER_METRIC_SQL,
        "x": [],
        "y": [axis("出征平均战斗力", axis_type="y"), axis("日环比", axis_type="y"), axis("周同比", axis_type="y")],
        "series": [],
    },
    {
        "id": "2296000000000000004",
        "title": "出征总耗时",
        "type": "metric",
        "layout": (55, 1, 18, 8),
        "sql": AVG_DURATION_METRIC_SQL,
        "x": [],
        "y": [axis("出征总耗时", axis_type="y"), axis("日环比", axis_type="y"), axis("周同比", axis_type="y")],
        "series": [],
    },
    {
        "id": "2296000000000000005",
        "title": "出征相关明细",
        "type": "table",
        "layout": (1, 9, 72, 22),
        "sql": EXPEDITION_DETAIL_TABLE_SQL,
        "x": [],
        "y": [],
        "series": [],
    },
    {
        "id": "2296000000000000006",
        "title": "过去7日各兵种出征情况",
        "type": "table",
        "layout": (1, 31, 72, 18),
        "sql": TROOP_PIVOT_TABLE_SQL,
        "x": [],
        "y": [],
        "series": [],
    },
    {
        "id": "2296000000000000007",
        "title": "各将领出征量分布",
        "type": "table",
        "layout": (1, 49, 36, 18),
        "sql": HERO_DISTRIBUTION_TABLE_SQL,
        "x": [],
        "y": [],
        "series": [],
    },
    {
        "id": "2296000000000000008",
        "title": "各等级出征胜率",
        "type": "column",
        "layout": (37, 49, 36, 18),
        "sql": LEVEL_WIN_RATE_SQL,
        "x": [axis("等级", axis_type="x")],
        "y": [axis("出征胜率", axis_type="y")],
        "series": [],
        "showLabel": True,
    },
    {
        "id": "2296000000000000009",
        "title": "各将领出征胜率",
        "type": "table",
        "layout": (1, 67, 36, 18),
        "sql": HERO_WIN_RATE_TABLE_SQL,
        "x": [],
        "y": [],
        "series": [],
    },
    {
        "id": "2296000000000000010",
        "title": "各主城等级参与演习次数",
        "type": "line",
        "layout": (37, 67, 36, 18),
        "sql": CITY_LEVEL_DRILL_TREND_SQL,
        "x": [axis("日期", axis_type="x")],
        "y": [axis("参与演习次数", axis_type="y")],
        "series": [axis("主城等级", axis_type="series")],
    },
]


def run_chart_sql(conn: Any, chart_info: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(chart_info["sql"])
        rows = cur.fetchall()
        fields = [desc.name for desc in cur.description]
    return fields, [normalize_row(dict(row)) for row in rows]


def build_dashboard_payload(bi_conn: Any, datasource_id: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
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
            "datasource": datasource_id,
            "data": {"fields": fields, "data": rows},
            "chart": chart_config,
            "sourceId": "",
            "status": "success",
            "message": "",
            "fields": fields,
        }
        print(f"{chart_info['title']}: rows={len(rows)} fields={fields}")

    return component_data, canvas_view_info


def resolve_dashboard_context(system_conn: Any) -> tuple[int, int, str]:
    with system_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id FROM public.sys_tenant WHERE name = %s LIMIT 1", (TENANT_NAME,))
        tenant = cur.fetchone()
        tenant_id = int(tenant["id"]) if tenant else FALLBACK_TENANT_ID

        cur.execute(
            """
            SELECT id
            FROM public.core_datasource
            WHERE name = %s AND tenant_id = %s
            ORDER BY id
            LIMIT 1
            """,
            (DATASOURCE_NAME, tenant_id),
        )
        datasource = cur.fetchone()
        datasource_id = int(datasource["id"]) if datasource else FALLBACK_DATASOURCE_ID

        cur.execute(
            """
            SELECT user_id
            FROM public.sys_tenant_user
            WHERE tenant_id = %s AND role = 'owner' AND status = 1
            ORDER BY is_primary DESC, id
            LIMIT 1
            """,
            (tenant_id,),
        )
        owner = cur.fetchone()
        update_by = str(owner["user_id"]) if owner else FALLBACK_UPDATE_BY

    return tenant_id, datasource_id, update_by


def backup_dashboard_row(row: dict[str, Any]) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"expedition_dashboard_{DASHBOARD_ID}_{int(time.time())}.json"
    backup_path.write_text(
        json.dumps(normalize_row(dict(row)), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return backup_path


def upsert_dashboard(
    system_conn: Any,
    tenant_id: int,
    datasource_id: int,
    update_by: str,
    component_data: list[dict[str, Any]],
    canvas_view_info: dict[str, Any],
) -> None:
    component_json = json.dumps(component_data, ensure_ascii=False, separators=(",", ":"))
    view_json = json.dumps(canvas_view_info, ensure_ascii=False, separators=(",", ":"))
    now = int(time.time())

    with system_conn:
        with system_conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM public.core_dashboard
                WHERE id = %s
                FOR UPDATE
                """,
                (DASHBOARD_ID,),
            )
            dashboard = cur.fetchone()
            if dashboard:
                backup_path = backup_dashboard_row(dict(dashboard))
                cur.execute(
                    """
                    UPDATE public.core_dashboard
                       SET tenant_id = %s,
                           name = %s,
                           pid = 'root',
                           datasource = %s,
                           org_id = '',
                           level = 1,
                           node_type = 'leaf',
                           type = 'dashboard',
                           canvas_style_data = '{}',
                           component_data = %s,
                           canvas_view_info = %s,
                           mobile_layout = 0,
                           status = 1,
                           self_watermark_status = 0,
                           is_default = 1,
                           update_time = %s,
                           update_by = %s,
                           source = NULL,
                           delete_flag = 0,
                           version = 3,
                           content_id = '0',
                           check_version = '1'
                     WHERE id = %s
                    """,
                    (
                        tenant_id,
                        DASHBOARD_NAME,
                        datasource_id,
                        component_json,
                        view_json,
                        now,
                        update_by,
                        DASHBOARD_ID,
                    ),
                )
                print(f"updated_dashboard rows={cur.rowcount} backup={backup_path}")
                return

            cur.execute(
                """
                SELECT coalesce(max(sort), 0) + 1 AS next_sort
                FROM public.core_dashboard
                WHERE tenant_id = %s AND datasource = %s AND pid = 'root' AND delete_flag = 0
                """,
                (tenant_id, datasource_id),
            )
            next_sort = int(cur.fetchone()["next_sort"])
            cur.execute(
                """
                INSERT INTO public.core_dashboard (
                    id, tenant_id, name, pid, datasource, org_id, level, node_type,
                    type, canvas_style_data, component_data, canvas_view_info,
                    mobile_layout, status, self_watermark_status, is_default, sort,
                    create_time, create_by, update_time, update_by, source,
                    delete_flag, version, content_id, check_version
                ) VALUES (
                    %s, %s, %s, 'root', %s, '', 1, 'leaf',
                    'dashboard', '{}', %s, %s,
                    0, 1, 0, 1, %s,
                    %s, %s, %s, %s, NULL,
                    0, 3, '0', '1'
                )
                """,
                (
                    DASHBOARD_ID,
                    tenant_id,
                    DASHBOARD_NAME,
                    datasource_id,
                    component_json,
                    view_json,
                    next_sort,
                    now,
                    update_by,
                    now,
                    update_by,
                ),
            )
            print(f"inserted_dashboard rows={cur.rowcount} sort={next_sort}")


def verify(system_conn: Any, bi_conn: Any, datasource_id: int) -> None:
    with bi_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT count(*) AS expedition_rows,
                   min(event_date) AS min_date,
                   max(event_date) AS max_date,
                   count(DISTINCT player_id) AS players,
                   count(DISTINCT hero_id) AS heroes,
                   count(DISTINCT troop_type) AS troop_types,
                   round(avg(troops_sent), 2) AS avg_troops,
                   round(avg(team_power), 2) AS avg_power
            FROM public.fact_expeditions
            WHERE expedition_uid LIKE 'exp_mock_%'
            """
        )
        print("verify_expeditions=" + json.dumps(normalize_row(dict(cur.fetchone())), ensure_ascii=False))
        cur.execute(
            """
            SELECT event_date,
                   count(*) AS expeditions,
                   count(DISTINCT player_id) AS players,
                   round(sum(troops_sent) / 10000.0, 2) AS troops_wan,
                   round(avg(team_power), 2) AS avg_power,
                   round(avg(duration_seconds), 2) AS avg_duration,
                   round(avg(CASE WHEN result = 'win' THEN 1 ELSE 0 END)::numeric * 100, 2) AS win_rate
            FROM public.fact_expeditions
            WHERE event_date BETWEEN DATE '2026-06-18' AND DATE '2026-06-26'
            GROUP BY event_date
            ORDER BY event_date
            """
        )
        print("verify_daily=")
        for row in cur.fetchall():
            print(json.dumps(normalize_row(dict(row)), ensure_ascii=False))

    with system_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT t.id AS table_id,
                   t.table_name,
                   t.checked,
                   count(f.id) FILTER (WHERE f.checked = true) AS checked_field_count,
                   count(f.id) AS field_count
            FROM public.core_table t
            LEFT JOIN public.core_field f ON f.table_id = t.id AND f.ds_id = t.ds_id
            WHERE t.ds_id = %s AND t.table_name = %s
            GROUP BY t.id, t.table_name, t.checked
            """,
            (datasource_id, EXPEDITION_TABLE_NAME),
        )
        metadata_row = cur.fetchone()
        print(
            "verify_metadata="
            + json.dumps(normalize_row(dict(metadata_row)) if metadata_row else None, ensure_ascii=False)
        )
        cur.execute(
            """
            SELECT id, tenant_id, name, datasource,
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
        tenant_id, datasource_id, update_by = resolve_dashboard_context(system_conn)
        print(
            json.dumps(
                {"tenant_id": tenant_id, "datasource_id": datasource_id, "update_by": update_by},
                ensure_ascii=False,
            )
        )
        seed_bi_data(bi_conn)
        sync_expedition_metadata(system_conn, bi_conn, datasource_id)
        component_data, canvas_view_info = build_dashboard_payload(bi_conn, datasource_id)
        upsert_dashboard(system_conn, tenant_id, datasource_id, update_by, component_data, canvas_view_info)
        verify(system_conn, bi_conn, datasource_id)
    finally:
        bi_conn.close()
        system_conn.close()


if __name__ == "__main__":
    main()
