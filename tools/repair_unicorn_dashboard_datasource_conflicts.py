# -*- coding: utf-8 -*-
"""清理 unicorn 空间 50 张普通 SQL 图表残留的数据源冲突。

默认只读验证；``--apply`` 才写入。脚本仅接受固定空间、固定看板/图表集合、
固定 9/6 冲突，并在目标数据源 Schema 可以覆盖全部 SQL 引用表时删除旧内层字段。
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


TENANT_ID = 7493583885482070016
TENANT_PUBLIC_ID = "WSWGCD2XXN"
TENANT_NAME = "unicorn"
TARGET_DATASOURCE_ID = 9
LEGACY_DATASOURCE_ID = 6
LOCK_KEY = "repair-unicorn-dashboard-datasource-conflicts-v1"
BACKUP_KIND = "unicorn_dashboard_datasource_conflict_cleanup_v1"
BACKUP_DIR = ROOT / ".codex-runtime" / "dashboard-datasource-backups"

EXPECTED_CHARTS = {
    "06983ff7cf7248f1a0baade2d723587c": {
        "b26188f2239f410fa6dcb3267835d681",
        "2ee2e6f9a19f4a90ad3613e57bd6a6ca",
    },
    "23530c49bf6342e7a14d296db984b655": {
        "2a4676f86d7642faa0c21be327f9acbb",
        "3f199383717c410cb83d0e3e0d29ff6e",
    },
    "3cce6ad2532e435886e65030764772e1": {
        "f4849278bb7f4bd5b9bc9bd58a27a4ed",
        "659d1a7c745546469be25532c244827c",
        "53ebf4fd8a3f4d2bb35cbf989dd5d142",
        "8760e428c5d646699580a56491456a6d",
        "9409cb5a8cbe47959d7cfb55b6abe3a0",
    },
    "435b7d52f4af447dbb877364345cd229": {
        "3878f780bc1f4b63935d21c1a4b5dede",
        "ac7aa7d4b3df4f35999f6e77ad6336aa",
        "5375a968f47645308a195a84a6d659b3",
        "60b95cb8061547b5a0f73c68bf752965",
        "cb97dd2417914635828584c0ad472d5c",
        "75a7568808344c49a3090d74a6b48a8f",
        "147a7b40b9364912bc84acabcc333e64",
    },
    "70a9b8167124499999e3c14cfbece2c6": {
        "7176d9a683f541a5a8600933320f9f6a",
        "5a520df2676f4c6aa0eff72948bd8ff5",
        "0261a2ed96924fec95d6a5d2835c4b2f",
        "0446598a808048dd906c16c03347b952",
        "78a9cb8866ec4177a6bed463d18a100c",
        "98968f68c6dc4e429c6a98f07f7463aa",
    },
    "849356dd6e61432dbac036ebd47d2af7": {
        "8936756a35974435b06ea07172e0c263",
        "ee4148a54ef94edf848d228d180cd2e9",
        "ab56ee393e4740768f7191f29b9a839a",
        "7ba49d5c48fc46348d562580cce85ca8",
        "7bb262de9db94711a693e4b5643fb714",
        "770319dcd39c452ca62b2c21f1befd73",
        "06e6f08715f7478c8f2d5dfda4e649df",
        "6fa7bbcc37cb472085b6e2556f155419",
        "58969022165546e6baa36be023298cd2",
        "20d12ec0a468470284ca44b557558c8a",
        "fa362edce7344777b469084eb3594638",
        "52884a3bc1054909a065d74821c32f0f",
        "006f5c9c76884b8bbd10b5828a3099aa",
        "5a5b69915b264288874d815e8a7b4888",
        "1adbf73372564089a98c25acf38c5022",
    },
    "8560dfb189f34e8bac6ef5b9541868b4": {
        "a4073b10b2d742eea6ffacc3fff18ff0",
        "9270d524b85e40299b70c5df67952533",
        "af7281e9ca2a4a7d98703b94638f5db7",
        "6ae3829f02b04319993d5ac2225465c9",
        "a2bde4fa93d8437390426ce94515a5fc",
    },
    "9fc56e59c92f434f95ddf5db95ffdf17": {
        "d938ef5f0e3f4d7fac7ae6077a043f10",
        "a2f4ac39fa574552bcd6bc72f1e2d050",
        "dcafa18469924151997a3ffc5a162d04",
        "fe2b01a07b884b1bba62d3b8b1bf5620",
        "5650a3689abf4b2ab639cd5b28a115aa",
    },
    "bfdca1687f2c48b7bffc10bd9fcd5d75": {
        "9e43d9cc51aa4eb09031fd6fdc5e5181",
        "e57321ca479a43eab57b7c163bc219f1",
        "cd24e3dee331477f93bd144dce25ca1f",
    },
}


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _datasource_id(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _sql_config(view: dict[str, Any]) -> dict[str, Any]:
    source_config = view.get("sourceConfig")
    if not isinstance(source_config, dict):
        source_config = view.get("source_config")
    if not isinstance(source_config, dict) or not isinstance(source_config.get("sql"), dict):
        raise RuntimeError("目标图表缺少 sourceConfig.sql")
    return source_config["sql"]


def _validate_context(cur: Any) -> set[str]:
    cur.execute("SELECT public_id, name, status FROM sys_tenant WHERE id = %s", (TENANT_ID,))
    tenant = cur.fetchone()
    if (
        tenant is None
        or tenant["public_id"] != TENANT_PUBLIC_ID
        or tenant["name"] != TENANT_NAME
        or int(tenant["status"]) != 1
    ):
        raise RuntimeError("unicorn 空间身份或状态已变化")

    cur.execute(
        "SELECT datasource_id FROM core_datasource_tenant_binding WHERE tenant_id = %s",
        (TENANT_ID,),
    )
    bindings = cur.fetchall()
    if len(bindings) != 1 or int(bindings[0]["datasource_id"]) != TARGET_DATASOURCE_ID:
        raise RuntimeError("unicorn 空间当前绑定数据源不是 9")

    cur.execute(
        "SELECT tenant_id, status FROM core_datasource WHERE id = %s",
        (TARGET_DATASOURCE_ID,),
    )
    datasource = cur.fetchone()
    if (
        datasource is None
        or int(datasource["tenant_id"]) != TENANT_ID
        or str(datasource["status"]).lower() != "success"
    ):
        raise RuntimeError("目标数据源 9 的所有权或状态无效")

    cur.execute(
        "SELECT table_name FROM core_table WHERE ds_id = %s AND COALESCE(checked, true) = true",
        (TARGET_DATASOURCE_ID,),
    )
    return {str(row["table_name"]) for row in cur.fetchall()}


def _load_rows(cur: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT id, tenant_id, name, datasource, canvas_view_info, update_time
        FROM core_dashboard
        WHERE tenant_id = %s
          AND id = ANY(%s)
          AND COALESCE(delete_flag, 0) = 0
          AND node_type = 'leaf'
        ORDER BY id
        """,
        (TENANT_ID, list(EXPECTED_CHARTS)),
    )
    rows = list(cur.fetchall())
    if {str(row["id"]) for row in rows} != set(EXPECTED_CHARTS):
        raise RuntimeError("目标看板集合已变化")
    return rows


