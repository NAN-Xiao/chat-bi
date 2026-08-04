"""将 flam 默认看板的通用视觉配置同步到修仙默认看板。"""

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
TENANT_ID = 7482727237662281728
DATASOURCE_ID = 6
CORE_DASHBOARD_ID = "afe201c9762c448aa0495f3508c01793"
ROI_DASHBOARD_ID = "17531de20e5d439f9ddfb2eeececced5"
ROI_EXTRA_VIEW_ID = "f8a0e9a2a3f94e7ea5c2aab5ef19b0c1"
BACKUP_ROOT = ROOT / ".codex-runtime" / "xiuxian-dashboard-visual-sync-backups"
FLAM_TENANT_ID = 7477202383789887488
FLAM_DATASOURCE_ID = 3

TARGETS = {
    CORE_DASHBOARD_ID: "核心看板",
    ROI_DASHBOARD_ID: "ROI看板",
}
FLAM_TARGETS = {
    "6d50bd7dfc9f46ba961d636814c3294d": "核心看板",
    "2b990d3821fa4c3d97f0dda519b644e8": "ROI看板",
}

CORE_LAYOUT = {
    "活跃用户": (1, 1, 18, 10),
    "新增用户": (19, 1, 18, 10),
    "充值人数": (37, 1, 18, 10),
    "充值总额": (55, 1, 18, 10),
    "ARPU与ARPPU": (1, 11, 36, 16),
    "日付费率": (37, 11, 36, 16),
    "DAU趋势": (1, 27, 36, 16),
    "新增用户趋势": (37, 27, 36, 16),
    "每日渠道新增用户": (1, 43, 36, 16),
    "累计付费用户趋势": (37, 43, 36, 16),
    "礼包购买情况": (1, 59, 36, 16),
    "渠道累计付费排行": (37, 59, 36, 16),
    "新增用户ARPU与ARPPU": (1, 75, 36, 14),
    "当前等级分布": (37, 75, 35, 16),
    "各渠道新增留存": (1, 91, 72, 18),
}

ROI_REQUIRED_FIELDS = {
    "ROI总览": {"日期", "首日ROI", "3日ROI"},
    "ROI数据总览": {"日期", "首日ROI", "3日ROI"},
    "ROI地区总览": {"日期", "地区", "首日ROI", "3日ROI"},
    "ROI广告地区总览": {
        "日期",
        "广告渠道",
        "安装数",
        "投放成本",
        "单次安装成本",
        "首日收入",
        "3日收入",
        "首日ROI",
        "3日ROI",
    },
}

VOLATILE_VIEW_KEYS = {
    "data",
    "loadingProgress",
    "refreshState",
    "externalSnapshot",
    "snapshotRefreshedAt",
    "status",
    "message",
    "dataState",
}


def _component(
    view_id: str, x: int, y: int, size_x: int, size_y: int
) -> dict[str, Any]:
    return {
        "id": view_id,
        "component": "SQView",
        "name": "new-view",
        "propValue": "&nbsp;",
        "icon": "icon_graphical",
        "innerType": "bar",
        "locked": False,
        "editing": False,
        "x": x,
        "y": y,
        "sizeX": size_x,
        "sizeY": size_y,
        "style": {},
        "_dragId": view_id,
        "show": True,
    }


def _chart(canvas: Mapping[str, Any], view_id: str) -> dict[str, Any]:
    view = canvas.get(view_id)
    if not isinstance(view, Mapping):
        raise ValueError(f"缺少视图 {view_id}")
    value = view.get("chart")
    if not isinstance(value, Mapping):
        raise ValueError(f"视图 {view_id} 缺少 chart 配置")
    return dict(value)


def _title_index(
    components: Sequence[Mapping[str, Any]], canvas: Mapping[str, Any]
) -> dict[str, str]:
    ids = [str(item.get("id")) for item in components]
    if len(ids) != len(set(ids)):
        raise ValueError("组件 ID 重复")
    if set(ids) != set(canvas):
        raise ValueError("组件与 canvas 视图清单不一致")
    result: dict[str, str] = {}
    for view_id in ids:
        title = _chart(canvas, view_id).get("title")
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"视图 {view_id} 缺少标题")
        if title in result:
            raise ValueError(f"图表标题重复：{title}")
        result[title] = view_id
    return result


