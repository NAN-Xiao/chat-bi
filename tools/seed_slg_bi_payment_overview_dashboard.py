"""Seed payment detail rows and create the SLG BI Mock payment overview.

Targets:
- BI tracking database: 127.0.0.1:5432 / slg_bi_mock / postgres / 111111
- App system database: 127.0.0.1:15432 / zhishu_bi / root / Password123@pg

The generated data remains detail-level session/event/payment data. Payment
KPIs and LTV are computed at query time. LTV is deliberately calculated as a
cohort estimate from observed payments and a projection curve; no direct LTV
result table, aggregate table, snapshot table, or analysis view is created.
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

DASHBOARD_ID = "62616b33e94b4877a61ebc8750f79042"
DATASOURCE_ID = 1
UPDATE_BY = "7471612174524223488"
BACKUP_DIR = Path(".codex-runtime/backups")

START_DAY = date(2026, 4, 25)
END_DAY = date(2026, 6, 23)
PAYMENT_SESSION_ID_START = 10_100_000

PRODUCTS = [
    ("pay_mock_newbie_pack", "新手礼包", "starter", Decimal("6.00"), "once", 1, True, 34),
    ("pay_mock_monthly_card", "普通月卡", "subscription", Decimal("30.00"), "monthly", 4, True, 18),
    ("pay_mock_growth_pack", "新手成长礼包", "starter", Decimal("68.00"), "once", 6, True, 16),
    ("pay_mock_super_monthly_card", "超级月卡", "subscription", Decimal("98.00"), "monthly", 8, False, 8),
    ("pay_mock_pack_30", "30元", "gift_pack", Decimal("30.00"), "daily", 5, False, 7),
    ("pay_mock_pack_68", "68元", "gift_pack", Decimal("68.00"), "weekly", 8, False, 7),
    ("pay_mock_pack_128", "128元", "gift_pack", Decimal("128.00"), "weekly", 10, False, 5),
    ("pay_mock_pack_328", "328元", "gift_pack", Decimal("328.00"), "event", 12, False, 3),
    ("pay_mock_pack_648", "648元", "gift_pack", Decimal("648.00"), "event", 15, False, 2),
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


def choose_product(rng: random.Random, first_pay: bool) -> tuple:
    candidates = [item for item in PRODUCTS if first_pay or not item[6]]
    total = sum(item[7] for item in candidates)
    roll = rng.randint(1, total)
    running = 0
    for item in candidates:
        running += item[7]
        if roll <= running:
            return item
    return candidates[-1]


def ensure_payment_columns(conn: Any) -> None:
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
            ALTER TABLE public.fact_payments
                ADD COLUMN IF NOT EXISTS payment_source_channel text,
                ADD COLUMN IF NOT EXISTS payment_level_bucket integer
            """
        )
        cur.execute(
            """
            UPDATE public.fact_payments fp
               SET payment_source_channel = coalesce(p.registration_channel, p.channel),
                   payment_level_bucket = least(greatest(fp.player_level, 1), 9)
              FROM public.dim_player p
             WHERE p.player_id = fp.player_id
               AND (fp.payment_source_channel IS NULL OR fp.payment_level_bucket IS NULL)
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


def load_players(conn: Any) -> list[Player]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT player_id, account_id, role_id, device_id, install_date, country, language,
                   platform, channel, campaign, coalesce(registration_channel, channel) AS registration_channel,
                   device_tier, device_model, os_version, register_server_id AS server_id,
                   current_level, current_vip_level, current_power
            FROM public.dim_player
            WHERE install_date BETWEEN %s AND %s
              AND lower(platform) IN ('ios', 'android')
            ORDER BY install_date, player_id
            """,
            (START_DAY, END_DAY),
        )
        return [Player(**dict(row)) for row in cur.fetchall()]


def load_existing_pay_mock_orders(conn: Any) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM public.fact_payments WHERE order_id LIKE 'PAYMOCK%'")
        return cur.fetchone()[0]