def _build_plans(cur: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    target_tables = _validate_context(cur)
    rows = _load_rows(cur)
    plans: list[dict[str, Any]] = []
    chart_reports: list[dict[str, Any]] = []

    for row in rows:
        dashboard_id = str(row["id"])
        if _datasource_id(row["datasource"]) != TARGET_DATASOURCE_ID:
            raise RuntimeError(f"看板资产数据源不是 9：{dashboard_id}")
        old_canvas = str(row["canvas_view_info"] or "{}")
        canvas = json.loads(old_canvas)
        if not isinstance(canvas, dict):
            raise RuntimeError(f"画布不是 JSON 对象：{dashboard_id}")

        expected_chart_ids = EXPECTED_CHARTS[dashboard_id]
        for chart_id in expected_chart_ids:
            view = canvas.get(chart_id)
            if not isinstance(view, dict):
                raise RuntimeError(f"目标图表不存在：{dashboard_id}/{chart_id}")
            sql_config = _sql_config(view)
            if (
                _datasource_id(view.get("datasource")) != TARGET_DATASOURCE_ID
                or _datasource_id(sql_config.get("datasource")) != LEGACY_DATASOURCE_ID
            ):
                raise RuntimeError(f"目标图表已不再是预期的 9/6 冲突：{dashboard_id}/{chart_id}")
            sql = str(view.get("sql") or sql_config.get("sql") or "").strip()
            if not sql:
                raise RuntimeError(f"目标图表 SQL 为空：{dashboard_id}/{chart_id}")
            tables = sorted(extract_physical_tables(parse_sql_statements(sql, "mysql")))
            missing = sorted(set(tables) - target_tables)
            if missing:
                raise RuntimeError(
                    f"目标数据源 9 缺少 SQL 引用表：{dashboard_id}/{chart_id}: {', '.join(missing)}"
                )
            sql_config.pop("datasource")
            chart_reports.append(
                {
                    "dashboard_id": dashboard_id,
                    "dashboard_name": row["name"],
                    "chart_id": chart_id,
                    "tables": tables,
                }
            )

        new_canvas = json.dumps(canvas, ensure_ascii=False, separators=(",", ":"))
        plans.append(
            {
                "dashboard_id": dashboard_id,
                "dashboard_name": row["name"],
                "old_canvas": old_canvas,
                "new_canvas": new_canvas,
                "old_sha256": _sha256(old_canvas),
                "new_sha256": _sha256(new_canvas),
                "old_update_time": row["update_time"],
            }
        )

    if len(chart_reports) != 50:
        raise RuntimeError(f"目标冲突图表数量不是 50：{len(chart_reports)}")
    return plans, chart_reports


def run(*, apply: bool) -> dict[str, Any]:
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            if apply:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (LOCK_KEY,))
            plans, charts = _build_plans(cur)
            result: dict[str, Any] = {
                "apply": apply,
                "tenant_id": str(TENANT_ID),
                "tenant_name": TENANT_NAME,
                "target_datasource": TARGET_DATASOURCE_ID,
                "removed_legacy_datasource": LEGACY_DATASOURCE_ID,
                "dashboard_count": len(plans),
                "chart_count": len(charts),
                "dashboards": [
                    {
                        "dashboard_id": plan["dashboard_id"],
                        "dashboard_name": plan["dashboard_name"],
                        "chart_count": len(EXPECTED_CHARTS[plan["dashboard_id"]]),
                    }
                    for plan in plans
                ],
            }
            if not apply:
                conn.rollback()
                return result

            new_update_time = int(time.time())
            for plan in plans:
                plan["new_update_time"] = new_update_time
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            backup = BACKUP_DIR / f"unicorn_dashboard_datasource_conflicts_{time.time_ns()}.json"
            backup.write_text(
                json.dumps(
                    {"kind": BACKUP_KIND, "created_at": int(time.time()), "rows": plans, **result},
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )

            for plan in plans:
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
                        plan["new_canvas"],
                        new_update_time,
                        plan["dashboard_id"],
                        TENANT_ID,
                        plan["old_canvas"],
                        plan["old_update_time"],
                    ),
                )
                if cur.rowcount != 1:
                    raise RuntimeError(f"CAS 更新失败：{plan['dashboard_id']}")
                cur.execute("SELECT canvas_view_info FROM core_dashboard WHERE id = %s", (plan["dashboard_id"],))
                if _sha256(str(cur.fetchone()["canvas_view_info"])) != plan["new_sha256"]:
                    raise RuntimeError(f"读回校验失败：{plan['dashboard_id']}")
            conn.commit()
            result.update({"backup": str(backup.resolve()), "new_update_time": new_update_time})
            return result


