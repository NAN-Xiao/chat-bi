"""Seed gift-package payment detail rows and create the SLG BI Mock gift dashboard.

Targets:
- BI tracking database: 127.0.0.1:5432 / slg_bi_mock / postgres / 111111
- App system database: core ZHISHU_DB_* settings from the repo .env

This follows the BI tracking strategy:
- fact_sessions rows model login/payment sessions;
- fact_events rows model purchase_start / purchase_success events;
- fact_payments rows model gift-package orders with package dimensions.

No aggregate KPI tables, result tables, snapshots, or analysis views are
created. Repeat purchase and retention metrics are computed from detail rows
at query time.
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

DASHBOARD_ID = "45c4bd8dec1e46c3a33f2f45703b8117"
DATASOURCE_ID = 1
UPDATE_BY = "7471612174524223488"
BACKUP_DIR = Path(".codex-runtime/backups")

START_DAY = date(2026, 4, 14)
END_DAY = date(2026, 6, 23)
GIFT_SESSION_ID_START = 10_500_000

PRODUCTS = [
    ("gift_mock_newbie_pack", "新手礼包", "starter", Decimal("6.00"), "once", 1, True, "新手礼包", "starter_pack"),
    ("gift_mock_regular_monthly_card", "普通月卡", "subscription", Decimal("30.00"), "monthly", 3, True, "普通月卡", "monthly_card"),
    ("gift_mock_super_monthly_card", "超级月卡", "subscription", Decimal("98.00"), "monthly", 8, False, "超级月卡", "monthly_card"),
    ("gift_mock_growth_pack", "新手成长礼包", "starter", Decimal("68.00"), "once", 6, False, "新手成长礼包", "starter_pack"),
    ("gift_mock_30_pack", "30元", "gift_pack", Decimal("30.00"), "daily", 5, False, "30元", "gift_pack"),
    ("gift_mock_68_pack", "68元", "gift_pack", Decimal("68.00"), "weekly", 8, False, "68元", "gift_pack"),
]

REPEAT_PRODUCTS = PRODUCTS[3:]
MONTHLY_PRODUCTS = [PRODUCTS[1], PRODUCTS[2]]

WEEKLY_NEWBIE_TARGETS = [
    (date(2026, 5, 25), 260),
    (date(2026, 6, 1), 255),
    (date(2026, 6, 8), 265),
    (date(2026, 6, 15), 255),
    (date(2026, 6, 22), 90),
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


def ensure_gift_columns(conn: Any) -> None:
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
                ADD COLUMN IF NOT EXISTS payment_level_bucket integer,
                ADD COLUMN IF NOT EXISTS gift_package_type text,
                ADD COLUMN IF NOT EXISTS gift_package_group text,
                ADD COLUMN IF NOT EXISTS gift_purchase_stage text
            """
        )
        cur.execute(
            """
            UPDATE public.fact_payments fp
               SET payment_source_channel = coalesce(fp.payment_source_channel, p.registration_channel, p.channel),
                   payment_level_bucket = coalesce(fp.payment_level_bucket, least(greatest(fp.player_level, 1), 9)),
                   gift_package_type = coalesce(
                       fp.gift_package_type,
                       CASE
                         WHEN fp.product_name IN ('新手礼包', '新增首日礼包') THEN '新手礼包'
                         WHEN fp.product_name = '普通月卡' THEN '普通月卡'
                         WHEN fp.product_name IN ('月卡', '超级月卡') THEN fp.product_name
                         WHEN fp.product_name LIKE '%礼包%' OR fp.product_id LIKE '%pack%' THEN fp.product_name
                         ELSE NULL
                       END
                   ),
                   gift_package_group = coalesce(
                       fp.gift_package_group,
                       CASE
                         WHEN fp.product_name IN ('普通月卡', '月卡', '超级月卡') THEN 'monthly_card'
                         WHEN fp.product_name IN ('新手礼包', '新增首日礼包', '新手成长礼包') THEN 'starter_pack'
                         WHEN fp.product_name LIKE '%礼包%' OR fp.product_id LIKE '%pack%' THEN 'gift_pack'
                         ELSE NULL
                       END
                   ),
                   gift_purchase_stage = coalesce(fp.gift_purchase_stage, CASE WHEN fp.is_first_pay THEN '首购' ELSE '复购' END)
              FROM public.dim_player p
             WHERE p.player_id = fp.player_id
               AND (
                   fp.payment_source_channel IS NULL
                OR fp.payment_level_bucket IS NULL
                OR fp.gift_package_type IS NULL
                OR fp.gift_package_group IS NULL
                OR fp.gift_purchase_stage IS NULL
               )
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
            WHERE install_date <= %s
              AND lower(platform) IN ('ios', 'android')
            ORDER BY install_date, player_id
            """,
            (END_DAY,),
        )
        return [Player(**dict(row)) for row in cur.fetchall()]


