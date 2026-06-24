"""Seed diamond economy detail rows and create the SLG BI Mock economy dashboard.

Targets:
- BI tracking database: 127.0.0.1:5432 / slg_bi_mock / postgres / 111111
- App system database: 127.0.0.1:15432 / zhishu_bi / root / Password123@pg

The generated data stays at event/detail level:
- fact_events rows model resource_change tracking events;
- fact_resource_transactions rows model diamond resource ledger changes.

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

DASHBOARD_ID = "57f1225c0d3343fcbfd71efcff0f8e8b"
DATASOURCE_ID = 1
UPDATE_BY = "7471612174524223488"
BACKUP_DIR = Path(".codex-runtime/backups")

START_DAY = date(2026, 5, 25)
END_DAY = date(2026, 6, 23)
RESOURCE_TRANS_ID_START = 8_100_000

GAIN_PATHS = [
    ("新手奖励", "newbie_reward", Decimal("0.487"), False),
    ("充值", "payment_grant", Decimal("0.342"), True),
    ("签到", "daily_checkin", Decimal("0.145"), False),
    ("超级月卡", "super_monthly_card", Decimal("0.018"), True),
    ("月卡", "monthly_card", Decimal("0.008"), True),
]

SINK_PATHS = [
    ("抽卡", "gacha", Decimal("0.508"), False),
    ("商城购买", "shop_purchase", Decimal("0.224"), False),
    ("升级建筑加速", "building_speedup", Decimal("0.204"), False),
    ("购买建筑栏位", "extra_build_queue", Decimal("0.024"), False),
    ("研究科技加速", "research_speedup", Decimal("0.020"), False),
    ("公会捐赠", "alliance_donate", Decimal("0.011"), False),
    ("招募士兵加速", "troop_train_speedup", Decimal("0.009"), False),
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


def target_gain(day: date) -> int:
    if day == END_DAY:
        return 1_165_300
    base = 1_120_000 + ((day.toordinal() % 7) - 3) * 22_000
    if day.weekday() in {4, 5}:
        base += 360_000
    elif day.weekday() == 6:
        base += 120_000
    return max(860_000, base)


def target_sink(day: date) -> int:
    if day == END_DAY:
        return 990_500
    base = 950_000 + ((day.toordinal() % 7) - 3) * 20_000
    if day.weekday() in {4, 5}:
        base += 270_000
    elif day.weekday() == 6:
        base += 80_000
    return max(760_000, base)


def split_amount(total: int, pieces: int, rng: random.Random) -> list[int]:
    if pieces <= 1:
        return [total]
    weights = [rng.uniform(0.75, 1.35) for _ in range(pieces)]
    weight_sum = sum(weights)
    parts = [max(1, int(total * weight / weight_sum)) for weight in weights]
    delta = total - sum(parts)
    for index in range(abs(delta)):
        parts[index % len(parts)] += 1 if delta > 0 else -1
    return [part for part in parts if part > 0]


def path_amounts(total: int, paths: list[tuple[str, str, Decimal, bool]]) -> list[tuple[str, str, int, bool]]:
    amounts: list[tuple[str, str, int, bool]] = []
    allocated = 0
    for index, (path_name, reason, weight, is_paid_related) in enumerate(paths):
        if index == len(paths) - 1:
            amount = total - allocated
        else:
            amount = int((Decimal(total) * weight).quantize(Decimal("1")))
            allocated += amount
        amounts.append((path_name, reason, amount, is_paid_related))
    return amounts


def ensure_economy_columns(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            ALTER TABLE public.fact_resource_transactions
                ADD COLUMN IF NOT EXISTS resource_path_type text,
                ADD COLUMN IF NOT EXISTS resource_path_name text,
                ADD COLUMN IF NOT EXISTS economy_action text
            """
        )
        cur.execute(
            """
            UPDATE public.fact_resource_transactions
               SET resource_path_type = CASE WHEN change_amount >= 0 THEN 'gain' ELSE 'sink' END,
                   resource_path_name = reason,
                   economy_action = reason
             WHERE resource_path_type IS NULL
                OR resource_path_name IS NULL
                OR economy_action IS NULL
            """
        )
    conn.commit()


