# -*- coding: utf-8 -*-
"""Repair flam realtime dashboard SQL from datasource-scoped Data Skills.

The timezone rule for this dashboard belongs to the flam workspace Data Skill,
not to shared dashboard runtime code. This script reads the persisted SQL blocks
from that Data Skill and writes them into the existing dashboard components.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import pymysql

from core_system_db import core_system_db_config


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
BACKUP_DIR = ROOT / ".codex-runtime" / "pg-backups"

SYSTEM_DB = core_system_db_config()

TENANT_ID = 7477202383789887488
DATASOURCE_ID = 3
DASHBOARD_ID = "760150000bdc4abbb740880d494f5a5a"
UPDATE_BY = "codex"
SKILL_MARKER = "<!-- data-skill-source:flam:first-zombie:timezone-realtime -->"
SQL_BLOCK_PATTERN = re.compile(
    r"<!--\s*dashboard-sql:(?P<view_id>[a-f0-9]+)\s*-->\s*```sql\s*(?P<sql>.*?)```",
    re.IGNORECASE | re.DOTALL,
)

EXPECTED_VIEW_IDS = {
    "e3fe7e4819e64b71b76d9329a3023359",
    "4fc570b4be7d406c9f648d9088f760bb",
    "2149b7abbc6c4cd7ad6f52379e69b15a",
}

PROD_ID = 110000038
LOOKBACK_DAYS = 15
PAY_EVENTS = (
    "'PayBuyRet','PayBuyRetBenifit','PayBuyRetSandBox','PayFinish',"
    "'ServerPayLog','ep_pay_purchase_finish','ep_pay_update_db_finish'"
)

REALTIME_VIEW_FIELDS = {
    "e3fe7e4819e64b71b76d9329a3023359": {
        "x_value": "time_label",
        "x_name": "时间",
        "y_value": "online_users",
        "y_name": "实时在线人数",
    },
    "4fc570b4be7d406c9f648d9088f760bb": {
        "x_value": "hour_label",
        "x_name": "小时",
        "y_value": "pay_count",
        "y_name": "实时付费事件次数",
    },
    "2149b7abbc6c4cd7ad6f52379e69b15a": {
        "x_value": "hour_label",
        "x_name": "小时",
        "y_value": "cumulative_pay_count",
        "y_name": "累计付费事件次数",
    },
}


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _setup_backend_imports() -> None:
    _load_env_file(ROOT / ".env")
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))


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


def yyyymmdd(value: date) -> int:
    return int(value.strftime("%Y%m%d"))


def load_skill_sql_blocks(cur: Any) -> dict[str, str]:
    cur.execute(
        """
        SELECT id, prompt
        FROM public.custom_prompt
        WHERE tenant_id = %s
          AND type = 'DATA_SKILL'
          AND active = TRUE
          AND visible = TRUE
          AND specific_ds = TRUE
          AND datasource_ids @> %s::jsonb
          AND position(%s in COALESCE(prompt, '')) > 0
        ORDER BY id
        LIMIT 1
        """,
        (TENANT_ID, json.dumps([DATASOURCE_ID]), SKILL_MARKER),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError("flam realtime Data Skill not found; run seed_flam_first_zombie_data_skills.py first")

    skill_id, prompt = row
    blocks = {
        match.group("view_id"): match.group("sql").strip()
        for match in SQL_BLOCK_PATTERN.finditer(prompt or "")
    }
    missing = sorted(EXPECTED_VIEW_IDS.difference(blocks))
    if missing:
        raise RuntimeError(f"Data Skill {skill_id} is missing dashboard SQL blocks: {missing}")
    print(f"skill_id={skill_id}")
    return {view_id: blocks[view_id] for view_id in sorted(EXPECTED_VIEW_IDS)}


def load_flam_mysql_config(cur: Any):
    _setup_backend_imports()
    from apps.datasource.models.datasource import DatasourceConf
    from apps.datasource.utils.utils import aes_decrypt

    cur.execute(
        """
        SELECT id, name, type, configuration
        FROM public.core_datasource
        WHERE id = %s
          AND tenant_id = %s
        """,
        (DATASOURCE_ID, TENANT_ID),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError(f"Datasource not found: {DATASOURCE_ID}")
    datasource_id, name, ds_type, configuration = row
    if ds_type != "mysql":
        raise RuntimeError(f"Datasource {datasource_id} type={ds_type}, expected mysql")
    conf = DatasourceConf(**json.loads(aes_decrypt(configuration)))
    print(f"datasource={datasource_id} name={name} database={conf.database}")
    return conf


def run_chart_sql(conf: Any, sql: str) -> tuple[list[str], list[dict[str, Any]]]:
    conn = pymysql.connect(
        host=conf.host,
        port=int(conf.port),
        user=conf.username,
        password=conf.password,
        database=conf.database,
        charset="utf8mb4",
        connect_timeout=20,
        read_timeout=60,
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            fields = [field[0] for field in cur.description or []]
    finally:
        conn.close()
    return fields, [normalize_row(dict(row)) for row in rows]


def run_single_row_sql(conf: Any, sql: str) -> dict[str, Any] | None:
    fields, rows = run_chart_sql(conf, sql)
    del fields
    return rows[0] if rows else None


def load_latest_pay_business_date(conf: Any) -> date | None:
    row = run_single_row_sql(
        conf,
        f"""
        WITH latest_dt AS (
            SELECT e.dt
            FROM `event` e
            WHERE e.dt BETWEEN CAST(DATE_FORMAT(DATE_SUB(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR), INTERVAL {LOOKBACK_DAYS} DAY), '%Y%m%d') AS SIGNED)
                           AND CAST(DATE_FORMAT(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR), '%Y%m%d') AS SIGNED)
              AND e.prod = {PROD_ID}
              AND e.event IN ({PAY_EVENTS})
            GROUP BY e.dt
            ORDER BY e.dt DESC
            LIMIT 1
        )
        SELECT DATE(MAX(DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR))) AS biz_date,
               COUNT(*) AS rows_in_latest_dt
        FROM `event` e
        JOIN latest_dt ld ON e.dt = ld.dt
        WHERE e.prod = {PROD_ID}
          AND e.event IN ({PAY_EVENTS})
        """.strip(),
    )
    raw_value = row.get("biz_date") if row else None
    if isinstance(raw_value, date):
        return raw_value
    if isinstance(raw_value, str) and raw_value:
        return date.fromisoformat(raw_value[:10])
    return None


def load_latest_ccu_business_date(conf: Any) -> date | None:
    row = run_single_row_sql(
        conf,
        f"""
        WITH latest_dt AS (
            SELECT e.dt
            FROM `event` e
            WHERE e.dt BETWEEN CAST(DATE_FORMAT(DATE_SUB(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR), INTERVAL {LOOKBACK_DAYS} DAY), '%Y%m%d') AS SIGNED)
                           AND CAST(DATE_FORMAT(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR), '%Y%m%d') AS SIGNED)
              AND e.prod = {PROD_ID}
              AND e.event = 'CCU'
              AND NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.ext, '$.ed_ccu')), '') IS NOT NULL
            GROUP BY e.dt
            ORDER BY e.dt DESC
            LIMIT 1
        )
        SELECT DATE(MAX(DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR))) AS biz_date,
               COUNT(*) AS rows_in_latest_dt
        FROM `event` e
        JOIN latest_dt ld ON e.dt = ld.dt
        WHERE e.prod = {PROD_ID}
          AND e.event = 'CCU'
          AND NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.ext, '$.ed_ccu')), '') IS NOT NULL
        """.strip(),
    )
    raw_value = row.get("biz_date") if row else None
    if isinstance(raw_value, date):
        return raw_value
    if isinstance(raw_value, str) and raw_value:
        return date.fromisoformat(raw_value[:10])
    return None


def build_fixed_realtime_sql(sql_blocks: dict[str, str], conf: Any) -> dict[str, str]:
    pay_biz_date = load_latest_pay_business_date(conf)
    ccu_biz_date = load_latest_ccu_business_date(conf)
    fixed_sql = dict(sql_blocks)
    if ccu_biz_date is not None:
        fixed_sql["e3fe7e4819e64b71b76d9329a3023359"] = build_online_sql(ccu_biz_date)
    else:
        fixed_sql["e3fe7e4819e64b71b76d9329a3023359"] = build_empty_sql(
            "time_label",
            "online_users",
        )
    if pay_biz_date is not None:
        fixed_sql["4fc570b4be7d406c9f648d9088f760bb"] = build_hourly_pay_sql(pay_biz_date)
        fixed_sql["2149b7abbc6c4cd7ad6f52379e69b15a"] = build_cumulative_pay_sql(pay_biz_date)
    else:
        fixed_sql["4fc570b4be7d406c9f648d9088f760bb"] = build_empty_sql(
            "hour_label",
            "pay_count",
        )
        fixed_sql["2149b7abbc6c4cd7ad6f52379e69b15a"] = build_empty_sql(
            "hour_label",
            "cumulative_pay_count",
        )
    print(
        json.dumps(
            {
                "latest_pay_biz_date": pay_biz_date.isoformat() if pay_biz_date else None,
                "latest_ccu_biz_date": ccu_biz_date.isoformat() if ccu_biz_date else None,
            },
            ensure_ascii=False,
        )
    )
    return fixed_sql


def build_empty_sql(x_field: str, y_field: str) -> str:
    return f"""
