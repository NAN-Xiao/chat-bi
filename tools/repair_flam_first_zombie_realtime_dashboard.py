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
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import pymysql


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
BACKUP_DIR = ROOT / ".codex-runtime" / "pg-backups"

SYSTEM_DB = {
    "host": "127.0.0.1",
    "port": 15432,
    "dbname": "zhishu_bi",
    "user": "root",
    "password": "Password123@pg",
}

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
        with system_conn.transaction():
            repair_dashboard(system_conn, conf, sql_blocks)
    verify_data_side(conf)


if __name__ == "__main__":
    main()
