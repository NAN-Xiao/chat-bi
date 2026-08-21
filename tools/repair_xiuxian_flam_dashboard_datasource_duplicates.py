# -*- coding: utf-8 -*-
"""清理修仙与 flam 空间看板中内外相同的数据源重复字段。

默认只读验证；``--apply`` 才写入。脚本固定目标空间、看板画布哈希与重复
图表数量，并验证绑定源、ROI 源、SQL 方言和目标 Schema 后删除旧内层字段。
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


LOCK_KEY = "repair-xiuxian-flam-dashboard-datasource-duplicates-v1"
BACKUP_KIND = "xiuxian_flam_dashboard_datasource_duplicate_cleanup_v1"
BACKUP_DIR = ROOT / ".codex-runtime" / "dashboard-datasource-backups"

PROFILES = {
    7482727237662281728: {
        "public_id": "WSTH6DZKJK",
        "name": "\u4fee\u4ed9",
        "bound_datasource": 6,
        "roi_datasource": 8,
    },
    7477202383789887488: {
        "public_id": "WSTY4JM9CD",
        "name": "flam",
        "bound_datasource": 3,
        "roi_datasource": 7,
    },
}

# dashboard_id: (tenant_id, canvas_sha256, expected_duplicate_count)
EXPECTED_DASHBOARDS = {
    "1683de014d814e90b2c6dc002df8da1f": (7477202383789887488, "6e03e2c41751960e13e17f873be6276075271a4dc8a873c09caace34d220274c", 1),
    "259414f219f94aacaa46f4e531646b9d": (7477202383789887488, "dc9c35c352f5e5569e91ad67566ebc6cd8360de207c098bf0595f8c2384ed50b", 5),
    "2b990d3821fa4c3d97f0dda519b644e8": (7477202383789887488, "fa13e3a0a5cd666166dfead3969a07a05544d98a1590f54c12a28d24a0e3f141", 5),
    "4bae835c4243481b9963122b5275ed81": (7477202383789887488, "5382f9393e50176686ee21e540d9845662bc0ebbc43089b6178330cf81cab83b", 5),
    "5cee4cf41a024c56ac9de0e3aef9aefe": (7477202383789887488, "d9678de0b4fe7c2db468c3231aed462e4297b8ed80fce37324c86a20a88f7631", 5),
    "6773e46d6a8e49e18c8811ec1dbab37e": (7477202383789887488, "8ec6891132cb364ee80ad16d479828537120205a76434c816351dc28e9e28eec", 5),
    "6d50bd7dfc9f46ba961d636814c3294d": (7477202383789887488, "7585eed5ad047f885d946b8d029c75c02ba3ac2e72bdb5d728655192eb08c759", 15),
    "760150000bdc4abbb740880d494f5a5a": (7477202383789887488, "40ca214f98207da1249558f983ab184a1f5fe4ce12f935e31c1007d3a9463d24", 4),
    "854d0ee1f6684ae0a30e7bcd3f5d1dfa": (7477202383789887488, "1882a57629e5fd38a94e6af37eeae6f9fb3f7368a32145ad129346b84e08e903", 2),
    "8c93878ee7af41b9b3832547856d25e6": (7477202383789887488, "9990773d922bc0d256d03b77c517461de2e7c0b21d61f47151c5622d24f36638", 4),
    "8cb3b30497d84b4e8d4ca5ac20d1325f": (7477202383789887488, "9d0d55f6d4cf06b054c0d25ffc65ba38f049b9ff022e2f3ebc05d5bb6e88cf03", 2),
    "8f86e50234794606bd2a33ec41ffa660": (7477202383789887488, "43fd4ed854625d06cd8b69b4de0d44e8a0d878a6fea0f77775b5b5a55371d493", 3),
    "ab4630e923594d23b4f0474d4c6fac42": (7477202383789887488, "20451fde7b22564a3bc6c5854afeed2188699ba4fc523ac1a6a37c582b65d639", 1),
    "af5bd9e37d06444194017e6aa4c6f41d": (7477202383789887488, "0ab3c7900904fad26489ee4588213bef4fe95588ca7b5aa15cf2ea9430d39666", 1),
    "af9db793af17402e8a0c8df12140a193": (7477202383789887488, "6a0be4f407e38d7d29df00dfc8f6e94395f7b14eb9df553f622e9f996e9c1e26", 4),
    "b390ea7963e44f9fb17584781ad9cadf": (7477202383789887488, "d81d6544d22c370bff11fe9fc8f78ef55211dd4889230b9553bbd930a9319a3e", 1),
    "bb3ab5f2697a42af98ab90da4679cb77": (7477202383789887488, "37942daef9899424696ce68412a2c7fd3cddf9f5c3cf34f150cfbd605dc866c3", 3),
    "db9df7a9015c4b4bb033810ffc5a84d2": (7477202383789887488, "d9cabd640e1a77bfdb39ecfc4d3343437a9539bca08d3858a37cf94930c29b95", 4),
    "e146aa12aed74c429a1f558f7bd672cf": (7477202383789887488, "ef6e5ffeb1f5babcbac8a0efc1add85b0169646560bb7a6797a90ded1f151fd3", 3),
    "f26870db68cb44bd974b0160ea91cdae": (7477202383789887488, "368014501ecbfe523fb285ef8b5ea6899a74b529957e86eb5a0dc7649c13a0ea", 2),
    "10604280d5a941af9720800bce6e030f": (7482727237662281728, "b021c7eccfe7daef3b14f5ab48dfe7347e1528691a1f15ad85a18d285f944e75", 2),
    "146ba4deb8b74ab293f38f69d89d4b21": (7482727237662281728, "fa7fb6b9e73e69caec1aed37b3f3ef1c106866c928881a66301e5b186e781742", 3),
    "17531de20e5d439f9ddfb2eeececced5": (7482727237662281728, "8c2d551bb1a62c7cc8ee8e091ecb8dae4c46da46cd73d92086f8818ded488e39", 5),
    "2ac0a784310c41fd99dee1e6bb307a0c": (7482727237662281728, "6233182c18ccd8d01a4147dfe43ac6c0e1d962f6fca104950c988a553e0d9f4e", 2),
    "32909e56ee174a2a9d8226be17d51ddf": (7482727237662281728, "334a44da0f8bb9dd6295893c9ccbe6648ceb7a721320e4eea34ecd4fdd5baed3", 5),
    "4f08e75945c3498486963e70f3c75688": (7482727237662281728, "7a63eef413b06fb4a7303656002446849043b7f47e2dcafdebb2314855b85a5d", 4),
    "5df5b385700048a49e99a6cb33a52dd8": (7482727237662281728, "84001ad3d299de62bf883d258d1a9a4d7d7fcc55e0c525943ec4f5bdf02d3e48", 1),
    "60c291cf41254cb993c6dff2b38cdca6": (7482727237662281728, "4d49e42ca331963ddf1a3975ba4b19a8924afc6eb773a9218d9b563449c036ec", 2),
    "6234ec38697c4924b65c7de11d8bd829": (7482727237662281728, "0351f1f800c3ca6bc194994b553d796f87f72615b5fb05c9de23c690d7e62a55", 6),
    "7d666e96e17d4a648a35627ac91a7ff3": (7482727237662281728, "e4b7ef8011a144db5b44b0b44faf272e50e7e0599e2d576c09f1d218d987626f", 1),
    "a34aef6cb7214f7fa23e5846a0a66236": (7482727237662281728, "a0ad2a3e96bb783c15e6c1eaa68c7cf42d26750829686f38c0bbb877053d98df", 5),
    "afe201c9762c448aa0495f3508c01793": (7482727237662281728, "bf5a77ed90d1a513ee9a25119965dedcee3612ba8476f1ab5e953e966e2de262", 15),
    "b09e4d57f57b41859a0c2d4609f80f26": (7482727237662281728, "bbad3aff578c7aad1f891975d782ef518e5f71f26c860e0002a943319f3b138e", 5),
    "c68e08ee9b4a4be59c3c8fbbe918affd": (7482727237662281728, "db4380ddb59dad7726ba6e638c84ad0dbf1537fad85331e9e69c8138a6bbb2dd", 7),
    "ef9af92c3d6744d780f82cba4c534482": (7482727237662281728, "eb9eae816f98503d6f3596a90d9e55e77c3383d832a40a9d50729b3647ea1c01", 1),
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


def _validate_profiles(cur: Any) -> dict[int, dict[str, Any]]:
    contexts: dict[int, dict[str, Any]] = {}
    for tenant_id, profile in PROFILES.items():
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
        cur.execute("SELECT id, type, status FROM core_datasource WHERE id = ANY(%s)", (datasource_ids,))
        datasources = {int(row["id"]): row for row in cur.fetchall()}
        if set(datasources) != set(datasource_ids) or any(
            str(datasources[ds_id]["status"]).lower() != "success" for ds_id in datasource_ids
        ):
            raise RuntimeError(f"空间数据源不存在或状态无效：{profile['name']}")

        cur.execute(
            "SELECT ds_id, table_name FROM core_table WHERE ds_id = ANY(%s) AND COALESCE(checked, true) = true",
            (datasource_ids,),
        )
        tables = {ds_id: set() for ds_id in datasource_ids}
        for row in cur.fetchall():
            tables[int(row["ds_id"])].add(str(row["table_name"]))
        contexts[tenant_id] = {"datasources": datasources, "tables": tables}
    return contexts


def _build_plans(cur: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    contexts = _validate_profiles(cur)
    cur.execute(
        """
        SELECT id, tenant_id, name, datasource, canvas_view_info, update_time
        FROM core_dashboard
        WHERE id = ANY(%s)
          AND tenant_id = ANY(%s)
          AND COALESCE(delete_flag, 0) = 0
          AND node_type = 'leaf'
        ORDER BY tenant_id, id
        """,
        (list(EXPECTED_DASHBOARDS), list(PROFILES)),
    )
    rows = list(cur.fetchall())
    if {str(row["id"]) for row in rows} != set(EXPECTED_DASHBOARDS):
        raise RuntimeError("目标看板集合已变化")

    plans: list[dict[str, Any]] = []
    charts: list[dict[str, Any]] = []
    for row in rows:
        dashboard_id = str(row["id"])
        tenant_id, expected_hash, expected_count = EXPECTED_DASHBOARDS[dashboard_id]
        profile = PROFILES[tenant_id]
        context = contexts[tenant_id]
        old_canvas = str(row["canvas_view_info"] or "{}")
        if int(row["tenant_id"]) != tenant_id or _sha256(old_canvas) != expected_hash:
            raise RuntimeError(f"看板空间或画布已变化：{dashboard_id}")
        if _datasource_id(row["datasource"]) != profile["bound_datasource"]:
            raise RuntimeError(f"看板资产数据源已变化：{dashboard_id}")

        canvas = json.loads(old_canvas)
        if not isinstance(canvas, dict):
            raise RuntimeError(f"画布不是 JSON 对象：{dashboard_id}")
        duplicate_count = 0
        for chart_id, view in canvas.items():
            if not isinstance(view, dict):
                continue
            sql_config = _sql_config(view)
            sql = str(view.get("sql") or (sql_config or {}).get("sql") or "").strip()
            if not sql:
                continue
            outer = _datasource_id(view.get("datasource"))
            inner = _datasource_id(sql_config.get("datasource")) if sql_config else None
            if outer is None:
                raise RuntimeError(f"SQL 图表缺少外层数据源：{dashboard_id}/{chart_id}")
            if outer not in {profile["bound_datasource"], profile["roi_datasource"]}:
                raise RuntimeError(f"SQL 图表使用未配置数据源：{dashboard_id}/{chart_id}")
            if inner is not None and inner != outer:
                raise RuntimeError(f"SQL 图表出现异值冲突：{dashboard_id}/{chart_id}")

            dialect = str(context["datasources"][outer]["type"])
            physical_tables = sorted(extract_physical_tables(parse_sql_statements(sql, dialect)))
            missing = sorted(set(physical_tables) - context["tables"][outer])
            if missing:
                raise RuntimeError(
                    f"目标数据源缺少 SQL 引用表：{dashboard_id}/{chart_id}: {', '.join(missing)}"
                )
            if inner is None:
                continue
            sql_config.pop("datasource")
            duplicate_count += 1
            charts.append(
                {
                    "tenant_id": str(tenant_id),
                    "tenant_name": profile["name"],
                    "dashboard_id": dashboard_id,
                    "dashboard_name": row["name"],
                    "chart_id": str(chart_id),
                    "datasource": outer,
                    "tables": physical_tables,
                }
            )

        if duplicate_count != expected_count:
            raise RuntimeError(
                f"重复图表数量已变化：{dashboard_id}: {duplicate_count} != {expected_count}"
            )
        new_canvas = json.dumps(canvas, ensure_ascii=False, separators=(",", ":"))
        plans.append(
            {
                "tenant_id": str(tenant_id),
                "tenant_name": profile["name"],
                "dashboard_id": dashboard_id,
                "dashboard_name": row["name"],
                "duplicate_count": duplicate_count,
                "old_canvas": old_canvas,
                "new_canvas": new_canvas,
                "old_sha256": expected_hash,
                "new_sha256": _sha256(new_canvas),
                "old_update_time": row["update_time"],
            }
        )

    if len(plans) != 35 or len(charts) != 139:
        raise RuntimeError(f"目标集合数量无效：dashboards={len(plans)}, charts={len(charts)}")
    return plans, charts


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
                        "chart_count": sum(int(chart["tenant_id"]) == tenant_id for chart in charts),
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
            backup = BACKUP_DIR / f"xiuxian_flam_dashboard_datasources_{time.time_ns()}.json"
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
    if (
        payload.get("kind") != BACKUP_KIND
        or not isinstance(plans, list)
        or {str(plan.get("dashboard_id")) for plan in plans} != set(EXPECTED_DASHBOARDS)
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
