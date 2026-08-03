"""扩大 flam 核心看板指标抽屉并保持后续布局不重叠。"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

import psycopg
from psycopg.rows import dict_row

from core_system_db import core_system_db_config


ROOT = Path(__file__).resolve().parents[1]
BACKUP_ROOT = ROOT / ".codex-runtime" / "flam-core-dashboard-metric-drawer-backups"
BACKUP_SCHEMA = "flam-core-dashboard-metric-drawer/v1"
TENANT_ID = 7477202383789887488
DASHBOARD_ID = "6d50bd7dfc9f46ba961d636814c3294d"
DASHBOARD_NAME = "核心看板"
DATASOURCE_ID = 3
CREATE_BY = "7471612174524223488"
METRIC_IDS = (
    "c23c019171804f608e92961dc06ae8b2",
    "d84e234a7f3b4e728a8b02d61911d88f",
    "4d250a8575cc4bcd84f7b9514abbf455",
    "ba0dc1580f0d43c29c0d6cdf26a6239c",
)
OLD_HEIGHT = 8
TARGET_HEIGHT = 10
METRIC_Y = 1


def _json_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def resize_metric_drawers(components: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Upgrade the known metric row without changing unrelated component fields."""

    target_ids = set(METRIC_IDS)
    component_ids = [str(item.get("id")) for item in components]
    duplicate_targets = {
        metric_id for metric_id in target_ids if component_ids.count(metric_id) != 1
    }
    if duplicate_targets:
        raise RuntimeError(f"目标指标抽屉 ID 重复或缺失：{sorted(duplicate_targets)}")
    by_id = {str(item.get("id")): item for item in components}
    if set(by_id).intersection(target_ids) != target_ids:
        raise RuntimeError("flam 核心看板指标抽屉必须完整存在")

    targets = [by_id[metric_id] for metric_id in METRIC_IDS]
    if any(item.get("y") != METRIC_Y for item in targets):
        raise RuntimeError("目标指标抽屉必须位于首行")
    heights = {item.get("sizeY") for item in targets}
    if heights not in ({OLD_HEIGHT}, {TARGET_HEIGHT}):
        raise RuntimeError(f"目标指标抽屉高度不一致：{sorted(heights, key=str)}")

    delta = TARGET_HEIGHT - OLD_HEIGHT if heights == {OLD_HEIGHT} else 0
    minimum_following_y = METRIC_Y + TARGET_HEIGHT
    for item in components:
        if str(item.get("id")) in target_ids:
            continue
        y = item.get("y")
        if not isinstance(y, int) or y < minimum_following_y - delta:
            raise RuntimeError("后续抽屉与指标抽屉重叠或缺少整数 y 坐标")

    result = copy.deepcopy([dict(item) for item in components])
    for item in result:
        if str(item.get("id")) in target_ids:
            item["sizeY"] = TARGET_HEIGHT
        elif delta:
            item["y"] += delta
    return result


def _select_dashboard(cursor: Any, *, for_update: bool = False) -> dict[str, Any]:
    suffix = " FOR UPDATE" if for_update else ""
    cursor.execute(
        f"""
        SELECT id, tenant_id, name, datasource, create_by, component_data,
               update_time, update_by
        FROM public.core_dashboard
        WHERE id = %s AND tenant_id = %s AND datasource = %s
          AND create_by = %s AND name = %s AND type = 'dashboard'
          AND COALESCE(delete_flag, 0) = 0{suffix}
        """,
        (DASHBOARD_ID, TENANT_ID, DATASOURCE_ID, CREATE_BY, DASHBOARD_NAME),
    )
    row = cursor.fetchone()
    if not row:
        raise RuntimeError("未找到 flam 核心看板")
    return dict(row)


def cas_update_dashboard(cursor: Any, *, old_raw: str, new_raw: str) -> None:
    cursor.execute(
        """
        UPDATE public.core_dashboard
        SET component_data = %s, update_time = %s, update_by = %s
        WHERE id = %s AND tenant_id = %s AND datasource = %s
          AND create_by = %s AND name = %s AND component_data = %s
          AND COALESCE(delete_flag, 0) = 0
        """,
        (
            new_raw,
            max(int(time.time()), int(time.time())),
            "codex",
            DASHBOARD_ID,
            TENANT_ID,
            DATASOURCE_ID,
            CREATE_BY,
            DASHBOARD_NAME,
            old_raw,
        ),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("flam 核心看板 CAS 更新失败")


def _backup(row: Mapping[str, Any], new_raw: str) -> Path:
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    old_raw = str(row["component_data"])
    path = BACKUP_ROOT / f"{timestamp}-{_json_hash(old_raw)[:8]}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": BACKUP_SCHEMA,
                "created_at": int(time.time()),
                "dashboard_id": DASHBOARD_ID,
                "tenant_id": TENANT_ID,
                "datasource": DATASOURCE_ID,
                "create_by": CREATE_BY,
                "old_component_sha256": _json_hash(old_raw),
                "new_component_sha256": _json_hash(new_raw),
                "row": row,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    return path.resolve()


def apply_dashboard() -> Path | None:
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (DASHBOARD_ID,))
                row = _select_dashboard(cursor, for_update=True)
                old_raw = str(row["component_data"] or "[]")
                components = json.loads(old_raw)
                new_components = resize_metric_drawers(components)
                new_raw = json.dumps(new_components, ensure_ascii=False, separators=(",", ":"))
                if new_raw == old_raw:
                    connection.rollback()
                    return None
                backup = _backup(row, new_raw)
                cas_update_dashboard(cursor, old_raw=old_raw, new_raw=new_raw)
                cursor.execute(
                    "SELECT component_data FROM public.core_dashboard WHERE id = %s FOR UPDATE",
                    (DASHBOARD_ID,),
                )
                if cursor.fetchone()["component_data"] != new_raw:
                    raise RuntimeError("事务内读回布局不一致")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    return backup


def verify_dashboard() -> dict[str, Any]:
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            row = _select_dashboard(cursor)
    current = json.loads(str(row["component_data"] or "[]"))
    expected = resize_metric_drawers(current)
    if expected != current:
        raise RuntimeError("flam 核心看板仍未达到目标抽屉高度")
    return {"verified": True, "dashboard_id": DASHBOARD_ID, "metric_height": TARGET_HEIGHT}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="备份并更新 flam 核心看板")
    parser.add_argument("--verify", action="store_true", help="只读验证 flam 核心看板")
    args = parser.parse_args(argv)
    if args.apply:
        backup = apply_dashboard()
        print(json.dumps({"applied": backup is not None, "backup": str(backup) if backup else None}, ensure_ascii=False))
        return 0
    print(json.dumps(verify_dashboard() if args.verify else {"dry_run": True, **verify_dashboard()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
