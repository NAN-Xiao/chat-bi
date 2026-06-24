"""Seed activity detail events and create the SLG BI Mock activity dashboard.

Targets:
- BI tracking database: 127.0.0.1:5432 / slg_bi_mock / postgres / 111111
- App system database: 127.0.0.1:15432 / zhishu_bi / root / Password123@pg

The dataset remains event/detail-level. Activity metrics are computed from
fact_events, fact_sessions, and fact_payments at query time. No aggregate
tables, snapshot tables, or analysis views are created.
"""
from __future__ import annotations

import json
import random
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor
from zoneinfo import ZoneInfo


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

DASHBOARD_ID = "f3c72d29399b4936b4e8c4c934348859"
DATASOURCE_ID = 1
UPDATE_BY = "7471612174524223488"
BACKUP_DIR = Path(".codex-runtime/backups")

START_DAY = date(2026, 5, 25)
END_DAY = date(2026, 6, 23)

ACTIVITY_TYPES = [
    ("newbie", "新手活动", Decimal("0.62"), 1.16),
    ("festival", "节日活动", Decimal("0.20"), 0.34),
    ("weekly", "每周活动", Decimal("0.19"), 0.33),
    ("daily", "日常活动", Decimal("0.18"), 0.32),
]


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


def ensure_activity_columns(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            ALTER TABLE public.fact_events
                ADD COLUMN IF NOT EXISTS activity_id text,
                ADD COLUMN IF NOT EXISTS activity_type text,
                ADD COLUMN IF NOT EXISTS activity_stage integer,
                ADD COLUMN IF NOT EXISTS activity_participation_count integer
            """
        )
    conn.commit()


def seed_event_dictionary(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO public.dim_event_name (
                event_name, event_category, event_cn_name, description, required_attrs
            ) VALUES (
                'activity_participate',
                'activity',
                '活动参与',
                '玩家参与运营活动',
                '{"activity_id":"活动ID","activity_type":"活动类型","activity_stage":"活动阶段","participation_count":"本次会话参与次数"}'::jsonb
            )
            ON CONFLICT (event_name) DO UPDATE SET
                event_category = EXCLUDED.event_category,
                event_cn_name = EXCLUDED.event_cn_name,
                description = EXCLUDED.description,
                required_attrs = EXCLUDED.required_attrs
            """
        )
    conn.commit()


