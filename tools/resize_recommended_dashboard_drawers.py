"""Resize every drawer in the recommended dashboards for the two demo spaces."""
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
BACKUP_ROOT = ROOT / ".codex-runtime" / "recommended-dashboard-drawer-backups"
BACKUP_SCHEMA = "recommended-dashboard-drawer/v1"

SPACE_DASHBOARDS: dict[str, tuple[tuple[int, str, str], ...]] = {
    "flam": (
        (7477202383789887488, "4bae835c4243481b9963122b5275ed81", "出征数据"),
        (7477202383789887488, "259414f219f94aacaa46f4e531646b9d", "付费概览"),
        (7477202383789887488, "6d50bd7dfc9f46ba961d636814c3294d", "核心看板"),
        (7477202383789887488, "29ea652e2969440b91899cfb254dd0ca", "活动分析"),
        (7477202383789887488, "8c93878ee7af41b9b3832547856d25e6", "活跃看板"),
        (7477202383789887488, "f26870db68cb44bd974b0160ea91cdae", "经济系统"),
        (7477202383789887488, "8f86e50234794606bd2a33ec41ffa660", "留存分析"),
        (7477202383789887488, "5cee4cf41a024c56ac9de0e3aef9aefe", "渠道分析"),
        (7477202383789887488, "760150000bdc4abbb740880d494f5a5a", "实时看板"),
        (7477202383789887488, "e423819a72454bc9ab71646d41aa5fd6", "投放看板"),
        (7477202383789887488, "bb3ab5f2697a42af98ab90da4679cb77", "新增看板"),
        (7477202383789887488, "1683de014d814e90b2c6dc002df8da1f", "养成看板"),
        (7477202383789887488, "db9df7a9015c4b4bb033810ffc5a84d2", "主城建设"),
        (7477202383789887488, "b7d9a98bd48d46d4bc3d61a7b2c36b08", "ChatMon 流失风险看板"),
        (7477202383789887488, "c4888f5f6ffb4588a4f6c447b7439848", "ChatMon 玩家热点与吐槽看板"),
        (7477202383789887488, "e7305389ebd24f94b12235519dd0d859", "ChatMon 运营问题总览"),
        (7477202383789887488, "4f47cfcd8c014cd9b52ba9d7a5af2d23", "ChatMon Bug反馈看板"),
        (7477202383789887488, "2b990d3821fa4c3d97f0dda519b644e8", "ROI看板"),
    ),
    "xiuxian": (
        (7482727237662281728, "6234ec38697c4924b65c7de11d8bd829", "付费概览"),
        (7482727237662281728, "afe201c9762c448aa0495f3508c01793", "核心看板"),
        (7482727237662281728, "c68e08ee9b4a4be59c3c8fbbe918affd", "活跃看板"),
        (7482727237662281728, "32909e56ee174a2a9d8226be17d51ddf", "留存分析"),
        (7482727237662281728, "a34aef6cb7214f7fa23e5846a0a66236", "渠道分析"),
        (7482727237662281728, "10604280d5a941af9720800bce6e030f", "实时看板"),
        (7482727237662281728, "146ba4deb8b74ab293f38f69d89d4b21", "投放看板"),
        (7482727237662281728, "b09e4d57f57b41859a0c2d4609f80f26", "新增看板"),
        (7482727237662281728, "60c291cf41254cb993c6dff2b38cdca6", "养成看板"),
        (7482727237662281728, "17531de20e5d439f9ddfb2eeececced5", "ROI看板"),
    ),
}

MIN_HEIGHT_BY_TYPE = {
    "metric": 10,
    "table": 14,
}
DEFAULT_MIN_HEIGHT = 16


def _chart_type(view_info: Mapping[str, Any]) -> str:
    chart = view_info.get("chart")
    if not isinstance(chart, Mapping):
        raise RuntimeError("抽屉缺少图表配置")
    chart_type = chart.get("type") or chart.get("sourceType")
    if not isinstance(chart_type, str) or not chart_type.strip():
        raise RuntimeError("抽屉缺少图表类型")
    return chart_type.strip().lower()


def _minimum_height(view_info: Mapping[str, Any]) -> int:
    chart_type = _chart_type(view_info)
    return MIN_HEIGHT_BY_TYPE.get(chart_type, DEFAULT_MIN_HEIGHT)


