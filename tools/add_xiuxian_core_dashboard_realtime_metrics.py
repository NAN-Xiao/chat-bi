"""在修仙核心看板顶部添加四张当天实时指标卡。"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from core_system_db import core_system_db_config


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "backend"
BACKUP_ROOT = ROOT / ".codex-runtime" / "xiuxian-core-dashboard-metric-backups"

TENANT_ID = 7482727237662281728
DATASOURCE_ID = 6
DASHBOARD_ID = "afe201c9762c448aa0495f3508c01793"
DASHBOARD_NAME = "核心看板"
PRODUCT_ID = 110000047
HEADER_HEIGHT = 8


@dataclass(frozen=True)
class MetricSpec:
    """单张实时指标卡的固定定义。"""

    view_id: str
    title: str
    field: str
    sql: str
    x: int


METRIC_SPECS = (
    MetricSpec(
        view_id="c3d6ca851f8150ba94d73a83ca18b438",
        title="活跃用户",
        field="活跃用户",
        x=1,
        sql="""SELECT
    DATE_FORMAT(CURDATE(), '%Y-%m-%d') AS `日期`,
    COUNT(DISTINCT uid) AS `活跃用户`
FROM event_realtime
WHERE dt = CAST(DATE_FORMAT(CURDATE(), '%Y%m%d') AS SIGNED)
  AND prod = 110000047
  AND event = 'UserActive'""",
    ),
    MetricSpec(
        view_id="2ca07023c33d514eaa07977425ee7f53",
        title="新增用户",
        field="新增用户",
        x=19,
        sql="""SELECT
    DATE_FORMAT(CURDATE(), '%Y-%m-%d') AS `日期`,
    COUNT(DISTINCT uid) AS `新增用户`
FROM event_realtime
WHERE dt = CAST(DATE_FORMAT(CURDATE(), '%Y%m%d') AS SIGNED)
  AND prod = 110000047
  AND event = 'UserRegister'""",
    ),
    MetricSpec(
        view_id="f212cbcd03a15590a39519e874a1a6f4",
        title="充值人数",
        field="充值人数",
        x=37,
        sql="""SELECT
    DATE_FORMAT(CURDATE(), '%Y-%m-%d') AS `日期`,
    COUNT(DISTINCT uid) AS `充值人数`
FROM event_realtime
WHERE dt = CAST(DATE_FORMAT(CURDATE(), '%Y%m%d') AS SIGNED)
  AND prod = 110000047
  AND event = 'ServerPayLog'""",
    ),
    MetricSpec(
        view_id="5bb72c937f565b7295b3bf4d1b746496",
        title="充值总额",
        field="充值总额（万）",
        x=55,
        sql="""SELECT
    DATE_FORMAT(CURDATE(), '%Y-%m-%d') AS `日期`,
    ROUND(
        COALESCE(
            SUM(
                CAST(
                    NULLIF(
                        NULLIF(
                            JSON_UNQUOTE(JSON_EXTRACT(personal, '$.money')),
                            ''
                        ),
                        'null'
                    ) AS DECIMAL(18, 4)
                )
            ),
            0
        ) / 10000,
        2
    ) AS `充值总额（万）`
