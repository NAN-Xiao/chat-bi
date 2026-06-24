"""Lightweight seed for SLG BI Mock core dashboard gaps.

This script targets the tracking/detail BI database:
    127.0.0.1:5432 / slg_bi_mock / postgres / 111111

It only fills the current gaps needed by the core dashboard reference:
- extend detail data from 2026-06-13 through 2026-06-21;
- add gift/month-card product dimension rows used by the reference dashboard;
- add matching detail-level sessions, events, and payments.

It does not create aggregate KPI tables, snapshot tables, or analysis views.
All generated rows use core_gap_* / GAPMOCK prefixes and are removed before reseeding.
"""
from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import psycopg


TZ = ZoneInfo("Asia/Shanghai")
START_DATE = date(2026, 6, 13)
END_DATE = date(2026, 6, 21)
PLAYER_ID_START = 900_000
SESSION_ID_START = 9_000_000

DAILY_NEW_USERS = {
    date(2026, 6, 13): 180,
    date(2026, 6, 14): 190,
    date(2026, 6, 15): 130,
    date(2026, 6, 16): 135,
    date(2026, 6, 17): 125,
    date(2026, 6, 18): 130,
    date(2026, 6, 19): 185,
    date(2026, 6, 20): 190,
    date(2026, 6, 21): 180,
}

RETENTION_RATE = {
    0: 1.00,
    1: 0.43,
    2: 0.18,
    3: 0.11,
    4: 0.08,
    5: 0.07,
    6: 0.06,
    7: 0.052,
    8: 0.047,
}

CORE_PRODUCTS = [
    ("core_gap_pack_6", "6元", "gift_pack", Decimal("6.00"), "daily", 1, False),
    ("core_gap_event_pack", "活动礼包", "event_pack", Decimal("68.00"), "event", 3, False),
    ("core_gap_pack_12", "12元", "gift_pack", Decimal("12.00"), "daily", 2, False),
    ("core_gap_event_big_pack", "活动大礼包", "event_pack", Decimal("128.00"), "event", 8, False),
    ("core_gap_pack_30", "30元", "gift_pack", Decimal("30.00"), "daily", 5, False),
    ("core_gap_monthly_card", "普通月卡", "subscription", Decimal("30.00"), "monthly", 4, False),
    ("core_gap_pack_68", "68元", "gift_pack", Decimal("68.00"), "weekly", 8, False),
    ("core_gap_super_monthly_card", "超级月卡", "subscription", Decimal("98.00"), "monthly", 8, False),
    ("core_gap_newbie_pack", "新手礼包", "starter", Decimal("6.00"), "once", 1, True),
]

PRODUCT_WEIGHTS = [
    ("core_gap_pack_6", 0.22),
    ("core_gap_event_pack", 0.16),
    ("core_gap_pack_12", 0.12),
    ("core_gap_event_big_pack", 0.09),
    ("core_gap_pack_30", 0.08),
    ("core_gap_monthly_card", 0.07),
    ("core_gap_pack_68", 0.07),
    ("core_gap_super_monthly_card", 0.05),
    ("core_gap_newbie_pack", 0.06),
    ("resource_pack_1999", 0.04),
    ("speedup_pack_999", 0.04),
]

CHANNELS = [
    ("iOS,app store", "ios", 0.42),
    ("google_play", "android", 0.18),
    ("facebook_ads", "android", 0.13),
    ("tiktok_ads", "android", 0.11),
    ("organic", "android", 0.10),
    ("huawei_store", "android", 0.06),
]
COUNTRIES = [("CN", "zh-CN", 0.58), ("TW", "zh-TW", 0.10), ("US", "en", 0.10), ("JP", "ja", 0.08), ("KR", "ko", 0.06), ("TH", "th", 0.04), ("VN", "vi", 0.04)]
IOS_MODELS = ["iPhone 14", "iPhone 15", "iPhone 15 Pro", "iPhone 16"]
ANDROID_MODELS = ["Xiaomi 15", "Huawei Mate 70", "OPPO Find X8", "vivo X200", "Samsung S25"]


