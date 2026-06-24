"""Seed new-user mock detail rows and create the SLG BI Mock new-user dashboard.

Targets:
- BI tracking database: 127.0.0.1:5432 / slg_bi_mock / postgres / 111111
- App system database: 127.0.0.1:15432 / zhishu_bi / root / Password123@pg

The dataset stays at tracking/detail level. New-user, channel, OS, retention,
and first-day payment metrics are computed from dim_player, fact_sessions,
fact_events, and fact_payments at query time. No aggregate tables, snapshots,
or analysis views are created.
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

DASHBOARD_ID = "2a25f4f6690d490f8efc2280d2cc2a51"
DATASOURCE_ID = 1
UPDATE_BY = "7471612174524223488"
BACKUP_DIR = Path(".codex-runtime/backups")

NEW_PLAYER_ID_START = 930_000
NEW_SESSION_ID_START = 9_700_000
NEW_USER_DAYS = [
    (date(2026, 6, 22), 170),
    (date(2026, 6, 23), 180),
]

CHANNEL_WEIGHTS = [
    ("app store", 52),
    ("华为应用商城", 14),
    ("应用宝", 10),
    ("小米应用商城", 8),
    ("Google Play", 7),
    ("360手机助手", 4),
    ("百度手机助手", 3),
    ("豌豆荚", 2),
]

CHANNEL_SOURCE = {
    "app store": ("ios", "iOS,app store"),
    "华为应用商城": ("android", "huawei_store"),
    "应用宝": ("android", "yingyongbao"),
    "小米应用商城": ("android", "xiaomi_store"),
    "Google Play": ("android", "google_play"),
    "360手机助手": ("android", "qihu_360"),
    "百度手机助手": ("android", "baidu_store"),
    "豌豆荚": ("android", "wandoujia"),
}

PRODUCT = (
    "new_mock_first_pay_pack",
    "新增首日礼包",
    "starter",
    Decimal("6.00"),
    "once",
    1,
    True,
)


@dataclass(slots=True)
class NewPlayer:
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
    registration_channel: str
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


def weighted_choice(rng: random.Random) -> str:
    total = sum(weight for _, weight in CHANNEL_WEIGHTS)
    roll = rng.randint(1, total)
    running = 0
    for channel, weight in CHANNEL_WEIGHTS:
        running += weight
        if roll <= running:
            return channel
    return CHANNEL_WEIGHTS[-1][0]


def dt_at(day: date, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime.combine(day, dt_time(hour, minute, second), TZ)


def lifecycle_day(player: NewPlayer, current_day: date) -> int:
    return max(0, (current_day - player.install_date).days)


def ensure_registration_channel(conn: Any) -> None:
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
    conn.commit()


def cleanup(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM public.fact_payments WHERE order_id LIKE 'NEWMOCK%'")
        cur.execute("DELETE FROM public.fact_events WHERE event_uid LIKE 'new_mock_%'")
        cur.execute(
            """
            UPDATE public.dim_player
               SET first_pay_time = NULL,
                   total_pay_amount = 0,
                   last_active_date = install_date
             WHERE player_id >= %s
               AND player_id < %s
               AND account_id LIKE 'new_mock_acc_%%'
            """,
            (NEW_PLAYER_ID_START, NEW_PLAYER_ID_START + 1000),
        )
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
                product_name = EXCLUDED.product_name,
                product_type = EXCLUDED.product_type,
                price_usd = EXCLUDED.price_usd,
                limit_type = EXCLUDED.limit_type,
                unlock_level = EXCLUDED.unlock_level,
                is_first_pay_pack = EXCLUDED.is_first_pay_pack
            """,
            PRODUCT,
        )
    conn.commit()


