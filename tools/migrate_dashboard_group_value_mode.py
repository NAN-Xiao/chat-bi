# -*- coding: utf-8 -*-
"""将指定工作空间默认看板的分组值配置迁移为动态全部展示。

默认只读扫描；传入 ``--apply`` 后才会备份并写入系统数据库。迁移仅修改
启用透视分组的 ``pivot.group_value_mode`` 和 ``pivot.group_values``，不会修改
SQL、数据源、坐标轴、指标、日期范围或其他图表配置。
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
BACKUP_DIR = ROOT / ".codex-runtime" / "dashboard-group-value-mode-backups"
BACKUP_KIND = "dashboard_group_value_mode_all_v1"
LOCK_NAME = "dashboard-group-value-mode-all-v1"

TARGET_WORKSPACES = {
    "flam": 7477202383789887488,
    "修仙": 7482727237662281728,
    "gig": 7493272549510352896,
    "lds": 7493272675721154560,
    "unicorn": 7493583885482070016,
    "j2000": 7493583991958671360,
}
WORKSPACE_BY_TENANT = {tenant_id: name for name, tenant_id in TARGET_WORKSPACES.items()}


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def parse_canvas(value: Any) -> dict[str, Any]:
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    try:
        canvas = json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError as exc:
        raise ValueError("canvas_view_info 不是合法 JSON") from exc
    if not isinstance(canvas, dict):
        raise ValueError("canvas_view_info 必须是 JSON 对象")
    return canvas


def dump_canvas(canvas: dict[str, Any]) -> str:
    return json.dumps(canvas, ensure_ascii=False, separators=(",", ":"))


def is_grouped_pivot(view: Any) -> bool:
    if not isinstance(view, dict):
        return False
    pivot = view.get("pivot")
    return bool(
        isinstance(pivot, dict)
        and pivot.get("enabled") is True
        and pivot.get("group_enabled") is not False
        and str(pivot.get("group_field") or "").strip()
    )


def is_dynamic_all(pivot: dict[str, Any]) -> bool:
    return pivot.get("group_value_mode") == "all" and pivot.get("group_values") == []


def migrate_canvas(canvas: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    migrated = copy.deepcopy(canvas)
    changes: list[dict[str, Any]] = []
    for view_id, view in migrated.items():
        if not is_grouped_pivot(view):
            continue
        pivot = view["pivot"]
        if is_dynamic_all(pivot):
            continue
        old_values = pivot.get("group_values")
        changes.append(
            {
                "view_id": str(view_id),
                "chart_type": str(view.get("chart", {}).get("type") or "unknown"),
                "group_field": str(pivot.get("group_field") or ""),
                "old_mode": pivot.get("group_value_mode"),
                "old_group_values": copy.deepcopy(old_values) if isinstance(old_values, list) else [],
            }
        )
        pivot["group_value_mode"] = "all"
        pivot["group_values"] = []
    return migrated, changes


def build_plan(row: dict[str, Any]) -> dict[str, Any] | None:
    old_canvas = row.get("canvas_view_info")
    if not isinstance(old_canvas, str):
        raise ValueError(f"看板 {row.get('id')} 缺少 canvas_view_info")
    canvas = parse_canvas(old_canvas)
    migrated, changes = migrate_canvas(canvas)
    if not changes:
        return None
    new_canvas = dump_canvas(migrated)
    return {
        "row": row,
        "old_canvas": old_canvas,
        "new_canvas": new_canvas,
        "changes": changes,
    }


def select_target_dashboards(cur: Any, *, lock: bool) -> list[dict[str, Any]]:
    cur.execute(
        f"""
        SELECT d.id, d.tenant_id, d.datasource, d.name, d.update_time,
               d.canvas_view_info
        FROM public.core_dashboard d
        WHERE d.tenant_id = ANY(%s)
          AND d.type = 'dashboard' AND d.node_type = 'leaf'
          AND d.status = 1 AND d.is_default = 1
          AND COALESCE(d.delete_flag, 0) = 0
          AND EXISTS (
              SELECT 1
              FROM public.core_dashboard_tree t
              WHERE t.dashboard_id = d.id AND t.tenant_id = d.tenant_id
                AND t.scope = 'default'
          )
        ORDER BY d.tenant_id, d.id
        {'FOR UPDATE' if lock else ''}
        """,
        (list(TARGET_WORKSPACES.values()),),
    )
    return list(cur.fetchall())


def select_dashboard(cur: Any, dashboard_id: str, tenant_id: int, *, lock: bool) -> dict[str, Any]:
    cur.execute(
        f"""
        SELECT id, tenant_id, datasource, name, update_time, canvas_view_info
        FROM public.core_dashboard
        WHERE id = %s AND tenant_id = %s
          AND type = 'dashboard' AND node_type = 'leaf'
          AND status = 1 AND is_default = 1 AND COALESCE(delete_flag, 0) = 0
        {'FOR UPDATE' if lock else ''}
        """,
        (dashboard_id, tenant_id),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError(f"目标默认看板不存在或范围已变化：{tenant_id}/{dashboard_id}")
    return row


def build_plans(cur: Any, *, lock: bool) -> list[dict[str, Any]]:
    return [
        plan
        for row in select_target_dashboards(cur, lock=lock)
        if (plan := build_plan(row)) is not None
    ]


def summarize(plans: list[dict[str, Any]], *, applied: bool) -> dict[str, Any]:
    workspaces: dict[str, dict[str, Any]] = {}
    for plan in plans:
        tenant_id = int(plan["row"]["tenant_id"])
        workspace = WORKSPACE_BY_TENANT[tenant_id]
        summary = workspaces.setdefault(
            workspace,
            {"tenant_id": tenant_id, "dashboard_count": 0, "chart_count": 0, "chart_types": {}},
        )
        summary["dashboard_count"] += 1
        summary["chart_count"] += len(plan["changes"])
        type_counts = Counter(change["chart_type"] for change in plan["changes"])
        summary["chart_types"] = dict(Counter(summary["chart_types"]) + type_counts)
    return {
        "applied": applied,
        "dashboard_count": len(plans),
        "chart_count": sum(len(plan["changes"]) for plan in plans),
        "workspaces": workspaces,
    }


def write_backup(plans: list[dict[str, Any]]) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "kind": BACKUP_KIND,
        "created_at": int(time.time()),
        "target_workspaces": TARGET_WORKSPACES,
        "dashboards": [
            {
                "id": str(plan["row"]["id"]),
                "tenant_id": int(plan["row"]["tenant_id"]),
                "name": str(plan["row"]["name"] or ""),
                "old_canvas": plan["old_canvas"],
                "old_canvas_sha256": sha256_text(plan["old_canvas"]),
                "new_canvas_sha256": sha256_text(plan["new_canvas"]),
                "changes": plan["changes"],
            }
            for plan in plans
        ],
    }
    path = BACKUP_DIR / f"dashboard_group_value_mode_all_{time.time_ns()}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path.resolve()


def read_backup(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("迁移备份无法读取") from exc
    dashboards = payload.get("dashboards")
    if payload.get("kind") != BACKUP_KIND or not isinstance(dashboards, list) or not dashboards:
        raise RuntimeError("迁移备份类型或内容无效")
    for item in dashboards:
        old_canvas = item.get("old_canvas") if isinstance(item, dict) else None
        if (
            not isinstance(item.get("id"), str)
            or int(item.get("tenant_id", 0)) not in WORKSPACE_BY_TENANT
            or not isinstance(old_canvas, str)
            or item.get("old_canvas_sha256") != sha256_text(old_canvas)
            or not isinstance(item.get("new_canvas_sha256"), str)
        ):
            raise RuntimeError("迁移备份记录无效")
    return payload


def verify_canvas_is_dynamic_all(canvas_value: str, expected_view_ids: set[str]) -> None:
    canvas = parse_canvas(canvas_value)
    for view_id in expected_view_ids:
        view = canvas.get(view_id)
        if not is_grouped_pivot(view) or not is_dynamic_all(view["pivot"]):
            raise RuntimeError(f"迁移读回验证失败：{view_id}")


def apply_migration() -> dict[str, Any]:
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (LOCK_NAME,))
            plans = build_plans(cur, lock=True)
            if not plans:
                conn.rollback()
                return summarize([], applied=True) | {"backup": None, "verified": True}
            backup = write_backup(plans)
            for plan in plans:
                row = plan["row"]
                cur.execute(
                    """
                    UPDATE public.core_dashboard
                    SET canvas_view_info = %s, update_time = %s
                    WHERE id = %s AND tenant_id = %s
                      AND canvas_view_info = %s AND COALESCE(delete_flag, 0) = 0
                    """,
                    (
                        plan["new_canvas"],
                        int(time.time()),
                        row["id"],
                        row["tenant_id"],
                        plan["old_canvas"],
                    ),
                )
                if cur.rowcount != 1:
                    raise RuntimeError(f"看板 CAS 更新数量异常：{row['id']}")
            for plan in plans:
                row = select_dashboard(
                    cur, str(plan["row"]["id"]), int(plan["row"]["tenant_id"]), lock=False
                )
                verify_canvas_is_dynamic_all(
                    row["canvas_view_info"],
                    {change["view_id"] for change in plan["changes"]},
                )
            conn.commit()
    return summarize(plans, applied=True) | {"backup": str(backup), "verified": True}


def scan_migration() -> dict[str, Any]:
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            plans = build_plans(cur, lock=False)
        conn.rollback()
    return summarize(plans, applied=False)


def verify_migration() -> dict[str, Any]:
    result = scan_migration()
    if result["chart_count"]:
        raise RuntimeError(f"仍有 {result['chart_count']} 张分组图未迁移为动态全部展示")
    return {"verified": True, "chart_count": 0, "workspaces": list(TARGET_WORKSPACES)}


def restore_migration(path: Path) -> dict[str, Any]:
    payload = read_backup(path)
    dashboards = payload["dashboards"]
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (LOCK_NAME,))
            current_rows: dict[tuple[int, str], dict[str, Any]] = {}
            for item in dashboards:
                key = (int(item["tenant_id"]), item["id"])
                row = select_dashboard(cur, item["id"], key[0], lock=True)
                if sha256_text(row["canvas_view_info"]) != item["new_canvas_sha256"]:
                    raise RuntimeError(f"回滚 CAS 哈希不匹配：{key[0]}/{key[1]}")
                current_rows[key] = row
            for item in dashboards:
                key = (int(item["tenant_id"]), item["id"])
                cur.execute(
                    """
                    UPDATE public.core_dashboard
                    SET canvas_view_info = %s, update_time = %s
                    WHERE id = %s AND tenant_id = %s AND canvas_view_info = %s
                      AND COALESCE(delete_flag, 0) = 0
                    """,
                    (
                        item["old_canvas"],
                        int(time.time()),
                        key[1],
                        key[0],
                        current_rows[key]["canvas_view_info"],
                    ),
                )
                if cur.rowcount != 1:
                    raise RuntimeError(f"回滚更新数量异常：{key[0]}/{key[1]}")
            conn.commit()
    return {"restored": True, "backup": str(path.resolve()), "dashboard_count": len(dashboards)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="备份后迁移 6 个空间的目标默认看板")
    mode.add_argument("--verify", action="store_true", help="只读验证不存在未迁移的目标图表")
    mode.add_argument("--restore", type=Path, help="使用指定备份按 CAS 边界恢复")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.restore:
        result = restore_migration(args.restore)
    elif args.verify:
        result = verify_migration()
    elif args.apply:
        result = apply_migration()
    else:
        result = scan_migration()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
