# -*- coding: utf-8 -*-
"""审计看板 SQL 图表执行数据源；可选择仅清理无歧义的重复字段。

默认只读。``--apply`` 只处理 viewInfo.datasource 与
sourceConfig.sql.datasource 相同的 duplicate 状态，不迁移 legacy_only，
也不修改 conflict 或 missing。
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from core_system_db import core_system_db_config


ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = ROOT / ".codex-runtime" / "dashboard-datasource-backups"
LOCK_KEY = "dashboard-chart-datasource-single-source-migration-v1"


def _datasource_id(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError("数据源 ID 不能是布尔值")
    result = int(value)
    if result <= 0:
        raise ValueError("数据源 ID 必须为正整数")
    return result


def _sql_config(view: dict[str, Any]) -> dict[str, Any] | None:
    source_config = view.get("sourceConfig")
    if not isinstance(source_config, dict):
        source_config = view.get("source_config")
    if not isinstance(source_config, dict):
        return None
    sql_config = source_config.get("sql")
    return sql_config if isinstance(sql_config, dict) else None


def _sql_text(view: dict[str, Any]) -> str:
    sql_config = _sql_config(view) or {}
    return str(view.get("sql") or sql_config.get("sql") or "").strip()


def classify_view(view: dict[str, Any]) -> tuple[str, int | None, int | None]:
    """返回状态、外层 ID、旧内层 ID。"""
    sql_config = _sql_config(view)
    try:
        outer = _datasource_id(view.get("datasource"))
        inner = _datasource_id(sql_config.get("datasource")) if sql_config else None
    except (TypeError, ValueError):
        return "invalid", None, None
    if outer is not None and inner is not None:
        return ("duplicate" if outer == inner else "conflict"), outer, inner
    if outer is not None:
        return "clean", outer, None
    if inner is not None:
        return "legacy_only", None, inner
    return "missing", None, None


def audit_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Counter[str]]:
    details: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for row in rows:
        try:
            canvas = json.loads(str(row.get("canvas_view_info") or "{}"))
        except json.JSONDecodeError:
            counts["invalid_canvas"] += 1
            details.append({
                "dashboard_id": str(row["id"]),
                "dashboard_name": row.get("name"),
                "chart_id": None,
                "status": "invalid_canvas",
            })
            continue
        if not isinstance(canvas, dict):
            counts["invalid_canvas"] += 1
            continue
        for chart_id, view in canvas.items():
            if not isinstance(view, dict) or not _sql_text(view):
                continue
            status, outer, inner = classify_view(view)
            counts[status] += 1
            details.append({
                "dashboard_id": str(row["id"]),
                "dashboard_name": row.get("name"),
                "tenant_id": str(row.get("tenant_id")),
                "chart_id": str(chart_id),
                "status": status,
                "view_datasource": outer,
                "legacy_datasource": inner,
            })
    return details, counts


def normalize_duplicate_canvas(raw_canvas: str) -> tuple[str, list[str]]:
    canvas = json.loads(raw_canvas or "{}")
    if not isinstance(canvas, dict):
        raise ValueError("canvas_view_info 不是 JSON 对象")
    result = copy.deepcopy(canvas)
    changed: list[str] = []
    for chart_id, view in result.items():
        if not isinstance(view, dict) or not _sql_text(view):
            continue
        status, _outer, _inner = classify_view(view)
        if status != "duplicate":
            continue
        sql_config = _sql_config(view)
        if sql_config is not None:
            sql_config.pop("datasource", None)
            changed.append(str(chart_id))
    return json.dumps(result, ensure_ascii=False, separators=(",", ":")), changed


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _select_rows(cur: Any, *, lock: bool) -> list[dict[str, Any]]:
    cur.execute(
        f"""
        SELECT id, tenant_id, name, canvas_view_info, update_time
        FROM public.core_dashboard
        WHERE COALESCE(delete_flag, 0) = 0
          AND node_type = 'leaf'
          AND canvas_view_info IS NOT NULL
        ORDER BY tenant_id, id
        {'FOR UPDATE' if lock else ''}
        """
    )
    return list(cur.fetchall())


def _write_backup(plans: list[dict[str, Any]]) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f"dashboard_datasource_duplicate_{time.time_ns()}.json"
    payload = {
        "created_at": int(time.time()),
        "kind": "dashboard_chart_datasource_duplicate_cleanup",
        "rows": plans,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path.resolve()


def restore(backup_file: Path) -> dict[str, Any]:
    payload = json.loads(backup_file.read_text(encoding="utf-8"))
    plans = payload.get("rows")
    if payload.get("kind") != "dashboard_chart_datasource_duplicate_cleanup" or not isinstance(plans, list):
        raise RuntimeError("备份文件类型无效")
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (LOCK_KEY,))
            for plan in plans:
                cur.execute(
                    """
                    UPDATE public.core_dashboard
                    SET canvas_view_info = %s, update_time = %s
                    WHERE id = %s
                      AND tenant_id = %s
                      AND canvas_view_info = %s
                      AND update_time IS NOT DISTINCT FROM %s
                      AND COALESCE(delete_flag, 0) = 0
                    """,
                    (
                        plan["old_canvas"],
                        plan["update_time"],
                        plan["dashboard_id"],
                        int(plan["tenant_id"]),
                        plan["new_canvas"],
                        plan["new_update_time"],
                    ),
                )
                if cur.rowcount != 1:
                    raise RuntimeError(f"恢复 CAS 校验失败：{plan['dashboard_id']}")
                cur.execute(
                    "SELECT canvas_view_info FROM public.core_dashboard WHERE id = %s",
                    (plan["dashboard_id"],),
                )
                if _sha256(str(cur.fetchone()["canvas_view_info"])) != plan["old_sha256"]:
                    raise RuntimeError(f"恢复读回校验失败：{plan['dashboard_id']}")
            conn.commit()
    return {"restored": len(plans), "backup": str(backup_file.resolve())}


def run(*, apply: bool) -> dict[str, Any]:
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            if apply:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (LOCK_KEY,))
            # Advisory lock serializes this migration; row-level CAS protects against app writes.
            rows = _select_rows(cur, lock=False)
            details, counts = audit_rows(rows)
            result: dict[str, Any] = {
                "apply": apply,
                "counts": dict(sorted(counts.items())),
                "details": details,
            }
            if not apply:
                conn.rollback()
                return result

            plans: list[dict[str, Any]] = []
            new_update_time = int(time.time())
            for row in rows:
                old_canvas = str(row.get("canvas_view_info") or "{}")
                new_canvas, chart_ids = normalize_duplicate_canvas(old_canvas)
                if not chart_ids:
                    continue
                plans.append({
                    "dashboard_id": str(row["id"]),
                    "tenant_id": str(row["tenant_id"]),
                    "name": row.get("name"),
                    "update_time": row.get("update_time"),
                    "new_update_time": new_update_time,
                    "chart_ids": chart_ids,
                    "old_canvas": old_canvas,
                    "new_canvas": new_canvas,
                    "old_sha256": _sha256(old_canvas),
                    "new_sha256": _sha256(new_canvas),
                })
            backup_path = _write_backup(plans)

            for plan in plans:
                cur.execute(
                    """
                    UPDATE public.core_dashboard
                    SET canvas_view_info = %s, update_time = %s
                    WHERE id = %s
                      AND tenant_id = %s
                      AND canvas_view_info = %s
                      AND update_time IS NOT DISTINCT FROM %s
                      AND COALESCE(delete_flag, 0) = 0
                    """,
                    (
                        plan["new_canvas"],
                        plan["new_update_time"],
                        plan["dashboard_id"],
                        int(plan["tenant_id"]),
                        plan["old_canvas"],
                        plan["update_time"],
                    ),
                )
                if cur.rowcount != 1:
                    raise RuntimeError(f"CAS 更新失败：{plan['dashboard_id']}")
                cur.execute(
                    "SELECT canvas_view_info FROM public.core_dashboard WHERE id = %s",
                    (plan["dashboard_id"],),
                )
                read_back = str(cur.fetchone()["canvas_view_info"])
                if _sha256(read_back) != plan["new_sha256"]:
                    raise RuntimeError(f"读回校验失败：{plan['dashboard_id']}")

            conn.commit()
            result["backup"] = str(backup_path)
            result["updated_dashboards"] = len(plans)
            result["updated_charts"] = sum(len(plan["chart_ids"]) for plan in plans)
            return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="仅清理内外相同的 duplicate 字段")
    parser.add_argument("--restore", type=Path, help="使用 --apply 生成的备份执行 CAS 恢复")
    parser.add_argument("--details", action="store_true", help="输出逐图审计明细")
    args = parser.parse_args()
    if args.apply and args.restore:
        parser.error("--apply 与 --restore 不能同时使用")
    result = restore(args.restore) if args.restore else run(apply=args.apply)
    if not args.details:
        result.pop("details", None)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