def build_players() -> list[NewPlayer]:
    rng = random.Random(20260624)
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
    players: list[NewPlayer] = []
    player_no = 0

    for current_day, count in NEW_USER_DAYS:
        for _ in range(count):
            player_id = NEW_PLAYER_ID_START + player_no
            player_no += 1
            registration_channel = weighted_choice(rng)
            platform, source_channel = CHANNEL_SOURCE[registration_channel]
            country, language = rng.choice(countries)
            register_time = dt_at(current_day, rng.randint(8, 23), rng.randint(0, 59), rng.randint(0, 50))
            model_pool = ios_models if platform == "ios" else android_models
            os_version = f"iOS {rng.choice(['17.5', '18.0'])}" if platform == "ios" else f"Android {rng.choice(['13', '14', '15'])}"
            players.append(
                NewPlayer(
                    player_id=player_id,
                    account_id=f"new_mock_acc_{player_id}",
                    role_id=f"new_mock_role_{player_id}",
                    device_id=f"new_mock_dev_{player_id}",
                    register_time=register_time,
                    install_date=current_day,
                    country=country,
                    language=language,
                    platform=platform,
                    channel=source_channel,
                    campaign=f"new_mock_{source_channel.replace(',', '_')}_202606",
                    registration_channel=registration_channel,
                    device_tier=rng.choice(["mid", "mid", "high"]),
                    device_model=rng.choice(model_pool),
                    os_version=os_version,
                    server_id=rng.choice([101, 102, 103, 104, 105, 106]),
                    current_level=rng.randint(2, 6),
                    current_vip_level=0,
                    current_power=rng.randint(900, 2600),
                    current_city_level=rng.randint(1, 3),
                )
            )
    return players