def build_session_row(session_id: int, player: Player, event_time: datetime) -> tuple:
    current_day = event_time.date()
    lifecycle = lifecycle_day(player, current_day)
    start_at = event_time - timedelta(minutes=4)
    end_at = event_time + timedelta(minutes=28)
    return (
        session_id,
        f"pay_mock_sess_{session_id}",
        player.player_id,
        player.account_id,
        player.role_id,
        player.device_id,
        player.server_id,
        start_at,
        end_at,
        int((end_at - start_at).total_seconds()),
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
        player.registration_channel,
        lifecycle_segment(lifecycle),
    )


def build_event_row(
    event_uid: str,
    player: Player,
    session_id: int,
    event_time: datetime,
    event_name: str,
    sequence: int,
    attributes: dict[str, Any],
    source: str,
) -> tuple:
    current_day = event_time.date()
    return (
        event_uid,
        f"pay_mock_cli_{event_uid}",
        f"pay_mock_trace_{session_id}_{sequence}",
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
        source,
        sequence,
        json.dumps(attributes, ensure_ascii=False),
    )


def build_payment_rows(players: list[Player]) -> tuple[list[tuple], list[tuple], list[tuple]]:
    rng = random.Random(20260627)
    players_by_day: dict[date, list[Player]] = {}
    for player in players:
        players_by_day.setdefault(player.install_date, []).append(player)

    session_rows: list[tuple] = []
    event_rows: list[tuple] = []
    payment_rows: list[tuple] = []
    paid_players: set[int] = set()
    session_id = PAYMENT_SESSION_ID_START
    order_no = 1

    for day_offset in range((END_DAY - START_DAY).days + 1):
        install_day = START_DAY + timedelta(days=day_offset)
        cohort = list(players_by_day.get(install_day, []))
        if not cohort:
            continue
        rng.shuffle(cohort)
        cohort_pay_count = max(6, min(len(cohort), round(len(cohort) * (0.20 + 0.04 * rng.random()))))
        payers = cohort[:cohort_pay_count]
        for player_index, player in enumerate(payers):
            lifecycle_offsets = [0]
            if rng.random() < 0.54 and install_day + timedelta(days=1) <= END_DAY:
                lifecycle_offsets.append(1)
            if rng.random() < 0.32 and install_day + timedelta(days=rng.randint(2, 4)) <= END_DAY:
                lifecycle_offsets.append(rng.randint(2, 4))
            if rng.random() < 0.20 and install_day + timedelta(days=rng.randint(5, 7)) <= END_DAY:
                lifecycle_offsets.append(rng.randint(5, 7))
            if rng.random() < 0.14:
                later_day = min(END_DAY, install_day + timedelta(days=rng.randint(8, 29)))
                if later_day >= install_day:
                    lifecycle_offsets.append((later_day - install_day).days)

            seen_offsets: set[int] = set()
            for pay_index, offset in enumerate(lifecycle_offsets):
                if offset in seen_offsets:
                    continue
                seen_offsets.add(offset)
                pay_day = install_day + timedelta(days=offset)
                if pay_day > END_DAY:
                    continue
                first_pay = player.player_id not in paid_players
                product = choose_product(rng, first_pay)
                product_id, product_name, _, price_usd, _, _, _, _ = product
                multiplier = Decimal(str(rng.choice([1, 1, 1, 1, 2])))
                amount = (price_usd * multiplier).quantize(Decimal("0.01"))
                pay_time = dt_at(pay_day, rng.randint(9, 23), rng.randint(0, 59), rng.randint(0, 45))
                order_id = f"PAYMOCK{order_no:08d}"
                start_uid = f"pay_mock_start_evt_{order_no:08d}"
                final_uid = f"pay_mock_success_evt_{order_no:08d}"
                session_rows.append(build_session_row(session_id, player, pay_time))
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
                        pay_time + timedelta(seconds=5),
                        "purchase_success",
                        2,
                        {"order_id": order_id, "product_id": product_id, "amount_usd": str(amount), "is_first_pay": first_pay},
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
                        session_id,
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
                        first_pay,
                        pay_index + 1,
                        lifecycle_day(player, pay_day),
                        max(player.current_vip_level, 1),
                        player.current_level,
                        "whale" if amount >= Decimal("328") else ("mid" if amount >= Decimal("68") else "low"),
                        json.dumps({"source": "pay_mock_seed", "registration_channel": player.registration_channel}, ensure_ascii=False),
                        player.registration_channel,
                        min(max(player.current_level, 1), 9),
                    )
                )
                paid_players.add(player.player_id)
                session_id += 1
                order_no += 1

        # A small repeat-spend tail keeps the 7-day rank and weekly buckets useful.
        repeat_pool = [player for player in cohort if player.player_id in paid_players]
        rng.shuffle(repeat_pool)
        for player in repeat_pool[: max(2, len(repeat_pool) // 20)]:
            pay_day = min(END_DAY, install_day + timedelta(days=rng.randint(0, 29)))
            if pay_day < install_day:
                continue
            product = rng.choice([item for item in PRODUCTS if not item[6]])
            product_id, product_name, _, price_usd, _, _, _, _ = product
            amount = (price_usd * Decimal(str(rng.choice([1, 1, 2])))).quantize(Decimal("0.01"))
            pay_time = dt_at(pay_day, rng.randint(10, 23), rng.randint(0, 59), rng.randint(0, 45))
            order_id = f"PAYMOCK{order_no:08d}"
            start_uid = f"pay_mock_start_evt_{order_no:08d}"
            final_uid = f"pay_mock_success_evt_{order_no:08d}"
            session_rows.append(build_session_row(session_id, player, pay_time))
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
                    pay_time + timedelta(seconds=5),
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
                    pay_time + timedelta(seconds=5),
                    pay_day,
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
                    "app_store" if player.platform == "ios" else "android_store",
                    "success",
                    None,
                    None,
                    False,
                    2,
                    lifecycle_day(player, pay_day),
                    max(player.current_vip_level, 1),
                    player.current_level,
                    "whale" if amount >= Decimal("328") else ("mid" if amount >= Decimal("68") else "low"),
                    json.dumps({"source": "pay_mock_seed", "registration_channel": player.registration_channel}, ensure_ascii=False),
                    player.registration_channel,
                    min(max(player.current_level, 1), 9),
                )
            )
            session_id += 1
            order_no += 1

    return session_rows, event_rows, payment_rows


