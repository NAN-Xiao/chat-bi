# -*- coding: utf-8 -*-
"""定点修复 unicorn ROI 看板 5 张图表的执行数据源冲突。

默认只读验证；``--apply`` 才写入。SQL、图表集合、工作空间 ROI 配置或
目标 Schema 任一项不匹配时拒绝修改。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from core_system_db import core_system_db_config


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from apps.datasource.crud.sql_permission import extract_physical_tables, parse_sql_statements  # noqa: E402


DASHBOARD_ID = "dcb7645772724045bf3097811b2e9a14"
TENANT_ID = 7493583885482070016
ASSET_DATASOURCE_ID = 9
LEGACY_ROI_DATASOURCE_ID = 8
TARGET_ROI_DATASOURCE_ID = 16
LOCK_KEY = "repair-unicorn-roi-dashboard-datasource-v1"
BACKUP_DIR = ROOT / ".codex-runtime" / "dashboard-datasource-backups"
EXPECTED_SQL_HASHES = {
    "3c53b6bf5006492c93c7a809ff267ea9": "cb280ff077eb76fc5651308ea9d93ce561a32ad647cce57505b58cbe8467d1c9",
    "f6127cba43714110a02af256805c454f": "3a0c252724ca5aa3c6c86ce526a29fd1db1c43339eda3a6b5da0baca54a94ba0",
    "2df551ca587d4f95857cccec6bec37e7": "1525a0c7bc71330de20720ee239fbf9b752b1b24aa05b82f5b7b2adf739e95d1",
    "93a062421dca4dbc913aa1097628a51c": "3a0c252724ca5aa3c6c86ce526a29fd1db1c43339eda3a6b5da0baca54a94ba0",
    "b902708ad2a44344ba59ed83001138bc": "3a0c252724ca5aa3c6c86ce526a29fd1db1c43339eda3a6b5da0baca54a94ba0",
}


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sql_config(view: dict[str, Any]) -> dict[str, Any]:
    source_config = view.get("sourceConfig")
    if not isinstance(source_config, dict) or not isinstance(source_config.get("sql"), dict):
        raise RuntimeError("目标图表缺少 sourceConfig.sql")
    return source_config["sql"]


def _validate_and_build(cur: Any, row: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    if int(row["tenant_id"]) != TENANT_ID or int(row["datasource"]) != ASSET_DATASOURCE_ID:
        raise RuntimeError("看板所有权或资产数据源已变化")
    cur.execute(
        """
        SELECT datasource_id
        FROM core_roi_workspace_config
        WHERE tenant_id = %s AND deleted = false
        """,
        (TENANT_ID,),
    )
    roi_rows = cur.fetchall()
    if len(roi_rows) != 1 or int(roi_rows[0]["datasource_id"]) != TARGET_ROI_DATASOURCE_ID:
        raise RuntimeError("当前空间 ROI 数据源配置不是预期的 16")
    cur.execute(
        "SELECT table_name FROM core_table WHERE ds_id = %s AND COALESCE(checked, true) = true",
        (TARGET_ROI_DATASOURCE_ID,),
    )
    target_tables = {str(item["table_name"]) for item in cur.fetchall()}

    canvas = json.loads(str(row["canvas_view_info"] or "{}"))
    if not isinstance(canvas, dict):
        raise RuntimeError("canvas_view_info 不是 JSON 对象")
    found: set[str] = set()
    report: list[dict[str, Any]] = []
    for chart_id, expected_hash in EXPECTED_SQL_HASHES.items():
        view = canvas.get(chart_id)
        if not isinstance(view, dict):
            raise RuntimeError(f"目标图表不存在：{chart_id}")
        sql_config = _sql_config(view)
        sql = str(view.get("sql") or sql_config.get("sql") or "").strip()
        actual_hash = _sha256(sql)
        if actual_hash != expected_hash:
            raise RuntimeError(f"SQL 哈希已变化：{chart_id}")
        if view.get("datasource") != ASSET_DATASOURCE_ID or sql_config.get("datasource") != LEGACY_ROI_DATASOURCE_ID:
            raise RuntimeError(f"目标图表已不再是预期的 9/8 冲突：{chart_id}")
        tables = sorted(extract_physical_tables(parse_sql_statements(sql, "mysql")))
        missing = sorted(set(tables) - target_tables)
        if missing:
            raise RuntimeError(f"目标 ROI Schema 缺表：{chart_id}: {', '.join(missing)}")
        view["datasource"] = TARGET_ROI_DATASOURCE_ID
        sql_config.pop("datasource", None)
        found.add(chart_id)
        report.append({"chart_id": chart_id, "sql_sha256": actual_hash, "tables": tables})
    if found != set(EXPECTED_SQL_HASHES):
        raise RuntimeError("目标图表集合不完整")
    return json.dumps(canvas, ensure_ascii=False, separators=(",", ":")), report


def run(*, apply: bool) -> dict[str, Any]:
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            if apply:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (LOCK_KEY,))
            cur.execute(
                """
                SELECT id, tenant_id, name, datasource, canvas_view_info, update_time
                FROM core_dashboard
                WHERE id = %s AND tenant_id = %s AND COALESCE(delete_flag, 0) = 0
                """,
                (DASHBOARD_ID, TENANT_ID),
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("目标看板不存在")
            old_canvas = str(row["canvas_view_info"])
            new_canvas, charts = _validate_and_build(cur, row)
            result: dict[str, Any] = {
                "apply": apply,
                "dashboard_id": DASHBOARD_ID,
                "tenant_id": str(TENANT_ID),
                "old_canvas_sha256": _sha256(old_canvas),
                "new_canvas_sha256": _sha256(new_canvas),
                "target_datasource": TARGET_ROI_DATASOURCE_ID,
                "charts": charts,
            }
            if not apply:
                conn.rollback()
                return result

            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            backup = BACKUP_DIR / f"unicorn_roi_dashboard_{time.time_ns()}.json"
            backup.write_text(
                json.dumps({"row": dict(row), **result}, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            new_update_time = int(time.time())
            cur.execute(
                """
                UPDATE core_dashboard
                SET canvas_view_info = %s, update_time = %s
                WHERE id = %s AND tenant_id = %s
                  AND canvas_view_info = %s
                  AND update_time IS NOT DISTINCT FROM %s
                  AND COALESCE(delete_flag, 0) = 0
                """,
                (new_canvas, new_update_time, DASHBOARD_ID, TENANT_ID, old_canvas, row["update_time"]),
            )
            if cur.rowcount != 1:
                raise RuntimeError("CAS 更新失败")
            cur.execute("SELECT canvas_view_info FROM core_dashboard WHERE id = %s", (DASHBOARD_ID,))
            if _sha256(str(cur.fetchone()["canvas_view_info"])) != _sha256(new_canvas):
                raise RuntimeError("读回校验失败")
            conn.commit()
            result.update({"backup": str(backup.resolve()), "new_update_time": new_update_time})
            return result


def restore(backup_file: Path) -> dict[str, Any]:
    payload = json.loads(backup_file.read_text(encoding="utf-8"))
    row = payload.get("row")
    if (
        not isinstance(row, dict)
        or str(row.get("id")) != DASHBOARD_ID
        or int(row.get("tenant_id") or 0) != TENANT_ID
        or not payload.get("new_canvas_sha256")
    ):
        raise RuntimeError("备份文件与目标看板不匹配")
    old_canvas = str(row.get("canvas_view_info") or "")
    if _sha256(old_canvas) != payload.get("old_canvas_sha256"):
        raise RuntimeError("备份原画布哈希不匹配")
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (LOCK_KEY,))
            cur.execute(
                """
                SELECT canvas_view_info, update_time
                FROM core_dashboard
                WHERE id = %s AND tenant_id = %s AND COALESCE(delete_flag, 0) = 0
                """,
                (DASHBOARD_ID, TENANT_ID),
            )
            current = cur.fetchone()
            if current is None or _sha256(str(current["canvas_view_info"])) != payload["new_canvas_sha256"]:
                raise RuntimeError("当前画布已不是本次修复结果，拒绝恢复")
            cur.execute(
                """
                UPDATE core_dashboard
                SET canvas_view_info = %s, update_time = %s
                WHERE id = %s AND tenant_id = %s
                  AND canvas_view_info = %s
                  AND update_time IS NOT DISTINCT FROM %s
                  AND COALESCE(delete_flag, 0) = 0
                """,
                (
                    old_canvas,
                    row.get("update_time"),
                    DASHBOARD_ID,
                    TENANT_ID,
                    current["canvas_view_info"],
                    current["update_time"],
                ),
            )
            if cur.rowcount != 1:
                raise RuntimeError("恢复 CAS 更新失败")
            cur.execute("SELECT canvas_view_info FROM core_dashboard WHERE id = %s", (DASHBOARD_ID,))
            if _sha256(str(cur.fetchone()["canvas_view_info"])) != payload["old_canvas_sha256"]:
                raise RuntimeError("恢复读回校验失败")
            conn.commit()
    return {"restored": True, "dashboard_id": DASHBOARD_ID, "backup": str(backup_file.resolve())}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--restore", type=Path)
    args = parser.parse_args()
    if args.apply and args.restore:
        parser.error("--apply 与 --restore 不能同时使用")
    result = restore(args.restore) if args.restore else run(apply=args.apply)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
