"""Seed channel-attribution detail rows and create the SLG BI Mock channel dashboard.

Targets:
- BI tracking database: 127.0.0.1:5432 / slg_bi_mock / postgres / 111111
- App system database: 127.0.0.1:15432 / zhishu_bi / root / Password123@pg

This follows the BI tracking strategy:
- dim_player rows model attributed registrations;
- fact_events rows model register / purchase tracking events;
- fact_sessions rows model channel-attributed active sessions;
- fact_payments rows model channel-attributed successful orders.

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

DASHBOARD_ID = "fca7da4b19794ede8369316021387c15"
DATASOURCE_ID = 1
UPDATE_BY = "7471612174524223488"
BACKUP_DIR = Path(".codex-runtime/backups")

START_DAY = date(2026, 5, 25)
END_DAY = date(2026, 6, 23)
PLAYER_ID_START = 950_000
SESSION_ID_START = 10_800_000

CHANNELS = [
    ("app store", "store", "ios", "iOS,app store", 52),
    ("华为应用商城", "store", "android", "huawei_store", 14),
    ("应用宝", "store", "android", "yingyongbao", 10),
    ("小米应用商城", "store", "android", "xiaomi_store", 8),
    ("Google Play", "store", "android", "google_play", 7),
    ("360手机助手", "store", "android", "qihu_360", 4),
    ("百度手机助手", "store", "android", "baidu_store", 3),
    ("豌豆荚", "store", "android", "wandoujia", 2),
]

PRODUCTS = [
    ("channel_mock_starter_pack", "渠道新手礼包", "starter", Decimal("6.00"), "once", 1, True, 44),
    ("channel_mock_monthly_card", "渠道月卡", "subscription", Decimal("30.00"), "monthly", 3, False, 24),
    ("channel_mock_growth_pack", "渠道成长礼包", "starter", Decimal("68.00"), "once", 6, False, 14),
    ("channel_mock_war_pack", "渠道战争礼包", "war", Decimal("128.00"), "weekly", 10, False, 10),
    ("channel_mock_whale_pack", "渠道高价值礼包", "event_pack", Decimal("648.00"), "event", 15, False, 8),
]


@dataclass(slots=True)
class Player:
    player_id: int
    account_id: str
    role_id: str
    device_id: str
    register_time: datetime
    install_date: date
    country: str
    language: str
    platform: str
    channel: str
    campaign: str
    bi_channel_name: str
    bi_channel_group: str
    device_tier: str
    device_model: str
    os_version: str
    server_id: int
    current_level: int
    current_vip_level: int
    current_power: int
    current_city_level: int


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


def target_new_users(day: date) -> int:
    base = 118 + ((day.toordinal() % 7) - 3) * 6
    if day.weekday() in {4, 5}:
        base += 52
    elif day.weekday() == 6:
        base += 24
    if day >= date(2026, 6, 20):
        base += 34
    return max(80, base)


def weighted_channel(rng: random.Random) -> tuple[str, str, str, str, int]:
    total = sum(item[4] for item in CHANNELS)
    roll = rng.randint(1, total)
    running = 0
    for item in CHANNELS:
        running += item[4]
        if roll <= running:
            return item
    return CHANNELS[-1]


def weighted_product(rng: random.Random) -> tuple:
    total = sum(item[7] for item in PRODUCTS)
    roll = rng.randint(1, total)
    running = 0
    for item in PRODUCTS:
        running += item[7]
        if roll <= running:
            return item
    return PRODUCTS[-1]


def ensure_channel_columns(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            ALTER TABLE public.dim_player
                ADD COLUMN IF NOT EXISTS registration_channel text,
                ADD COLUMN IF NOT EXISTS bi_channel_name text,
                ADD COLUMN IF NOT EXISTS bi_channel_group text
            """
        )
        cur.execute(
            """
            ALTER TABLE public.fact_sessions
                ADD COLUMN IF NOT EXISTS registration_channel text,
                ADD COLUMN IF NOT EXISTS active_lifecycle_segment text,
                ADD COLUMN IF NOT EXISTS bi_channel_name text,
                ADD COLUMN IF NOT EXISTS bi_channel_group text
            """
        )
        cur.execute(
            """
            ALTER TABLE public.fact_events
                ADD COLUMN IF NOT EXISTS bi_channel_name text,
                ADD COLUMN IF NOT EXISTS bi_channel_group text
            """
        )
        cur.execute(
            """
            ALTER TABLE public.fact_payments
                ADD COLUMN IF NOT EXISTS payment_source_channel text,
                ADD COLUMN IF NOT EXISTS payment_level_bucket integer,
                ADD COLUMN IF NOT EXISTS bi_channel_name text,
                ADD COLUMN IF NOT EXISTS bi_channel_group text
            """
        )
    conn.commit()