def _geometry(item: Mapping[str, Any]) -> tuple[int, int, int, int]:
    try:
        x, y = int(item["x"]), int(item["y"])
        size_x, size_y = int(item["sizeX"]), int(item["sizeY"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("抽屉缺少有效网格坐标") from exc
    if min(size_x, size_y) < 1 or min(x, y) < 1:
        raise RuntimeError("抽屉网格坐标必须为正整数")
    return x, y, size_x, size_y


def _has_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def _validate_no_overlap(components: Sequence[Mapping[str, Any]]) -> None:
    geometries = [_geometry(item) for item in components]
    for index, geometry in enumerate(geometries):
        if any(_has_overlap(geometry, other) for other in geometries[index + 1 :]):
            raise RuntimeError("抽屉布局存在重叠")


def resize_dashboard_components(
    components: Sequence[Mapping[str, Any]], view_info: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Raise undersized drawers and shift complete rows without changing content."""

    if not isinstance(components, Sequence) or isinstance(components, (str, bytes)):
        raise RuntimeError("component_data 必须是数组")
    result = copy.deepcopy([dict(item) for item in components])
    ids = [str(item.get("id")) for item in result]
    if len(ids) != len(set(ids)):
        raise RuntimeError("抽屉 ID 重复")
    for item in result:
        component_id = str(item.get("id"))
        if component_id not in view_info:
            raise RuntimeError(f"抽屉 {component_id} 缺少图表配置")
        _geometry(item)
        minimum = _minimum_height(view_info[component_id])
        item["sizeY"] = max(int(item["sizeY"]), minimum)

    _validate_no_overlap(components)
    original_by_id = {str(item["id"]): item for item in components}
    rows: list[list[dict[str, Any]]] = []
    row_bottoms: list[int] = []
    for item in sorted(result, key=lambda value: (int(value["y"]), int(value["x"]))):
        original = original_by_id[str(item["id"])]
        _, original_y, _, original_size_y = _geometry(original)
        placed = False
        for index, bottom in enumerate(row_bottoms):
            if original_y < bottom:
                rows[index].append(item)
                row_bottoms[index] = max(bottom, original_y + original_size_y)
                placed = True
                break
        if not placed:
            rows.append([item])
            row_bottoms.append(original_y + original_size_y)

    cumulative_shift = 0
    for row, original_bottom in zip(rows, row_bottoms):
        desired_bottom = 0
        for item in row:
            original_item = original_by_id[str(item["id"])]
            desired_bottom = max(desired_bottom, int(original_item["y"]) + int(item["sizeY"]))
        row_shift = max(0, desired_bottom - original_bottom)
        for item in row:
            original_item = original_by_id[str(item["id"])]
            item["y"] = int(original_item["y"]) + cumulative_shift
        cumulative_shift += row_shift

    _validate_no_overlap(result)
    return result


def _json_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _select_dashboards(cursor: Any, entries: Sequence[tuple[int, str, str]], *, for_update: bool) -> list[dict[str, Any]]:
    ids = [entry[1] for entry in entries]
    suffix = " FOR UPDATE" if for_update else ""
    cursor.execute(
        f"""
        SELECT id, tenant_id, name, type, delete_flag, component_data, canvas_view_info,
               update_time, update_by, version
        FROM public.core_dashboard
        WHERE id = ANY(%s) AND type = 'dashboard' AND COALESCE(delete_flag, 0) = 0{suffix}
        """,
        (ids,),
    )
    rows = {str(row["id"]): dict(row) for row in cursor.fetchall()}
    expected = {dashboard_id: (tenant_id, name) for tenant_id, dashboard_id, name in entries}
    if set(rows) != set(expected):
        raise RuntimeError("推荐看板清单与数据库记录不一致")
    for dashboard_id, row in rows.items():
        tenant_id, name = expected[dashboard_id]
        if int(row["tenant_id"]) != tenant_id or row["name"] != name:
            raise RuntimeError(f"推荐看板归属校验失败：{dashboard_id}")
    return [rows[dashboard_id] for _, dashboard_id, _ in entries]


def _backup(row: Mapping[str, Any], old_raw: str, new_raw: str) -> Path:
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    dashboard_id = str(row["id"])
    path = BACKUP_ROOT / f"{timestamp}-{dashboard_id}-{_json_hash(old_raw)[:8]}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": BACKUP_SCHEMA,
                "created_at": int(time.time()),
                "dashboard_id": dashboard_id,
                "tenant_id": row["tenant_id"],
                "name": row["name"],
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


def _migrate_rows(rows: Sequence[Mapping[str, Any]], cursor: Any, *, apply: bool) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for row in rows:
        old_raw = str(row["component_data"] or "[]")
        components = json.loads(old_raw)
        canvas = json.loads(str(row["canvas_view_info"] or "{}"))
        if not isinstance(canvas, dict):
            raise RuntimeError(f"看板 {row['id']} 的 canvas_view_info 必须是对象")
        new_components = resize_dashboard_components(components, canvas)
        new_raw = json.dumps(new_components, ensure_ascii=False, separators=(",", ":"))
        changed = new_raw != old_raw
        backup = None
        if apply and changed:
            backup = _backup(row, old_raw, new_raw)
            cursor.execute(
                """
                UPDATE public.core_dashboard
                SET component_data = %s, update_time = %s, update_by = %s,
                    version = COALESCE(version, 0) + 1
                WHERE id = %s AND tenant_id = %s AND component_data = %s
                  AND COALESCE(delete_flag, 0) = 0
                """,
                (new_raw, int(time.time() * 1000), "codex", row["id"], row["tenant_id"], old_raw),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"看板 {row['id']} CAS 更新失败")
            cursor.execute("SELECT component_data FROM public.core_dashboard WHERE id = %s FOR UPDATE", (row["id"],))
            if cursor.fetchone()["component_data"] != new_raw:
                raise RuntimeError(f"看板 {row['id']} 事务内读回布局不一致")
        summaries.append(
            {
                "id": row["id"],
                "name": row["name"],
                "changed": changed,
                "backup": str(backup) if backup else None,
                "component_count": len(components),
            }
        )
    return summaries


def run(space: str, *, apply: bool) -> list[dict[str, Any]]:
    entries = SPACE_DASHBOARDS[space]
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as connection:
        try:
            with connection.cursor() as cursor:
                for _, dashboard_id, _ in entries:
                    cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (dashboard_id,))
                rows = _select_dashboards(cursor, entries, for_update=True)
                summaries = _migrate_rows(rows, cursor, apply=apply)
            if apply:
                connection.commit()
            else:
                connection.rollback()
        except BaseException:
            connection.rollback()
            raise
    return summaries


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--space", choices=["all", *SPACE_DASHBOARDS], default="all")
    parser.add_argument("--apply", action="store_true", help="备份并更新数据库")
    args = parser.parse_args(argv)
    spaces = list(SPACE_DASHBOARDS) if args.space == "all" else [args.space]
    summaries = [summary for space in spaces for summary in run(space, apply=args.apply)]
    print(json.dumps({"apply": args.apply, "spaces": spaces, "dashboards": summaries}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