def upsert_detail_rows(conn: Any, session_rows: list[tuple], event_rows: list[tuple], payment_rows: list[tuple]) -> None:
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
                attributes = EXCLUDED.attributes
            """,
            event_rows,
        )
        cur.executemany(
            """
            INSERT INTO public.fact_payments (
                order_id, start_event_uid, final_event_uid, event_time, event_date, player_id, server_id,
                session_id, product_id, product_name, amount_usd, gross_revenue_usd, refund_amount_usd,
                net_revenue_usd, local_currency, payment_channel, payment_status, fail_reason, refund_reason,
                is_first_pay, pay_sequence, lifecycle_day, vip_level_after, player_level, revenue_tier,
                attributes, payment_source_channel, payment_level_bucket
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
                payment_level_bucket = EXCLUDED.payment_level_bucket
            """,
            payment_rows,
        )
    conn.commit()
    print(f"upserted payment sessions={len(session_rows)} events={len(event_rows)} payments={len(payment_rows)}")


PAYMENT_FILTER = """
p.payment_status = 'success'
AND p.net_revenue_usd > 0
AND p.product_id <> 'rt_mock_realtime_pack'
"""

PAYMENT_OVERVIEW_SQL = f"""
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
), daily_payment AS (
    SELECT p.event_date AS dt,
           count(*) AS pay_count,
           count(DISTINCT p.player_id) AS pay_users,
           round(sum(p.net_revenue_usd), 2) AS pay_amount
    FROM public.fact_payments p, obs
    WHERE {PAYMENT_FILTER}
      AND p.event_date BETWEEN obs.max_date - 29 AND obs.max_date
    GROUP BY p.event_date
), daily AS (
    SELECT d.dt,
           coalesce(dp.pay_count, 0) AS pay_count,
           coalesce(dp.pay_users, 0) AS pay_users,
           coalesce(dp.pay_amount, 0) AS pay_amount,
           coalesce(da.dau, 0) AS dau
    FROM days d
    LEFT JOIN daily_payment dp ON dp.dt = d.dt
    LEFT JOIN daily_active da ON da.dt = d.dt
), output_rows AS (
    SELECT 0 AS sort_no,
           '阶段汇总' AS "日期",
           sum(pay_count)::numeric AS "付费次数",
           round(avg(pay_users), 2) AS "付费用户数",
           round(sum(pay_amount), 2) AS "付费总额",
           round(sum(pay_amount) / nullif(sum(dau), 0), 2) AS "ARPU",
           round(sum(pay_amount) / nullif(sum(pay_users), 0), 2) AS "ARPPU",
           round(sum(pay_users)::numeric / nullif(sum(dau), 0) * 100, 2)::text || '%' AS "付费渗透率"
    FROM daily
    UNION ALL
    SELECT 1 AS sort_no,
           to_char(dt, 'YYYY-MM-DD') AS "日期",
           pay_count::numeric AS "付费次数",
           pay_users::numeric AS "付费用户数",
           pay_amount AS "付费总额",
           round(pay_amount / nullif(dau, 0), 2) AS "ARPU",
           round(pay_amount / nullif(pay_users, 0), 2) AS "ARPPU",
           round(pay_users::numeric / nullif(dau, 0) * 100, 2)::text || '%' AS "付费渗透率"
    FROM daily
)
SELECT "日期", "付费次数", "付费用户数", "付费总额", "ARPU", "ARPPU", "付费渗透率"
FROM output_rows
ORDER BY sort_no, "日期" DESC
"""

TOP_7D_PAYERS_SQL = f"""
WITH obs AS (
    SELECT max(install_date) AS max_date FROM public.dim_player
), payer_rank AS (
    SELECT p.player_id,
           min(dp.account_id) AS account_id,
           coalesce(min(p.payment_source_channel), min(dp.registration_channel), min(dp.channel)) AS source_channel,
           min(p.server_id) AS server_id,
           round(sum(p.net_revenue_usd), 2) AS pay_amount
    FROM public.fact_payments p
    JOIN public.dim_player dp ON dp.player_id = p.player_id
    JOIN obs ON true
    WHERE {PAYMENT_FILTER}
      AND p.event_date BETWEEN obs.max_date - 6 AND obs.max_date
    GROUP BY p.player_id
)
SELECT account_id AS "账号ID",
       source_channel AS "来源渠道",
       server_id AS "区服ID",
       pay_amount AS "付费总额"