def seed_products(conn: Any) -> None:
    rows = [item[:7] for item in PRODUCTS]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO public.dim_product (
                product_id, product_name, product_type, price_usd, limit_type,
                unlock_level, is_first_pay_pack
            ) VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (product_id) DO UPDATE SET
                product_name = EXCLUDED.product_name,
                product_type = EXCLUDED.product_type,
                price_usd = EXCLUDED.price_usd,
                limit_type = EXCLUDED.limit_type,
                unlock_level = EXCLUDED.unlock_level,
                is_first_pay_pack = EXCLUDED.is_first_pay_pack
            """,
            rows,
        )
    conn.commit()


def build_players() -> list[Player]:
    rng = random.Random(20260630)
    countries = [
        ("CN", "zh-CN"),
        ("US", "en"),
        ("JP", "ja"),
        ("KR", "ko"),
        ("VN", "vi"),
        ("BR", "pt-BR"),
        ("DE", "de"),
    ]
    ios_models = ["iPhone 15 Pro", "iPhone 16", "iPhone 16 Pro", "iPhone 15"]
    android_models = ["HUAWEI Mate 70", "Xiaomi 15", "OPPO Find X8", "vivo X100", "Samsung S24"]
    players: list[Player] = []
    player_no = 0
    for day_offset in range((END_DAY - START_DAY).days + 1):
        current_day = START_DAY + timedelta(days=day_offset)
        for _ in range(target_new_users(current_day)):
            player_id = PLAYER_ID_START + player_no
            player_no += 1
            channel_name, channel_group, platform, raw_channel, _weight = weighted_channel(rng)
            country, language = rng.choice(countries)
            register_time = dt_at(current_day, rng.randint(8, 23), rng.randint(0, 59), rng.randint(0, 45))
            model_pool = ios_models if platform == "ios" else android_models
            os_version = f"iOS {rng.choice(['17.5', '18.0'])}" if platform == "ios" else f"Android {rng.choice(['13', '14', '15'])}"
            players.append(
                Player(
                    player_id=player_id,
                    account_id=f"channel_mock_acc_{player_id}",
                    role_id=f"channel_mock_role_{player_id}",
                    device_id=f"channel_mock_dev_{player_id}",
                    register_time=register_time,
                    install_date=current_day,
                    country=country,
                    language=language,
                    platform=platform,
                    channel=raw_channel,
                    campaign=f"channel_mock_{raw_channel.replace(',', '_')}_202606",
                    bi_channel_name=channel_name,
                    bi_channel_group=channel_group,
                    device_tier=rng.choice(["mid", "mid", "high"]),
                    device_model=rng.choice(model_pool),
                    os_version=os_version,
                    server_id=rng.choice([101, 102, 103, 104, 105, 106]),
                    current_level=rng.randint(2, 9),
                    current_vip_level=0,
                    current_power=rng.randint(900, 4200),
                    current_city_level=rng.randint(1, 4),
                )
            )
    return players


def upsert_players(conn: Any, players: list[Player]) -> None:
    rows = [
        (
            p.player_id,
            p.account_id,
            p.role_id,
            p.device_id,
            p.register_time,
            p.install_date,
            p.country,
            p.language,
            p.platform,
            p.channel,
            p.campaign,
            p.device_tier,
            p.device_model,
            p.os_version,
            p.server_id,
            "casual",
            "non_spender",
            p.current_level,
            p.current_vip_level,
            p.current_power,
            p.current_city_level,
            None,
            None,
            Decimal("0.00"),
            p.install_date,
            p.bi_channel_name,
            p.bi_channel_name,
            p.bi_channel_group,
        )
        for p in players
    ]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO public.dim_player (
                player_id, account_id, role_id, device_id, register_time, install_date,
                country, language, platform, channel, campaign, device_tier, device_model,
                os_version, register_server_id, activity_segment, payer_segment, current_level,
                current_vip_level, current_power, current_city_level, current_alliance_id,
                first_pay_time, total_pay_amount, last_active_date, registration_channel,
                bi_channel_name, bi_channel_group
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (player_id) DO UPDATE SET
                account_id = EXCLUDED.account_id,
                role_id = EXCLUDED.role_id,
                device_id = EXCLUDED.device_id,
                register_time = EXCLUDED.register_time,
                install_date = EXCLUDED.install_date,
                country = EXCLUDED.country,
                language = EXCLUDED.language,
                platform = EXCLUDED.platform,
                channel = EXCLUDED.channel,
                campaign = EXCLUDED.campaign,
                device_tier = EXCLUDED.device_tier,
                device_model = EXCLUDED.device_model,
                os_version = EXCLUDED.os_version,
                register_server_id = EXCLUDED.register_server_id,
                activity_segment = EXCLUDED.activity_segment,
                payer_segment = EXCLUDED.payer_segment,
                current_level = EXCLUDED.current_level,
                current_vip_level = EXCLUDED.current_vip_level,
                current_power = EXCLUDED.current_power,
                current_city_level = EXCLUDED.current_city_level,
                current_alliance_id = EXCLUDED.current_alliance_id,
                first_pay_time = EXCLUDED.first_pay_time,
                total_pay_amount = EXCLUDED.total_pay_amount,
                last_active_date = EXCLUDED.last_active_date,
                registration_channel = EXCLUDED.registration_channel,
                bi_channel_name = EXCLUDED.bi_channel_name,
                bi_channel_group = EXCLUDED.bi_channel_group
            """,
            rows,
        )
    conn.commit()
    print(f"upserted channel players={len(players)}")