def cleanup(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM public.fact_events WHERE event_uid LIKE 'activity_mock_%'")
    conn.commit()


def load_session_candidates(conn: Any) -> dict[date, list[dict[str, Any]]]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT s.session_id, s.player_id, s.account_id, s.role_id, s.device_id, s.server_id,
                   s.session_start, s.lifecycle_day, s.player_level_end AS player_level,
                   s.power_end AS power, s.platform, s.channel, s.campaign,
                   s.client_version, s.app_build, s.sdk_version, s.device_tier,
                   s.device_model, s.os_version, s.network_type, s.country, s.ip_country,
                   p.language, p.current_vip_level AS vip_level
            FROM public.fact_sessions s
            JOIN public.dim_player p ON p.player_id = s.player_id
            WHERE s.session_start::date BETWEEN %s AND %s
            ORDER BY s.session_start, s.session_id
            """,
            (START_DAY, END_DAY),
        )
        rows = [dict(row) for row in cur.fetchall()]
    by_day: dict[date, list[dict[str, Any]]] = {}
    for row in rows:
        by_day.setdefault(row["session_start"].date(), []).append(row)
    return by_day


def target_rate(activity_key: str, day: date, base_rate: Decimal) -> float:
    wave = 0.015 * ((day.day % 7) - 3)
    if activity_key == "festival" and day.weekday() in {4, 5, 6}:
        wave += 0.035
    if activity_key == "weekly" and day.weekday() in {0, 1}:
        wave += 0.025
    if activity_key == "daily":
        wave += 0.012 * (1 if day.weekday() < 5 else -1)
    return max(0.04, min(0.76, float(base_rate) + wave))


def event_time_for(session: dict[str, Any], rng: random.Random) -> datetime:
    return session["session_start"] + timedelta(minutes=rng.randint(2, 35), seconds=rng.randint(0, 45))


def build_activity_events(by_day: dict[date, list[dict[str, Any]]]) -> list[tuple]:
    rng = random.Random(20260624)
    event_rows: list[tuple] = []
    event_no = 1

    for current_day in sorted(by_day):
        sessions = by_day[current_day]
        if not sessions:
            continue
        for activity_key, activity_name, base_rate, mean_count in ACTIVITY_TYPES:
            rate = target_rate(activity_key, current_day, base_rate)
            sample_size = min(len(sessions), round(len(sessions) * rate))
            sampled = rng.sample(sessions, sample_size)
            for session in sampled:
                participation_count = 1 + (1 if rng.random() < max(0, mean_count - 1) else 0)
                if activity_key == "newbie" and rng.random() < 0.12:
                    participation_count += 1
                stage = max(3, min(9, 3 + session["player_level"] // 10 + rng.randint(0, 1)))
                activity_id = f"{activity_key}_{current_day:%Y%m}"
                for seq_offset in range(participation_count):
                    event_uid = f"activity_mock_evt_{event_no:08d}"
                    event_no += 1
                    event_time = event_time_for(session, rng) + timedelta(minutes=seq_offset * 3)
                    attrs = {
                        "activity_id": activity_id,
                        "activity_type": activity_name,
                        "activity_stage": stage,
                        "participation_count": participation_count,
                    }
                    event_rows.append(
                        (
                            event_uid,
                            f"activity_mock_cli_{event_no:08d}",
                            f"activity_mock_trace_{session['session_id']}_{seq_offset + 1}",
                            event_time,
                            event_time,
                            event_time + timedelta(milliseconds=320),
                            event_time + timedelta(seconds=1),
                            current_day,
                            session["player_id"],
                            session["account_id"],
                            session["role_id"],
                            session["device_id"],
                            session["server_id"],
                            session["session_id"],
                            "activity_participate",
                            "activity",
                            session["lifecycle_day"],
                            session["player_level"],
                            session["vip_level"],
                            session["power"],
                            None,
                            session["client_version"],
                            session["app_build"],
                            session["sdk_version"],
                            "slg_event_v4",
                            session["platform"],
                            session["channel"],
                            session["campaign"],
                            session["country"],
                            session["ip_country"],
                            session["language"],
                            session["device_model"],
                            session["os_version"],
                            session["device_tier"],
                            session["network_type"],
                            "client",
                            50 + seq_offset,
                            json.dumps(attrs, ensure_ascii=False),
                            activity_id,
                            activity_name,
                            stage,
                            participation_count,
                        )
                    )
    return event_rows


def insert_activity_events(conn: Any, event_rows: list[tuple]) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO public.fact_events (
                event_uid, client_event_id, trace_id, event_time, client_time, server_receive_time, ingest_time,
                event_date, player_id, account_id, role_id, device_id, server_id, session_id, event_name,
                event_category, lifecycle_day, player_level, vip_level, power, alliance_id, client_version,
                app_build, sdk_version, event_schema_version, platform, channel, campaign, country, ip_country,
                language, device_model, os_version, device_tier, network_type, event_source,
                sequence_in_session, attributes, activity_id, activity_type, activity_stage,
                activity_participation_count
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            event_rows,
        )
    conn.commit()
    print(f"seeded activity events={len(event_rows)}")


ACTIVITY_BASE = """
WITH obs AS (
    SELECT max(event_date) AS max_date
    FROM public.fact_events
    WHERE event_category = 'activity'
), days AS (
    SELECT generate_series(max_date - 29, max_date, interval '1 day')::date AS dt
    FROM obs
)
"""

PARTICIPATION_RATE_SQL = ACTIVITY_BASE + """
, dau AS (
    SELECT s.session_start::date AS dt,
           count(DISTINCT s.player_id) AS active_users
    FROM public.fact_sessions s, obs
    WHERE s.session_start::date BETWEEN obs.max_date - 29 AND obs.max_date
    GROUP BY 1
), activity_users AS (
    SELECT e.event_date AS dt,
           e.activity_type,
           count(DISTINCT e.player_id) AS participants
    FROM public.fact_events e, obs
    WHERE e.event_category = 'activity'
      AND e.event_date BETWEEN obs.max_date - 29 AND obs.max_date
    GROUP BY 1, 2
)
SELECT d.dt AS "日期",
       '活动参与率.' || au.activity_type AS "活动类型",
       round(au.participants::numeric / nullif(dau.active_users, 0) * 100, 2) AS "活动参与率"
FROM days d
JOIN activity_users au ON au.dt = d.dt
JOIN dau ON dau.dt = d.dt
ORDER BY d.dt, "活动类型"
"""

AVG_PARTICIPATION_SQL = ACTIVITY_BASE + """
, activity_daily AS (
    SELECT e.event_date AS dt,
           e.activity_type,
           count(*) AS participations,
           count(DISTINCT e.player_id) AS participants
    FROM public.fact_events e, obs
    WHERE e.event_category = 'activity'
      AND e.event_date BETWEEN obs.max_date - 29 AND obs.max_date
    GROUP BY 1, 2
)
SELECT dt AS "日期",
       '活动人均参与次数.' || activity_type AS "活动类型",
       round(participations::numeric / nullif(participants, 0), 2) AS "人均参与次数"
FROM activity_daily
ORDER BY dt, "活动类型"
"""

STAGE_DISTRIBUTION_SQL = """
WITH obs AS (
    SELECT max(event_date) AS max_date
    FROM public.fact_events
    WHERE event_category = 'activity'
)
SELECT e.activity_stage AS "阶段",
       count(DISTINCT e.player_id) AS "参与人数"
FROM public.fact_events e, obs
WHERE e.event_category = 'activity'
  AND e.activity_type = '日常活动'
  AND e.event_date BETWEEN obs.max_date - 29 AND obs.max_date
GROUP BY e.activity_stage
ORDER BY e.activity_stage
"""

WEEKLY_COUNT_DISTRIBUTION_SQL = """
WITH obs AS (
    SELECT max(event_date) AS max_date
    FROM public.fact_events
    WHERE event_category = 'activity'
), player_week AS (
    SELECT date_trunc('week', e.event_date)::date AS week_start,
           e.player_id,
           count(*) AS participate_count
    FROM public.fact_events e, obs
    WHERE e.event_category = 'activity'
      AND e.event_date BETWEEN obs.max_date - 29 AND obs.max_date
    GROUP BY 1, 2
), bucketed AS (
    SELECT week_start,
           CASE
             WHEN participate_count < 2 THEN '[0, 2)次'
             WHEN participate_count < 4 THEN '[2, 4)次'
             WHEN participate_count < 6 THEN '[4, 6)次'
             WHEN participate_count < 8 THEN '[6, 8)次'
             WHEN participate_count < 10 THEN '[8, 10)次'
             WHEN participate_count < 12 THEN '[10, 12)次'
             WHEN participate_count < 14 THEN '[12, 14)次'
             WHEN participate_count < 16 THEN '[14, 16)次'
             ELSE '[16, +∞)次'
           END AS count_bucket,
           CASE
             WHEN participate_count < 2 THEN 1
             WHEN participate_count < 4 THEN 2
             WHEN participate_count < 6 THEN 3
             WHEN participate_count < 8 THEN 4
             WHEN participate_count < 10 THEN 5
             WHEN participate_count < 12 THEN 6
             WHEN participate_count < 14 THEN 7
             WHEN participate_count < 16 THEN 8
             ELSE 9
           END AS bucket_sort
    FROM player_week
)
SELECT to_char(week_start, 'YYYY-MM-DD') || '当周' AS "周",
       count_bucket AS "参与次数区间",
       count(*) AS "人数"
FROM bucketed
GROUP BY week_start, count_bucket, bucket_sort
ORDER BY week_start, bucket_sort
"""

NEWBIE_RETENTION_SQL = """
WITH obs AS (
    SELECT max(event_date) AS max_date
    FROM public.fact_events
    WHERE event_category = 'activity'
), cohort AS (
    SELECT e.event_date AS activity_date,
           e.player_id
    FROM public.fact_events e, obs
    WHERE e.event_category = 'activity'
      AND e.activity_type = '新手活动'
      AND e.event_date BETWEEN obs.max_date - 29 AND obs.max_date
    GROUP BY e.event_date, e.player_id
), retained AS (
    SELECT c.activity_date,
           c.player_id,
           gs.day AS retain_day,
           EXISTS (
               SELECT 1
               FROM public.fact_sessions s
               WHERE s.player_id = c.player_id
                 AND s.session_start::date = c.activity_date + gs.day
           ) AS retained
    FROM cohort c
    CROSS JOIN generate_series(0, 7) AS gs(day)
)
SELECT activity_date AS "日期",
       count(DISTINCT player_id) AS "参与新手活动用户数",
       count(DISTINCT player_id) FILTER (WHERE retain_day = 0 AND retained) AS "当日",
       count(DISTINCT player_id) FILTER (WHERE retain_day = 1 AND retained) AS "第1日",
       count(DISTINCT player_id) FILTER (WHERE retain_day = 2 AND retained) AS "第2日",
       count(DISTINCT player_id) FILTER (WHERE retain_day = 3 AND retained) AS "第3日",
       count(DISTINCT player_id) FILTER (WHERE retain_day = 4 AND retained) AS "第4日",
       count(DISTINCT player_id) FILTER (WHERE retain_day = 5 AND retained) AS "第5日",
       count(DISTINCT player_id) FILTER (WHERE retain_day = 6 AND retained) AS "第6日",
       count(DISTINCT player_id) FILTER (WHERE retain_day = 7 AND retained) AS "第7日"
FROM retained
GROUP BY activity_date
ORDER BY activity_date
"""

FESTIVAL_PAY_RETENTION_SQL = """
WITH obs AS (
    SELECT max(event_date) AS max_date
    FROM public.fact_events
    WHERE event_category = 'activity'
), cohort AS (
    SELECT e.event_date AS activity_date,
           e.player_id
    FROM public.fact_events e, obs
    WHERE e.event_category = 'activity'
      AND e.activity_type = '节日活动'
      AND e.event_date BETWEEN obs.max_date - 29 AND obs.max_date
    GROUP BY e.event_date, e.player_id
), payment_retained AS (
    SELECT c.activity_date,
           c.player_id,
           gs.day AS retain_day,
           EXISTS (
               SELECT 1
               FROM public.fact_payments p
               WHERE p.player_id = c.player_id
                 AND p.payment_status = 'success'
                 AND p.net_revenue_usd > 0
                 AND p.event_date = c.activity_date + gs.day
           ) AS paid
    FROM cohort c
    CROSS JOIN generate_series(0, 7) AS gs(day)
)
SELECT activity_date AS "日期",
       count(DISTINCT player_id) AS "参与节日活动用户数",
       count(DISTINCT player_id) FILTER (WHERE retain_day = 0 AND paid) AS "当日",
       count(DISTINCT player_id) FILTER (WHERE retain_day = 1 AND paid) AS "第1日",
       count(DISTINCT player_id) FILTER (WHERE retain_day = 2 AND paid) AS "第2日",
       count(DISTINCT player_id) FILTER (WHERE retain_day = 3 AND paid) AS "第3日",
       count(DISTINCT player_id) FILTER (WHERE retain_day = 4 AND paid) AS "第4日",
       count(DISTINCT player_id) FILTER (WHERE retain_day = 5 AND paid) AS "第5日",
       count(DISTINCT player_id) FILTER (WHERE retain_day = 6 AND paid) AS "第6日",
       count(DISTINCT player_id) FILTER (WHERE retain_day = 7 AND paid) AS "第7日"
FROM payment_retained
GROUP BY activity_date
ORDER BY activity_date
"""


CHARTS = [
    {
        "id": "2188000000000000001",
        "title": "各类活动参与率",
        "type": "line",
        "layout": (1, 1, 36, 16),
        "sql": PARTICIPATION_RATE_SQL,
        "x": [axis("日期", axis_type="x")],
        "y": [axis("活动参与率", axis_type="y")],
        "series": [axis("活动类型", axis_type="series")],
    },
    {
        "id": "2188000000000000002",
        "title": "各类活动人均参与次数",
        "type": "line",
        "layout": (37, 1, 36, 16),
        "sql": AVG_PARTICIPATION_SQL,
        "x": [axis("日期", axis_type="x")],
        "y": [axis("人均参与次数", axis_type="y")],
        "series": [axis("活动类型", axis_type="series")],
    },
    {
        "id": "2188000000000000003",
        "title": "各等级段参与日常活动的人数分布",
        "type": "column",
        "layout": (1, 17, 36, 16),
        "sql": STAGE_DISTRIBUTION_SQL,
        "x": [axis("阶段", axis_type="x")],
        "y": [axis("参与人数", axis_type="y")],
        "series": [],
    },
    {
        "id": "2188000000000000004",
        "title": "每周活动参与次数分布",
        "type": "column",
        "layout": (37, 17, 36, 16),
        "sql": WEEKLY_COUNT_DISTRIBUTION_SQL,
        "x": [axis("周", axis_type="x")],
        "y": [axis("人数", axis_type="y")],
        "series": [axis("参与次数区间", axis_type="series")],
    },
    {
        "id": "2188000000000000005",
        "title": "参与新手活动的后续7日留存率",
        "type": "table",
        "layout": (1, 33, 72, 18),
        "sql": NEWBIE_RETENTION_SQL,
        "x": [],
        "y": [],
        "series": [],
    },
    {
        "id": "2188000000000000006",
        "title": "参与节日活动的后续7日付费留存率",
        "type": "table",
        "layout": (1, 51, 72, 18),
        "sql": FESTIVAL_PAY_RETENTION_SQL,
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
    backup_path = BACKUP_DIR / f"activity_dashboard_{DASHBOARD_ID}_{int(time.time())}.json"
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
                raise RuntimeError(f"Activity dashboard does not exist: {DASHBOARD_ID}")
            if dashboard["datasource"] != DATASOURCE_ID:
                raise RuntimeError(f"Activity dashboard datasource={dashboard['datasource']}, expected {DATASOURCE_ID}")
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
            SELECT count(*) FILTER (WHERE event_uid LIKE 'activity_mock_%') AS activity_events,
                   min(event_date) FILTER (WHERE event_uid LIKE 'activity_mock_%') AS min_date,
                   max(event_date) FILTER (WHERE event_uid LIKE 'activity_mock_%') AS max_date,
                   count(DISTINCT player_id) FILTER (WHERE event_uid LIKE 'activity_mock_%') AS players
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
    ensure_activity_columns(conn)
    seed_event_dictionary(conn)
    cleanup(conn)
    by_day = load_session_candidates(conn)
    event_rows = build_activity_events(by_day)
    insert_activity_events(conn, event_rows)


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
