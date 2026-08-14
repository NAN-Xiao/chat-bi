# -*- coding: utf-8 -*-
"""将 gig 空间推荐看板的 SQL 产品条件统一为 ``prod = 110000036``。

默认只读验证；``--apply`` 才写入。修复同时覆盖图表执行 SQL 和编辑器 SQL，
清空旧查询结果快照，但不修改图表执行数据源、看板资产归属或用户自建看板。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import psycopg
import sqlglot
from psycopg.rows import dict_row
from sqlglot import exp

from core_system_db import core_system_db_config


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from apps.datasource.crud.sql_permission import extract_physical_tables, parse_sql_statements  # noqa: E402


TENANT_ID = 7493272549510352896
TENANT_PUBLIC_ID = "WSB9NZYM99"
TENANT_NAME = "gig"
BOUND_DATASOURCE = 12
ROI_DATASOURCE = 13
TARGET_PRODUCT_ID = "110000036"
OLD_PRODUCT_COUNTS = {"110000047": 158, "110000038": 36}
MISSING_FILTER_DASHBOARD_ID = "b0cdf1b2629b42f7899c7be655ec868d"
MISSING_FILTER_CHART_ID = "99e31069e8b54504a321b7b8066bf946"
EXCLUDED_USER_DASHBOARD_ID = "237bb30c2bef49aaa43c7fba653ec568"
EXCLUDED_USER_DASHBOARD_IDS = (EXCLUDED_USER_DASHBOARD_ID,)

LOCK_KEY = "repair-gig-recommended-dashboard-product-id-v1"
BACKUP_KIND = "gig_recommended_dashboard_product_id_repair_v1"
BACKUP_FILENAME_PREFIX = "gig_recommended_dashboard_product_id"
BACKUP_DIR = ROOT / ".codex-runtime" / "dashboard-datasource-backups"

DASHBOARDS = {
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
}

OLD_LITERAL_PATTERNS = {
    value: re.compile(rf"(?<![A-Za-z0-9_]){value}(?![A-Za-z0-9_])")
    for value in OLD_PRODUCT_COUNTS
}


def configure_profile(profile: dict[str, Any]) -> None:
    """为独立 CLI 入口配置一个固定工作空间的修复边界。"""
    required = {
        "tenant_id",
        "tenant_public_id",
        "tenant_name",
        "bound_datasource",
        "roi_datasource",
        "target_product_id",
        "old_product_counts",
        "missing_filter_dashboard_id",
        "missing_filter_chart_id",
        "excluded_user_dashboard_id",
        "lock_key",
        "backup_kind",
        "backup_filename_prefix",
        "dashboards",
    }
    missing = sorted(required - set(profile))
    if missing:
        raise RuntimeError(f"修复配置缺少字段：{', '.join(missing)}")

    global TENANT_ID, TENANT_PUBLIC_ID, TENANT_NAME
    global BOUND_DATASOURCE, ROI_DATASOURCE, TARGET_PRODUCT_ID, OLD_PRODUCT_COUNTS
    global MISSING_FILTER_DASHBOARD_ID, MISSING_FILTER_CHART_ID
    global EXCLUDED_USER_DASHBOARD_ID, EXCLUDED_USER_DASHBOARD_IDS
    global LOCK_KEY, BACKUP_KIND, BACKUP_FILENAME_PREFIX, DASHBOARDS, OLD_LITERAL_PATTERNS

    TENANT_ID = int(profile["tenant_id"])
    TENANT_PUBLIC_ID = str(profile["tenant_public_id"])
    TENANT_NAME = str(profile["tenant_name"])
    BOUND_DATASOURCE = int(profile["bound_datasource"])
    ROI_DATASOURCE = int(profile["roi_datasource"])
    TARGET_PRODUCT_ID = str(profile["target_product_id"])
    OLD_PRODUCT_COUNTS = {
        str(value): int(count) for value, count in dict(profile["old_product_counts"]).items()
    }
    MISSING_FILTER_DASHBOARD_ID = str(profile["missing_filter_dashboard_id"])
    MISSING_FILTER_CHART_ID = str(profile["missing_filter_chart_id"])
    EXCLUDED_USER_DASHBOARD_ID = str(profile["excluded_user_dashboard_id"])
    EXCLUDED_USER_DASHBOARD_IDS = tuple(
        str(value) for value in profile.get("excluded_user_dashboard_ids", (EXCLUDED_USER_DASHBOARD_ID,))
    )
    if not EXCLUDED_USER_DASHBOARD_IDS or EXCLUDED_USER_DASHBOARD_ID not in EXCLUDED_USER_DASHBOARD_IDS:
        raise RuntimeError("排除的用户看板配置无效")
    LOCK_KEY = str(profile["lock_key"])
    BACKUP_KIND = str(profile["backup_kind"])
    BACKUP_FILENAME_PREFIX = str(profile["backup_filename_prefix"])
    DASHBOARDS = dict(profile["dashboards"])
    OLD_LITERAL_PATTERNS = {
        value: re.compile(rf"(?<![A-Za-z0-9_]){value}(?![A-Za-z0-9_])")
        for value in OLD_PRODUCT_COUNTS
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


def _parse(sql: str) -> list[exp.Expression]:
    statements = sqlglot.parse(sql, read="mysql")
    if not statements:
        raise RuntimeError("SQL 解析结果为空")
    return statements


def _literal_product_predicates(sql: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for statement in _parse(sql):
        for predicate in statement.find_all(exp.EQ):
            left, right = predicate.this, predicate.expression
            literal: exp.Literal | None = None
            if isinstance(left, exp.Column) and left.name.lower() == "prod" and isinstance(right, exp.Literal):
                literal = right
            elif isinstance(right, exp.Column) and right.name.lower() == "prod" and isinstance(left, exp.Literal):
                literal = left
            if literal is None or literal.is_string:
                continue
            value = str(literal.this)
            counts[value] = counts.get(value, 0) + 1
    return counts


def _replace_old_product_predicates(sql: str) -> tuple[str, dict[str, int]]:
    predicate_counts = _literal_product_predicates(sql)
    replaced_counts: dict[str, int] = {}
    rewritten = sql
    for old_value, pattern in OLD_LITERAL_PATTERNS.items():
        raw_count = len(pattern.findall(sql))
        predicate_count = predicate_counts.get(old_value, 0)
        if raw_count != predicate_count:
            raise RuntimeError(
                f"旧产品常量不全是 prod 等值条件：{old_value}, raw={raw_count}, predicate={predicate_count}"
            )
        rewritten, replaced_counts[old_value] = pattern.subn(TARGET_PRODUCT_ID, rewritten)
    return rewritten, replaced_counts


def _add_missing_product_filter(sql: str, *, column_sql: str) -> str:
    if _literal_product_predicates(sql):
        raise RuntimeError(f"预期缺少 prod 条件的 SQL 已出现条件：{column_sql}")
    group_by = re.search(r"(?im)^(?P<indent>[ \t]*)GROUP\s+BY\b", sql)
    if group_by is None:
        raise RuntimeError("缺少可定位的 GROUP BY，无法安全增加产品条件")
    indent = group_by.group("indent")
    condition = f"{indent}AND {column_sql} = {TARGET_PRODUCT_ID}\n"
    rewritten = sql[: group_by.start()] + condition + sql[group_by.start() :]
    if _literal_product_predicates(rewritten).get(TARGET_PRODUCT_ID, 0) != 1:
        raise RuntimeError("新增产品条件后 SQL 解析校验失败")
    return rewritten


def _clear_result_snapshot(view: dict[str, Any], sql_config: dict[str, Any]) -> None:
    data = view.get("data")
    if not isinstance(data, dict):
        data = {}
        view["data"] = data
    data["data"] = []
    data["fields"] = []
    data.pop("source_data", None)
    data.pop("source_fields", None)
    data["snapshotRefreshedAt"] = 0
    view["fields"] = []
    view["status"] = "success"
    view["message"] = ""
    view["dataState"] = "ready"
    view["loadingProgress"] = 100
    view["snapshotRefreshedAt"] = 0
    view["refreshState"] = ""
    sql_config.pop("lastResult", None)


def _validate_workspace(cur: Any) -> dict[str, Any]:
    cur.execute("SELECT public_id, name, status FROM sys_tenant WHERE id = %s", (TENANT_ID,))
    tenant = cur.fetchone()
    if (
        tenant is None
        or tenant["public_id"] != TENANT_PUBLIC_ID
        or tenant["name"] != TENANT_NAME
        or int(tenant["status"]) != 1
    ):
        raise RuntimeError(f"{TENANT_NAME} 空间身份或状态已变化")

    cur.execute(
        "SELECT datasource_id FROM core_datasource_tenant_binding WHERE tenant_id = %s",
        (TENANT_ID,),
    )
    bindings = cur.fetchall()
    if len(bindings) != 1 or int(bindings[0]["datasource_id"]) != BOUND_DATASOURCE:
        raise RuntimeError(f"{TENANT_NAME} 空间绑定数据源已变化")

    cur.execute(
        "SELECT datasource_id FROM core_roi_workspace_config WHERE tenant_id = %s AND deleted = false",
        (TENANT_ID,),
    )
    roi_rows = cur.fetchall()
    if len(roi_rows) != 1 or int(roi_rows[0]["datasource_id"]) != ROI_DATASOURCE:
        raise RuntimeError(f"{TENANT_NAME} 空间 ROI 数据源配置已变化")

    datasource_ids = [BOUND_DATASOURCE, ROI_DATASOURCE]
    cur.execute("SELECT id, type, status FROM core_datasource WHERE id = ANY(%s)", (datasource_ids,))
    datasources = {int(row["id"]): row for row in cur.fetchall()}
    if set(datasources) != set(datasource_ids) or any(
        str(datasources[ds_id]["status"]).lower() != "success" for ds_id in datasource_ids
    ):
        raise RuntimeError(f"{TENANT_NAME} 普通数据源或 ROI 数据源不存在或状态无效")

    cur.execute(
        "SELECT ds_id, table_name FROM core_table WHERE ds_id = ANY(%s) AND COALESCE(checked, true) = true",
        (datasource_ids,),
    )
    tables = {ds_id: set() for ds_id in datasource_ids}
    for row in cur.fetchall():
        tables[int(row["ds_id"])].add(str(row["table_name"]))
    return {"datasources": datasources, "tables": tables}


def _validate_dashboard_scope(cur: Any) -> tuple[list[dict[str, Any]], dict[str, str]]:
    cur.execute(
        """
        SELECT id, tenant_id, name, datasource, canvas_view_info, update_time, is_default
        FROM core_dashboard
        WHERE tenant_id = %s
          AND COALESCE(delete_flag, 0) = 0
          AND node_type = 'leaf'
          AND is_default = 1
        ORDER BY id
        """,
        (TENANT_ID,),
    )
    rows = list(cur.fetchall())
    if {str(row["id"]) for row in rows} != set(DASHBOARDS):
        raise RuntimeError(f"{TENANT_NAME} 推荐看板集合已变化")

    cur.execute(
        """
        SELECT id, name, is_default, canvas_view_info
        FROM core_dashboard
        WHERE id = ANY(%s) AND tenant_id = %s AND COALESCE(delete_flag, 0) = 0
        """,
        (list(EXCLUDED_USER_DASHBOARD_IDS), TENANT_ID),
    )
    excluded_rows = cur.fetchall()
    if (
        {str(row["id"]) for row in excluded_rows} != set(EXCLUDED_USER_DASHBOARD_IDS)
        or any(int(row["is_default"]) != 0 for row in excluded_rows)
    ):
        raise RuntimeError(f"排除的 {TENANT_NAME} 用户自建看板不存在或属性已变化")
    return rows, {
        str(row["id"]): _sha256(str(row["canvas_view_info"] or "{}")) for row in excluded_rows
    }


def _build_plans(cur: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    context = _validate_workspace(cur)
    rows, excluded_hashes = _validate_dashboard_scope(cur)
    plans: list[dict[str, Any]] = []
    charts: list[dict[str, Any]] = []
    total_old_counts = {value: 0 for value in OLD_PRODUCT_COUNTS}
    missing_paths: list[str] = []
    target_path_count = 0

    for row in rows:
        dashboard_id = str(row["id"])
        expected_name, role, expected_chart_count = DASHBOARDS[dashboard_id]
        target_datasource = ROI_DATASOURCE if role == "roi" else BOUND_DATASOURCE
        if row["name"] != expected_name or _datasource_id(row["datasource"]) != BOUND_DATASOURCE:
            raise RuntimeError(f"看板名称或资产数据源已变化：{dashboard_id}")

        old_canvas = str(row["canvas_view_info"] or "{}")
        canvas = json.loads(old_canvas)
        if not isinstance(canvas, dict):
            raise RuntimeError(f"画布不是 JSON 对象：{dashboard_id}")

        dashboard_chart_count = 0
        dashboard_changed = False
        for chart_id, view in canvas.items():
            if not isinstance(view, dict) or not str(view.get("sql") or "").strip():
                continue
            sql_config = _sql_config(view)
            if sql_config is None or not str(sql_config.get("sql") or "").strip():
                raise RuntimeError(f"SQL 图表缺少编辑器 SQL：{dashboard_id}/{chart_id}")
            if _datasource_id(view.get("datasource")) != target_datasource:
                raise RuntimeError(f"图表执行数据源已变化：{dashboard_id}/{chart_id}")
            if "datasource" in sql_config:
                raise RuntimeError(f"图表重新出现重复内层数据源：{dashboard_id}/{chart_id}")

            path_specs = (
                ("sql", view, "sql", "e.prod"),
                ("sourceConfig.sql.sql", sql_config, "sql", "`event`.`prod`"),
            )
            chart_old_counts = {value: 0 for value in OLD_PRODUCT_COUNTS}
            chart_changed = False
            path_reports: list[dict[str, Any]] = []
            for path_name, owner, key, missing_column in path_specs:
                original_sql = str(owner[key]).strip()
                predicates = _literal_product_predicates(original_sql)
                original_tables = sorted(
                    extract_physical_tables(
                        parse_sql_statements(
                            original_sql,
                            str(context["datasources"][target_datasource]["type"]),
                        )
                    )
                )
                old_count = sum(predicates.get(value, 0) for value in OLD_PRODUCT_COUNTS)
                target_count = predicates.get(TARGET_PRODUCT_ID, 0)
                path_key = f"{dashboard_id}/{chart_id}/{path_name}"
                if old_count == 0 and target_count == 0:
                    missing_paths.append(path_key)
                    rewritten_sql = original_sql
                else:
                    rewritten_sql, replaced = _replace_old_product_predicates(original_sql)
                    for value, count in replaced.items():
                        chart_old_counts[value] += count
                        total_old_counts[value] += count
                    if target_count > 0:
                        target_path_count += 1

                if str(chart_id) == MISSING_FILTER_CHART_ID and old_count == 0 and target_count == 0:
                    rewritten_sql = _add_missing_product_filter(original_sql, column_sql=missing_column)

                final_predicates = _literal_product_predicates(rewritten_sql)
                if final_predicates.get(TARGET_PRODUCT_ID, 0) < 1:
                    raise RuntimeError(f"SQL 未得到目标产品条件：{path_key}")
                if any(final_predicates.get(value, 0) for value in OLD_PRODUCT_COUNTS):
                    raise RuntimeError(f"SQL 仍包含旧产品条件：{path_key}")

                rewritten_tables = sorted(
                    extract_physical_tables(
                        parse_sql_statements(rewritten_sql, str(context["datasources"][target_datasource]["type"]))
                    )
                )
                if rewritten_tables != original_tables:
                    raise RuntimeError(f"产品条件变更意外改变 SQL 引用表：{path_key}")
                missing_tables = sorted(set(rewritten_tables) - context["tables"][target_datasource])
                if path_name == "sql" and missing_tables:
                    raise RuntimeError(
                        f"目标数据源缺少 SQL 引用表：{path_key}: {', '.join(missing_tables)}"
                    )
                if rewritten_sql != original_sql:
                    owner[key] = rewritten_sql
                    chart_changed = True
                path_reports.append(
                    {
                        "path": path_name,
                        "old_product_counts": {
                            value: predicates.get(value, 0) for value in OLD_PRODUCT_COUNTS
                        },
                        "target_product_count": final_predicates.get(TARGET_PRODUCT_ID, 0),
                        "tables": rewritten_tables,
                        "editor_only_unresolved_tables": (
                            missing_tables if path_name == "sourceConfig.sql.sql" else []
                        ),
                    }
                )

            if chart_changed:
                _clear_result_snapshot(view, sql_config)
                dashboard_changed = True
            dashboard_chart_count += 1
            charts.append(
                {
                    "dashboard_id": dashboard_id,
                    "dashboard_name": expected_name,
                    "chart_id": str(chart_id),
                    "role": role,
                    "datasource": target_datasource,
                    "old_product_counts": chart_old_counts,
                    "paths": path_reports,
                }
            )

        if dashboard_chart_count != expected_chart_count:
            raise RuntimeError(
                f"SQL 图表数量已变化：{dashboard_id}: {dashboard_chart_count} != {expected_chart_count}"
            )
        new_canvas = json.dumps(canvas, ensure_ascii=False, separators=(",", ":"))
        plans.append(
            {
                "tenant_id": str(TENANT_ID),
                "dashboard_id": dashboard_id,
                "dashboard_name": expected_name,
                "role": role,
                "chart_count": dashboard_chart_count,
                "changed": dashboard_changed,
                "old_canvas": old_canvas,
                "new_canvas": new_canvas,
                "old_sha256": _sha256(old_canvas),
                "new_sha256": _sha256(new_canvas),
                "old_update_time": row["update_time"],
            }
        )

    if len(plans) != 10 or len(charts) != 55:
        raise RuntimeError(f"目标集合数量无效：dashboards={len(plans)}, charts={len(charts)}")

    pending_state = total_old_counts == OLD_PRODUCT_COUNTS and target_path_count == 0
    clean_state = all(count == 0 for count in total_old_counts.values()) and target_path_count == 110
    expected_missing = {
        f"{MISSING_FILTER_DASHBOARD_ID}/{MISSING_FILTER_CHART_ID}/sql",
        f"{MISSING_FILTER_DASHBOARD_ID}/{MISSING_FILTER_CHART_ID}/sourceConfig.sql.sql",
    }
    if pending_state and set(missing_paths) != expected_missing:
        raise RuntimeError(f"缺少产品条件的 SQL 集合已变化：{missing_paths}")
    if clean_state and missing_paths:
        raise RuntimeError(f"已修复状态仍有 SQL 缺少产品条件：{missing_paths}")
    if not pending_state and not clean_state:
        raise RuntimeError(
            f"推荐看板产品条件处于混合状态：old={total_old_counts}, target_paths={target_path_count}"
        )

    state = "pending" if pending_state else "clean"
    return plans, charts, {
        "state": state,
        "old_product_counts": total_old_counts,
        "missing_filter_paths": missing_paths,
        "excluded_user_dashboard_id": EXCLUDED_USER_DASHBOARD_ID,
        "excluded_user_dashboard_sha256": excluded_hashes[EXCLUDED_USER_DASHBOARD_ID],
        "excluded_user_dashboard_sha256s": excluded_hashes,
    }


def run(*, apply: bool) -> dict[str, Any]:
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            if apply:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (LOCK_KEY,))
            plans, charts, audit = _build_plans(cur)
            changed_plans = [plan for plan in plans if plan["changed"]]
            result: dict[str, Any] = {
                "apply": apply,
                "tenant_id": str(TENANT_ID),
                "tenant_name": TENANT_NAME,
                "bound_datasource": BOUND_DATASOURCE,
                "roi_datasource": ROI_DATASOURCE,
                "target_product_id": TARGET_PRODUCT_ID,
                "dashboard_count": len(plans),
                "chart_count": len(charts),
                "sql_copy_count": len(charts) * 2,
                "changed_dashboard_count": len(changed_plans),
                **audit,
            }
            if not apply or not changed_plans:
                conn.rollback()
                return result

            new_update_time = int(time.time())
            for plan in changed_plans:
                plan["new_update_time"] = new_update_time
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            backup = BACKUP_DIR / f"{BACKUP_FILENAME_PREFIX}_{time.time_ns()}.json"
            backup.write_text(
                json.dumps(
                    {"kind": BACKUP_KIND, "created_at": int(time.time()), "rows": changed_plans, **result},
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )

            for plan in changed_plans:
                cur.execute(
                    """
                    UPDATE core_dashboard
                    SET canvas_view_info = %s, update_time = %s
                    WHERE id = %s AND tenant_id = %s
                      AND is_default = 1
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

            cur.execute(
                "SELECT id, canvas_view_info FROM core_dashboard WHERE id = ANY(%s) AND tenant_id = %s",
                (list(EXCLUDED_USER_DASHBOARD_IDS), TENANT_ID),
            )
            current_excluded_hashes = {
                str(row["id"]): _sha256(str(row["canvas_view_info"] or "{}")) for row in cur.fetchall()
            }
            if current_excluded_hashes != audit["excluded_user_dashboard_sha256s"]:
                raise RuntimeError("排除的用户自建看板在事务中发生变化")
            conn.commit()
            result.update(
                {
                    "state": "clean",
                    "backup": str(backup.resolve()),
                    "new_update_time": new_update_time,
                }
            )
            return result


def restore(backup_file: Path) -> dict[str, Any]:
    payload = json.loads(backup_file.read_text(encoding="utf-8"))
    plans = payload.get("rows")
    if (
        payload.get("kind") != BACKUP_KIND
        or not isinstance(plans, list)
        or {str(plan.get("dashboard_id")) for plan in plans} != set(DASHBOARDS)
    ):
        raise RuntimeError(f"备份文件与 {TENANT_NAME} 推荐看板集合不匹配")

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
                      AND is_default = 1
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