FROM payer_rank
ORDER BY pay_amount DESC, account_id
LIMIT 50
"""

DAILY_PAY_COUNT_SQL = f"""
WITH obs AS (
    SELECT max(install_date) AS max_date FROM public.dim_player
), days AS (
    SELECT generate_series(max_date - 29, max_date, interval '1 day')::date AS dt
    FROM obs
), daily_payment AS (
    SELECT p.event_date AS dt,
           count(*) AS pay_count
    FROM public.fact_payments p, obs
    WHERE {PAYMENT_FILTER}
      AND p.event_date BETWEEN obs.max_date - 29 AND obs.max_date
    GROUP BY p.event_date
)
SELECT d.dt AS "日期",
       coalesce(dp.pay_count, 0) AS "充值次数"
FROM days d
LEFT JOIN daily_payment dp ON dp.dt = d.dt
ORDER BY d.dt
"""

DAILY_PAYER_SQL = f"""
WITH obs AS (
    SELECT max(install_date) AS max_date FROM public.dim_player
), days AS (
    SELECT generate_series(max_date - 29, max_date, interval '1 day')::date AS dt
    FROM obs
), payer_first AS (
    SELECT p.player_id,
           min(p.event_date) AS first_pay_date
    FROM public.fact_payments p
    WHERE {PAYMENT_FILTER}
    GROUP BY p.player_id
), daily_payer AS (
    SELECT p.event_date AS dt,
           count(DISTINCT p.player_id) AS pay_users
    FROM public.fact_payments p, obs
    WHERE {PAYMENT_FILTER}
      AND p.event_date BETWEEN obs.max_date - 29 AND obs.max_date
    GROUP BY p.event_date
), daily_new_payer AS (
    SELECT first_pay_date AS dt,
           count(*) AS new_pay_users
    FROM payer_first, obs
    WHERE first_pay_date BETWEEN obs.max_date - 29 AND obs.max_date
    GROUP BY first_pay_date
)
SELECT d.dt AS "日期",
       coalesce(dp.pay_users, 0) AS "日充值用户数",
       coalesce(dn.new_pay_users, 0) AS "日新增充值用户数"