def _geometry(item: Mapping[str, Any]) -> tuple[int, int, int, int]:
    try:
        raw_values = tuple(item[key] for key in ("x", "y", "sizeX", "sizeY"))
    except KeyError as exc:
        raise ValueError("组件缺少有效网格坐标") from exc
    if any(type(value) is not int for value in raw_values):
        raise ValueError("组件网格坐标必须为整数")
    values = raw_values
    if any(value < 1 for value in values):
        raise ValueError("组件网格坐标必须为正整数")
    return values  # type: ignore[return-value]


def _overlap(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> bool:
    lx, ly, lw, lh = left
    rx, ry, rw, rh = right
    return lx < rx + rw and rx < lx + lw and ly < ry + rh and ry < ly + lh


def validate_layout(components: Sequence[Mapping[str, Any]]) -> None:
    geometries = [_geometry(item) for item in components]
    for index, geometry in enumerate(geometries):
        if any(_overlap(geometry, other) for other in geometries[index + 1 :]):
            raise ValueError("布局存在重叠")


def _field_names(view: Mapping[str, Any]) -> set[str]:
    fields = view.get("fields")
    if not isinstance(fields, list):
        raise ValueError("视图缺少 fields 字段清单")
    result: set[str] = set()
    for field in fields:
        if isinstance(field, str):
            result.add(field)
        elif isinstance(field, Mapping):
            value = field.get("fieldName") or field.get("name") or field.get("value")
            if isinstance(value, str):
                result.add(value)
    return result


def _require_fields(view: Mapping[str, Any], title: str, required: set[str]) -> None:
    missing = required - _field_names(view)
    if missing:
        raise ValueError(f"{title} 缺少字段：{', '.join(sorted(missing))}")


def _validate_core_contract(
    components: Sequence[Mapping[str, Any]], canvas: Mapping[str, Any]
) -> None:
    titles = _title_index(components, canvas)
    if set(titles) != set(CORE_LAYOUT):
        raise ValueError("核心看板组件清单与目标布局不一致")
    for title, expected in CORE_LAYOUT.items():
        component = next(
            item for item in components if str(item.get("id")) == titles[title]
        )
        if _geometry(component) != expected:
            raise ValueError(f"核心看板 {title} 布局不一致")
    _require_fields(
        canvas[titles["ARPU与ARPPU"]], "ARPU与ARPPU", {"dt", "ARPU", "ARPPU"}
    )
    _require_fields(
        canvas[titles["新增用户趋势"]], "新增用户趋势", {"日期", "新增用户数"}
    )
    _require_fields(
        canvas[titles["每日渠道新增用户"]],
        "每日渠道新增用户",
        {"日期", "渠道", "新增用户数"},
    )


def _set_type(view: dict[str, Any], chart_type: str) -> None:
    chart = dict(view["chart"])
    chart["type"] = chart_type
    chart["sourceType"] = chart_type
    view["chart"] = chart


def transform_core_dashboard(
    components: Sequence[Mapping[str, Any]], canvas: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    result_components = copy.deepcopy([dict(item) for item in components])
    result_canvas = copy.deepcopy(dict(canvas))
    _validate_core_contract(result_components, result_canvas)
    titles = _title_index(result_components, result_canvas)
    changes = {
        "ARPU与ARPPU": "column",
        "新增用户趋势": "column",
        "每日渠道新增用户": "area",
    }
    changed_titles: list[str] = []
    for title, chart_type in changes.items():
        view_id = titles.get(title)
        if view_id is None:
            raise ValueError(f"核心看板缺少必需图表：{title}")
        chart = _chart(result_canvas, view_id)
        if chart.get("type") != chart_type or chart.get("sourceType") != chart_type:
            _set_type(result_canvas[view_id], chart_type)
            changed_titles.append(title)
    validate_layout(result_components)
    return (
        result_components,
        result_canvas,
        {"changed": bool(changed_titles), "titles": changed_titles},
    )


def _extra_roi_view(summary_view: Mapping[str, Any]) -> dict[str, Any]:
    view = copy.deepcopy(dict(summary_view))
    view["id"] = ROI_EXTRA_VIEW_ID
    chart = dict(view.get("chart") or {})
    chart.update(
        {
            "id": ROI_EXTRA_VIEW_ID,
            "title": "图表",
            "type": "column",
            "sourceType": "column",
            "xAxis": [{"value": "日期"}],
            "yAxis": [
                {"value": "首日ROI", "metricType": "ratio", "pivotAggregation": "avg"},
                {"value": "3日ROI", "metricType": "ratio", "pivotAggregation": "avg"},
            ],
            "series": [],
            "columns": [],
        }
    )
    view["chart"] = chart
    return view


def _matches_extra(view: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    stable_view = {
        key: value for key, value in view.items() if key not in VOLATILE_VIEW_KEYS
    }
    stable_expected = {
        key: value for key, value in expected.items() if key not in VOLATILE_VIEW_KEYS
    }
    return stable_view == stable_expected


def transform_roi_dashboard(
    components: Sequence[Mapping[str, Any]], canvas: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    result_components = copy.deepcopy([dict(item) for item in components])
    result_canvas = copy.deepcopy(dict(canvas))
    titles = _title_index(result_components, result_canvas)
    for title in ("安装投放趋势", "ROI地区总览", "ROI广告地区总览"):
        if title not in titles:
            raise ValueError(f"ROI 看板缺少必需图表：{title}")
    summary_title = "ROI总览" if "ROI总览" in titles else "ROI数据总览"
    if summary_title not in titles:
        raise ValueError("ROI 看板缺少必需图表：ROI总览")
    expected_titles = {
        "安装投放趋势",
        summary_title,
        "ROI地区总览",
        "ROI广告地区总览",
    }
    if ROI_EXTRA_VIEW_ID in result_canvas:
        expected_titles.add("图表")
    if set(titles) != expected_titles:
        raise ValueError("ROI 看板组件清单与五组件契约不一致")
    for title in (summary_title, "ROI地区总览", "ROI广告地区总览"):
        _require_fields(
            result_canvas[titles[title]],
            title,
            ROI_REQUIRED_FIELDS[title],
        )

    _set_type(result_canvas[titles["ROI地区总览"]], "area")
    region_chart = dict(result_canvas[titles["ROI地区总览"]]["chart"])
    region_chart["xAxis"] = [{"value": "日期"}]
    region_chart["yAxis"] = [
        {"value": "首日ROI", "metricType": "ratio", "pivotAggregation": "avg"},
        {"value": "3日ROI", "metricType": "ratio", "pivotAggregation": "avg"},
    ]
    region_chart["series"] = [{"value": "地区"}]
    result_canvas[titles["ROI地区总览"]]["chart"] = region_chart

    _set_type(result_canvas[titles["ROI广告地区总览"]], "column")
    ad_chart = dict(result_canvas[titles["ROI广告地区总览"]]["chart"])
    ad_chart["xAxis"] = [{"value": "日期"}]
    ad_chart["series"] = [{"value": "广告渠道"}]
    ad_chart["yAxis"] = [
        {
            "value": field,
            "metricType": "ratio" if "ROI" in field else "additive",
            "pivotAggregation": "avg" if "ROI" in field else "sum",
        }
        for field in (
            "安装数",
            "投放成本",
            "单次安装成本",
            "首日收入",
            "3日收入",
            "首日ROI",
            "3日ROI",
        )
    ]
    result_canvas[titles["ROI广告地区总览"]]["chart"] = ad_chart

    summary_id = titles[summary_title]
    summary_view = result_canvas[summary_id]
    summary_was_renamed = summary_view["chart"].get("title") != "ROI数据总览"
    summary_chart = dict(summary_view["chart"])
    summary_chart["title"] = "ROI数据总览"
    result_canvas[summary_id]["chart"] = summary_chart

    if ROI_EXTRA_VIEW_ID in result_canvas:
        extra_component = next(
            item
            for item in result_components
            if str(item.get("id")) == ROI_EXTRA_VIEW_ID
        )
        expected_component = _component(ROI_EXTRA_VIEW_ID, 36, 1, 36, 17)
        geometry_keys = {"x", "y", "sizeX", "sizeY"}
        actual_metadata = {
            key: value
            for key, value in extra_component.items()
            if key not in geometry_keys
        }
        expected_metadata = {
            key: value
            for key, value in expected_component.items()
            if key not in geometry_keys
        }
        if actual_metadata != expected_metadata:
            raise ValueError("ROI 新图组件元数据不一致")
        expected_extra = _extra_roi_view(summary_view)
        if not _matches_extra(result_canvas[ROI_EXTRA_VIEW_ID], expected_extra):
            raise ValueError("ROI 新图已存在但配置不一致")
        extra_added = False
    else:
        result_canvas[ROI_EXTRA_VIEW_ID] = _extra_roi_view(summary_view)
        result_components.append(_component(ROI_EXTRA_VIEW_ID, 36, 1, 36, 17))
        extra_added = True

    by_title = {
        str(_chart(result_canvas, str(item["id"])).get("title")): item
        for item in result_components
    }
    by_title["安装投放趋势"].update({"x": 2, "y": 1, "sizeX": 34, "sizeY": 17})
    by_title["图表"].update({"x": 36, "y": 1, "sizeX": 36, "sizeY": 17})
    by_title["ROI地区总览"].update({"x": 2, "y": 18, "sizeX": 70, "sizeY": 18})
    by_title["ROI广告地区总览"].update({"x": 2, "y": 37, "sizeX": 70, "sizeY": 16})
    by_title["ROI数据总览"].update({"x": 2, "y": 53, "sizeX": 70, "sizeY": 15})
    result_components.sort(
        key=lambda item: (int(item["y"]), int(item["x"]), str(item["id"]))
    )
    validate_layout(result_components)
    return (
        result_components,
        result_canvas,
        {"changed": extra_added or summary_was_renamed, "extra_added": extra_added},
    )


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_targets(cursor: Any, *, for_update: bool) -> list[dict[str, Any]]:
    lock_clause = " FOR UPDATE" if for_update else ""
    cursor.execute(
        f"""
        SELECT d.*
        FROM public.core_dashboard d
        JOIN public.core_dashboard_tree t
          ON t.dashboard_id = d.id AND t.tenant_id = d.tenant_id AND t.scope = 'default'
        WHERE d.id = ANY(%s) AND d.tenant_id = %s AND d.datasource = %s
          AND d.type = 'dashboard' AND COALESCE(d.delete_flag, 0) = 0
        ORDER BY d.id
        {lock_clause}
        """,
        (list(TARGETS), TENANT_ID, DATASOURCE_ID),
    )
    rows = [dict(row) for row in cursor.fetchall()]
    if {str(row["id"]) for row in rows} != set(TARGETS):
        raise RuntimeError("修仙默认推荐看板清单不完整")
    if any(row["name"] != TARGETS[str(row["id"])] for row in rows):
        raise RuntimeError("修仙看板名称校验失败")
    return rows


def _backup(
    row: Mapping[str, Any],
    new_component_raw: str,
    new_canvas_raw: str,
    flam_hashes: Mapping[str, Any],
) -> Path:
    old_component_raw = str(row["component_data"] or "[]")
    old_canvas_raw = str(row["canvas_view_info"] or "{}")
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = BACKUP_ROOT / f"{timestamp}-{row['id']}-{_hash(old_canvas_raw)[:8]}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": "xiuxian-dashboard-visual-sync/v2",
                "dashboard_id": str(row["id"]),
                "old_component_sha256": _hash(old_component_raw),
                "new_component_sha256": _hash(new_component_raw),
                "old_canvas_sha256": _hash(old_canvas_raw),
                "new_canvas_sha256": _hash(new_canvas_raw),
                "flam_hashes": flam_hashes,
                "row": row,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    return path.resolve()


def _transform_row(row: Mapping[str, Any]) -> tuple[str, str, dict[str, Any]]:
    components = json.loads(str(row["component_data"] or "[]"))
    canvas = json.loads(str(row["canvas_view_info"] or "{}"))
    if str(row["id"]) == CORE_DASHBOARD_ID:
        new_components, new_canvas, summary = transform_core_dashboard(
            components, canvas
        )
    else:
        new_components, new_canvas, summary = transform_roi_dashboard(
            components, canvas
        )
    return (
        json.dumps(new_components, ensure_ascii=False, separators=(",", ":")),
        json.dumps(new_canvas, ensure_ascii=False, separators=(",", ":")),
        summary,
    )


def _stable_top_level(view: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in view.items()
        if key not in VOLATILE_VIEW_KEYS and key != "chart"
    }


def _verify_preserved_views(
    dashboard_id: str,
    old_canvas: Mapping[str, Any],
    current_canvas: Mapping[str, Any],
) -> None:
    allowed_ids = set(old_canvas)
    if dashboard_id == ROI_DASHBOARD_ID:
        allowed_ids.add(ROI_EXTRA_VIEW_ID)
    if set(current_canvas) != allowed_ids:
        raise RuntimeError("当前视图清单与迁移前备份不一致")

    for view_id, old_value in old_canvas.items():
        current_value = current_canvas.get(view_id)
        if not isinstance(old_value, Mapping) or not isinstance(current_value, Mapping):
            raise RuntimeError(f"视图 {view_id} 结构无效")
        title = str((old_value.get("chart") or {}).get("title") or view_id)
        old_stable = _stable_top_level(old_value)
        current_stable = _stable_top_level(current_value)
        for key in sorted(set(old_stable) | set(current_stable)):
            if old_stable.get(key) != current_stable.get(key):
                raise RuntimeError(f"{title} 的 {key} 与迁移前备份不一致")

        old_chart = dict(old_value.get("chart") or {})
        current_chart = dict(current_value.get("chart") or {})
        allowed_chart_changes: set[str] = set()
        if dashboard_id == CORE_DASHBOARD_ID and title in {
            "ARPU与ARPPU",
            "新增用户趋势",
            "每日渠道新增用户",
        }:
            allowed_chart_changes.update({"type", "sourceType"})
        elif dashboard_id == ROI_DASHBOARD_ID:
            if title in {"ROI地区总览", "ROI广告地区总览"}:
                allowed_chart_changes.update(
                    {"type", "sourceType", "xAxis", "yAxis", "series"}
                )
            elif title == "ROI总览":
                allowed_chart_changes.add("title")
        for key in allowed_chart_changes:
            old_chart.pop(key, None)
            current_chart.pop(key, None)
        if old_chart != current_chart:
            raise RuntimeError(f"{title} 的其他 chart 配置与迁移前备份不一致")

    if dashboard_id == ROI_DASHBOARD_ID:
        summary_ids = [
            view_id
            for view_id, view in old_canvas.items()
            if (view.get("chart") or {}).get("title") in {"ROI总览", "ROI数据总览"}
        ]
        if len(summary_ids) != 1:
            raise RuntimeError("迁移前 ROI 汇总视图不唯一")
        summary_id = summary_ids[0]
        expected_extra = _extra_roi_view(old_canvas[summary_id])
        if not _matches_extra(current_canvas[ROI_EXTRA_VIEW_ID], expected_extra):
            raise RuntimeError("ROI 新图未完整继承迁移前执行配置")


def _load_flam_hashes(cursor: Any, *, for_share: bool) -> dict[str, dict[str, str]]:
    lock_clause = " FOR SHARE" if for_share else ""
    cursor.execute(
        f"""
        SELECT d.id, d.name, d.component_data, d.canvas_view_info
        FROM public.core_dashboard d
        JOIN public.core_dashboard_tree t
          ON t.dashboard_id = d.id AND t.tenant_id = d.tenant_id AND t.scope = 'default'
        WHERE d.id = ANY(%s) AND d.tenant_id = %s AND d.datasource = %s
          AND d.type = 'dashboard' AND COALESCE(d.delete_flag, 0) = 0
        ORDER BY d.id
        {lock_clause}
        """,
        (list(FLAM_TARGETS), FLAM_TENANT_ID, FLAM_DATASOURCE_ID),
    )
    rows = [dict(row) for row in cursor.fetchall()]
    if {str(row["id"]) for row in rows} != set(FLAM_TARGETS):
        raise RuntimeError("flam 基准看板清单不完整")
    if any(row["name"] != FLAM_TARGETS[str(row["id"])] for row in rows):
        raise RuntimeError("flam 基准看板名称校验失败")
    return {
        str(row["id"]): {
            "component_sha256": _hash(str(row["component_data"] or "[]")),
            "canvas_sha256": _hash(str(row["canvas_view_info"] or "{}")),
        }
        for row in rows
    }


def _verify_row_against_backup(
    current_row: Mapping[str, Any],
    payload: Mapping[str, Any],
    current_flam_hashes: Mapping[str, Any],
) -> None:
    dashboard_id = str(current_row["id"])
    if payload.get("schema") != "xiuxian-dashboard-visual-sync/v2":
        raise RuntimeError("验证需要 v2 迁移备份")
    if payload.get("dashboard_id") != dashboard_id:
        raise RuntimeError("迁移备份的看板 ID 不匹配")
    row_payload = payload.get("row")
    if not isinstance(row_payload, Mapping):
        raise RuntimeError("迁移备份缺少原始看板行")
    expected_identity = {
        "id": dashboard_id,
        "name": TARGETS[dashboard_id],
        "tenant_id": TENANT_ID,
        "datasource": DATASOURCE_ID,
    }
    for key, value in expected_identity.items():
        if row_payload.get(key) != value or current_row.get(key) != value:
            raise RuntimeError(f"迁移备份的 {key} 身份不匹配")
    if "component_data" not in row_payload or "canvas_view_info" not in row_payload:
        raise RuntimeError("迁移备份缺少原始 JSON")

    old_component_raw = str(row_payload["component_data"])
    old_canvas_raw = str(row_payload["canvas_view_info"])
    current_component_raw = str(current_row["component_data"] or "[]")
    current_canvas_raw = str(current_row["canvas_view_info"] or "{}")
    hash_checks = {
        "old_component_sha256": _hash(old_component_raw),
        "old_canvas_sha256": _hash(old_canvas_raw),
        "new_component_sha256": _hash(current_component_raw),
        "new_canvas_sha256": _hash(current_canvas_raw),
    }
    for key, actual in hash_checks.items():
        if payload.get(key) != actual:
            raise RuntimeError(f"迁移备份的 {key} 不匹配")
    if payload.get("flam_hashes") != current_flam_hashes:
        raise RuntimeError("flam 基准看板哈希与迁移时不一致")

    old_canvas = json.loads(old_canvas_raw)
    current_canvas = json.loads(current_canvas_raw)
    _verify_preserved_views(dashboard_id, old_canvas, current_canvas)


def _matching_v2_backup(row: Mapping[str, Any]) -> tuple[Path, dict[str, Any]]:
    if not BACKUP_ROOT.exists():
        raise RuntimeError("未找到迁移备份目录")
    dashboard_id = str(row["id"])
    current_component_hash = _hash(str(row["component_data"] or "[]"))
    current_canvas_hash = _hash(str(row["canvas_view_info"] or "{}"))
    for path in sorted(BACKUP_ROOT.glob(f"*-{dashboard_id}-*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            payload.get("schema") == "xiuxian-dashboard-visual-sync/v2"
            and payload.get("new_component_sha256") == current_component_hash
            and payload.get("new_canvas_sha256") == current_canvas_hash
        ):
            return path.resolve(), payload
    raise RuntimeError(f"未找到匹配当前状态的 v2 迁移备份：{dashboard_id}")


def _read_dashboard_for_restore(cursor: Any, dashboard_id: str) -> dict[str, Any]:
    cursor.execute(
        """
        SELECT d.id, d.name, d.tenant_id, d.datasource,
               d.component_data, d.canvas_view_info
        FROM public.core_dashboard d
        JOIN public.core_dashboard_tree t
          ON t.dashboard_id = d.id AND t.tenant_id = d.tenant_id AND t.scope = 'default'
        WHERE d.id = %s AND d.name = %s AND d.tenant_id = %s AND d.datasource = %s
          AND d.type = 'dashboard' AND COALESCE(d.delete_flag, 0) = 0
        FOR UPDATE
        """,
        (dashboard_id, TARGETS[dashboard_id], TENANT_ID, DATASOURCE_ID),
    )
    row = cursor.fetchone()
    if not row:
        raise RuntimeError(f"未找到修仙看板：{dashboard_id}")
    return dict(row)


def restore_backup(path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema") not in {
        "xiuxian-dashboard-visual-sync/v1",
        "xiuxian-dashboard-visual-sync/v2",
    }:
        raise ValueError("备份 schema 不匹配")
    row_payload = payload.get("row")
    if not isinstance(row_payload, Mapping):
        raise ValueError("备份缺少原始看板行")
    dashboard_id = str(payload.get("dashboard_id"))
    if dashboard_id not in TARGETS:
        raise ValueError("备份不是目标看板")
    expected_identity = {
        "id": dashboard_id,
        "name": TARGETS[dashboard_id],
        "tenant_id": TENANT_ID,
        "datasource": DATASOURCE_ID,
    }
    if any(row_payload.get(key) != value for key, value in expected_identity.items()):
        raise ValueError("备份看板身份不匹配")
    if "component_data" not in row_payload or "canvas_view_info" not in row_payload:
        raise ValueError("备份缺少原始 JSON")
    old_component_raw = str(row_payload["component_data"])
    old_canvas_raw = str(row_payload["canvas_view_info"])
    if _hash(old_component_raw) != payload.get("old_component_sha256"):
        raise ValueError("备份旧组件哈希不匹配")
    if _hash(old_canvas_raw) != payload.get("old_canvas_sha256"):
        raise ValueError("备份旧画布哈希不匹配")
    for key in ("new_component_sha256", "new_canvas_sha256"):
        value = payload.get(key)
        if not isinstance(value, str) or len(value) != 64:
            raise ValueError(f"备份缺少有效 {key}")
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))", (dashboard_id,)
                )
                current = _read_dashboard_for_restore(cursor, dashboard_id)
                if _hash(str(current["component_data"] or "")) != payload.get(
                    "new_component_sha256"
                ):
                    raise RuntimeError("当前组件哈希不是备份的新组件哈希")
                if _hash(str(current["canvas_view_info"] or "")) != payload.get(
                    "new_canvas_sha256"
                ):
                    raise RuntimeError("当前新画布哈希不匹配，拒绝恢复")
                cursor.execute(
                    """
                    UPDATE public.core_dashboard
                    SET component_data = %s, canvas_view_info = %s,
                        update_time = %s, update_by = %s,
                        version = COALESCE(version, 0) + 1
                    WHERE id = %s AND tenant_id = %s AND datasource = %s
                      AND component_data = %s AND canvas_view_info = %s
                      AND COALESCE(delete_flag, 0) = 0
                    """,
                    (
                        old_component_raw,
                        old_canvas_raw,
                        int(time.time() * 1000),
                        "codex-restore",
                        dashboard_id,
                        TENANT_ID,
                        DATASOURCE_ID,
                        current["component_data"],
                        current["canvas_view_info"],
                    ),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("恢复 CAS 更新失败")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    return {
        "restored": True,
        "dashboard_id": dashboard_id,
        "backup": str(Path(path).resolve()),
    }


def run(*, apply: bool) -> dict[str, Any]:
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as connection:
        try:
            with connection.cursor() as cursor:
                for dashboard_id in TARGETS:
                    cursor.execute(
                        "SELECT pg_advisory_xact_lock(hashtext(%s))", (dashboard_id,)
                    )
                flam_hashes = (
                    _load_flam_hashes(cursor, for_share=True) if apply else None
                )
                rows = _load_targets(cursor, for_update=True)
                results = []
                for row in rows:
                    old_component_raw = str(row["component_data"] or "[]")
                    old_canvas_raw = str(row["canvas_view_info"] or "{}")
                    new_component_raw, new_canvas_raw, summary = _transform_row(row)
                    changed = (
                        new_component_raw != old_component_raw
                        or new_canvas_raw != old_canvas_raw
                    )
                    backup = None
                    if apply and changed:
                        backup = _backup(
                            row,
                            new_component_raw,
                            new_canvas_raw,
                            flam_hashes or {},
                        )
                        cursor.execute(
                            """
                            UPDATE public.core_dashboard
                            SET component_data = %s, canvas_view_info = %s,
                                update_time = %s, update_by = %s,
                                version = COALESCE(version, 0) + 1
                            WHERE id = %s AND tenant_id = %s AND datasource = %s
                              AND component_data = %s AND canvas_view_info = %s
                              AND COALESCE(delete_flag, 0) = 0
                            """,
                            (
                                new_component_raw,
                                new_canvas_raw,
                                int(time.time() * 1000),
                                "codex",
                                row["id"],
                                TENANT_ID,
                                DATASOURCE_ID,
                                old_component_raw,
                                old_canvas_raw,
                            ),
                        )
                        if cursor.rowcount != 1:
                            raise RuntimeError(f"看板 CAS 更新失败：{row['id']}")
                        cursor.execute(
                            "SELECT component_data, canvas_view_info FROM public.core_dashboard WHERE id = %s FOR UPDATE",
                            (row["id"],),
                        )
                        current = cursor.fetchone()
                        if (
                            current["component_data"] != new_component_raw
                            or current["canvas_view_info"] != new_canvas_raw
                        ):
                            raise RuntimeError(f"看板事务内读回不一致：{row['id']}")
                    results.append(
                        {
                            "id": str(row["id"]),
                            "name": row["name"],
                            "changed": changed,
                            "summary": summary,
                            "backup": str(backup) if backup else None,
                        }
                    )
                if apply and _load_flam_hashes(cursor, for_share=True) != flam_hashes:
                    raise RuntimeError("flam 基准看板在迁移事务中发生变化")
            if apply:
                connection.commit()
            else:
                connection.rollback()
        except BaseException:
            connection.rollback()
            raise
    return {"applied": apply, "verified": False, "dashboards": results}


def verify() -> dict[str, Any]:
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as connection:
        try:
            with connection.cursor() as cursor:
                rows = _load_targets(cursor, for_update=False)
                flam_hashes = _load_flam_hashes(cursor, for_share=False)
                results = []
                for row in rows:
                    new_component_raw, new_canvas_raw, summary = _transform_row(row)
                    if new_component_raw != str(
                        row["component_data"] or "[]"
                    ) or new_canvas_raw != str(row["canvas_view_info"] or "{}"):
                        raise RuntimeError(f"修仙看板尚未达到目标视觉配置：{row['id']}")
                    backup_path, payload = _matching_v2_backup(row)
                    _verify_row_against_backup(row, payload, flam_hashes)
                    results.append(
                        {
                            "id": str(row["id"]),
                            "name": row["name"],
                            "changed": False,
                            "summary": summary,
                            "backup": str(backup_path),
                        }
                    )
            connection.rollback()
        except BaseException:
            connection.rollback()
            raise
    return {
        "applied": False,
        "verified": True,
        "flam_hashes": flam_hashes,
        "dashboards": results,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--restore", type=Path)
    args = parser.parse_args(argv)
    if args.restore:
        result = restore_backup(args.restore)
    else:
        result = verify() if args.verify else run(apply=args.apply)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