@dataclass
class Player:
    player_id: int
    account_id: str
    role_id: str
    device_id: str
    install_date: date
    register_time: datetime
    country: str
    language: str
    platform: str
    channel: str
    campaign: str
    device_tier: str
    device_model: str
    os_version: str
    server_id: int
    activity_segment: str
    payer_segment: str
    current_level: int = 1
    current_vip_level: int = 0
    current_power: int = 1200
    current_city_level: int = 1
    first_pay_time: datetime | None = None
    total_pay_amount: Decimal = Decimal("0.00")
    last_active_date: date | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed lightweight core dashboard gap data.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--db-name", default="slg_bi_mock")
    parser.add_argument("--user", default="postgres")
    parser.add_argument("--password", default="111111")
    parser.add_argument("--seed", type=int, default=20260624)
    return parser.parse_args()


def weighted_choice(items):
    values = [item[0] for item in items]
    weights = [item[-1] for item in items]
    return random.choices(values, weights=weights, k=1)[0]


def weighted_tuple(items):
    weights = [item[-1] for item in items]
    return random.choices(items, weights=weights, k=1)[0]


def day_dt(day: date, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute, second), tzinfo=TZ)


def daterange(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def cleanup(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("set session_replication_role = replica")
        cur.execute("delete from fact_payments where order_id like 'GAPMOCK%'")
        cur.execute("delete from fact_events where event_uid like 'core_gap_%'")
        cur.execute("delete from fact_sessions where session_uid like 'core_gap_%'")
        cur.execute("delete from dim_player where account_id like 'core_gap_%'")
        cur.execute("delete from dim_product where product_id like 'core_gap_%'")
        cur.execute("set session_replication_role = origin")
    conn.commit()


def seed_products(conn: psycopg.Connection) -> dict[str, tuple[str, Decimal]]:
    with conn.cursor() as cur:
        cur.executemany(
            """
            insert into dim_product (
                product_id, product_name, product_type, price_usd, limit_type, unlock_level, is_first_pay_pack
            ) values (%s,%s,%s,%s,%s,%s,%s)
            on conflict (product_id) do update set
                product_name=excluded.product_name,
                product_type=excluded.product_type,
                price_usd=excluded.price_usd,
                limit_type=excluded.limit_type,
                unlock_level=excluded.unlock_level,
                is_first_pay_pack=excluded.is_first_pay_pack
            """,
            CORE_PRODUCTS,
        )
        cur.execute("select product_id, product_name, price_usd from dim_product")
        result = {row[0]: (row[1], Decimal(row[2])) for row in cur.fetchall()}
    conn.commit()
    return result


def load_servers(conn: psycopg.Connection) -> list[int]:
    with conn.cursor() as cur:
        cur.execute("select server_id from dim_server order by server_id")
        return [row[0] for row in cur.fetchall()]


def device_for(platform: str) -> tuple[str, str, str]:
    if platform == "ios":
        return "high", random.choice(IOS_MODELS), f"iOS {random.choice(['17.5', '18.0', '18.1'])}"
    return str(weighted_choice([("mid", 0.60), ("high", 0.34), ("ultra", 0.06)])), random.choice(ANDROID_MODELS), f"Android {random.choice(['13', '14', '15'])}"


def vip_level(total_paid: Decimal) -> int:
    thresholds = [0, 6, 30, 68, 128, 300, 680, 1200, 2500, 5000]
    level = 0
    amount = float(total_paid)
    for idx, threshold in enumerate(thresholds):
        if amount >= threshold:
            level = idx
    return level


def build_players(servers: list[int]) -> list[Player]:
    players = []
    player_id = PLAYER_ID_START
    for day in daterange(START_DATE, END_DATE):
        for index in range(DAILY_NEW_USERS[day]):
            channel, platform, _ = weighted_tuple(CHANNELS)
            country, language, _ = weighted_tuple(COUNTRIES)
            device_tier, device_model, os_version = device_for(platform)
            payer_segment = str(weighted_choice([("non_spender", 0.70), ("minnow", 0.20), ("dolphin", 0.08), ("whale", 0.02)]))
            activity_segment = str(weighted_choice([("casual", 0.45), ("regular", 0.32), ("engaged", 0.16), ("social", 0.05), ("hardcore", 0.02)]))
            register_time = day_dt(day, int(weighted_choice([(9, 0.12), (12, 0.16), (18, 0.22), (20, 0.34), (22, 0.16)])), random.randint(0, 59), random.randint(0, 59))
            players.append(
                Player(
                    player_id=player_id,
                    account_id=f"core_gap_acc_{player_id}",
                    role_id=f"core_gap_role_{player_id}",
                    device_id=f"core_gap_dev_{player_id}",
                    install_date=day,
                    register_time=register_time,
                    country=country,
                    language=language,
                    platform=platform,
                    channel=channel,
                    campaign=f"core_gap_{channel.replace(',', '_')}_{day:%Y%m}",
                    device_tier=device_tier,
                    device_model=device_model,
                    os_version=os_version,
                    server_id=servers[(index + (day - START_DATE).days) % len(servers)],
                    activity_segment=activity_segment,
                    payer_segment=payer_segment,
                    current_power=random.randint(900, 1500),
                )
            )
            player_id += 1
    return players


def add_event(event_rows: list[tuple], event_no: int, player: Player, event_time: datetime, session_id: int, event_name: str, category: str, lifecycle_day: int, seq: int, attrs: dict, source: str = "client") -> tuple[str, int]:
    event_uid = f"core_gap_evt_{event_no:010d}"
    event_rows.append(
        (
            event_uid,
            f"core_gap_cli_{event_no:010d}",
            f"core_gap_trace_{session_id}_{seq}",
            event_time,
            event_time,
            event_time + timedelta(milliseconds=random.randint(80, 2200)),
            event_time + timedelta(milliseconds=random.randint(800, 4200)),
            event_time.date(),
            player.player_id,
            player.account_id,
            player.role_id,
            player.device_id,
            player.server_id,
            session_id,
            event_name,
            category,
            lifecycle_day,
            player.current_level,
            player.current_vip_level,
            player.current_power,
            None,
            "1.2.0",
            102000,
            "slg-sdk-4.0.2",
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
            str(weighted_choice([("wifi", 0.58), ("5g", 0.24), ("4g", 0.16), ("unknown", 0.02)])),
            source,
            seq,
            json.dumps(attrs, ensure_ascii=False),
        )
    )
    return event_uid, event_no + 1


def seed_detail_rows(conn: psycopg.Connection, products: dict[str, tuple[str, Decimal]], players: list[Player]) -> None:
    cohorts: dict[date, list[Player]] = {}
    for player in players:
        cohorts.setdefault(player.install_date, []).append(player)

    session_rows: list[tuple] = []
    event_rows: list[tuple] = []
    payment_rows: list[tuple] = []
    session_id = SESSION_ID_START
    event_no = 1
    order_no = 1
    pay_seq: dict[int, int] = {}

    for install_day, cohort in cohorts.items():
        random.shuffle(cohort)
        for lifecycle_day, retention in RETENTION_RATE.items():
            current_day = install_day + timedelta(days=lifecycle_day)
            if current_day > END_DATE:
                continue
            active_players = cohort[: round(len(cohort) * retention)]
            for player in active_players:
                player.last_active_date = current_day
                player.current_level = max(player.current_level, min(72, 1 + lifecycle_day // 2 + random.randint(0, 2)))
                player.current_city_level = max(player.current_city_level, min(30, player.current_level // 2 + 1))
                player.current_power += random.randint(80, 260)
                start = day_dt(current_day, int(weighted_choice([(9, 0.08), (12, 0.14), (18, 0.24), (20, 0.40), (22, 0.14)])), random.randint(0, 59), random.randint(0, 45))
                duration = random.randint(8, 32) * 60
                end = min(start + timedelta(seconds=duration), day_dt(current_day, 23, 59, 59))
                duration = int((end - start).total_seconds())
                session_uid = f"core_gap_sess_{session_id}"
                session_rows.append(
                    (
                        session_id,
                        session_uid,
                        player.player_id,
                        player.account_id,
                        player.role_id,
                        player.device_id,
                        player.server_id,
                        start,
                        end,
                        duration,
                        lifecycle_day,
                        max(1, player.current_level - 1),
                        player.current_level,
                        max(900, player.current_power - random.randint(20, 120)),
                        player.current_power,
                        player.platform,
                        player.channel,
                        player.campaign,
                        "1.2.0",
                        102000,
                        "slg-sdk-4.0.2",
                        player.device_tier,
                        player.device_model,
                        player.os_version,
                        "wifi",
                        player.country,
                        player.country,
                    )
                )

                seq = 1
                event_time = start + timedelta(seconds=2)
                _, event_no = add_event(event_rows, event_no, player, event_time, session_id, "app_start", "session", lifecycle_day, seq, {"network_type": "wifi"})
                seq += 1
                _, event_no = add_event(event_rows, event_no, player, event_time + timedelta(seconds=3), session_id, "login", "session", lifecycle_day, seq, {"login_day": lifecycle_day})
                seq += 1
                if lifecycle_day == 0:
                    for event_name, category, attrs in [
                        ("device_register", "account", {"device_id": player.device_id}),
                        ("install", "account", {"campaign_id": player.campaign, "ad_channel": player.channel}),
                        ("register", "account", {"server_id": player.server_id, "role_id": player.role_id}),
                        ("server_select", "account", {"server_code": f"K{player.server_id}"}),
                    ]:
                        _, event_no = add_event(event_rows, event_no, player, event_time + timedelta(seconds=seq * 4), session_id, event_name, category, lifecycle_day, seq, attrs)
                        seq += 1
                    tutorial_target = int(weighted_choice([(4, 0.04), (6, 0.08), (8, 0.12), (10, 0.18), (12, 0.58)]))
                    for step in range(1, tutorial_target + 1):
                        tutorial_attrs = {
                            "step": step,
                            "chapter": int((step + 3) // 4),
                        }
                        _, event_no = add_event(event_rows, event_no, player, event_time + timedelta(seconds=40 + step * 5), session_id, "tutorial_step", "tutorial", lifecycle_day, seq, tutorial_attrs)
                        seq += 1

                if random.random() < (0.22 if player.payer_segment == "non_spender" else 0.70):
                    shop_attrs = {
                        "shop_tab": str(weighted_choice([("daily_pack", 0.34), ("limited", 0.26), ("monthly_card", 0.18), ("event_pack", 0.22)])),
                    }
                    _, event_no = add_event(event_rows, event_no, player, event_time + timedelta(seconds=90), session_id, "shop_view", "monetization", lifecycle_day, seq, shop_attrs)
                    seq += 1

                should_pay = random.random() < {"non_spender": 0.006, "minnow": 0.16, "dolphin": 0.36, "whale": 0.62}[player.payer_segment]
                if should_pay:
                    orders = 1 + (1 if player.payer_segment in {"dolphin", "whale"} and random.random() < 0.25 else 0)
                    for order_idx in range(orders):
                        product_id = str(weighted_choice(PRODUCT_WEIGHTS))
                        product_name, amount = products[product_id]
                        order_id = f"GAPMOCK{current_day:%Y%m%d}{order_no:06d}"
                        order_no += 1
                        pay_time = event_time + timedelta(seconds=120 + order_idx * 35)
                        purchase_start_attrs = {
                            "order_id": order_id,
                            "product_id": product_id,
                            "price_usd": str(amount),
                        }
                        start_uid, event_no = add_event(event_rows, event_no, player, pay_time, session_id, "purchase_start", "monetization", lifecycle_day, seq, purchase_start_attrs)
                        seq += 1
                        first_pay = player.first_pay_time is None
                        purchase_success_attrs = {
                            "order_id": order_id,
                            "product_id": product_id,
                            "amount_usd": str(amount),
                            "is_first_pay": first_pay,
                        }
                        final_uid, event_no = add_event(event_rows, event_no, player, pay_time + timedelta(seconds=random.randint(3, 12)), session_id, "purchase_success", "monetization", lifecycle_day, seq, purchase_success_attrs, "server")
                        seq += 1
                        if first_pay:
                            player.first_pay_time = pay_time
                        player.total_pay_amount += amount
                        player.current_vip_level = vip_level(player.total_pay_amount)
                        pay_seq[player.player_id] = pay_seq.get(player.player_id, 0) + 1
                        payment_rows.append(
                            (
                                order_id,
                                start_uid,
                                final_uid,
                                pay_time,
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
                                "CNY" if player.country in {"CN", "TW", "HK"} else "USD",
                                "app_store" if player.platform == "ios" else "google_play",
                                "success",
                                None,
                                None,
                                first_pay,
                                pay_seq[player.player_id],
                                lifecycle_day,
                                player.current_vip_level,
                                player.current_level,
                                "whale" if amount >= Decimal("68") else "mid" if amount >= Decimal("12") else "low",
                                json.dumps({"source": "core_gap_seed", "payer_segment": player.payer_segment}, ensure_ascii=False),
                            )
                        )

                _, event_no = add_event(event_rows, event_no, player, end, session_id, "logout", "session", lifecycle_day, seq, {"duration_seconds": duration})
                session_id += 1

    player_rows = [
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
            p.activity_segment,
            p.payer_segment,
            p.current_level,
            p.current_vip_level,
            p.current_power,
            p.current_city_level,
            None,
            p.first_pay_time,
            p.total_pay_amount,
            p.last_active_date,
        )
        for p in players
    ]

    with conn.cursor() as cur:
        cur.executemany(
            """
            insert into dim_player (
                player_id, account_id, role_id, device_id, register_time, install_date, country, language,
                platform, channel, campaign, device_tier, device_model, os_version, register_server_id,
                activity_segment, payer_segment, current_level, current_vip_level, current_power,
                current_city_level, current_alliance_id, first_pay_time, total_pay_amount, last_active_date
            ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            player_rows,
        )
        cur.executemany(
            """
            insert into fact_sessions (
                session_id, session_uid, player_id, account_id, role_id, device_id, server_id, session_start,
                session_end, duration_seconds, lifecycle_day, player_level_start, player_level_end, power_start,
                power_end, platform, channel, campaign, client_version, app_build, sdk_version, device_tier,
                device_model, os_version, network_type, country, ip_country
            ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            session_rows,
        )
        cur.executemany(
            """
            insert into fact_events (
                event_uid, client_event_id, trace_id, event_time, client_time, server_receive_time, ingest_time,
                event_date, player_id, account_id, role_id, device_id, server_id, session_id, event_name,
                event_category, lifecycle_day, player_level, vip_level, power, alliance_id, client_version,
                app_build, sdk_version, event_schema_version, platform, channel, campaign, country, ip_country,
                language, device_model, os_version, device_tier, network_type, event_source,
                sequence_in_session, attributes
            ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            event_rows,
        )
        cur.executemany(
            """
            insert into fact_payments (
                order_id, start_event_uid, final_event_uid, event_time, event_date, player_id, server_id,
                session_id, product_id, product_name, amount_usd, gross_revenue_usd, refund_amount_usd,
                net_revenue_usd, local_currency, payment_channel, payment_status, fail_reason, refund_reason,
                is_first_pay, pay_sequence, lifecycle_day, vip_level_after, player_level, revenue_tier, attributes
            ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            payment_rows,
        )
    conn.commit()


def main() -> None:
    args = parse_args()
    random.seed(args.seed)
    with psycopg.connect(host=args.host, port=args.port, dbname=args.db_name, user=args.user, password=args.password) as conn:
        cleanup(conn)
        products = seed_products(conn)
        servers = load_servers(conn)
        players = build_players(servers)
        seed_detail_rows(conn, products, players)
    print(f"Seeded lightweight core gap data: {sum(DAILY_NEW_USERS.values())} players, {START_DATE} to {END_DATE}.")


if __name__ == "__main__":
    main()