def upsert_players(conn: Any, players: list[NewPlayer]) -> None:
    rows = [
        (
            player.player_id,
            player.account_id,
            player.role_id,
            player.device_id,
            player.register_time,
            player.install_date,
            player.country,
            player.language,
            player.platform,
            player.channel,
            player.campaign,
            player.device_tier,
            player.device_model,
            player.os_version,
            player.server_id,
            "casual",
            "non_spender",
            player.current_level,
            player.current_vip_level,
            player.current_power,
            player.current_city_level,
            None,
            None,
            Decimal("0.00"),
            player.install_date,
            player.registration_channel,
        )
        for player in players
    ]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO public.dim_player (
                player_id, account_id, role_id, device_id, register_time, install_date,
                country, language, platform, channel, campaign, device_tier, device_model,
                os_version, register_server_id, activity_segment, payer_segment, current_level,
                current_vip_level, current_power, current_city_level, current_alliance_id,
                first_pay_time, total_pay_amount, last_active_date, registration_channel
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
                registration_channel = EXCLUDED.registration_channel
            """,
            rows,
        )
    conn.commit()
    print(f"seeded new players={len(players)}")


def build_session_row(session_id: int, session_uid: str, player: NewPlayer, start_at: datetime, duration_minutes: int) -> tuple:
    current_day = start_at.date()
    end_at = min(start_at + timedelta(minutes=duration_minutes), dt_at(current_day, 23, 59, 30))
    duration_seconds = max(60, int((end_at - start_at).total_seconds()))
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
        max(1, player.current_level - 1),
        player.current_level,
        max(500, player.current_power - 150),
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
    )


def build_event_row(
    event_uid: str,
    player: NewPlayer,
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
        f"new_mock_cli_{event_uid}",
        f"new_mock_trace_{session_id}_{sequence}",
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
    )


def build_detail_rows(players: list[NewPlayer]) -> tuple[list[tuple], list[tuple], list[tuple], list[tuple]]:
    rng = random.Random(20260625)
    session_rows: list[tuple] = []
    event_rows: list[tuple] = []
    payment_rows: list[tuple] = []
    player_updates: list[tuple] = []
    session_id = NEW_SESSION_ID_START
    order_no = 1

    for index, player in enumerate(players):
        d0_start = player.register_time + timedelta(minutes=rng.randint(1, 8))
        d0_session_id = session_id
        session_id += 1
        session_rows.append(build_session_row(d0_session_id, f"new_mock_sess_{d0_session_id}", player, d0_start, rng.randint(22, 58)))
        event_rows.append(
            build_event_row(
                f"new_mock_register_evt_{player.player_id}",
                player,
                d0_session_id,
                player.register_time,
                "register",
                "account",
                1,
                {"registration_channel": player.registration_channel, "platform": player.platform},
                "server",
            )
        )
        event_rows.append(
            build_event_row(
                f"new_mock_login_evt_{player.player_id}_d0",
                player,
                d0_session_id,
                d0_start,
                "login",
                "session",
                2,
                {"registration_channel": player.registration_channel},
                "client",
            )
        )

        paid = rng.random() < (0.095 if player.registration_channel == "app store" else 0.072)
        pay_amount = Decimal("0.00")
        first_pay_time: datetime | None = None
        if paid:
            amount = rng.choices(
                [Decimal("6.00"), Decimal("12.00"), Decimal("30.00"), Decimal("68.00")],
                weights=[50, 30, 15, 5],
                k=1,
            )[0]
            pay_time = d0_start + timedelta(minutes=rng.randint(3, 20), seconds=rng.randint(0, 45))
            order_id = f"NEWMOCK{player.install_date:%Y%m%d}{order_no:05d}"
            order_no += 1
            start_uid = f"new_mock_pay_start_evt_{player.player_id}"
            final_uid = f"new_mock_pay_success_evt_{player.player_id}"
            event_rows.append(
                build_event_row(
                    start_uid,
                    player,
                    d0_session_id,
                    pay_time,
                    "purchase_start",
                    "monetization",
                    3,
                    {"order_id": order_id, "product_id": PRODUCT[0], "price_usd": str(amount)},
                    "client",
                )
            )
            event_rows.append(
                build_event_row(
                    final_uid,
                    player,
                    d0_session_id,
                    pay_time + timedelta(seconds=5),
                    "purchase_success",
                    "monetization",
                    4,
                    {"order_id": order_id, "product_id": PRODUCT[0], "amount_usd": str(amount), "is_first_pay": True},
                    "server",
                )
            )
            payment_rows.append(
                (
                    order_id,
                    start_uid,
                    final_uid,
                    pay_time + timedelta(seconds=5),
                    player.install_date,
                    player.player_id,
                    player.server_id,
                    d0_session_id,
                    PRODUCT[0],
                    PRODUCT[1],
                    amount,
                    amount,
                    Decimal("0.00"),
                    amount,
                    "CNY",
                    "app_store" if player.platform == "ios" else "android_store",
                    "success",
                    None,
                    None,
                    True,
                    1,
                    0,
                    1,
                    player.current_level,
                    "low",
                    json.dumps({"source": "new_mock_seed", "registration_channel": player.registration_channel}, ensure_ascii=False),
                )
            )
            pay_amount = amount
            first_pay_time = pay_time + timedelta(seconds=5)

        retained = rng.random() < (0.265 if index % 5 else 0.215)
        last_active_date = player.install_date
        if retained:
            d1_day = player.install_date + timedelta(days=1)
            d1_start = dt_at(d1_day, rng.randint(9, 23), rng.randint(0, 59), rng.randint(0, 45))
            d1_session_id = session_id
            session_id += 1
            session_rows.append(build_session_row(d1_session_id, f"new_mock_sess_{d1_session_id}", player, d1_start, rng.randint(18, 52)))
            event_rows.append(
                build_event_row(
                    f"new_mock_login_evt_{player.player_id}_d1",
                    player,
                    d1_session_id,
                    d1_start,
                    "login",
                    "session",
                    1,
                    {"registration_channel": player.registration_channel, "retention_day": 1},
                    "client",
                )
            )
            last_active_date = d1_day

        player_updates.append((first_pay_time, pay_amount, last_active_date, player.player_id))

    return session_rows, event_rows, payment_rows, player_updates


def upsert_sessions(conn: Any, session_rows: list[tuple]) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO public.fact_sessions (
                session_id, session_uid, player_id, account_id, role_id, device_id, server_id, session_start,
                session_end, duration_seconds, lifecycle_day, player_level_start, player_level_end, power_start,
                power_end, platform, channel, campaign, client_version, app_build, sdk_version, device_tier,
                device_model, os_version, network_type, country, ip_country
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
                ip_country = EXCLUDED.ip_country
            """,
            session_rows,
        )
    conn.commit()
    print(f"seeded new sessions={len(session_rows)}")


def insert_events_and_payments(conn: Any, event_rows: list[tuple], payment_rows: list[tuple], player_updates: list[tuple]) -> None:
    with conn.cursor() as cur:
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
        cur.executemany(
            """
            UPDATE public.dim_player
               SET first_pay_time = %s,
                   total_pay_amount = %s,
                   last_active_date = %s,
                   payer_segment = CASE WHEN %s > 0 THEN 'new_payer' ELSE 'non_spender' END,
                   current_vip_level = CASE WHEN %s > 0 THEN 1 ELSE current_vip_level END
             WHERE player_id = %s
            """,
            [(first_pay_time, amount, last_active_date, amount, amount, player_id) for first_pay_time, amount, last_active_date, player_id in player_updates],
        )
    conn.commit()
    print(f"seeded new events={len(event_rows)} payments={len(payment_rows)}")