def restore(backup_file: Path) -> dict[str, Any]:
    payload = json.loads(backup_file.read_text(encoding="utf-8"))
    plans = payload.get("rows")
    if (
        payload.get("kind") != BACKUP_KIND
        or str(payload.get("tenant_id")) != str(TENANT_ID)
        or not isinstance(plans, list)
        or {str(plan.get("dashboard_id")) for plan in plans} != set(EXPECTED_CHARTS)
    ):
        raise RuntimeError("备份文件与 unicorn 目标看板集合不匹配")

    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (LOCK_KEY,))
            for plan in plans:
                if _sha256(str(plan["old_canvas"])) != plan["old_sha256"]:
                    raise RuntimeError(f"备份原画布哈希无效：{plan['dashboard_id']}")
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
                        plan["old_canvas"],
                        plan["old_update_time"],
                        plan["dashboard_id"],
                        TENANT_ID,
                        plan["new_canvas"],
                        plan["new_update_time"],
                    ),
                )
                if cur.rowcount != 1:
                    raise RuntimeError(f"恢复 CAS 校验失败：{plan['dashboard_id']}")
                cur.execute("SELECT canvas_view_info FROM core_dashboard WHERE id = %s", (plan["dashboard_id"],))
                if _sha256(str(cur.fetchone()["canvas_view_info"])) != plan["old_sha256"]:
                    raise RuntimeError(f"恢复读回校验失败：{plan['dashboard_id']}")
            conn.commit()
    return {"restored": len(plans), "tenant_id": str(TENANT_ID), "backup": str(backup_file.resolve())}


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
