# -*- coding: utf-8 -*-
"""修复 gig、lds、j2000、unicorn ROI 看板中的跨库 SQL 限定名。

默认只读审计；显式传入 ``--apply`` 才更新系统数据库。修复只移除
``first_zombie.`` / ``xtxdj.`` 前缀，使查询落到每个空间配置的 ROI 数据库，
不改变表、字段、prod、日期参数、聚合或图表执行数据源。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from sqlglot import exp

from core_system_db import core_system_db_config


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from apps.datasource.crud.sql_permission import (  # noqa: E402
    extract_physical_tables,
    normalize_identifier,
    parse_sql_statements,
)
from apps.datasource.utils.utils import aes_decrypt  # noqa: E402


LOCK_KEY = "repair-clone-roi-dashboard-namespaces-v1"
BACKUP_KIND = "clone_roi_dashboard_namespaces_v1"
BACKUP_DIR = ROOT / ".codex-runtime" / "dashboard-namespace-backups"
OLD_NAMESPACES = {"first_zombie", "xtxdj"}
TARGET_DASHBOARD_NAME = "ROI看板"
LEGACY_DASHBOARD_NAME = "ROI였겼"
PRODUCT_PATTERN = re.compile(r"(?<!\d)110000\d{3}(?!\d)")
PARAMETER_PATTERN = re.compile(r"\{\{[A-Za-z_][A-Za-z0-9_]*\}\}")

PROFILES = {
    "gig": {
        "tenant_id": 7493272549510352896,
        "asset_datasource": 12,
        "roi_datasource": 13,
        "dashboard_id": "a882fa4c6d8b418da44503f2486835d4",
        "product_id": "110000036",
    },
    "lds": {
        "tenant_id": 7493272675721154560,
        "asset_datasource": 10,
        "roi_datasource": 14,
        "dashboard_id": "1c6f7e9d972b437dbb2330d85028528f",
        "product_id": "110000039",
    },
    "j2000": {
        "tenant_id": 7493583991958671360,
        "asset_datasource": 11,
        "roi_datasource": 15,
        "dashboard_id": "ff98c30d2a844fb1b0d4bf2a07eb2a3a",
        "product_id": "110000034",
    },
    "unicorn": {
        "tenant_id": 7493583885482070016,
        "asset_datasource": 9,
        "roi_datasource": 16,
        "dashboard_id": "dcb7645772724045bf3097811b2e9a14",
        "product_id": "110000030",
    },
}


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sql_config(view: dict[str, Any]) -> dict[str, Any] | None:
    source_config = view.get("sourceConfig")
    if not isinstance(source_config, dict):
        return None
    sql_config = source_config.get("sql")
    return sql_config if isinstance(sql_config, dict) else None


def _physical_table_nodes(statements: list[exp.Expression]):
    for statement in statements:
        cte_names = {
            normalize_identifier(cte.alias_or_name)
            for cte in statement.find_all(exp.CTE)
            if cte.alias_or_name
        }
        for table in statement.find_all(exp.Table):
            table_name = normalize_identifier(table.name)
            if (
                table_name in cte_names
                and not normalize_identifier(table.db)
                and not normalize_identifier(table.catalog)
            ):
                continue
            if table_name:
                yield table


def rewrite_sql_namespaces(sql: str, dialect: str) -> tuple[str, Counter[str]]:
    """按 SQL AST 确认目标后，仅删除已知旧数据库前缀。"""
    statements = parse_sql_statements(sql, dialect)
    original_tables = extract_physical_tables(statements)
    qualified_nodes = [
        table
        for table in _physical_table_nodes(statements)
        if normalize_identifier(table.db) or normalize_identifier(table.catalog)
    ]
    unexpected = {
        ".".join(
            part
            for part in (
                normalize_identifier(table.catalog),
                normalize_identifier(table.db),
                normalize_identifier(table.name),
            )
            if part
        )
        for table in qualified_nodes
        if normalize_identifier(table.catalog)
        or normalize_identifier(table.db) not in OLD_NAMESPACES
    }
    if unexpected:
        raise RuntimeError("SQL 含非预期限定表：" + ", ".join(sorted(unexpected)))

    counts = Counter(normalize_identifier(table.db) for table in qualified_nodes)
    if not qualified_nodes:
        return sql, counts

    table_names = sorted(
        {normalize_identifier(table.name) for table in qualified_nodes},
        key=len,
        reverse=True,
    )
    namespace_pattern = "|".join(re.escape(value) for value in sorted(OLD_NAMESPACES))
    table_pattern = "|".join(re.escape(value) for value in table_names)
    pattern = re.compile(
        rf"(?i)(?:`?(?:{namespace_pattern})`?)\s*\.\s*(?P<table>`?(?:{table_pattern})`?)"
    )
    rewritten, replacement_count = pattern.subn(lambda match: match.group("table"), sql)
    if replacement_count != len(qualified_nodes):
        raise RuntimeError(
            f"SQL 限定名文本与 AST 数量不一致：text={replacement_count}, ast={len(qualified_nodes)}"
        )

    rewritten_statements = parse_sql_statements(rewritten, dialect)
    rewritten_qualified = [
        table
        for table in _physical_table_nodes(rewritten_statements)
        if normalize_identifier(table.db) or normalize_identifier(table.catalog)
    ]
    if rewritten_qualified:
        raise RuntimeError("SQL 改写后仍包含库或 Schema 限定名")
    if extract_physical_tables(rewritten_statements) != original_tables:
        raise RuntimeError("移除限定名意外改变了 SQL 物理表集合")
    if Counter(PARAMETER_PATTERN.findall(rewritten)) != Counter(PARAMETER_PATTERN.findall(sql)):
        raise RuntimeError("移除限定名意外改变了看板日期参数")
    if Counter(PRODUCT_PATTERN.findall(rewritten)) != Counter(PRODUCT_PATTERN.findall(sql)):
        raise RuntimeError("移除限定名意外改变了产品条件")
    return rewritten, counts


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


def _validate_profile_context(cur: Any, name: str, profile: dict[str, Any]) -> tuple[str, set[str]]:
    cur.execute(
        "SELECT datasource_id FROM core_roi_workspace_config WHERE tenant_id=%s AND deleted=false",
        (profile["tenant_id"],),
    )
    roi_rows = cur.fetchall()
    if len(roi_rows) != 1 or int(roi_rows[0]["datasource_id"]) != profile["roi_datasource"]:
        raise RuntimeError(f"{name} ROI 数据源绑定已变化")

    cur.execute(
        "SELECT id, type, status, configuration FROM core_datasource WHERE id=%s",
        (profile["roi_datasource"],),
    )
    datasource = cur.fetchone()
    if datasource is None or str(datasource["status"]).casefold() != "success":
        raise RuntimeError(f"{name} ROI 数据源不存在或状态无效")
    configuration = json.loads(aes_decrypt(datasource["configuration"]) or "{}")
    if normalize_identifier(configuration.get("database")) != name:
        raise RuntimeError(f"{name} ROI 数据源物理数据库已变化")

    cur.execute(
        "SELECT table_name FROM core_table WHERE ds_id=%s AND COALESCE(checked,true)=true",
        (profile["roi_datasource"],),
    )
    tables = {normalize_identifier(row["table_name"]) for row in cur.fetchall()}
    if not tables:
        raise RuntimeError(f"{name} ROI 数据源没有可用 Schema 元数据")
    return str(datasource["type"]), tables


def _build_plans(cur: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    plans: list[dict[str, Any]] = []
    total_counts: Counter[str] = Counter()
    pending_sql_copies = 0
    total_sql_copies = 0
    total_charts = 0

    for name, profile in PROFILES.items():
        dialect, available_tables = _validate_profile_context(cur, name, profile)
        cur.execute(
            """
            SELECT id, tenant_id, name, datasource, canvas_view_info, update_time,
                   is_default, status, delete_flag, node_type
            FROM core_dashboard
            WHERE id=%s AND tenant_id=%s
            """,
            (profile["dashboard_id"], profile["tenant_id"]),
        )
        row = cur.fetchone()
        if (
            row is None
            or int(row["datasource"]) != profile["asset_datasource"]
            or int(row["is_default"]) != 1
            or int(row["status"]) != 1
            or int(row["delete_flag"] or 0) != 0
            or row["node_type"] != "leaf"
            or row["name"] not in {LEGACY_DASHBOARD_NAME, TARGET_DASHBOARD_NAME}
        ):
            raise RuntimeError(f"{name} ROI 看板身份或状态已变化")

        old_canvas = str(row["canvas_view_info"] or "{}")
        canvas = json.loads(old_canvas)
        if not isinstance(canvas, dict):
            raise RuntimeError(f"{name} ROI 看板画布不是 JSON 对象")

        chart_count = 0
        dashboard_changed = False
        for chart_id, view in canvas.items():
            if not isinstance(view, dict) or not str(view.get("sql") or "").strip():
                continue
            sql_config = _sql_config(view)
            if sql_config is None or not str(sql_config.get("sql") or "").strip():
                raise RuntimeError(f"{name}/{chart_id} 缺少编辑器 SQL")
            if int(view.get("datasource") or 0) != profile["roi_datasource"]:
                raise RuntimeError(f"{name}/{chart_id} 图表执行数据源已变化")
            if sql_config.get("datasource") not in (None, ""):
                raise RuntimeError(f"{name}/{chart_id} 重新出现内层数据源冲突")

            chart_changed = False
            for path_name, owner in (("sql", view), ("sourceConfig.sql.sql", sql_config)):
                original_sql = str(owner["sql"])
                products = set(PRODUCT_PATTERN.findall(original_sql))
                if products - {profile["product_id"]}:
                    raise RuntimeError(
                        f"{name}/{chart_id}/{path_name} 含其他产品条件：{sorted(products)}"
                    )
                rewritten_sql, counts = rewrite_sql_namespaces(original_sql, dialect)
                tables = extract_physical_tables(parse_sql_statements(rewritten_sql, dialect))
                missing_tables = tables - available_tables
                if missing_tables:
                    raise RuntimeError(
                        f"{name}/{chart_id}/{path_name} 目标数据源缺表：{sorted(missing_tables)}"
                    )
                total_sql_copies += 1
                total_counts.update(counts)
                if counts:
                    pending_sql_copies += 1
                if rewritten_sql != original_sql:
                    owner["sql"] = rewritten_sql
                    chart_changed = True

            if chart_changed:
                _clear_result_snapshot(view, sql_config)
                dashboard_changed = True
            chart_count += 1

        if chart_count != 5:
            raise RuntimeError(f"{name} ROI SQL 图表数量已变化：{chart_count} != 5")
        total_charts += chart_count
        new_canvas = json.dumps(canvas, ensure_ascii=False, separators=(",", ":"))
        new_name = TARGET_DASHBOARD_NAME
        changed = dashboard_changed or row["name"] != new_name
        plans.append(
            {
                "tenant_id": str(profile["tenant_id"]),
                "dashboard_id": profile["dashboard_id"],
                "old_name": row["name"],
                "new_name": new_name,
                "old_canvas": old_canvas,
                "new_canvas": new_canvas,
                "old_sha256": _sha256(old_canvas),
                "new_sha256": _sha256(new_canvas),
                "old_update_time": row["update_time"],
                "changed": changed,
            }
        )

    if total_charts != 20 or total_sql_copies != 40:
        raise RuntimeError(f"目标规模已变化：charts={total_charts}, sql_copies={total_sql_copies}")
    if pending_sql_copies not in {0, total_sql_copies}:
        raise RuntimeError(
            f"ROI SQL 限定名处于混合状态：pending={pending_sql_copies}/{total_sql_copies}"
        )
    state = "pending" if pending_sql_copies else "clean"
    return plans, {
        "state": state,
        "dashboard_count": len(plans),
        "chart_count": total_charts,
        "sql_copy_count": total_sql_copies,
        "pending_sql_copy_count": pending_sql_copies,
        "namespace_reference_counts": dict(sorted(total_counts.items())),
    }


def run(*, apply: bool) -> dict[str, Any]:
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            if apply:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (LOCK_KEY,))
            plans, audit = _build_plans(cur)
            changed_plans = [plan for plan in plans if plan["changed"]]
            result = {"apply": apply, "changed_dashboard_count": len(changed_plans), **audit}
            if not apply or not changed_plans:
                conn.rollback()
                return result

            new_update_time = int(time.time())
            for plan in changed_plans:
                plan["new_update_time"] = new_update_time
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            backup = BACKUP_DIR / f"clone_roi_dashboard_namespaces_{time.time_ns()}.json"
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
                    SET name=%s, canvas_view_info=%s, update_time=%s
                    WHERE id=%s AND tenant_id=%s AND name=%s
                      AND canvas_view_info=%s
                      AND update_time IS NOT DISTINCT FROM %s
                      AND is_default=1 AND COALESCE(delete_flag,0)=0
                    """,
                    (
                        plan["new_name"],
                        plan["new_canvas"],
                        new_update_time,
                        plan["dashboard_id"],
                        int(plan["tenant_id"]),
                        plan["old_name"],
                        plan["old_canvas"],
                        plan["old_update_time"],
                    ),
                )
                if cur.rowcount != 1:
                    raise RuntimeError(f"CAS 更新失败：{plan['dashboard_id']}")

            _readback_plans, readback = _build_plans(cur)
            if readback["state"] != "clean" or any(plan["changed"] for plan in _readback_plans):
                raise RuntimeError("写后复核未达到 clean 状态")
            conn.commit()
            return {
                **result,
                "repaired_sql_copy_count": audit["pending_sql_copy_count"],
                "repaired_namespace_reference_counts": audit["namespace_reference_counts"],
                **readback,
                "changed_dashboard_count": len(changed_plans),
                "backup": str(backup.resolve()),
                "new_update_time": new_update_time,
            }