NEW_USERS_DAILY_SQL = """
WITH obs AS (
    SELECT max(install_date) AS max_date FROM public.dim_player
), days AS (
    SELECT generate_series(max_date - 29, max_date, interval '1 day')::date AS dt
    FROM obs
), daily_new AS (
    SELECT p.install_date AS dt,
           count(*) AS new_users
    FROM public.dim_player p, obs
    WHERE p.install_date BETWEEN obs.max_date - 29 AND obs.max_date
    GROUP BY p.install_date
)
SELECT d.dt AS "日期",
       coalesce(n.new_users, 0) AS "新增用户数"
FROM days d
LEFT JOIN daily_new n ON n.dt = d.dt
ORDER BY d.dt
"""

NEW_USERS_BY_CHANNEL_SQL = """
WITH obs AS (
    SELECT max(install_date) AS max_date FROM public.dim_player
), days AS (
    SELECT generate_series(max_date - 6, max_date, interval '1 day')::date AS dt
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
    SELECT p.install_date AS dt,
           coalesce(p.registration_channel, p.channel) AS registration_channel,
           count(*) AS new_users
    FROM public.dim_player p, obs
    WHERE p.install_date BETWEEN obs.max_date - 6 AND obs.max_date
    GROUP BY p.install_date, coalesce(p.registration_channel, p.channel)
)
SELECT d.dt AS "日期",
       c.registration_channel AS "渠道",
       coalesce(dc.new_users, 0) AS "新增用户数"
FROM days d
CROSS JOIN channels c
LEFT JOIN daily_channel dc
  ON dc.dt = d.dt
 AND dc.registration_channel = c.registration_channel
ORDER BY d.dt, c.sort_no
"""

NEW_USERS_BY_OS_SQL = """
WITH obs AS (
    SELECT max(install_date) AS max_date FROM public.dim_player
), days AS (
    SELECT generate_series(max_date - 6, max_date, interval '1 day')::date AS dt
    FROM obs
), systems AS (
    SELECT * FROM (VALUES ('iOS', 1), ('Android', 2)) AS t(os_name, sort_no)
), daily_os AS (
    SELECT p.install_date AS dt,
           CASE WHEN lower(p.platform) = 'ios' THEN 'iOS' ELSE 'Android' END AS os_name,
           count(*) AS new_users
    FROM public.dim_player p, obs
    WHERE p.install_date BETWEEN obs.max_date - 6 AND obs.max_date
      AND lower(p.platform) IN ('ios', 'android')
    GROUP BY p.install_date, CASE WHEN lower(p.platform) = 'ios' THEN 'iOS' ELSE 'Android' END
)
SELECT d.dt AS "日期",
       s.os_name AS "系统",
       coalesce(o.new_users, 0) AS "新增用户数"
FROM days d
CROSS JOIN systems s
LEFT JOIN daily_os o
  ON o.dt = d.dt
 AND o.os_name = s.os_name
ORDER BY d.dt, s.sort_no
"""

D1_RETENTION_SQL = """
WITH obs AS (
    SELECT max(install_date) AS max_date FROM public.dim_player
), days AS (
    SELECT generate_series(max_date - 70, max_date - 40, interval '1 day')::date AS dt
    FROM obs
), cohort AS (
    SELECT p.install_date AS dt,
           p.player_id
    FROM public.dim_player p, obs
    WHERE p.install_date BETWEEN obs.max_date - 70 AND obs.max_date - 40
), retained AS (
    SELECT c.dt,
           c.player_id,
           EXISTS (
               SELECT 1
               FROM public.fact_sessions s
               WHERE s.player_id = c.player_id
                 AND s.session_start::date = c.dt + 1
           ) AS is_retained
    FROM cohort c
)
SELECT d.dt AS "日期",
       round(
           count(DISTINCT r.player_id) FILTER (WHERE r.is_retained)::numeric
           / nullif(count(DISTINCT r.player_id), 0) * 100,
           2
       ) AS "次日留存率"
FROM days d
LEFT JOIN retained r ON r.dt = d.dt
GROUP BY d.dt
ORDER BY d.dt
"""