FROM days d
LEFT JOIN daily_payer dp ON dp.dt = d.dt
LEFT JOIN daily_new_payer dn ON dn.dt = d.dt
ORDER BY d.dt
"""

LTV_7D_SQL = f"""
WITH obs AS (
    SELECT max(install_date) AS max_date FROM public.dim_player
), days AS (
    SELECT generate_series(max_date - 59, max_date, interval '1 day')::date AS cohort_date
    FROM obs
), curve AS (
    SELECT *
    FROM (VALUES
        (0, 0.38::numeric),
        (1, 0.62::numeric),
        (2, 0.72::numeric),
        (3, 0.80::numeric),
        (4, 0.86::numeric),
        (5, 0.91::numeric),
        (6, 0.96::numeric),
        (7, 1.00::numeric)
    ) AS t(day_index, ratio)
), cohort AS (
    SELECT p.install_date AS cohort_date,
           count(*) AS registered_users
    FROM public.dim_player p, obs
    WHERE p.install_date BETWEEN obs.max_date - 59 AND obs.max_date
    GROUP BY p.install_date
), payment AS (
    SELECT dp.install_date AS cohort_date,
           p.lifecycle_day,
           sum(p.net_revenue_usd) AS revenue
    FROM public.fact_payments p
    JOIN public.dim_player dp ON dp.player_id = p.player_id
    JOIN obs ON true
    WHERE {PAYMENT_FILTER}
      AND dp.install_date BETWEEN obs.max_date - 59 AND obs.max_date
      AND p.lifecycle_day BETWEEN 0 AND 7
      AND p.event_date <= obs.max_date
    GROUP BY dp.install_date, p.lifecycle_day
), estimates AS (
    SELECT c.cohort_date,
           c.registered_users,
           target.day_index,
           CASE
             WHEN c.cohort_date + target.day_index <= obs.max_date THEN
               coalesce((
                   SELECT sum(p.revenue)
                   FROM payment p
                   WHERE p.cohort_date = c.cohort_date
                     AND p.lifecycle_day <= target.day_index
               ), 0)
             ELSE
               coalesce((
                   SELECT sum(p.revenue)
                   FROM payment p
                   WHERE p.cohort_date = c.cohort_date
                     AND p.lifecycle_day <= greatest((obs.max_date - c.cohort_date), 0)
               ), 0)
               / nullif(observed.ratio, 0)
               * target.ratio
           END AS estimated_revenue
    FROM cohort c
    JOIN obs ON true
    CROSS JOIN curve target
    JOIN curve observed ON observed.day_index = least(greatest((obs.max_date - c.cohort_date), 0), target.day_index)
)
SELECT cohort_date AS "日期",
       registered_users AS "用户注册用户数",
       round(max(estimated_revenue) FILTER (WHERE day_index = 0) / nullif(registered_users, 0), 2) AS "当日",
       round(max(estimated_revenue) FILTER (WHERE day_index = 1) / nullif(registered_users, 0), 2) AS "第1日",
       round(max(estimated_revenue) FILTER (WHERE day_index = 2) / nullif(registered_users, 0), 2) AS "第2日",
       round(max(estimated_revenue) FILTER (WHERE day_index = 3) / nullif(registered_users, 0), 2) AS "第3日",
       round(max(estimated_revenue) FILTER (WHERE day_index = 4) / nullif(registered_users, 0), 2) AS "第4日",
       round(max(estimated_revenue) FILTER (WHERE day_index = 5) / nullif(registered_users, 0), 2) AS "第5日",
       round(max(estimated_revenue) FILTER (WHERE day_index = 6) / nullif(registered_users, 0), 2) AS "第6日",
       round(max(estimated_revenue) FILTER (WHERE day_index = 7) / nullif(registered_users, 0), 2) AS "第7日"