FROM event_realtime
WHERE dt = CAST(DATE_FORMAT(CURDATE(), '%Y%m%d') AS SIGNED)
  AND prod = 110000047
  AND event = 'ServerPayLog'""",
    ),
)
METRIC_VIEW_IDS = frozenset(spec.view_id for spec in METRIC_SPECS)


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"不支持的 JSON 类型：{type(value).__name__}")


def _normalize_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(
        json.dumps(dict(row), ensure_ascii=False, default=_json_default)
    )


def _metric_component(spec: MetricSpec) -> dict[str, Any]:
    return {
        "id": spec.view_id,
        "component": "SQView",
        "name": "new-view",
        "propValue": "&nbsp;",
        "icon": "icon_graphical",
        "innerType": "bar",
        "locked": False,
        "editing": False,
        "x": spec.x,
        "y": 1,
        "sizeX": 18,
        "sizeY": HEADER_HEIGHT,
        "style": {},
        "_dragId": spec.view_id,
        "show": True,
    }


def _metric_view(
    spec: MetricSpec,
    row: Mapping[str, Any],
    snapshot_refreshed_at: int,
) -> dict[str, Any]:
    fields = ["日期", spec.field]
    normalized_row = _normalize_row(row)
    return {
        "id": spec.view_id,
        "sql": spec.sql,
        "datasource": DATASOURCE_ID,
        "data": {"fields": fields, "data": [normalized_row]},
        "fields": fields,
        "chart": {
            "id": spec.view_id,
            "type": "metric",
            "sourceType": "metric",
            "title": spec.title,
            "columns": [{"value": field} for field in fields],
            "xAxis": [{"value": "日期", "type": "other-info"}],
            "yAxis": [{"value": spec.field, "type": "y"}],
            "series": [],
        },
        "refreshState": "",
        "pivot": {"enabled": False},
        "external_mcp_server_id": None,
        "mcp": None,
        "externalSnapshot": False,
        "dataSourceType": "sql",
        "snapshotRefreshedAt": snapshot_refreshed_at,
        "status": "success",
        "dataState": "ready",
        "message": "",
    }


def rewrite_dashboard(
    components: Sequence[Mapping[str, Any]],
    canvas: Mapping[str, Mapping[str, Any]],
    metric_rows: Mapping[str, Mapping[str, Any]],
    *,
    snapshot_refreshed_at: int = 0,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """幂等插入顶部指标卡，并保持原组件相对布局。"""

    component_ids = {str(item.get("id")) for item in components}
    canvas_ids = {str(view_id) for view_id in canvas}
    component_metric_ids = component_ids.intersection(METRIC_VIEW_IDS)
    canvas_metric_ids = canvas_ids.intersection(METRIC_VIEW_IDS)
    if component_metric_ids not in (set(), set(METRIC_VIEW_IDS)):
        raise ValueError("核心看板只存在部分实时指标组件，拒绝继续改写")
    if canvas_metric_ids not in (set(), set(METRIC_VIEW_IDS)):
        raise ValueError("核心看板只存在部分实时指标视图，拒绝继续改写")
    if bool(component_metric_ids) != bool(canvas_metric_ids):
        raise ValueError("实时指标组件与视图状态不一致，拒绝继续改写")

    missing_rows = [spec.view_id for spec in METRIC_SPECS if spec.view_id not in metric_rows]
    if missing_rows:
        raise ValueError(f"缺少实时指标查询结果：{missing_rows}")

    already_installed = bool(component_metric_ids)
    normal_components: list[dict[str, Any]] = []
    for item in components:
        item_id = str(item.get("id"))
        if item_id in METRIC_VIEW_IDS:
            continue
        copied = dict(item)
        if not already_installed:
            y = copied.get("y")
            if not isinstance(y, int):
                raise ValueError(f"组件 {item_id} 缺少整数 y 坐标")
            copied["y"] = y + HEADER_HEIGHT
        normal_components.append(copied)

    new_components = [_metric_component(spec) for spec in METRIC_SPECS]
    new_components.extend(normal_components)

    new_canvas = {str(view_id): dict(view) for view_id, view in canvas.items()}
    for spec in METRIC_SPECS:
        new_canvas[spec.view_id] = _metric_view(
            spec,
            metric_rows[spec.view_id],
            snapshot_refreshed_at,
        )
    return new_components, new_canvas


def validate_dashboard(
    components: Sequence[Mapping[str, Any]],
    canvas: Mapping[str, Mapping[str, Any]],
    metric_rows: Mapping[str, Mapping[str, Any]],
) -> None:
    component_by_id = {str(item.get("id")): item for item in components}
    if METRIC_VIEW_IDS.difference(component_by_id):
        raise ValueError("覆盖复验失败：缺少实时指标组件")
    if METRIC_VIEW_IDS.difference(canvas):
        raise ValueError("覆盖复验失败：缺少实时指标视图")

    for spec in METRIC_SPECS:
        component = component_by_id[spec.view_id]
        expected_layout = (spec.x, 1, 18, HEADER_HEIGHT)
        actual_layout = (
            component.get("x"),
            component.get("y"),
            component.get("sizeX"),
            component.get("sizeY"),
        )
        if actual_layout != expected_layout:
            raise ValueError(f"覆盖复验失败：{spec.title} 布局为 {actual_layout}")
        view = canvas[spec.view_id]
        if view.get("sql") != spec.sql:
            raise ValueError(f"覆盖复验失败：{spec.title} SQL 不一致")
        if view.get("datasource") != DATASOURCE_ID:
            raise ValueError(f"覆盖复验失败：{spec.title} 数据源不一致")
        if view.get("chart", {}).get("type") != "metric":
            raise ValueError(f"覆盖复验失败：{spec.title} 图表类型不一致")
        actual_rows = view.get("data", {}).get("data")
        if actual_rows != [_normalize_row(metric_rows[spec.view_id])]:
            raise ValueError(f"覆盖复验失败：{spec.title} 数据快照不一致")


def _setup_backend_imports() -> None:
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)


def _system_db_connection() -> Any:
    import psycopg

    return psycopg.connect(**core_system_db_config())


def _load_datasource_conf(cursor: Any) -> Any:
    from apps.datasource.models.datasource import DatasourceConf
    from apps.datasource.utils.utils import aes_decrypt

    cursor.execute(
        """
        SELECT configuration
        FROM core_datasource
        WHERE id = %s AND tenant_id = %s
        """,
        (DATASOURCE_ID, TENANT_ID),
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError("未找到修仙数据源配置")
    return DatasourceConf(**json.loads(aes_decrypt(row[0])))


def query_metric_rows() -> dict[str, dict[str, Any]]:
    """执行四条只读 SQL，返回看板快照数据。"""

    import pymysql

    _setup_backend_imports()
    with _system_db_connection() as system_connection:
        with system_connection.cursor() as cursor:
            datasource_conf = _load_datasource_conf(cursor)

    business_connection = pymysql.connect(
        host=datasource_conf.host,
        port=int(datasource_conf.port),
        user=datasource_conf.username,
        password=datasource_conf.password,
        database=datasource_conf.database,
        charset="utf8mb4",
        connect_timeout=10,
        read_timeout=30,
        write_timeout=30,
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        rows: dict[str, dict[str, Any]] = {}
        with business_connection.cursor() as cursor:
            for spec in METRIC_SPECS:
                cursor.execute(spec.sql)
                row = cursor.fetchone()
                if row is None:
                    raise ValueError(f"{spec.title} SQL 未返回结果")
                normalized = _normalize_row(row)
                if normalized.get("日期") is None or spec.field not in normalized:
                    raise ValueError(f"{spec.title} SQL 返回字段不完整：{list(normalized)}")
                rows[spec.view_id] = normalized
        return rows
    finally:
        business_connection.close()


def _backup_dashboard(row: Mapping[str, Any]) -> Path:
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    payload = dict(row)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        default=_json_default,
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    backup_dir = BACKUP_ROOT / f"{timestamp}-{digest[:8]}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    (backup_dir / "dashboard.json").write_bytes(encoded)
    (backup_dir / "manifest.json").write_text(
        json.dumps(
            {
                "dashboard_id": DASHBOARD_ID,
                "tenant_id": TENANT_ID,
                "datasource_id": DATASOURCE_ID,
                "dashboard_sha256": digest,
                "created_at": timestamp,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return backup_dir


def _load_dashboard(cursor: Any, *, for_update: bool = False) -> dict[str, Any]:
    suffix = " FOR UPDATE" if for_update else ""
    cursor.execute(
        f"""
        SELECT id, name, tenant_id, datasource, component_data,
               canvas_view_info, update_time, update_by, version
        FROM core_dashboard
        WHERE id = %s AND tenant_id = %s AND datasource = %s{suffix}
        """,
        (DASHBOARD_ID, TENANT_ID, DATASOURCE_ID),
    )
    row = cursor.fetchone()
    if not row:
        raise ValueError("未找到修仙核心看板")
    names = [column.name for column in cursor.description]
    dashboard = dict(zip(names, row))
    if dashboard["name"] != DASHBOARD_NAME:
        raise ValueError(f"目标看板名称异常：{dashboard['name']}")
    return dashboard


def apply_dashboard(metric_rows: Mapping[str, Mapping[str, Any]]) -> Path:
    """备份并通过 CAS 更新核心看板。"""

    _setup_backend_imports()
    connection = _system_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (DASHBOARD_ID,))
            dashboard = _load_dashboard(cursor, for_update=True)
            original_components = dashboard["component_data"]
            original_canvas = dashboard["canvas_view_info"]
            components = json.loads(original_components or "[]")
            canvas = json.loads(original_canvas or "{}")
            if not isinstance(components, list) or not isinstance(canvas, dict):
                raise ValueError("核心看板布局 JSON 结构无效")

            backup_dir = _backup_dashboard(dashboard)
            snapshot_ms = int(time.time() * 1000)
            new_components, new_canvas = rewrite_dashboard(
                components,
                canvas,
                metric_rows,
                snapshot_refreshed_at=snapshot_ms,
            )
            validate_dashboard(new_components, new_canvas, metric_rows)
            encoded_components = json.dumps(
                new_components, ensure_ascii=False, separators=(",", ":")
            )
            encoded_canvas = json.dumps(
                new_canvas, ensure_ascii=False, separators=(",", ":")
            )
            update_time = max(int(time.time()), int(dashboard["update_time"] or 0) + 1)
            cursor.execute(
                """
                UPDATE core_dashboard
                SET component_data = %s,
                    canvas_view_info = %s,
                    update_time = %s
                WHERE id = %s
                  AND tenant_id = %s
                  AND datasource = %s
                  AND component_data = %s
                  AND canvas_view_info = %s
                  AND update_time = %s
                """,
                (
                    encoded_components,
                    encoded_canvas,
                    update_time,
                    DASHBOARD_ID,
                    TENANT_ID,
                    DATASOURCE_ID,
                    original_components,
                    original_canvas,
                    dashboard["update_time"],
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("核心看板 CAS 更新失败，可能存在并发编辑")
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()

    verify_dashboard(metric_rows)
    return backup_dir


def verify_dashboard(metric_rows: Mapping[str, Mapping[str, Any]]) -> None:
    """重新读取系统库，校验写入结果。"""

    _setup_backend_imports()
    with _system_db_connection() as connection:
        with connection.cursor() as cursor:
            dashboard = _load_dashboard(cursor)
    components = json.loads(dashboard["component_data"] or "[]")
    canvas = json.loads(dashboard["canvas_view_info"] or "{}")
    validate_dashboard(components, canvas, metric_rows)


def _summary(metric_rows: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    return {
        spec.title: metric_rows[spec.view_id]
        for spec in METRIC_SPECS
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="实际写入核心看板")
    args = parser.parse_args(argv)

    metric_rows = query_metric_rows()
    print(json.dumps(_summary(metric_rows), ensure_ascii=False, indent=2))
    if not args.apply:
        print("只读检查完成；增加 --apply 才会修改核心看板。")
        return 0

    backup_dir = apply_dashboard(metric_rows)
    print(f"核心看板已更新，备份目录：{backup_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
