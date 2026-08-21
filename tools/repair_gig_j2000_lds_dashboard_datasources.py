# -*- coding: utf-8 -*-
"""修复 gig、j2000、lds 三个空间的看板执行数据源重复及 ROI 错配。

默认只读验证；``--apply`` 才写入。普通图表保留空间绑定数据源，ROI 图表改用
空间配置的 ROI 数据源，所有目标图表均删除 ``sourceConfig.sql.datasource``。
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


LOCK_KEY = "repair-gig-j2000-lds-dashboard-datasources-v1"
BACKUP_KIND = "gig_j2000_lds_dashboard_datasource_repair_v1"
BACKUP_DIR = ROOT / ".codex-runtime" / "dashboard-datasource-backups"

PROFILES = {
    7493272549510352896: {
        "public_id": "WSB9NZYM99",
        "name": "gig",
        "bound_datasource": 12,
        "roi_datasource": 13,
        "dashboards": {
            "2a3527a81ed5407cbbd20322a6888ba2": ("渠道分析", "bound", 5),
            "34ed883c086648d391b87541d5d29d1e": ("留存分析", "bound", 5),
            "3f87f3ed85034540880f90f52c32800a": ("付费概览", "bound", 6),
            "640531f36aac4e03890aa0dec9fd75a1": ("核心看板", "bound", 15),
            "641251f705144b18b1fa8e8d41d1f7f4": ("实时看板", "bound", 2),
            "69e3228a9b76451facea36ec2fc1b4f7": ("活跃看板", "bound", 7),
            "92db475452ef432b9911ca8a8da6f603": ("投放看板", "bound", 3),
            "a882fa4c6d8b418da44503f2486835d4": ("ROI看板", "roi", 5),
            "b0cdf1b2629b42f7899c7be655ec868d": ("养成看板", "bound", 2),
            "efb1a5f1e7074f7eaea8e56e937d79c2": ("新增看板", "bound", 5),
        },
    },
    7493583991958671360: {
        "public_id": "WSCWXDWV48",
        "name": "j2000",
        "bound_datasource": 11,
        "roi_datasource": 15,
        "dashboards": {
            "135c99728aae4664b68fd8c97b278934": ("投放看板", "bound", 3),
            "1c499cba259b497a852291379b0d80a6": ("留存分析", "bound", 5),
            "34a2f15ecc9d417d8ba378d042fdd08a": ("核心看板", "bound", 15),
            "4946ab9002bf4845a937972271d8bb02": ("付费概览", "bound", 6),
            "7df439da88974fbdba989fee86877d30": ("活跃看板", "bound", 7),
            "970030f34556447f9b513c1c5301ed2e": ("养成看板", "bound", 2),
            "ab30f1f1dd15450c8d8fc5d5cd958c06": ("渠道分析", "bound", 5),
            "db7dee845ff24d348263d1b9a8371cb4": ("新增看板", "bound", 5),
            "f4752ac1104e4b88aa53b377a3402055": ("实时看板", "bound", 2),
            "ff98c30d2a844fb1b0d4bf2a07eb2a3a": ("ROI看板", "roi", 5),
        },
    },
    7493272675721154560: {
        "public_id": "WS6MEJGDSA",
        "name": "lds",
        "bound_datasource": 10,
        "roi_datasource": 14,
        "dashboards": {
            "028e33c255824cda93320e78febe8d71": ("核心看板", "bound", 15),
            "0ce1b43d3640440f9f6ff78b4d4a38d2": ("留存分析", "bound", 5),
            "1c6f7e9d972b437dbb2330d85028528f": ("ROI看板", "roi", 5),
            "68a85458fa9f4c74b77376b650199c6b": ("付费概览", "bound", 6),
            "8900567ff2214a938774390d6f28ea8a": ("渠道分析", "bound", 5),
            "9e38e694e7db486298f57a5c7f462fec": ("新增看板", "bound", 5),
            "aab44e74534e4c8d940a48df34018ae4": ("实时看板", "bound", 2),
            "b9b54793e3da4cbab3a9a60f32b6f5f0": ("活跃看板", "bound", 7),
            "d11e4d66a255449fbb00448dd22bac31": ("投放看板", "bound", 3),
            "e39cc3bea92e49a8a0cd2009a4c38a5a": ("养成看板", "bound", 2),
        },
    },
}


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _datasource_id(value: Any) -> int | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _sql_config(view: dict[str, Any]) -> dict[str, Any] | None:
    source_config = view.get("sourceConfig")
    if not isinstance(source_config, dict):
        source_config = view.get("source_config")
    if not isinstance(source_config, dict):
        return None
    sql_config = source_config.get("sql")
    return sql_config if isinstance(sql_config, dict) else None


def _validate_profile(cur: Any, tenant_id: int, profile: dict[str, Any]) -> dict[str, Any]:
    cur.execute("SELECT public_id, name, status FROM sys_tenant WHERE id = %s", (tenant_id,))
    tenant = cur.fetchone()
    if (
        tenant is None
        or tenant["public_id"] != profile["public_id"]
        or tenant["name"] != profile["name"]
        or int(tenant["status"]) != 1
    ):
        raise RuntimeError(f"空间身份或状态已变化：{profile['name']}")

    cur.execute(
        "SELECT datasource_id FROM core_datasource_tenant_binding WHERE tenant_id = %s",
        (tenant_id,),
    )
    bindings = cur.fetchall()
    if len(bindings) != 1 or int(bindings[0]["datasource_id"]) != profile["bound_datasource"]:
        raise RuntimeError(f"空间绑定数据源已变化：{profile['name']}")

    cur.execute(
        "SELECT datasource_id FROM core_roi_workspace_config WHERE tenant_id = %s AND deleted = false",
        (tenant_id,),
    )
    roi_rows = cur.fetchall()
    if len(roi_rows) != 1 or int(roi_rows[0]["datasource_id"]) != profile["roi_datasource"]:
        raise RuntimeError(f"空间 ROI 数据源配置已变化：{profile['name']}")

    datasource_ids = [profile["bound_datasource"], profile["roi_datasource"]]
    cur.execute(
        "SELECT id, type, status FROM core_datasource WHERE id = ANY(%s)",
        (datasource_ids,),
    )
    datasources = {int(row["id"]): row for row in cur.fetchall()}
    if set(datasources) != set(datasource_ids) or any(
        str(datasources[ds_id]["status"]).lower() != "success" for ds_id in datasource_ids
    ):
        raise RuntimeError(f"空间数据源不存在或状态无效：{profile['name']}")

    cur.execute(
        """
        SELECT ds_id, table_name
        FROM core_table
        WHERE ds_id = ANY(%s) AND COALESCE(checked, true) = true
        """,
        (datasource_ids,),
    )
    tables = {ds_id: set() for ds_id in datasource_ids}
    for row in cur.fetchall():
        tables[int(row["ds_id"])].add(str(row["table_name"]))
    return {"datasources": datasources, "tables": tables}


def _build_plans(cur: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    plans: list[dict[str, Any]] = []
    chart_reports: list[dict[str, Any]] = []

    for tenant_id, profile in PROFILES.items():
        context = _validate_profile(cur, tenant_id, profile)
        dashboard_ids = list(profile["dashboards"])
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
            (tenant_id, dashboard_ids),
        )
        rows = list(cur.fetchall())
        if {str(row["id"]) for row in rows} != set(dashboard_ids):
            raise RuntimeError(f"目标看板集合已变化：{profile['name']}")

        for row in rows:
            dashboard_id = str(row["id"])
            expected_name, role, expected_chart_count = profile["dashboards"][dashboard_id]
            bound_datasource = int(profile["bound_datasource"])
            target_datasource = int(profile[f"{role}_datasource"])
            if row["name"] != expected_name or _datasource_id(row["datasource"]) != bound_datasource:
                raise RuntimeError(f"看板名称或资产数据源已变化：{profile['name']}/{dashboard_id}")

            old_canvas = str(row["canvas_view_info"] or "{}")
            canvas = json.loads(old_canvas)
            if not isinstance(canvas, dict):
                raise RuntimeError(f"画布不是 JSON 对象：{profile['name']}/{dashboard_id}")

            dashboard_chart_count = 0
            for chart_id, view in canvas.items():
                if not isinstance(view, dict):
                    continue
                sql_config = _sql_config(view)
                sql = str(view.get("sql") or (sql_config or {}).get("sql") or "").strip()
                if not sql:
                    continue
                if sql_config is None:
                    raise RuntimeError(f"SQL 图表缺少 sourceConfig.sql：{dashboard_id}/{chart_id}")
                if (
                    _datasource_id(view.get("datasource")) != bound_datasource
                    or _datasource_id(sql_config.get("datasource")) != bound_datasource
                ):
                    raise RuntimeError(f"图表已不再是预期的重复状态：{dashboard_id}/{chart_id}")

                dialect = str(context["datasources"][target_datasource]["type"])
                tables = sorted(extract_physical_tables(parse_sql_statements(sql, dialect)))
                missing = sorted(set(tables) - context["tables"][target_datasource])
                if missing:
                    raise RuntimeError(
                        f"目标数据源缺少 SQL 引用表：{dashboard_id}/{chart_id}: {', '.join(missing)}"
                    )
                view["datasource"] = target_datasource
                sql_config.pop("datasource")
                dashboard_chart_count += 1
                chart_reports.append(
                    {
                        "tenant_id": str(tenant_id),
                        "tenant_name": profile["name"],
                        "dashboard_id": dashboard_id,
                        "dashboard_name": expected_name,
                        "chart_id": str(chart_id),
                        "role": role,
                        "target_datasource": target_datasource,
                        "tables": tables,
                    }
                )

            if dashboard_chart_count != expected_chart_count:
                raise RuntimeError(
                    f"SQL 图表数量已变化：{profile['name']}/{dashboard_id}: "
                    f"{dashboard_chart_count} != {expected_chart_count}"
                )

            new_canvas = json.dumps(canvas, ensure_ascii=False, separators=(",", ":"))
            plans.append(
                {
                    "tenant_id": str(tenant_id),
                    "tenant_name": profile["name"],
                    "dashboard_id": dashboard_id,
                    "dashboard_name": expected_name,
                    "role": role,
                    "chart_count": dashboard_chart_count,
                    "old_canvas": old_canvas,
                    "new_canvas": new_canvas,
                    "old_sha256": _sha256(old_canvas),
                    "new_sha256": _sha256(new_canvas),
                    "old_update_time": row["update_time"],
                }
            )

    if len(plans) != 30 or len(chart_reports) != 165:
        raise RuntimeError(f"目标集合数量无效：dashboards={len(plans)}, charts={len(chart_reports)}")
    return plans, chart_reports


def run(*, apply: bool) -> dict[str, Any]:
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            if apply:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (LOCK_KEY,))
            plans, charts = _build_plans(cur)
            result: dict[str, Any] = {
                "apply": apply,
                "dashboard_count": len(plans),
                "chart_count": len(charts),
                "workspaces": [
                    {
                        "tenant_id": str(tenant_id),
                        "tenant_name": profile["name"],
                        "bound_datasource": profile["bound_datasource"],
                        "roi_datasource": profile["roi_datasource"],
                        "dashboard_count": sum(int(plan["tenant_id"]) == tenant_id for plan in plans),
                        "bound_chart_count": sum(
                            int(chart["tenant_id"]) == tenant_id and chart["role"] == "bound" for chart in charts
                        ),
                        "roi_chart_count": sum(
                            int(chart["tenant_id"]) == tenant_id and chart["role"] == "roi" for chart in charts
                        ),
                    }
                    for tenant_id, profile in PROFILES.items()
                ],
            }
            if not apply:
                conn.rollback()
                return result

            new_update_time = int(time.time())
            for plan in plans:
                plan["new_update_time"] = new_update_time
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            backup = BACKUP_DIR / f"gig_j2000_lds_dashboard_datasources_{time.time_ns()}.json"
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
                        int(plan["tenant_id"]),
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
    expected_dashboards = {
        dashboard_id
        for profile in PROFILES.values()
        for dashboard_id in profile["dashboards"]
    }
    if (
        payload.get("kind") != BACKUP_KIND
        or not isinstance(plans, list)
        or {str(plan.get("dashboard_id")) for plan in plans} != expected_dashboards
    ):
        raise RuntimeError("备份文件与目标看板集合不匹配")

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
                        int(plan["tenant_id"]),
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
    return {"restored": len(plans), "backup": str(backup_file.resolve())}


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
