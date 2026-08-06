"""Remove fixed UTC+8 time expressions from existing flam dashboard SQL."""

from __future__ import annotations

import copy
import json
import re
import time
from pathlib import Path
from typing import Any

import psycopg

from core_system_db import core_system_db_config


ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = ROOT / ".codex-runtime" / "pg-backups"
DB = core_system_db_config()
TENANT_ID = 7477202383789887488
DATASOURCE_ID = 3
UPDATE_BY = "codex"

_FROM_UNIXTIME_UTC8 = re.compile(
    r"DATE_ADD\(\s*(FROM_UNIXTIME\([^)]*\))\s*,\s*INTERVAL\s+8\s+HOUR\s*\)",
    re.IGNORECASE,
)
_UTC_TIMESTAMP_UTC8 = re.compile(
    r"DATE_ADD\(\s*(UTC_TIMESTAMP\(\))\s*,\s*INTERVAL\s+8\s+HOUR\s*\)",
    re.IGNORECASE,
)


def remove_fixed_utc8(sql: str) -> str:
    """Remove only the fixed UTC+8 wrappers from one SQL expression."""
    result = _FROM_UNIXTIME_UTC8.sub(r"\1", sql)
    return _UTC_TIMESTAMP_UTC8.sub(r"\1", result)


def _rewrite_sql_value(value: Any) -> tuple[Any, bool]:
    if not isinstance(value, str):
        return value, False
    if "INTERVAL 8 HOUR" not in value.upper():
        return value, False
    if "FROM_UNIXTIME" not in value.upper() and "UTC_TIMESTAMP" not in value.upper():
        return value, False
    rewritten = remove_fixed_utc8(value)
    return rewritten, rewritten != value


def _rewrite_json_value(value: Any) -> tuple[Any, bool]:
    if isinstance(value, dict):
        rewritten = {}
        changed = False
        for key, item in value.items():
            new_item, item_changed = _rewrite_json_value(item)
            rewritten[key] = new_item
            changed = changed or item_changed
        return rewritten, changed
    if isinstance(value, list):
        rewritten_items = []
        changed = False
        for item in value:
            new_item, item_changed = _rewrite_json_value(item)
            rewritten_items.append(new_item)
            changed = changed or item_changed
        return rewritten_items, changed
    return _rewrite_sql_value(value)


def rewrite_canvas(canvas: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Rewrite direct and sourceConfig SQL while preserving unrelated canvas data."""
    rewritten_canvas = copy.deepcopy(canvas)
    changed_views = 0
    for view_id, view in list(rewritten_canvas.items()):
        if not isinstance(view, dict):
            continue
        rewritten_view, view_changed = _rewrite_json_value(view)
        if view_changed:
            rewritten_canvas[view_id] = rewritten_view
            changed_views += 1
    return rewritten_canvas, changed_views


def _backup_rows(rows: list[dict[str, Any]]) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f"flam_realtime_utc8_dashboard_sql_{int(time.time())}.json"
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> None:
    changed_rows: list[dict[str, Any]] = []
    with psycopg.connect(**DB) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, tenant_id, datasource, canvas_view_info
                FROM public.core_dashboard
                WHERE tenant_id = %s
                  AND datasource = %s
                  AND COALESCE(delete_flag, 0) = 0
                  AND canvas_view_info ILIKE %s
                FOR UPDATE
                """,
                (TENANT_ID, DATASOURCE_ID, "%INTERVAL 8 HOUR%"),
            )
            rows = cur.fetchall()
            for dashboard_id, name, tenant_id, datasource, raw_canvas in rows:
                try:
                    canvas = json.loads(raw_canvas or "{}")
                except json.JSONDecodeError as exc:
                    raise RuntimeError(f"看板 {dashboard_id} 的 canvas_view_info 不是合法 JSON") from exc
                if not isinstance(canvas, dict):
                    raise RuntimeError(f"看板 {dashboard_id} 的 canvas_view_info 必须是对象")

                rewritten, changed_views = rewrite_canvas(canvas)
                if not changed_views:
                    continue
                changed_rows.append(
                    {
                        "id": dashboard_id,
                        "name": name,
                        "tenant_id": tenant_id,
                        "datasource": datasource,
                        "canvas_view_info": raw_canvas,
                    }
                )
                new_raw = json.dumps(rewritten, ensure_ascii=False, separators=(",", ":"))
                cur.execute(
                    """
                    UPDATE public.core_dashboard
                       SET canvas_view_info = %s,
                           update_time = %s,
                           update_by = %s
                     WHERE id = %s
                       AND tenant_id = %s
                       AND datasource = %s
                       AND canvas_view_info = %s
                       AND COALESCE(delete_flag, 0) = 0
                    """,
                    (
                        new_raw,
                        int(time.time()),
                        UPDATE_BY,
                        dashboard_id,
                        TENANT_ID,
                        DATASOURCE_ID,
                        raw_canvas,
                    ),
                )
                if cur.rowcount != 1:
                    raise RuntimeError(f"看板 {dashboard_id} 并发更新失败")
                print(f"updated_dashboard={dashboard_id} name={name} changed_views={changed_views}")

            if changed_rows:
                backup_path = _backup_rows(changed_rows)
                print(f"backup={backup_path}")
        conn.commit()
    print(f"updated_dashboards={len(changed_rows)}")


if __name__ == "__main__":
    main()