def restore(backup_file: Path) -> dict[str, Any]:
    payload = json.loads(backup_file.read_text(encoding="utf-8"))
    plans = payload.get("rows")
    if (
        payload.get("kind") != BACKUP_KIND
        or not isinstance(plans, list)
        or {str(plan.get("dashboard_id")) for plan in plans}
        != {profile["dashboard_id"] for profile in PROFILES.values()}
    ):
        raise RuntimeError("备份文件与四个 ROI 看板不匹配")

    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (LOCK_KEY,))
            for plan in plans:
                cur.execute(
                    """
                    UPDATE core_dashboard
                    SET name=%s, canvas_view_info=%s, update_time=%s
                    WHERE id=%s AND tenant_id=%s AND name=%s
                      AND canvas_view_info=%s
                      AND update_time IS NOT DISTINCT FROM %s
                      AND is_default=1 AND COALESCE(delete_flag,0)=0
                    """,
                    (
                        plan["old_name"],
                        plan["old_canvas"],
                        plan["old_update_time"],
                        plan["dashboard_id"],
                        int(plan["tenant_id"]),
                        plan["new_name"],
                        plan["new_canvas"],
                        plan["new_update_time"],
                    ),
                )
                if cur.rowcount != 1:
                    raise RuntimeError(f"恢复 CAS 校验失败：{plan['dashboard_id']}")
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