SELECT CAST(NULL AS CHAR) AS {x_field},
       CAST(NULL AS SIGNED) AS {y_field}
WHERE 1 = 0
""".strip()


def build_online_sql(biz_date: date) -> str:
    start_dt = yyyymmdd(biz_date - timedelta(days=1))
    end_dt = yyyymmdd(biz_date)
    biz_date_text = biz_date.isoformat()
    return f"""
SELECT DATE_FORMAT(DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR), '%H:00') AS time_label,
       MAX(CAST(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.ext, '$.ed_ccu')), '') AS DECIMAL(18,4))) AS online_users
FROM `event` e
WHERE e.dt BETWEEN {start_dt} AND {end_dt}
  AND DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR) >= '{biz_date_text}'
  AND DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR) < DATE_ADD('{biz_date_text}', INTERVAL 1 DAY)
  AND e.event = 'CCU'
  AND e.prod = {PROD_ID}
  AND NULLIF(JSON_UNQUOTE(JSON_EXTRACT(e.ext, '$.ed_ccu')), '') IS NOT NULL
GROUP BY HOUR(DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR)), time_label
ORDER BY HOUR(DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR))
LIMIT 24
""".strip()


def build_hourly_pay_base_sql(biz_date: date) -> str:
    start_dt = yyyymmdd(biz_date - timedelta(days=1))
    end_dt = yyyymmdd(biz_date)
    biz_date_text = biz_date.isoformat()
    return f"""