D0_PAYMENT_SQL = """
WITH obs AS (
    SELECT max(install_date) AS max_date FROM public.dim_player
), days AS (
    SELECT generate_series(max_date - 29, max_date, interval '1 day')::date AS dt
    FROM obs
), daily_payment AS (
    SELECT p.install_date AS dt,
           round(sum(fp.net_revenue_usd), 2) AS d0_payment
    FROM public.dim_player p
    JOIN public.fact_payments fp
      ON fp.player_id = p.player_id
     AND fp.payment_status = 'success'
     AND fp.net_revenue_usd > 0
     AND fp.lifecycle_day = 0
    JOIN obs ON true
    WHERE p.install_date BETWEEN obs.max_date - 29 AND obs.max_date
    GROUP BY p.install_date
)
SELECT d.dt AS "日期",
       coalesce(dp.d0_payment, 0) AS "新增首日付费金额"
FROM days d
LEFT JOIN daily_payment dp ON dp.dt = d.dt
ORDER BY d.dt
"""


CHARTS = [
    {
        "id": "2189000000000000001",
        "title": "新增用户数",
        "type": "line",
        "layout": (1, 1, 72, 17),
        "sql": NEW_USERS_DAILY_SQL,
        "x": [axis("日期", axis_type="x")],
        "y": [axis("新增用户数", axis_type="y")],
        "series": [],
    },
    {
        "id": "2189000000000000002",
        "title": "新增用户数（按渠道）",
        "type": "line",
        "layout": (1, 18, 36, 16),
        "sql": NEW_USERS_BY_CHANNEL_SQL,
        "x": [axis("日期", axis_type="x")],
        "y": [axis("新增用户数", axis_type="y")],
        "series": [axis("渠道", axis_type="series")],
    },
    {
        "id": "2189000000000000003",
        "title": "新增用户数（按系统）",
        "type": "line",
        "layout": (37, 18, 36, 16),
        "sql": NEW_USERS_BY_OS_SQL,
        "x": [axis("日期", axis_type="x")],
        "y": [axis("新增用户数", axis_type="y")],
        "series": [axis("系统", axis_type="series")],
    },
    {
        "id": "2189000000000000004",
        "title": "新增用户次日留存",
        "type": "line",
        "layout": (1, 34, 36, 16),
        "sql": D1_RETENTION_SQL,
        "x": [axis("日期", axis_type="x")],
        "y": [axis("次日留存率", axis_type="y")],
        "series": [],
    },
    {
        "id": "2189000000000000005",
        "title": "新增首日付费金额",
        "type": "line",
        "layout": (37, 34, 36, 16),
        "sql": D0_PAYMENT_SQL,
        "x": [axis("日期", axis_type="x")],
        "y": [axis("新增首日付费金额", axis_type="y")],
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
                "columns": [],
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
    backup_path = BACKUP_DIR / f"new_users_dashboard_{DASHBOARD_ID}_{int(time.time())}.json"
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
                raise RuntimeError(f"New-user dashboard does not exist: {DASHBOARD_ID}")
            if dashboard["datasource"] != DATASOURCE_ID:
                raise RuntimeError(f"New-user dashboard datasource={dashboard['datasource']}, expected {DATASOURCE_ID}")

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
            SELECT count(*) FILTER (WHERE account_id LIKE 'new_mock_acc_%') AS new_mock_players,
                   min(install_date) FILTER (WHERE account_id LIKE 'new_mock_acc_%') AS min_install,
                   max(install_date) FILTER (WHERE account_id LIKE 'new_mock_acc_%') AS max_install,
                   count(DISTINCT registration_channel) AS registration_channels
            FROM public.dim_player
            """
        )
        print("verify_players=" + json.dumps(normalize_row(dict(cur.fetchone())), ensure_ascii=False))
        cur.execute(
            """
            SELECT count(*) FILTER (WHERE session_uid LIKE 'new_mock_%') AS new_mock_sessions
            FROM public.fact_sessions
            """
        )
        print("verify_sessions=" + json.dumps(normalize_row(dict(cur.fetchone())), ensure_ascii=False))
        cur.execute(
            """
            SELECT count(*) FILTER (WHERE order_id LIKE 'NEWMOCK%') AS new_mock_payments,
                   round(sum(net_revenue_usd) FILTER (WHERE order_id LIKE 'NEWMOCK%'), 2) AS new_mock_revenue
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
    ensure_registration_channel(conn)
    cleanup(conn)
    seed_product(conn)
    players = build_players()
    upsert_players(conn, players)
    session_rows, event_rows, payment_rows, player_updates = build_detail_rows(players)
    upsert_sessions(conn, session_rows)
    insert_events_and_payments(conn, event_rows, payment_rows, player_updates)


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