FROM estimates
GROUP BY cohort_date, registered_users
ORDER BY cohort_date
"""

WEEKLY_CUMULATIVE_PAY_SQL = f"""
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
           p.player_id,
           sum(p.net_revenue_usd) AS weekly_amount
    FROM weeks w
    JOIN public.fact_payments p
      ON p.event_date BETWEEN w.week_start AND least(w.week_start + 6, w.max_date)
    WHERE {PAYMENT_FILTER}
    GROUP BY w.week_start, p.player_id
), bucketed AS (
    SELECT week_start,
           player_id,
           weekly_amount,
           CASE
             WHEN weekly_amount < 500 THEN 1
             WHEN weekly_amount < 1000 THEN 2
             WHEN weekly_amount < 1500 THEN 3
             WHEN weekly_amount < 2000 THEN 4
             WHEN weekly_amount < 2500 THEN 5
             WHEN weekly_amount < 3000 THEN 6
             ELSE 7
           END AS bucket_no
    FROM player_week
), summary AS (
    SELECT week_start,
           count(*) AS all_users,
           count(*) FILTER (WHERE bucket_no = 1) AS b1,
           count(*) FILTER (WHERE bucket_no = 2) AS b2,
           count(*) FILTER (WHERE bucket_no = 3) AS b3,
           count(*) FILTER (WHERE bucket_no = 4) AS b4,
           count(*) FILTER (WHERE bucket_no = 5) AS b5,
           count(*) FILTER (WHERE bucket_no = 6) AS b6,
           count(*) FILTER (WHERE bucket_no = 7) AS b7
    FROM bucketed
    GROUP BY week_start
)
SELECT to_char(week_start, 'YYYY-MM-DD') || '当周' AS "事件发生时间",
       all_users AS "全部用户",
       b1::text || chr(10) || round(b1::numeric / nullif(all_users, 0) * 100, 2)::text || '%' AS "(-∞, 500)",
       b2::text || chr(10) || round(b2::numeric / nullif(all_users, 0) * 100, 2)::text || '%' AS "[500, 1000)",
       b3::text || chr(10) || round(b3::numeric / nullif(all_users, 0) * 100, 2)::text || '%' AS "[1000, 1500)",
       b4::text || chr(10) || round(b4::numeric / nullif(all_users, 0) * 100, 2)::text || '%' AS "[1500, 2000)",
       b5::text || chr(10) || round(b5::numeric / nullif(all_users, 0) * 100, 2)::text || '%' AS "[2000, 2500)",
       b6::text || chr(10) || round(b6::numeric / nullif(all_users, 0) * 100, 2)::text || '%' AS "[2500, 3000)",
       b7::text || chr(10) || round(b7::numeric / nullif(all_users, 0) * 100, 2)::text || '%' AS "[3000, +∞)"
FROM summary
ORDER BY week_start
"""

FIRST_PURCHASE_SQL = f"""
WITH obs AS (
    SELECT max(install_date) AS max_date FROM public.dim_player
), first_pay AS (
    SELECT DISTINCT ON (p.player_id)
           p.player_id,
           p.product_name,
           p.event_date
    FROM public.fact_payments p, obs
    WHERE {PAYMENT_FILTER}
      AND p.event_date BETWEEN obs.max_date - 29 AND obs.max_date
    ORDER BY p.player_id, p.event_time
)
SELECT product_name AS "商品",
       count(*) AS "首次购买人数"
FROM first_pay
GROUP BY product_name
ORDER BY "首次购买人数" DESC, product_name
LIMIT 12
"""

LEVEL_AVG_PAYMENT_SQL = f"""
WITH obs AS (
    SELECT max(install_date) AS max_date FROM public.dim_player
), player_level_pay AS (
    SELECT least(greatest(coalesce(p.payment_level_bucket, p.player_level), 1), 9) AS level_bucket,
           p.player_id,
           sum(p.net_revenue_usd) AS pay_amount
    FROM public.fact_payments p, obs
    WHERE {PAYMENT_FILTER}
      AND p.event_date BETWEEN obs.max_date - 29 AND obs.max_date
    GROUP BY least(greatest(coalesce(p.payment_level_bucket, p.player_level), 1), 9), p.player_id
)
SELECT level_bucket::text AS "等级段",
       round(avg(pay_amount), 2) AS "人均付费金额"
