"""Repair the SLG BI Mock new-user dashboard D1 retention chart.

The business definition belongs to the workspace Data Skills and the saved
dashboard SQL. This script only refreshes the existing saved component; it does
not modify mock business detail tables.
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from core_system_db import core_system_db_config
from seed_slg_bi_new_users_dashboard import BI_DB, D1_RETENTION_SQL


DASHBOARD_ID = "2a25f4f6690d490f8efc2280d2cc2a51"
VIEW_ID = "2189000000000000004"
DATASOURCE_ID = 1
TENANT_ID = 7473600346187632640
UPDATE_BY = "7471612174524223488"
BACKUP_DIR = Path(".codex-runtime/backups")


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


def run_chart_sql() -> tuple[list[str], list[dict[str, Any]]]:
    with psycopg2.connect(**BI_DB) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(D1_RETENTION_SQL)
            rows = cur.fetchall()
            fields = [desc.name for desc in cur.description]
    return fields, [normalize_row(dict(row)) for row in rows]


def backup_dashboard(row: dict[str, Any]) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f"new_users_retention_dashboard_before_repair_{int(time.time())}.json"
    path.write_text(json.dumps(normalize_row(row), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def repair_dashboard(fields: list[str], rows: list[dict[str, Any]]) -> None:
    conn = psycopg2.connect(**core_system_db_config())
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
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
            if dashboard["datasource"] != DATASOURCE_ID:
                raise RuntimeError(f"Dashboard datasource={dashboard['datasource']}, expected {DATASOURCE_ID}")

            backup_path = backup_dashboard(dict(dashboard))
            canvas_view_info = json.loads(dashboard["canvas_view_info"] or "{}")
            view = canvas_view_info.get(VIEW_ID)
            if not isinstance(view, dict):
                raise RuntimeError(f"View not found in dashboard {DASHBOARD_ID}: {VIEW_ID}")

            view["datasource"] = DATASOURCE_ID
            view["sql"] = D1_RETENTION_SQL.strip()
            view["data"] = {"fields": fields, "data": rows}
            view["fields"] = fields
            view["status"] = "success"
            view["message"] = ""

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
            conn.commit()
            print(f"backup={backup_path}")
            print(f"updated_dashboard={DASHBOARD_ID} rows={cur.rowcount}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    fields, rows = run_chart_sql()
    if not rows:
        raise RuntimeError("D1 retention SQL returned no rows")
    repair_dashboard(fields, rows)
    print(
        json.dumps(
            {
                "view_id": VIEW_ID,
                "fields": fields,
                "row_count": len(rows),
                "first_row": rows[0],
                "last_row": rows[-1],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