def build_session_row(session_id: int, player: Player, start_at: datetime) -> tuple:
    current_day = start_at.date()
    lifecycle = lifecycle_day(player, current_day)
    end_at = min(start_at + timedelta(minutes=28), dt_at(current_day, 23, 59, 30))
    return (
        session_id,
        f"channel_mock_sess_{session_id}",
        player.player_id,
        player.account_id,
        player.role_id,
        player.device_id,
        player.server_id,
        start_at,
        end_at,
        max(60, int((end_at - start_at).total_seconds())),
        lifecycle,
        max(1, player.current_level - 1),
        player.current_level,
        max(500, player.current_power - 180),
        player.current_power,
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
        player.bi_channel_name,
        lifecycle_segment(lifecycle),
        player.bi_channel_name,
        player.bi_channel_group,
    )


def build_event_row(
    event_uid: str,
    player: Player,
    session_id: int,
    event_time: datetime,
    event_name: str,
    event_category: str,
    sequence: int,
    attributes: dict[str, Any],
    source: str,
) -> tuple:
    current_day = event_time.date()
    return (
        event_uid,
        f"channel_mock_cli_{event_uid}",
        f"channel_mock_trace_{session_id}_{sequence}",
        event_time,
        event_time,
        event_time + timedelta(milliseconds=320),
        event_time + timedelta(seconds=1),
        current_day,
        player.player_id,
        player.account_id,
        player.role_id,
        player.device_id,
        player.server_id,
        session_id,
        event_name,
        event_category,
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
        source,
        sequence,
        json.dumps(attributes, ensure_ascii=False),
        player.bi_channel_name,
        player.bi_channel_group,
    )