FROM player_level_pay
GROUP BY level_bucket
ORDER BY "人均付费金额" DESC, level_bucket
"""


CHARTS = [
    {
        "id": "2191000000000000001",
        "title": "付费情况",
        "type": "table",
        "layout": (1, 1, 72, 18),
        "sql": PAYMENT_OVERVIEW_SQL,
        "x": [],
        "y": [],
        "series": [],
    },
    {
        "id": "2191000000000000002",
        "title": "近7日累充排名",
        "type": "table",
        "layout": (1, 19, 72, 18),
        "sql": TOP_7D_PAYERS_SQL,
        "x": [],
        "y": [],
        "series": [],
    },
    {
        "id": "2191000000000000003",
        "title": "日充值总次数",
        "type": "line",
        "layout": (1, 37, 36, 16),
        "sql": DAILY_PAY_COUNT_SQL,
        "x": [axis("日期", axis_type="x")],
        "y": [axis("充值次数", axis_type="y")],
        "series": [],
    },
    {
        "id": "2191000000000000004",
        "title": "日充值用户数",
        "type": "line",
        "layout": (37, 37, 36, 16),
        "sql": DAILY_PAYER_SQL,
        "x": [axis("日期", axis_type="x")],
        "y": [axis("日充值用户数", axis_type="y", multi=True), axis("日新增充值用户数", axis_type="y", multi=True)],
        "series": [],
    },
    {
        "id": "2191000000000000005",
        "title": "7日LTV",
        "type": "table",
        "layout": (1, 53, 72, 18),
        "sql": LTV_7D_SQL,
        "x": [],
        "y": [],
        "series": [],
    },
    {
        "id": "2191000000000000006",
        "title": "充值用户周累充分布",
        "type": "table",
        "layout": (1, 71, 72, 16),
        "sql": WEEKLY_CUMULATIVE_PAY_SQL,
        "x": [],
        "y": [],
        "series": [],
    },
    {
        "id": "2191000000000000007",
        "title": "首次购买情况",
        "type": "column",
        "layout": (1, 87, 36, 16),
        "sql": FIRST_PURCHASE_SQL,
        "x": [axis("商品", axis_type="x")],
        "y": [axis("首次购买人数", axis_type="y")],
        "series": [],
    },
    {
        "id": "2191000000000000008",
        "title": "各等级段人均付费金额",
        "type": "column",
        "layout": (37, 87, 36, 16),
        "sql": LEVEL_AVG_PAYMENT_SQL,
        "x": [axis("等级段", axis_type="x")],
        "y": [axis("人均付费金额", axis_type="y")],
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
    backup_path = BACKUP_DIR / f"payment_overview_dashboard_{DASHBOARD_ID}_{int(time.time())}.json"
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
                raise RuntimeError(f"Payment overview dashboard does not exist: {DASHBOARD_ID}")
            if dashboard["datasource"] != DATASOURCE_ID:
                raise RuntimeError(f"Payment overview dashboard datasource={dashboard['datasource']}, expected {DATASOURCE_ID}")

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
            SELECT count(*) FILTER (WHERE order_id LIKE 'PAYMOCK%') AS pay_mock_payments,
                   min(event_date) FILTER (WHERE order_id LIKE 'PAYMOCK%') AS min_date,
                   max(event_date) FILTER (WHERE order_id LIKE 'PAYMOCK%') AS max_date,
                   count(DISTINCT player_id) FILTER (WHERE order_id LIKE 'PAYMOCK%') AS payers,
                   round(sum(net_revenue_usd) FILTER (WHERE order_id LIKE 'PAYMOCK%'), 2) AS revenue
            FROM public.fact_payments
            """
        )
        print("verify_payments=" + json.dumps(normalize_row(dict(cur.fetchone())), ensure_ascii=False))
        cur.execute(
            """
            SELECT count(*) FILTER (WHERE payment_source_channel IS NOT NULL) AS payment_channel_rows,
                   count(*) FILTER (WHERE payment_level_bucket IS NOT NULL) AS payment_level_rows
            FROM public.fact_payments
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
    ensure_payment_columns(conn)
    seed_products(conn)
    retained = load_existing_pay_mock_orders(conn)
    players = load_players(conn)
    if not players:
        raise RuntimeError("No eligible players for payment overview seed")
    session_rows, event_rows, payment_rows = build_payment_rows(players)
    upsert_detail_rows(conn, session_rows, event_rows, payment_rows)
    ensure_payment_columns(conn)
    print(f"retained pay_mock payments before upsert={retained}")


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
