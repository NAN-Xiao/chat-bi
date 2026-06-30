# -*- coding: utf-8 -*-
"""Repair flam new-user dashboard SQL from datasource-scoped Data Skills."""

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

from core_system_db import core_system_db_config
from flam_first_zombie_dashboard_sql import VIEW_SQL, axis


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
BACKUP_DIR = ROOT / ".codex-runtime" / "pg-backups"

SYSTEM_DB = core_system_db_config()

TENANT_ID = 7477202383789887488
DATASOURCE_ID = 3
DASHBOARD_ID = "bb3ab5f2697a42af98ab90da4679cb77"
UPDATE_BY = "codex"
SKILL_MARKER = "<!-- data-skill-source:flam:first-zombie:"
SQL_BLOCK_PATTERN = re.compile(
    r"<!--\s*dashboard-sql:(?P<view_id>[a-f0-9]+)\s*-->\s*```sql\s*(?P<sql>.*?)```",
    re.IGNORECASE | re.DOTALL,
)
NEW_USERS_DASHBOARD_VIEW_IDS = (
    "29055a5fcfd74169a12373b3f0d9a412",
    "cdf17cb957bb40499914a3ef790a79ef",
    "db1d8ef987724e68a1e0c9fe8b073ed1",
    "f0d759307a304043883a23499a281b97",
    "f784452553f1426ea5097b092deb818a",
)


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
    os.environ.setdefault("SECRET_KEY", "y5txe1mRmS_JpOrUzFzHEu-kIQn3lf7ll0AOv9DQh0s")
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
        SELECT id, name, prompt
        FROM public.custom_prompt
        WHERE tenant_id = %s
          AND type = 'DATA_SKILL'
          AND active = TRUE
          AND visible = TRUE
          AND specific_ds = TRUE
          AND datasource_ids @> %s::jsonb
          AND position(%s in COALESCE(prompt, '')) > 0
        ORDER BY id
        """,
        (TENANT_ID, json.dumps([DATASOURCE_ID]), SKILL_MARKER),
    )
    blocks: dict[str, str] = {}
    skill_ids: list[int] = []
    for skill_id, _name, prompt in cur.fetchall():
        skill_ids.append(int(skill_id))
        for match in SQL_BLOCK_PATTERN.finditer(prompt or ""):
            view_id = match.group("view_id")
            if view_id in NEW_USERS_DASHBOARD_VIEW_IDS:
                blocks[view_id] = match.group("sql").strip()
    missing = sorted(set(NEW_USERS_DASHBOARD_VIEW_IDS).difference(blocks))
    if missing:
        raise RuntimeError(f"Data Skills are missing new-user dashboard SQL blocks: {missing}")
    print(f"skills={skill_ids}")
    return {view_id: blocks[view_id] for view_id in NEW_USERS_DASHBOARD_VIEW_IDS}


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


def run_sql(conf: Any, sql: str) -> tuple[list[str], list[dict[str, Any]]]:
    conn = pymysql.connect(
        host=conf.host,
        port=int(conf.port),
        user=conf.username,
        password=conf.password,
        database=conf.database,
        charset="utf8mb4",
        connect_timeout=20,
        read_timeout=180,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            fields = [desc[0] for desc in cur.description or []]
    finally:
        conn.close()
    return fields, [normalize_row(dict(zip(fields, row))) for row in rows]


def backup_dashboard(row: dict[str, Any]) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f"flam_new_users_dashboard_before_skill_sql_repair_{int(time.time())}.json"
    path.write_text(json.dumps(normalize_row(row), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _clear_result(view: dict[str, Any], fields: tuple[str, ...]) -> None:
    data = view.setdefault("data", {})
    if not isinstance(data, dict):
        data = {}
        view["data"] = data
    data["fields"] = list(fields)
    data["data"] = []
    data.pop("source_fields", None)
    data.pop("source_data", None)
    data["snapshotRefreshedAt"] = 0
    view["fields"] = list(fields)
    view["status"] = "success"
    view["message"] = ""
    view["dataState"] = "ready"
    view["loadingProgress"] = 100
    view["snapshotRefreshedAt"] = 0


def _apply_chart_config(view: dict[str, Any], view_id: str, sql: str) -> None:
    spec = VIEW_SQL[view_id]
    view["datasource"] = DATASOURCE_ID
    view["sql"] = sql.strip()
    _clear_result(view, spec.fields)

    chart = view.setdefault("chart", {})
    chart["type"] = spec.chart_type
    chart["title"] = spec.title
    chart["xAxis"] = [axis(field) | {"type": "x"} for field in spec.x_axis]
    chart["yAxis"] = [axis(field) | {"type": "y"} for field in spec.y_axis]
    chart["columns"] = [axis(field) for field in (spec.columns or spec.fields)]


def repair_dashboard(system_conn: Any, sql_blocks: dict[str, str]) -> None:
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
        missing_views = sorted(set(NEW_USERS_DASHBOARD_VIEW_IDS).difference(canvas_view_info))
        if missing_views:
            raise RuntimeError(f"Expected new-user dashboard views not found: {missing_views}")

        touched: list[dict[str, Any]] = []
        for view_id in NEW_USERS_DASHBOARD_VIEW_IDS:
            view = canvas_view_info.get(view_id)
            if not isinstance(view, dict):
                continue
            _apply_chart_config(view, view_id, sql_blocks[view_id])
            spec = VIEW_SQL[view_id]
            touched.append(
                {
                    "view_id": view_id,
                    "title": view.get("chart", {}).get("title"),
                    "chart_type": view.get("chart", {}).get("type"),
                    "fields": list(spec.fields),
                }
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
        print(json.dumps({"views": touched}, ensure_ascii=False))


def main() -> None:
    with psycopg.connect(**SYSTEM_DB) as system_conn:
        with system_conn.cursor() as cur:
            sql_blocks = load_skill_sql_blocks(cur)
        with system_conn.transaction():
            repair_dashboard(system_conn, sql_blocks)


if __name__ == "__main__":
    main()