def build_detail_rows(players: list[Player]) -> tuple[list[tuple], list[tuple], list[tuple], list[tuple]]:
    rng = random.Random(20260701)
    session_rows: list[tuple] = []
    event_rows: list[tuple] = []
    payment_rows: list[tuple] = []
    player_updates: list[tuple] = []
    session_id = SESSION_ID_START
    order_no = 1

    for player in players:
        d0_start = player.register_time + timedelta(minutes=rng.randint(1, 8))
        d0_session_id = session_id
        session_id += 1
        session_rows.append(build_session_row(d0_session_id, player, d0_start))
        event_rows.append(
            build_event_row(
                f"channel_mock_register_evt_{player.player_id}",
                player,
                d0_session_id,
                player.register_time,
                "register",
                "account",
                1,
                {"bi_channel_name": player.bi_channel_name, "bi_channel_group": player.bi_channel_group},
                "server",
            )
        )

        last_active_date = player.install_date
        for retain_day, probability in [(1, 0.252), (2, 0.062), (3, 0.026), (4, 0.019), (5, 0.015), (6, 0.013), (7, 0.011)]:
            active_day = player.install_date + timedelta(days=retain_day)
            if active_day > END_DAY:
                continue
            if rng.random() < probability:
                start_at = dt_at(active_day, rng.randint(9, 23), rng.randint(0, 59), rng.randint(0, 45))
                session_rows.append(build_session_row(session_id, player, start_at))
                session_id += 1
                last_active_date = active_day

        paid = rng.random() < (0.19 if player.bi_channel_name == "app store" else 0.13)
        first_pay_time: datetime | None = None
        pay_amount = Decimal("0.00")
        if paid:
            payment_count = 1 + (1 if rng.random() < 0.28 else 0) + (1 if rng.random() < 0.08 else 0)
            for pay_index in range(payment_count):
                pay_day = min(END_DAY, player.install_date + timedelta(days=rng.randint(0, min(29, (END_DAY - player.install_date).days))))
                pay_time = dt_at(pay_day, rng.randint(10, 23), rng.randint(0, 59), rng.randint(0, 45))
                pay_session_id = session_id
                session_id += 1
                session_rows.append(build_session_row(pay_session_id, player, pay_time - timedelta(minutes=3)))
                product_id, product_name, _product_type, price_usd, _limit_type, _unlock_level, _first_pay_pack, _weight = weighted_product(rng)
                multiplier = Decimal(str(rng.choice([1, 1, 1, 2])))
                amount = (price_usd * multiplier).quantize(Decimal("0.01"))
                order_id = f"CHANMOCK{order_no:08d}"
                start_uid = f"channel_mock_pay_start_evt_{order_no:08d}"
                final_uid = f"channel_mock_pay_success_evt_{order_no:08d}"
                is_first_pay = pay_index == 0
                event_rows.append(
                    build_event_row(
                        start_uid,
                        player,
                        pay_session_id,
                        pay_time,
                        "purchase_start",
                        "monetization",
                        1,
                        {"order_id": order_id, "product_id": product_id, "price_usd": str(amount)},
                        "client",
                    )
                )
                event_rows.append(
                    build_event_row(
                        final_uid,
                        player,
                        pay_session_id,
                        pay_time + timedelta(seconds=5),
                        "purchase_success",
                        "monetization",
                        2,
                        {"order_id": order_id, "product_id": product_id, "amount_usd": str(amount), "is_first_pay": is_first_pay},
                        "server",
                    )
                )
                payment_rows.append(
                    (
                        order_id,
                        start_uid,
                        final_uid,
                        pay_time + timedelta(seconds=5),
                        pay_day,
                        player.player_id,
                        player.server_id,
                        pay_session_id,
                        product_id,
                        product_name,
                        amount,
                        amount,
                        Decimal("0.00"),
                        amount,
                        "CNY",
                        "app_store" if player.platform == "ios" else "android_store",
                        "success",
                        None,
                        None,
                        is_first_pay,
                        pay_index + 1,
                        lifecycle_day(player, pay_day),
                        max(player.current_vip_level, 1),
                        player.current_level,
                        "whale" if amount >= Decimal("328") else ("mid" if amount >= Decimal("68") else "low"),
                        json.dumps({"source": "channel_mock_seed", "bi_channel_name": player.bi_channel_name}, ensure_ascii=False),
                        player.bi_channel_name,
                        min(max(player.current_level, 1), 9),
                        player.bi_channel_name,
                        player.bi_channel_group,
                    )
                )
                pay_amount += amount
                if first_pay_time is None:
                    first_pay_time = pay_time + timedelta(seconds=5)
                order_no += 1

        player_updates.append((first_pay_time, pay_amount, last_active_date, pay_amount, pay_amount, player.player_id))

    return session_rows, event_rows, payment_rows, player_updates