def build_session_row(session_id: int, player: Player, event_time: datetime) -> tuple:
    current_day = event_time.date()
    lifecycle = lifecycle_day(player, current_day)
    start_at = event_time - timedelta(minutes=3)
    end_at = event_time + timedelta(minutes=25)
    return (
        session_id,
        f"gift_mock_sess_{session_id}",
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
        f"gift_mock_cli_{event_uid}",
        f"gift_mock_trace_{session_id}_{sequence}",
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


def add_purchase(
    session_rows: list[tuple],
    event_rows: list[tuple],
    payment_rows: list[tuple],
    player: Player,
    product: tuple,
    pay_time: datetime,
    order_no: int,
    session_id: int,
    first_pay: bool,
) -> None:
    product_id, product_name, _product_type, price_usd, _limit_type, _unlock_level, _is_first_pay_pack, package_type, package_group = product
    order_id = f"GIFTMOCK{order_no:08d}"
    start_uid = f"gift_mock_start_evt_{order_no:08d}"
    final_uid = f"gift_mock_success_evt_{order_no:08d}"
    session_rows.append(build_session_row(session_id, player, pay_time))
    event_rows.append(
        build_event_row(
            start_uid,
            player,
            session_id,
            pay_time,
            "purchase_start",
            1,
            {"order_id": order_id, "product_id": product_id, "gift_package_type": package_type},
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
            {"order_id": order_id, "product_id": product_id, "amount_usd": str(price_usd), "gift_package_type": package_type},
            "server",
        )
    )
    payment_rows.append(
        (
            order_id,
            start_uid,
            final_uid,
            pay_time + timedelta(seconds=5),
            pay_time.date(),
            player.player_id,
            player.server_id,
            session_id,
            product_id,
            product_name,
            price_usd,
            price_usd,
            Decimal("0.00"),
            price_usd,
            "CNY",
            "app_store" if player.platform == "ios" else "android_store",
            "success",
            None,
            None,
            first_pay,
            1 if first_pay else 2,
            lifecycle_day(player, pay_time.date()),
            max(player.current_vip_level, 1),
            player.current_level,
            "mid" if price_usd >= Decimal("68") else "low",
            json.dumps({"source": "gift_mock_seed", "gift_package_type": package_type, "gift_package_group": package_group}, ensure_ascii=False),
            player.registration_channel,
            min(max(player.current_level, 1), 9),
            package_type,
            package_group,
            "首购" if first_pay else "复购",
        )
    )


def add_retention_session(session_rows: list[tuple], player: Player, active_day: date, session_id: int, rng: random.Random) -> None:
    event_time = dt_at(active_day, rng.randint(9, 23), rng.randint(0, 59), rng.randint(0, 45))
    session_rows.append(build_session_row(session_id, player, event_time))


def build_detail_rows(players: list[Player]) -> tuple[list[tuple], list[tuple], list[tuple]]:
    rng = random.Random(20260629)
    eligible_by_day = [player for player in players if player.install_date <= END_DAY]
    session_rows: list[tuple] = []
    event_rows: list[tuple] = []
    payment_rows: list[tuple] = []
    session_id = GIFT_SESSION_ID_START
    order_no = 1
    used_newbie_players: set[int] = set()

    for week_start, target_count in WEEKLY_NEWBIE_TARGETS:
        candidates = [player for player in eligible_by_day if player.install_date <= week_start and player.player_id not in used_newbie_players]
        rng.shuffle(candidates)
        cohort = candidates[:target_count]
        for player in cohort:
            used_newbie_players.add(player.player_id)
            buy_day = week_start + timedelta(days=rng.randint(0, min(6, (END_DAY - week_start).days)))
            pay_time = dt_at(buy_day, rng.randint(9, 23), rng.randint(0, 59), rng.randint(0, 45))
            add_purchase(session_rows, event_rows, payment_rows, player, PRODUCTS[0], pay_time, order_no, session_id, True)
            order_no += 1
            session_id += 1

            for week_offset, probability in [(0, 0.56), (1, 0.09), (2, 0.018), (3, 0.010), (4, 0.004)]:
                target_week = week_start + timedelta(days=week_offset * 7)
                if target_week > END_DAY or rng.random() > probability:
                    continue
                repeat_day = target_week + timedelta(days=rng.randint(0, min(6, (END_DAY - target_week).days)))
                if repeat_day < buy_day:
                    repeat_day = buy_day
                repeat_time = dt_at(repeat_day, rng.randint(10, 23), rng.randint(0, 59), rng.randint(0, 45))
                repeat_product = rng.choice(REPEAT_PRODUCTS)
                add_purchase(session_rows, event_rows, payment_rows, player, repeat_product, repeat_time, order_no, session_id, False)
                order_no += 1
                session_id += 1

    monthly_candidates = [player for player in eligible_by_day if player.install_date <= date(2026, 5, 24)]
    rng.shuffle(monthly_candidates)
    monthly_buyers = monthly_candidates[:520]
    for index, player in enumerate(monthly_buyers):
        product = MONTHLY_PRODUCTS[0] if index % 3 else MONTHLY_PRODUCTS[1]
        buy_day = date(2026, 4, 14) + timedelta(days=rng.randint(0, 40))
        if buy_day < player.install_date:
            buy_day = player.install_date
        if buy_day > date(2026, 5, 24):
            buy_day = date(2026, 5, 24)
        pay_time = dt_at(buy_day, rng.randint(9, 22), rng.randint(0, 59), rng.randint(0, 45))
        add_purchase(session_rows, event_rows, payment_rows, player, product, pay_time, order_no, session_id, True)
        order_no += 1
        session_id += 1

        for retain_day in range(1, 31):
            active_day = buy_day + timedelta(days=retain_day)
            if active_day > END_DAY:
                continue
            if retain_day == 1:
                probability = 0.48 if product[7] == "普通月卡" else 0.52
            elif retain_day == 2:
                probability = 0.16 if product[7] == "普通月卡" else 0.18
            elif retain_day <= 7:
                probability = max(0.028, 0.105 - retain_day * 0.012)
            else:
                probability = max(0.006, 0.026 - retain_day * 0.0007)
            if rng.random() < probability:
                add_retention_session(session_rows, player, active_day, session_id, rng)
                session_id += 1

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
                attributes, payment_source_channel, payment_level_bucket, gift_package_type,
                gift_package_group, gift_purchase_stage
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
                gift_package_type = EXCLUDED.gift_package_type,
                gift_package_group = EXCLUDED.gift_package_group,
                gift_purchase_stage = EXCLUDED.gift_purchase_stage
            """,
            payment_rows,
        )
    conn.commit()
    print(f"upserted gift sessions={len(session_rows)} events={len(event_rows)} payments={len(payment_rows)}")


GIFT_FILTER = """
p.payment_status = 'success'
AND p.net_revenue_usd > 0
AND p.order_id LIKE 'GIFTMOCK%'
"""

NEWBIE_REPEAT_SQL = f"""
WITH obs AS (
    SELECT max(event_date) AS max_date
    FROM public.fact_payments
    WHERE order_id LIKE 'GIFTMOCK%'
), weeks AS (
    SELECT generate_series(
        date_trunc('week', obs.max_date - 29)::date,
        date_trunc('week', obs.max_date)::date,
        interval '1 week'
    )::date AS week_start,
    obs.max_date
    FROM obs
), newbie AS (
    SELECT p.player_id,
           min(p.event_time) AS newbie_time,
           date_trunc('week', min(p.event_date))::date AS week_start
    FROM public.fact_payments p, obs
    WHERE {GIFT_FILTER}
      AND p.gift_package_type = '新手礼包'
      AND p.event_date BETWEEN obs.max_date - 29 AND obs.max_date
    GROUP BY p.player_id
), repeat_buy AS (
    SELECT n.week_start,
           n.player_id,
           ((date_trunc('week', p.event_date)::date - n.week_start) / 7)::int AS week_offset
    FROM newbie n
    JOIN public.fact_payments p ON p.player_id = n.player_id
    WHERE {GIFT_FILTER}
      AND p.event_time > n.newbie_time
      AND p.gift_package_group IS NOT NULL
      AND ((date_trunc('week', p.event_date)::date - n.week_start) / 7)::int BETWEEN 0 AND 4
    GROUP BY n.week_start, n.player_id, ((date_trunc('week', p.event_date)::date - n.week_start) / 7)::int
), weekly AS (
    SELECT w.week_start,
           count(DISTINCT n.player_id) AS buyers,
           count(DISTINCT rb.player_id) FILTER (WHERE rb.week_offset = 0) AS w0,
           count(DISTINCT rb.player_id) FILTER (WHERE rb.week_offset = 1) AS w1,
           count(DISTINCT rb.player_id) FILTER (WHERE rb.week_offset = 2) AS w2,
           count(DISTINCT rb.player_id) FILTER (WHERE rb.week_offset = 3) AS w3,
           count(DISTINCT rb.player_id) FILTER (WHERE rb.week_offset = 4) AS w4,
           w.max_date
    FROM weeks w
    LEFT JOIN newbie n ON n.week_start = w.week_start
    LEFT JOIN repeat_buy rb ON rb.week_start = w.week_start AND rb.player_id = n.player_id
    GROUP BY w.week_start, w.max_date
), rows AS (
    SELECT 0 AS sort_no,
           '阶段值' AS "日期",
           sum(buyers) AS "购买新手礼包用户数",
           sum(w0) AS w0, sum(w1) AS w1, sum(w2) AS w2, sum(w3) AS w3, sum(w4) AS w4,
           sum(buyers) AS denom,
           max(max_date) AS max_date,
           null::date AS week_start
    FROM weekly
    UNION ALL
    SELECT 1 AS sort_no,
           to_char(week_start, 'YYYY-MM-DD') || '当周' AS "日期",
           buyers AS "购买新手礼包用户数",
           w0, w1, w2, w3, w4,
           buyers AS denom,
           max_date,
           week_start
    FROM weekly
)
SELECT "日期",
       "购买新手礼包用户数",
       CASE WHEN denom > 0 THEN w0::text || chr(10) || round(w0::numeric / denom * 100, 2)::text || '%' ELSE '-' END AS "当周",
       CASE WHEN sort_no = 0 OR week_start + 7 <= max_date THEN w1::text || chr(10) || round(w1::numeric / nullif(denom, 0) * 100, 2)::text || '%' ELSE '-' END AS "第1周",
       CASE WHEN sort_no = 0 OR week_start + 14 <= max_date THEN w2::text || chr(10) || round(w2::numeric / nullif(denom, 0) * 100, 2)::text || '%' ELSE '-' END AS "第2周",
       CASE WHEN sort_no = 0 OR week_start + 21 <= max_date THEN w3::text || chr(10) || round(w3::numeric / nullif(denom, 0) * 100, 2)::text || '%' ELSE '-' END AS "第3周",
       CASE WHEN sort_no = 0 OR week_start + 28 <= max_date THEN w4::text || chr(10) || round(w4::numeric / nullif(denom, 0) * 100, 2)::text || '%' ELSE '-' END AS "第4周"
FROM rows
ORDER BY sort_no, week_start
"""

MONTHLY_30D_RETENTION_SQL = f"""
WITH obs AS (
    SELECT max(event_date) AS max_date
    FROM public.fact_payments
    WHERE order_id LIKE 'GIFTMOCK%'
), first_card AS (
    SELECT DISTINCT ON (p.player_id, p.gift_package_type)
           p.player_id,
           p.gift_package_type,
           p.event_date AS buy_date
    FROM public.fact_payments p, obs
    WHERE {GIFT_FILTER}
      AND p.gift_package_type IN ('普通月卡', '超级月卡')
      AND p.event_date BETWEEN obs.max_date - 74 AND obs.max_date - 30
    ORDER BY p.player_id, p.gift_package_type, p.event_time
), day_index AS (
    SELECT generate_series(0, 30) AS retain_day
), series AS (
    SELECT '总体' AS gift_package_type, 1 AS sort_no
    UNION ALL SELECT '普通月卡', 2
    UNION ALL SELECT '超级月卡', 3
), cohort AS (
    SELECT s.gift_package_type AS series_name,
           fc.player_id,
           fc.buy_date
    FROM series s
    JOIN first_card fc ON s.gift_package_type = '总体' OR s.gift_package_type = fc.gift_package_type
), retained AS (
    SELECT c.series_name,
           d.retain_day,
           count(DISTINCT c.player_id) AS cohort_users,
           count(DISTINCT c.player_id) FILTER (
               WHERE EXISTS (
                   SELECT 1
                   FROM public.fact_sessions fs
                   WHERE fs.player_id = c.player_id
                     AND fs.session_start::date = c.buy_date + d.retain_day
               )
           ) AS retained_users
    FROM cohort c
    CROSS JOIN day_index d
    GROUP BY c.series_name, d.retain_day
)
SELECT CASE WHEN r.retain_day = 0 THEN '当日' ELSE '第' || r.retain_day::text || '日' END AS "留存日",
       r.series_name AS "礼包类型",
       round(r.retained_users::numeric / nullif(r.cohort_users, 0) * 100, 2) AS "留存率"
FROM retained r
JOIN series s ON s.gift_package_type = r.series_name
ORDER BY r.retain_day, s.sort_no
"""


CHARTS = [
    {
        "id": "2193000000000000001",
        "title": "购买新手礼包用户复购率",
        "type": "table",
        "layout": (1, 1, 72, 18),
        "sql": NEWBIE_REPEAT_SQL,
        "x": [],
        "y": [],
        "series": [],
    },
    {
        "id": "2193000000000000002",
        "title": "购买月卡用户的30日留存",
        "type": "line",
        "layout": (1, 19, 72, 18),
        "sql": MONTHLY_30D_RETENTION_SQL,
        "x": [axis("留存日", axis_type="x")],
        "y": [axis("留存率", axis_type="y")],
        "series": [axis("礼包类型", axis_type="series")],
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
    backup_path = BACKUP_DIR / f"gift_package_dashboard_{DASHBOARD_ID}_{int(time.time())}.json"
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
                raise RuntimeError(f"Gift package dashboard does not exist: {DASHBOARD_ID}")
            if dashboard["datasource"] != DATASOURCE_ID:
                raise RuntimeError(f"Gift package dashboard datasource={dashboard['datasource']}, expected {DATASOURCE_ID}")

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
            SELECT count(*) FILTER (WHERE order_id LIKE 'GIFTMOCK%') AS gift_payments,
                   min(event_date) FILTER (WHERE order_id LIKE 'GIFTMOCK%') AS min_date,
                   max(event_date) FILTER (WHERE order_id LIKE 'GIFTMOCK%') AS max_date,
                   count(DISTINCT player_id) FILTER (WHERE order_id LIKE 'GIFTMOCK%') AS payers
            FROM public.fact_payments
            """
        )
        print("verify_payments=" + json.dumps(normalize_row(dict(cur.fetchone())), ensure_ascii=False))
        cur.execute(
            """
            SELECT count(*) FILTER (WHERE session_uid LIKE 'gift_mock_%') AS gift_sessions
            FROM public.fact_sessions
            """
        )
        print("verify_sessions=" + json.dumps(normalize_row(dict(cur.fetchone())), ensure_ascii=False))
        cur.execute(
            """
            SELECT count(*) FILTER (WHERE event_uid LIKE 'gift_mock_%') AS gift_events
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
    ensure_gift_columns(conn)
    seed_products(conn)
    players = load_players(conn)
    if not players:
        raise RuntimeError("No eligible players for gift package seed")
    session_rows, event_rows, payment_rows = build_detail_rows(players)
    upsert_detail_rows(conn, session_rows, event_rows, payment_rows)
    ensure_gift_columns(conn)


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