SELECT HOUR(DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR)) AS hour_index,
       DATE_FORMAT(DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR), '%H:00') AS hour_label,
       COUNT(*) AS pay_count
FROM `event` e
WHERE e.dt BETWEEN {start_dt} AND {end_dt}
  AND DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR) >= '{biz_date_text}'
  AND DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR) < DATE_ADD('{biz_date_text}', INTERVAL 1 DAY)
  AND e.event IN ({PAY_EVENTS})
  AND e.prod = {PROD_ID}
GROUP BY hour_index, hour_label
""".strip()


def build_hourly_pay_sql(biz_date: date) -> str:
    base_sql = build_hourly_pay_base_sql(biz_date)
    return f"""
WITH hourly AS (
    {base_sql}
)
SELECT hour_label,
       pay_count
FROM hourly
ORDER BY hour_index
LIMIT 24
""".strip()


def build_cumulative_pay_sql(biz_date: date) -> str:
    hourly_sql = build_hourly_pay_base_sql(biz_date)
    return f"""
WITH hourly AS (
    {hourly_sql}
)
SELECT hour_label,
       SUM(pay_count) OVER (ORDER BY hour_index) AS cumulative_pay_count
FROM hourly
ORDER BY hour_index
LIMIT 24
""".strip()


def backup_dashboard(row: dict[str, Any]) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f"flam_realtime_dashboard_before_skill_sql_repair_{int(time.time())}.json"
    path.write_text(json.dumps(normalize_row(row), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def chart_axis(value: str) -> dict[str, str]:
    return {"value": value}


def repair_dashboard(system_conn: Any, conf: Any, sql_blocks: dict[str, str]) -> None:
    with system_conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, name, datasource, tenant_id, canvas_view_info, update_time
            FROM public.core_dashboard
            WHERE id = %s
              AND tenant_id = %s
              AND COALESCE(delete_flag, 0) = 0
            FOR UPDATE
            """,
            (DASHBOARD_ID, TENANT_ID),
        )
        dashboard = cur.fetchone()
        if not dashboard:
            raise RuntimeError(f"Dashboard not found: {DASHBOARD_ID}")
        dashboard_id, dashboard_name, datasource, tenant_id, canvas_view_info_text, _update_time = dashboard
        if datasource != DATASOURCE_ID:
            raise RuntimeError(f"Dashboard datasource={datasource}, expected {DATASOURCE_ID}")

        backup_path = backup_dashboard(
            {
                "id": dashboard_id,
                "name": dashboard_name,
                "datasource": datasource,
                "tenant_id": tenant_id,
                "canvas_view_info": canvas_view_info_text,
            }
        )
        print(f"backup={backup_path}")

        canvas_view_info = json.loads(canvas_view_info_text or "{}")
        for view_id, sql in sql_blocks.items():
            view = canvas_view_info.get(view_id)
            if not isinstance(view, dict):
                raise RuntimeError(f"View not found in dashboard {DASHBOARD_ID}: {view_id}")
            fields, rows = run_chart_sql(conf, sql)
            chart = view.setdefault("chart", {})
            field_meta = REALTIME_VIEW_FIELDS.get(view_id)
            if field_meta:
                chart["xAxis"] = [
                    {
                        "name": field_meta["x_name"],
                        "value": field_meta["x_value"],
                        "type": "x",
                    }
                ]
                chart["yAxis"] = [
                    {
                        "name": field_meta["y_name"],
                        "value": field_meta["y_value"],
                        "type": "y",
                    }
                ]
                chart["columns"] = [
                    {"name": field_meta["x_name"], "value": field_meta["x_value"]},
                    {"name": field_meta["y_name"], "value": field_meta["y_value"]},
                ]
            if chart.get("type") in {"table", "metric"}:
                chart["columns"] = [chart_axis(field) for field in fields]
            view["datasource"] = DATASOURCE_ID
            view["sql"] = sql
            view["data"] = {"fields": fields, "data": rows}
            view["fields"] = fields
            view["status"] = "success"
            view["message"] = ""
            view["dataState"] = "ready"
            view["loadingProgress"] = 100
            view["snapshotRefreshedAt"] = int(time.time() * 1000)
            print(
                json.dumps(
                    {
                        "view_id": view_id,
                        "title": chart.get("title"),
                        "rows": len(rows),
                        "fields": fields,
                    },
                    ensure_ascii=False,
                )
            )

        cur.execute(
            """
            UPDATE public.core_dashboard
               SET canvas_view_info = %s,
                   update_time = %s,
                   update_by = %s
             WHERE id = %s
               AND tenant_id = %s
            """,
            (
                json.dumps(canvas_view_info, ensure_ascii=False, separators=(",", ":")),
                int(time.time()),
                UPDATE_BY,
                DASHBOARD_ID,
                TENANT_ID,
            ),
        )
        print(f"updated_dashboard={DASHBOARD_ID} rows={cur.rowcount}")