def upsert_detail_rows(
    conn: Any,
    session_rows: list[tuple],
    event_rows: list[tuple],
    payment_rows: list[tuple],
    player_updates: list[tuple],
) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO public.fact_sessions (
                session_id, session_uid, player_id, account_id, role_id, device_id, server_id,
                session_start, session_end, duration_seconds, lifecycle_day, player_level_start,
                player_level_end, power_start, power_end, platform, channel, campaign,
                client_version, app_build, sdk_version, device_tier, device_model, os_version,
                network_type, country, ip_country, registration_channel, active_lifecycle_segment,
                bi_channel_name, bi_channel_group
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
                active_lifecycle_segment = EXCLUDED.active_lifecycle_segment,
                bi_channel_name = EXCLUDED.bi_channel_name,
                bi_channel_group = EXCLUDED.bi_channel_group
            """,
            session_rows,
        )
        cur.executemany(
            """
            INSERT INTO public.fact_events (
                event_uid, client_event_id, trace_id, event_time, client_time, server_receive_time, ingest_time,
                event_date, player_id, account_id, role_id, device_id, server_id, session_id, event_name,
                event_category, lifecycle_day, player_level, vip_level, power, alliance_id, client_version,
                app_build, sdk_version, event_schema_version, platform, channel, campaign, country, ip_country,
                language, device_model, os_version, device_tier, network_type, event_source,
                sequence_in_session, attributes, bi_channel_name, bi_channel_group
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
                bi_channel_name = EXCLUDED.bi_channel_name,
                bi_channel_group = EXCLUDED.bi_channel_group
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
                    is_first_pay, pay_sequence, lifecycle_day, vip_level_after, player_level, revenue_tier,
                    attributes, payment_source_channel, payment_level_bucket, bi_channel_name, bi_channel_group
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (order_id) DO UPDATE SET
                    start_event_uid = EXCLUDED.start_event_uid,
                    final_event_uid = EXCLUDED.final_event_uid,
                    event_time = EXCLUDED.event_time,
                    event_date = EXCLUDED.event_date,
                    player_id = EXCLUDED.player_id,
                    server_id = EXCLUDED.server_id,
                    session_id = EXCLUDED.session_id,
                    product_id = EXCLUDED.product_id,
                    product_name = EXCLUDED.product_name,
                    amount_usd = EXCLUDED.amount_usd,
                    gross_revenue_usd = EXCLUDED.gross_revenue_usd,
                    refund_amount_usd = EXCLUDED.refund_amount_usd,
                    net_revenue_usd = EXCLUDED.net_revenue_usd,
                    local_currency = EXCLUDED.local_currency,
                    payment_channel = EXCLUDED.payment_channel,
                    payment_status = EXCLUDED.payment_status,
                    fail_reason = EXCLUDED.fail_reason,
                    refund_reason = EXCLUDED.refund_reason,
                    is_first_pay = EXCLUDED.is_first_pay,
                    pay_sequence = EXCLUDED.pay_sequence,
                    lifecycle_day = EXCLUDED.lifecycle_day,
                    vip_level_after = EXCLUDED.vip_level_after,
                    player_level = EXCLUDED.player_level,
                    revenue_tier = EXCLUDED.revenue_tier,
                    attributes = EXCLUDED.attributes,
                    payment_source_channel = EXCLUDED.payment_source_channel,
                    payment_level_bucket = EXCLUDED.payment_level_bucket,
                    bi_channel_name = EXCLUDED.bi_channel_name,
                    bi_channel_group = EXCLUDED.bi_channel_group
                """,
                payment_rows,
            )
        cur.executemany(
            """
            UPDATE public.dim_player
               SET first_pay_time = %s,
                   total_pay_amount = %s,
                   last_active_date = %s,
                   payer_segment = CASE WHEN %s > 0 THEN 'payer' ELSE 'non_spender' END,
                   current_vip_level = CASE WHEN %s > 0 THEN 1 ELSE current_vip_level END
             WHERE player_id = %s
            """,
            player_updates,
        )
    conn.commit()
    print(f"upserted channel sessions={len(session_rows)} events={len(event_rows)} payments={len(payment_rows)}")


CHANNEL_LIST_SQL = """
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
) AS t(channel_name, sort_no)
"""

NEW_USERS_BY_CHANNEL_SQL = f"""
WITH obs AS (
    SELECT max(install_date) AS max_date FROM public.dim_player
), days AS (
    SELECT generate_series(max_date - 6, max_date, interval '1 day')::date AS dt FROM obs
), channels AS ({CHANNEL_LIST_SQL}), daily AS (
    SELECT p.install_date AS dt,
           coalesce(p.bi_channel_name, p.registration_channel, p.channel) AS channel_name,
           count(*) AS new_users
    FROM public.dim_player p, obs
    WHERE p.install_date BETWEEN obs.max_date - 6 AND obs.max_date
    GROUP BY p.install_date, coalesce(p.bi_channel_name, p.registration_channel, p.channel)
)
SELECT d.dt AS "日期",
       c.channel_name AS "渠道",
       coalesce(daily.new_users, 0) AS "新增用户数"
FROM days d
CROSS JOIN channels c
LEFT JOIN daily ON daily.dt = d.dt AND daily.channel_name = c.channel_name
ORDER BY d.dt, c.sort_no
"""

ACTIVE_BY_CHANNEL_SQL = f"""
WITH obs AS (
    SELECT max(install_date) AS max_date FROM public.dim_player
), days AS (
    SELECT generate_series(max_date - 29, max_date, interval '1 day')::date AS dt FROM obs
), channels AS ({CHANNEL_LIST_SQL}), daily AS (
    SELECT s.session_start::date AS dt,
           coalesce(s.bi_channel_name, s.registration_channel, p.bi_channel_name, p.registration_channel, p.channel) AS channel_name,
           count(DISTINCT s.player_id) AS active_users
    FROM public.fact_sessions s
    JOIN public.dim_player p ON p.player_id = s.player_id
    JOIN obs ON true
    WHERE s.session_start::date BETWEEN obs.max_date - 29 AND obs.max_date
    GROUP BY s.session_start::date, coalesce(s.bi_channel_name, s.registration_channel, p.bi_channel_name, p.registration_channel, p.channel)
)
SELECT d.dt AS "日期",
       c.channel_name AS "渠道",
       coalesce(daily.active_users, 0) AS "活跃用户数"
FROM days d
CROSS JOIN channels c
LEFT JOIN daily ON daily.dt = d.dt AND daily.channel_name = c.channel_name
ORDER BY d.dt, c.sort_no
"""

PAYER_BY_CHANNEL_SQL = f"""
WITH obs AS (
    SELECT max(install_date) AS max_date FROM public.dim_player
), days AS (
    SELECT generate_series(max_date - 29, max_date, interval '1 day')::date AS dt FROM obs
), channels AS ({CHANNEL_LIST_SQL}), daily AS (
    SELECT p.event_date AS dt,
           coalesce(p.bi_channel_name, p.payment_source_channel, dp.bi_channel_name, dp.registration_channel, dp.channel) AS channel_name,
           count(DISTINCT p.player_id) AS pay_users
    FROM public.fact_payments p
    JOIN public.dim_player dp ON dp.player_id = p.player_id
    JOIN obs ON true
    WHERE p.payment_status = 'success'
      AND p.net_revenue_usd > 0
      AND p.product_id <> 'rt_mock_realtime_pack'
      AND p.event_date BETWEEN obs.max_date - 29 AND obs.max_date
    GROUP BY p.event_date, coalesce(p.bi_channel_name, p.payment_source_channel, dp.bi_channel_name, dp.registration_channel, dp.channel)
)
SELECT d.dt AS "日期",
       c.channel_name AS "渠道",
       coalesce(daily.pay_users, 0) AS "付费用户数"
FROM days d
CROSS JOIN channels c
LEFT JOIN daily ON daily.dt = d.dt AND daily.channel_name = c.channel_name
ORDER BY d.dt, c.sort_no
"""

REVENUE_BY_CHANNEL_SQL = f"""
WITH obs AS (
    SELECT max(install_date) AS max_date FROM public.dim_player
), days AS (
    SELECT generate_series(max_date - 29, max_date, interval '1 day')::date AS dt FROM obs
), channels AS ({CHANNEL_LIST_SQL}), daily AS (
    SELECT p.event_date AS dt,
           coalesce(p.bi_channel_name, p.payment_source_channel, dp.bi_channel_name, dp.registration_channel, dp.channel) AS channel_name,
           round(sum(p.net_revenue_usd), 2) AS revenue
    FROM public.fact_payments p
    JOIN public.dim_player dp ON dp.player_id = p.player_id
    JOIN obs ON true
    WHERE p.payment_status = 'success'
      AND p.net_revenue_usd > 0
      AND p.product_id <> 'rt_mock_realtime_pack'
      AND p.event_date BETWEEN obs.max_date - 29 AND obs.max_date
    GROUP BY p.event_date, coalesce(p.bi_channel_name, p.payment_source_channel, dp.bi_channel_name, dp.registration_channel, dp.channel)
)
SELECT d.dt AS "日期",
       c.channel_name AS "渠道",
       coalesce(daily.revenue, 0) AS "付费金额"
FROM days d
CROSS JOIN channels c
LEFT JOIN daily ON daily.dt = d.dt AND daily.channel_name = c.channel_name
ORDER BY d.dt, c.sort_no
"""

RETENTION_BY_CHANNEL_SQL = f"""
WITH obs AS (
    SELECT max(install_date) AS max_date FROM public.dim_player
), channels AS ({CHANNEL_LIST_SQL}), cohort AS (
    SELECT p.install_date AS cohort_date,
           coalesce(p.bi_channel_name, p.registration_channel, p.channel) AS channel_name,
           p.player_id
    FROM public.dim_player p, obs
    WHERE p.install_date BETWEEN obs.max_date - 29 AND obs.max_date
), retained AS (
    SELECT c.cohort_date,
           c.channel_name,
           c.player_id,
           gs.day AS retain_day,
           EXISTS (
               SELECT 1
               FROM public.fact_sessions s
               WHERE s.player_id = c.player_id
                 AND s.session_start::date = c.cohort_date + gs.day
           ) AS retained
    FROM cohort c
    CROSS JOIN generate_series(0, 7) AS gs(day)
), daily AS (
    SELECT cohort_date,
           channel_name,
           count(DISTINCT player_id) AS users,
           count(DISTINCT player_id) FILTER (WHERE retain_day = 0 AND retained) AS d0,
           count(DISTINCT player_id) FILTER (WHERE retain_day = 1 AND retained) AS d1,
           count(DISTINCT player_id) FILTER (WHERE retain_day = 2 AND retained) AS d2,
           count(DISTINCT player_id) FILTER (WHERE retain_day = 3 AND retained) AS d3,
           count(DISTINCT player_id) FILTER (WHERE retain_day = 4 AND retained) AS d4,
           count(DISTINCT player_id) FILTER (WHERE retain_day = 5 AND retained) AS d5,
           count(DISTINCT player_id) FILTER (WHERE retain_day = 6 AND retained) AS d6,
           count(DISTINCT player_id) FILTER (WHERE retain_day = 7 AND retained) AS d7
    FROM retained
    GROUP BY cohort_date, channel_name
)
SELECT d.cohort_date AS "日期",
       d.channel_name AS "渠道",
       d.users AS "用户注册用户数",
       d.d0::text || chr(10) || round(d.d0::numeric / nullif(d.users, 0) * 100, 2)::text || '%' AS "当日",
       CASE WHEN d.cohort_date + 1 <= (SELECT max_date FROM obs) THEN d.d1::text || chr(10) || round(d.d1::numeric / nullif(d.users, 0) * 100, 2)::text || '%' ELSE '-' END AS "第1日",
       CASE WHEN d.cohort_date + 2 <= (SELECT max_date FROM obs) THEN d.d2::text || chr(10) || round(d.d2::numeric / nullif(d.users, 0) * 100, 2)::text || '%' ELSE '-' END AS "第2日",
       CASE WHEN d.cohort_date + 3 <= (SELECT max_date FROM obs) THEN d.d3::text || chr(10) || round(d.d3::numeric / nullif(d.users, 0) * 100, 2)::text || '%' ELSE '-' END AS "第3日",
       CASE WHEN d.cohort_date + 4 <= (SELECT max_date FROM obs) THEN d.d4::text || chr(10) || round(d.d4::numeric / nullif(d.users, 0) * 100, 2)::text || '%' ELSE '-' END AS "第4日",
       CASE WHEN d.cohort_date + 5 <= (SELECT max_date FROM obs) THEN d.d5::text || chr(10) || round(d.d5::numeric / nullif(d.users, 0) * 100, 2)::text || '%' ELSE '-' END AS "第5日",
       CASE WHEN d.cohort_date + 6 <= (SELECT max_date FROM obs) THEN d.d6::text || chr(10) || round(d.d6::numeric / nullif(d.users, 0) * 100, 2)::text || '%' ELSE '-' END AS "第6日",
       CASE WHEN d.cohort_date + 7 <= (SELECT max_date FROM obs) THEN d.d7::text || chr(10) || round(d.d7::numeric / nullif(d.users, 0) * 100, 2)::text || '%' ELSE '-' END AS "第7日"
FROM daily d
JOIN channels c ON c.channel_name = d.channel_name
ORDER BY d.cohort_date, c.sort_no
"""

WEEKLY_CUMULATIVE_PAY_SQL = f"""
WITH obs AS (
    SELECT max(install_date) AS max_date FROM public.dim_player
), channels AS ({CHANNEL_LIST_SQL}), weeks AS (
    SELECT generate_series(
        date_trunc('week', obs.max_date - 29)::date,
        date_trunc('week', obs.max_date)::date,
        interval '1 week'
    )::date AS week_start,
    obs.max_date
    FROM obs
), player_week AS (
    SELECT w.week_start,
           coalesce(p.bi_channel_name, p.payment_source_channel, dp.bi_channel_name, dp.registration_channel, dp.channel) AS channel_name,
           p.player_id,
           sum(p.net_revenue_usd) AS weekly_amount
    FROM weeks w
    JOIN public.fact_payments p
      ON p.event_date BETWEEN w.week_start AND least(w.week_start + 6, w.max_date)
    JOIN public.dim_player dp ON dp.player_id = p.player_id
    WHERE p.payment_status = 'success'
      AND p.net_revenue_usd > 0
      AND p.product_id <> 'rt_mock_realtime_pack'
    GROUP BY w.week_start, coalesce(p.bi_channel_name, p.payment_source_channel, dp.bi_channel_name, dp.registration_channel, dp.channel), p.player_id
), summary AS (
    SELECT week_start,
           channel_name,
           count(*) AS all_users,
           count(*) FILTER (WHERE weekly_amount < 500) AS b1,
           count(*) FILTER (WHERE weekly_amount >= 500 AND weekly_amount < 1000) AS b2,
           count(*) FILTER (WHERE weekly_amount >= 1000 AND weekly_amount < 1500) AS b3,
           count(*) FILTER (WHERE weekly_amount >= 1500 AND weekly_amount < 2000) AS b4,
           count(*) FILTER (WHERE weekly_amount >= 2000 AND weekly_amount < 2500) AS b5,
           count(*) FILTER (WHERE weekly_amount >= 2500 AND weekly_amount < 3000) AS b6,
           count(*) FILTER (WHERE weekly_amount >= 3000) AS b7
    FROM player_week
    GROUP BY week_start, channel_name
)
SELECT to_char(s.week_start, 'YYYY-MM-DD') || '当周' AS "事件发生时间",
       s.channel_name AS "渠道",
       s.all_users AS "全部用户",
       s.b1::text || chr(10) || round(s.b1::numeric / nullif(s.all_users, 0) * 100, 2)::text || '%' AS "(-∞, 500)",
       s.b2::text || chr(10) || round(s.b2::numeric / nullif(s.all_users, 0) * 100, 2)::text || '%' AS "[500, 1000)",
       s.b3::text || chr(10) || round(s.b3::numeric / nullif(s.all_users, 0) * 100, 2)::text || '%' AS "[1000, 1500)",
       s.b4::text || chr(10) || round(s.b4::numeric / nullif(s.all_users, 0) * 100, 2)::text || '%' AS "[1500, 2000)",
       s.b5::text || chr(10) || round(s.b5::numeric / nullif(s.all_users, 0) * 100, 2)::text || '%' AS "[2000, 2500)",
       s.b6::text || chr(10) || round(s.b6::numeric / nullif(s.all_users, 0) * 100, 2)::text || '%' AS "[2500, 3000)",
       s.b7::text || chr(10) || round(s.b7::numeric / nullif(s.all_users, 0) * 100, 2)::text || '%' AS "[3000, +∞)"
FROM summary s
JOIN channels c ON c.channel_name = s.channel_name
ORDER BY s.week_start, c.sort_no
"""


CHARTS = [
    {
        "id": "2194000000000000001",
        "title": "新增用户数（按渠道）",
        "type": "line",
        "layout": (1, 1, 36, 16),
        "sql": NEW_USERS_BY_CHANNEL_SQL,
        "x": [axis("日期", axis_type="x")],
        "y": [axis("新增用户数", axis_type="y")],
        "series": [axis("渠道", axis_type="series")],
    },
    {
        "id": "2194000000000000002",
        "title": "活跃用户数（按渠道）",
        "type": "line",
        "layout": (37, 1, 36, 16),
        "sql": ACTIVE_BY_CHANNEL_SQL,
        "x": [axis("日期", axis_type="x")],
        "y": [axis("活跃用户数", axis_type="y")],
        "series": [axis("渠道", axis_type="series")],
    },
    {
        "id": "2194000000000000003",
        "title": "付费用户数（按渠道）",
        "type": "line",
        "layout": (1, 17, 36, 16),
        "sql": PAYER_BY_CHANNEL_SQL,
        "x": [axis("日期", axis_type="x")],
        "y": [axis("付费用户数", axis_type="y")],
        "series": [axis("渠道", axis_type="series")],
    },
    {
        "id": "2194000000000000004",
        "title": "付费金额（按渠道）",
        "type": "line",
        "layout": (37, 17, 36, 16),
        "sql": REVENUE_BY_CHANNEL_SQL,
        "x": [axis("日期", axis_type="x")],
        "y": [axis("付费金额", axis_type="y")],
        "series": [axis("渠道", axis_type="series")],
    },
    {
        "id": "2194000000000000005",
        "title": "各渠道新增留存",
        "type": "table",
        "layout": (1, 33, 72, 18),
        "sql": RETENTION_BY_CHANNEL_SQL,
        "x": [],
        "y": [],
        "series": [],
    },
    {
        "id": "2194000000000000006",
        "title": "各渠道充值用户周累充分布",
        "type": "table",
        "layout": (1, 51, 72, 18),
        "sql": WEEKLY_CUMULATIVE_PAY_SQL,
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
    backup_path = BACKUP_DIR / f"channel_dashboard_{DASHBOARD_ID}_{int(time.time())}.json"
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
                raise RuntimeError(f"Channel dashboard does not exist: {DASHBOARD_ID}")
            if dashboard["datasource"] != DATASOURCE_ID:
                raise RuntimeError(f"Channel dashboard datasource={dashboard['datasource']}, expected {DATASOURCE_ID}")

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
            SELECT count(*) FILTER (WHERE account_id LIKE 'channel_mock_acc_%') AS channel_players,
                   min(install_date) FILTER (WHERE account_id LIKE 'channel_mock_acc_%') AS min_install,
                   max(install_date) FILTER (WHERE account_id LIKE 'channel_mock_acc_%') AS max_install
            FROM public.dim_player
            """
        )
        print("verify_players=" + json.dumps(normalize_row(dict(cur.fetchone())), ensure_ascii=False))
        cur.execute(
            """
            SELECT count(*) FILTER (WHERE session_uid LIKE 'channel_mock_%') AS channel_sessions
            FROM public.fact_sessions
            """
        )
        print("verify_sessions=" + json.dumps(normalize_row(dict(cur.fetchone())), ensure_ascii=False))
        cur.execute(
            """
            SELECT count(*) FILTER (WHERE order_id LIKE 'CHANMOCK%') AS channel_payments,
                   round(sum(net_revenue_usd) FILTER (WHERE order_id LIKE 'CHANMOCK%'), 2) AS revenue
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
    ensure_channel_columns(conn)
    seed_products(conn)
    players = build_players()
    upsert_players(conn, players)
    session_rows, event_rows, payment_rows, player_updates = build_detail_rows(players)
    upsert_detail_rows(conn, session_rows, event_rows, payment_rows, player_updates)
    ensure_channel_columns(conn)


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