def load_session_candidates(conn: Any) -> dict[date, list[SessionCandidate]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT s.session_id, s.player_id, s.account_id, s.role_id, s.device_id,
                   s.server_id, s.session_start, s.lifecycle_day,
                   s.player_level_end AS player_level, p.current_vip_level AS vip_level,
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
        rows = [SessionCandidate(**dict(row)) for row in cur.fetchall()]
    by_day: dict[date, list[SessionCandidate]] = {}
    for row in rows:
        by_day.setdefault(row.session_start.date(), []).append(row)
    return by_day


def event_time_for(session: SessionCandidate, current_day: date, rng: random.Random) -> datetime:
    event_time = session.session_start + timedelta(minutes=rng.randint(2, 35), seconds=rng.randint(0, 45))
    return min(event_time, dt_at(current_day, 23, 59, 30))


def build_event_row(
    event_uid: str,
    session: SessionCandidate,
    event_time: datetime,
    signed_amount: int,
    path_type: str,
    path_name: str,
    reason: str,
    sequence: int,
) -> tuple:
    attributes = {
        "resource_type": "diamond",
        "change_amount": signed_amount,
        "path_type": path_type,
        "path_name": path_name,
        "reason": reason,
    }
    return (
        event_uid,
        f"econ_mock_cli_{event_uid}",
        f"econ_mock_trace_{session.session_id}_{sequence}",
        event_time,
        event_time,
        event_time + timedelta(milliseconds=320),
        event_time + timedelta(seconds=1),
        event_time.date(),
        session.player_id,
        session.account_id,
        session.role_id,
        session.device_id,
        session.server_id,
        session.session_id,
        "resource_change",
        "economy",
        session.lifecycle_day,
        session.player_level,
        session.vip_level,
        session.power,
        None,
        session.client_version,
        session.app_build,
        session.sdk_version,
        "slg_event_v4",
        session.platform,
        session.channel,
        session.campaign,
        session.country,
        session.ip_country,
        session.language,
        session.device_model,
        session.os_version,
        session.device_tier,
        session.network_type,
        "server",
        sequence,
        json.dumps(attributes, ensure_ascii=False),
    )


def build_detail_rows(by_day: dict[date, list[SessionCandidate]]) -> tuple[list[tuple], list[tuple]]:
    rng = random.Random(20260628)
    balances: dict[int, int] = {}
    event_rows: list[tuple] = []
    resource_rows: list[tuple] = []
    trans_id = RESOURCE_TRANS_ID_START

    for day_offset in range((END_DAY - START_DAY).days + 1):
        current_day = START_DAY + timedelta(days=day_offset)
        sessions = by_day.get(current_day, [])
        if not sessions:
            continue
        daily_rows: list[tuple[str, str, str, int, bool]] = []
        for path_name, reason, amount, is_paid_related in path_amounts(target_gain(current_day), GAIN_PATHS):
            daily_rows.extend(("gain", path_name, reason, part, is_paid_related) for part in split_amount(amount, 10, rng))
        for path_name, reason, amount, is_paid_related in path_amounts(target_sink(current_day), SINK_PATHS):
            daily_rows.extend(("sink", path_name, reason, part, is_paid_related) for part in split_amount(amount, 8, rng))

        rng.shuffle(daily_rows)
        for sequence, (path_type, path_name, reason, amount, is_paid_related) in enumerate(daily_rows, start=1):
            session = rng.choice(sessions)
            signed_amount = amount if path_type == "gain" else -amount
            current_balance = balances.setdefault(session.player_id, rng.randint(8_000, 80_000))
            if current_balance + signed_amount < 0:
                current_balance = abs(signed_amount) + rng.randint(8_000, 35_000)
            balance_after = current_balance + signed_amount
            balances[session.player_id] = balance_after
            event_time = event_time_for(session, current_day, rng)
            event_uid = f"econ_mock_evt_{trans_id}"
            event_rows.append(build_event_row(event_uid, session, event_time, signed_amount, path_type, path_name, reason, sequence))
            resource_rows.append(
                (
                    trans_id,
                    event_uid,
                    None,
                    event_time,
                    current_day,
                    session.player_id,
                    session.server_id,
                    session.session_id,
                    "diamond",
                    signed_amount,
                    balance_after,
                    path_type,
                    reason,
                    is_paid_related,
                    json.dumps(
                        {
                            "source": "econ_mock_seed",
                            "path_name": path_name,
                            "path_type": path_type,
                            "daily_target": target_gain(current_day) if path_type == "gain" else target_sink(current_day),
                        },
                        ensure_ascii=False,
                    ),
                    path_type,
                    path_name,
                    reason,
                )
            )
            trans_id += 1

    return event_rows, resource_rows


def upsert_detail_rows(conn: Any, event_rows: list[tuple], resource_rows: list[tuple]) -> None:
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
            INSERT INTO public.fact_resource_transactions (
                trans_id, event_uid, business_event_uid, event_time, event_date, player_id, server_id,
                session_id, resource_type, change_amount, balance_after, source_sink, reason,
                is_paid_related, attributes, resource_path_type, resource_path_name, economy_action
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (trans_id) DO UPDATE SET
                event_uid = EXCLUDED.event_uid,
                business_event_uid = EXCLUDED.business_event_uid,
                event_time = EXCLUDED.event_time,
                event_date = EXCLUDED.event_date,
                player_id = EXCLUDED.player_id,
                server_id = EXCLUDED.server_id,
                session_id = EXCLUDED.session_id,
                resource_type = EXCLUDED.resource_type,
                change_amount = EXCLUDED.change_amount,
                balance_after = EXCLUDED.balance_after,
                source_sink = EXCLUDED.source_sink,
                reason = EXCLUDED.reason,
                is_paid_related = EXCLUDED.is_paid_related,
                attributes = EXCLUDED.attributes,
                resource_path_type = EXCLUDED.resource_path_type,
                resource_path_name = EXCLUDED.resource_path_name,
                economy_action = EXCLUDED.economy_action
            """,
            resource_rows,
        )
    conn.commit()
    print(f"upserted economy events={len(event_rows)} resource_transactions={len(resource_rows)}")


ECONOMY_FILTER = """
resource_type = 'diamond'
AND event_uid LIKE 'econ_mock_%'
"""

DIAMOND_OVERVIEW_SQL = f"""
WITH obs AS (
    SELECT max(event_date) AS max_date
    FROM public.fact_resource_transactions
    WHERE {ECONOMY_FILTER}
), days AS (
    SELECT generate_series(max_date - 29, max_date, interval '1 day')::date AS dt
    FROM obs
), daily AS (
    SELECT event_date AS dt,
           sum(change_amount) FILTER (WHERE change_amount > 0) AS gain_amount,
           sum(-change_amount) FILTER (WHERE change_amount < 0) AS sink_amount,
           sum(change_amount) AS net_change,
           count(DISTINCT player_id) AS users
    FROM public.fact_resource_transactions, obs
    WHERE {ECONOMY_FILTER}
      AND event_date BETWEEN obs.max_date - 29 AND obs.max_date
    GROUP BY event_date
)
SELECT d.dt AS "日期",
       round(coalesce(daily.gain_amount, 0)::numeric / 10000, 2) AS "钻石获取量",
       round(coalesce(daily.sink_amount, 0)::numeric / 10000, 2) AS "钻石消耗量",
       round(coalesce(daily.net_change, 0)::numeric / 10000, 2) AS "钻石存量变化",
       round(coalesce(daily.net_change, 0)::numeric / nullif(daily.users, 0) / 10000, 4) AS "钻石人均存量变化"
FROM days d
LEFT JOIN daily ON daily.dt = d.dt
ORDER BY d.dt
"""

GAIN_PATH_SQL = f"""
WITH obs AS (
    SELECT max(event_date) AS max_date
    FROM public.fact_resource_transactions
    WHERE {ECONOMY_FILTER}
), days AS (
    SELECT generate_series(max_date - 29, max_date, interval '1 day')::date AS dt
    FROM obs
), paths AS (
    SELECT *
    FROM (VALUES
        ('新手奖励', 1),
        ('充值', 2),
        ('签到', 3),
        ('超级月卡', 4),
        ('月卡', 5)
    ) AS t(path_name, sort_no)
), daily_path AS (
    SELECT event_date AS dt,
           resource_path_name AS path_name,
           sum(change_amount) AS gain_amount
    FROM public.fact_resource_transactions, obs
    WHERE {ECONOMY_FILTER}
      AND resource_path_type = 'gain'
      AND change_amount > 0
      AND event_date BETWEEN obs.max_date - 29 AND obs.max_date
    GROUP BY event_date, resource_path_name
)
SELECT d.dt AS "日期",
       p.path_name AS "获取途径",
       round(coalesce(dp.gain_amount, 0)::numeric / 10000, 2) AS "钻石获取量"
FROM days d
CROSS JOIN paths p
LEFT JOIN daily_path dp
  ON dp.dt = d.dt
 AND dp.path_name = p.path_name
ORDER BY d.dt, p.sort_no
"""

SINK_PATH_SQL = f"""
WITH obs AS (
    SELECT max(event_date) AS max_date
    FROM public.fact_resource_transactions
    WHERE {ECONOMY_FILTER}
), days AS (
    SELECT generate_series(max_date - 29, max_date, interval '1 day')::date AS dt
    FROM obs
), paths AS (
    SELECT *
    FROM (VALUES
        ('抽卡', 1),
        ('商城购买', 2),
        ('升级建筑加速', 3),
        ('购买建筑栏位', 4),
        ('研究科技加速', 5),
        ('公会捐赠', 6),
        ('招募士兵加速', 7)
    ) AS t(path_name, sort_no)
), daily_path AS (
    SELECT event_date AS dt,
           resource_path_name AS path_name,
           sum(-change_amount) AS sink_amount
    FROM public.fact_resource_transactions, obs
    WHERE {ECONOMY_FILTER}
      AND resource_path_type = 'sink'
      AND change_amount < 0
      AND event_date BETWEEN obs.max_date - 29 AND obs.max_date
    GROUP BY event_date, resource_path_name
)
SELECT d.dt AS "日期",
       p.path_name AS "消耗途径",
       round(coalesce(dp.sink_amount, 0)::numeric / 10000, 2) AS "钻石消耗量"
FROM days d
CROSS JOIN paths p
LEFT JOIN daily_path dp
  ON dp.dt = d.dt
 AND dp.path_name = p.path_name
ORDER BY d.dt, p.sort_no
"""


CHARTS = [
    {
        "id": "2192000000000000001",
        "title": "钻石消耗获取情况",
        "type": "line",
        "layout": (1, 1, 72, 17),
        "sql": DIAMOND_OVERVIEW_SQL,
        "x": [axis("日期", axis_type="x")],
        "y": [
            axis("钻石获取量", axis_type="y", multi=True),
            axis("钻石消耗量", axis_type="y", multi=True),
            axis("钻石存量变化", axis_type="y", multi=True),
            axis("钻石人均存量变化", axis_type="y", multi=True),
        ],
        "series": [],
    },
    {
        "id": "2192000000000000002",
        "title": "钻石获取途径分布",
        "type": "line",
        "layout": (1, 18, 72, 17),
        "sql": GAIN_PATH_SQL,
        "x": [axis("日期", axis_type="x")],
        "y": [axis("钻石获取量", axis_type="y")],
        "series": [axis("获取途径", axis_type="series")],
    },
    {
        "id": "2192000000000000003",
        "title": "钻石消耗途径分布",
        "type": "line",
        "layout": (1, 35, 72, 17),
        "sql": SINK_PATH_SQL,
        "x": [axis("日期", axis_type="x")],
        "y": [axis("钻石消耗量", axis_type="y")],
        "series": [axis("消耗途径", axis_type="series")],
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
    backup_path = BACKUP_DIR / f"economy_dashboard_{DASHBOARD_ID}_{int(time.time())}.json"
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
                raise RuntimeError(f"Economy dashboard does not exist: {DASHBOARD_ID}")
            if dashboard["datasource"] != DATASOURCE_ID:
                raise RuntimeError(f"Economy dashboard datasource={dashboard['datasource']}, expected {DATASOURCE_ID}")

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
            SELECT count(*) FILTER (WHERE event_uid LIKE 'econ_mock_%') AS econ_transactions,
                   min(event_date) FILTER (WHERE event_uid LIKE 'econ_mock_%') AS min_date,
                   max(event_date) FILTER (WHERE event_uid LIKE 'econ_mock_%') AS max_date,
                   count(DISTINCT player_id) FILTER (WHERE event_uid LIKE 'econ_mock_%') AS players,
                   sum(change_amount) FILTER (WHERE event_uid LIKE 'econ_mock_%' AND change_amount > 0) AS gain_amount,
                   sum(-change_amount) FILTER (WHERE event_uid LIKE 'econ_mock_%' AND change_amount < 0) AS sink_amount
            FROM public.fact_resource_transactions
            """
        )
        print("verify_resource_transactions=" + json.dumps(normalize_row(dict(cur.fetchone())), ensure_ascii=False))
        cur.execute(
            """
            SELECT count(*) FILTER (WHERE event_uid LIKE 'econ_mock_%') AS econ_events
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
    ensure_economy_columns(conn)
    by_day = load_session_candidates(conn)
    event_rows, resource_rows = build_detail_rows(by_day)
    upsert_detail_rows(conn, event_rows, resource_rows)
    ensure_economy_columns(conn)


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