def verify_data_side(conf: Any) -> None:
    checks = {
        "mysql_time": """
            SELECT NOW() AS now_time,
                   CURDATE() AS cur_date,
                   UTC_TIMESTAMP() AS utc_time,
                   DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR) AS business_time
        """,
        "ccu_payload": """
            SELECT COUNT(*) AS ccu_rows,
                   SUM(JSON_EXTRACT(e.ext, '$.ed_ccu') IS NOT NULL) AS rows_with_ed_ccu,
                   MIN(e.ext) AS sample_ext
            FROM `event` e
            WHERE e.dt BETWEEN CAST(DATE_FORMAT(DATE_SUB(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
                           AND CAST(DATE_FORMAT(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR), '%Y%m%d') AS SIGNED)
              AND DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR) >= DATE(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR))
              AND DATE_ADD(FROM_UNIXTIME(e.time / 1000), INTERVAL 8 HOUR) < DATE_FORMAT(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR), '%Y-%m-%d %H:00:00')
              AND e.event = 'CCU'
        """,
    }
    for name, sql in checks.items():
        fields, rows = run_chart_sql(conf, sql)
        print(f"{name}=" + json.dumps({"fields": fields, "rows": rows}, ensure_ascii=False))


def main() -> None:
    with psycopg.connect(**SYSTEM_DB) as system_conn:
        with system_conn.cursor() as cur:
            sql_blocks = load_skill_sql_blocks(cur)
            conf = load_flam_mysql_config(cur)
        sql_blocks = build_fixed_realtime_sql(sql_blocks, conf)
        with system_conn.transaction():
            repair_dashboard(system_conn, conf, sql_blocks)
    verify_data_side(conf)


if __name__ == "__main__":
    main()
