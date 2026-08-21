# -*- coding: utf-8 -*-
"""修复修仙空间遗留看板的 SQL、数据源和日期筛选配置。

脚本默认只读扫描；``--apply`` 使用行级锁、画布 CAS 和日期迁移审计表写入。
目标图表、日期口径和 SQL 改写均为显式白名单，不根据看板标题猜测配置。
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import time
import uuid
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from core_system_db import core_system_db_config


ROOT = Path(__file__).resolve().parents[1]
TENANT_ID = 7482727237662281728
BATCH_ID = "dashboard-date-filter-v2-xiuxian-repair-20260729"
BACKUP_DIR = ROOT / ".codex-runtime" / "dashboard-date-filter-repair-backups"
START_TOKEN = "{{dashboard_start_yyyymmdd}}"
END_TOKEN = "{{dashboard_end_yyyymmdd}}"


def preset(name: str) -> dict[str, Any]:
    return {"version": 1, "mode": "preset", "preset": name}


def dynamic_range(start_offset: int, end_offset: int) -> dict[str, Any]:
    return {
        "version": 1,
        "mode": "range",
        "start": {"mode": "dynamic", "unit": "day", "offset": start_offset},
        "end": {"mode": "dynamic", "unit": "day", "offset": end_offset},
    }


TARGETS: dict[str, dict[str, dict[str, Any]]] = {
    "afe201c9762c448aa0495f3508c01793": {
        "7f71477b49404ad289485f4f22d34c2f": {"expression": preset("past_30_days")},
    },
    "ef9af92c3d6744d780f82cba4c534482": {
        "2191880711655563264": {"expression": preset("past_30_days"), "datasource": 6},
    },
    "5147cf8d9a594847ac2dcce4b0752165": {
        "2196921958803873792": {"expression": preset("past_30_days")},
    },
    "5df5b385700048a49e99a6cb33a52dd8": {
        "2192208417505058816": {"expression": preset("past_30_days")},
    },
    "7d666e96e17d4a648a35627ac91a7ff3": {
        "2192244728437841920": {"expression": preset("past_30_days")},
    },
    "c68e08ee9b4a4be59c3c8fbbe918affd": {
        "fd9a8fe1127e4f21bf1809a6560ec6e2": {"expression": preset("past_30_days")},
    },
    "6234ec38697c4924b65c7de11d8bd829": {
        "3a449b3049314a668661ae65f70e38f1": {"expression": preset("past_30_days")},
    },
    "d054a853816a4e328cd0e684bf77046c": {
        "2192905090162139136": {"expression": dynamic_range(-31, -2)},
    },
    "a34aef6cb7214f7fa23e5846a0a66236": {
        "e797a8af6785452e9fdcee7d80786b6e": {"expression": dynamic_range(-36, -8)},
    },
    "b09e4d57f57b41859a0c2d4609f80f26": {
        "b0f27793e48349c1a6a7fbf40ff03ffd": {"expression": dynamic_range(-31, -2)},
        "a6eb26710f7b4dc6ab69ded704c32fee": {"expression": preset("past_30_days")},
    },
}


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _date_config(expression: dict[str, Any]) -> dict[str, Any]:
    return {
        "enabled": True,
        "parameterType": "yyyymmdd_number",
        "expression": copy.deepcopy(expression),
    }


def repair_level_distribution_sql(sql: str) -> str:
    marker = ")\nWITH user_level AS"
    if sql.count(marker) == 1:
        return sql.replace(marker, "),\nuser_level AS", 1)
    if re.search(r"\),\s*user_level\s+AS\s*\(", sql, re.IGNORECASE) and "WITH params AS" in sql:
        return sql
    raise ValueError("当前等级分布 SQL 不匹配白名单结构")


def repair_new_user_d1_retention_sql(sql: str) -> str:
    if "JOIN active AS a" not in sql or "WITH cohort AS" not in sql:
        raise ValueError("新增用户次日留存 SQL 不匹配白名单结构")
    return f"""WITH cohort AS (
  SELECT
    e.dt AS cohort_dt,
    CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST(e.dt AS CHAR), '%Y%m%d'), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED) AS d1_dt,
    e.uid
  FROM `event` AS e
  WHERE e.prod = 110000047
    AND e.event = 'UserRegister'
    AND e.dt BETWEEN CAST({START_TOKEN} AS SIGNED)
      AND CAST(DATE_FORMAT(DATE_SUB(STR_TO_DATE(CAST({END_TOKEN} AS CHAR), '%Y%m%d'), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
  GROUP BY e.dt, e.uid
), active AS (
  SELECT e.dt, e.uid
  FROM `event` AS e
  WHERE e.prod = 110000047
    AND e.event = 'UserActive'
    AND e.dt BETWEEN CAST(DATE_FORMAT(DATE_ADD(STR_TO_DATE(CAST({START_TOKEN} AS CHAR), '%Y%m%d'), INTERVAL 1 DAY), '%Y%m%d') AS SIGNED)
      AND CAST({END_TOKEN} AS SIGNED)
  GROUP BY e.dt, e.uid
), retained AS (
  SELECT c.cohort_dt, COUNT(DISTINCT c.uid) AS d1_retained_users
  FROM cohort AS c
  JOIN active AS a ON a.uid = c.uid AND a.dt = c.d1_dt
  GROUP BY c.cohort_dt
)
SELECT
  STR_TO_DATE(CAST(c.cohort_dt AS CHAR), '%Y%m%d') AS `日期`,
  COUNT(DISTINCT c.uid) AS `新增用户数`,
  COALESCE(r.d1_retained_users, 0) AS `次日留存用户数`,
  ROUND(COALESCE(r.d1_retained_users, 0) / NULLIF(COUNT(DISTINCT c.uid), 0) * 100, 2) AS `次日留存率`
FROM cohort AS c
LEFT JOIN retained AS r ON r.cohort_dt = c.cohort_dt
GROUP BY c.cohort_dt, r.d1_retained_users
ORDER BY c.cohort_dt"""


def repair_sql(view_id: str, sql: str) -> str:
    if view_id == "7f71477b49404ad289485f4f22d34c2f":
        return repair_level_distribution_sql(sql)
    if view_id == "b0f27793e48349c1a6a7fbf40ff03ffd":
        return repair_new_user_d1_retention_sql(sql)
    return sql


def configure_view(view: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(view)
    result["configVersion"] = 2
    result["dateFilter"] = _date_config(config["expression"])
    result.pop("date_filter", None)
    pivot = result.get("pivot")
    if isinstance(pivot, dict):
        pivot.pop("date_parameter_type", None)
        pivot.pop("date_expression", None)
    if "datasource" in config:
        result["datasource"] = config["datasource"]
        source_config = result.get("sourceConfig")
        sql_config = source_config.get("sql") if isinstance(source_config, dict) else None
        if isinstance(sql_config, dict):
            sql_config.pop("datasource", None)
    return result


def _load_canvas(raw: str) -> dict[str, Any]:
    canvas = json.loads(raw or "")
    if not isinstance(canvas, dict):
        raise ValueError("canvas_view_info 必须是 JSON 对象")
    return canvas


def _verify_canvas(canvas: dict[str, Any], dashboard_id: str) -> None:
    for chart_id, config in TARGETS[dashboard_id].items():
        view = canvas.get(chart_id)
        if not isinstance(view, dict):
            raise ValueError(f"缺少目标图表：{chart_id}")
        sql = str(view.get("sql") or "")
        if sql.count(START_TOKEN) < 1 or sql.count(END_TOKEN) < 1 or sql.count(START_TOKEN) != sql.count(END_TOKEN):
            raise ValueError(f"日期 token 数量错误：{chart_id}")
        date_filter = view.get("dateFilter")
        if view.get("configVersion") != 2 or date_filter != _date_config(config["expression"]):
            raise ValueError(f"V2 配置校验失败：{chart_id}")
        if chart_id == "7f71477b49404ad289485f4f22d34c2f" and re.search(r"\)\s+WITH\s+user_level", sql):
            raise ValueError("当前等级分布仍含重复 WITH")
        if chart_id == "b0f27793e48349c1a6a7fbf40ff03ffd":
            if len(re.findall(r"\bactive\s+AS\s*\(", sql, re.IGNORECASE)) != 1 or "JOIN active AS a" not in sql:
                raise ValueError("次日留存 active CTE 校验失败")


def _backup(rows: list[dict[str, Any]]) -> str:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f"xiuxian_dashboard_date_filter_repair_{time.strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return str(path.resolve())


def migrate(*, apply: bool) -> dict[str, Any]:
    dashboard_ids = list(TARGETS)
    with psycopg.connect(**core_system_db_config(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, tenant_id, name, datasource, canvas_view_info
                FROM public.core_dashboard
                WHERE tenant_id = %s AND id = ANY(%s) AND COALESCE(delete_flag, 0) = 0
                FOR UPDATE
                """,
                (TENANT_ID, dashboard_ids),
            )
            rows = cur.fetchall()
            by_id = {str(row["id"]): row for row in rows}
            if set(by_id) != set(dashboard_ids):
                raise RuntimeError("目标看板集合不完整，拒绝写入")

            original_rows: list[dict[str, Any]] = []
            changed: dict[str, list[str]] = {}
            new_canvases: dict[str, str] = {}
            for dashboard_id in dashboard_ids:
                row = by_id[dashboard_id]
                original = str(row["canvas_view_info"] or "")
                canvas = _load_canvas(original)
                original_rows.append(dict(row))
                touched: list[str] = []
                for chart_id, config in TARGETS[dashboard_id].items():
                    view = canvas.get(chart_id)
                    if not isinstance(view, dict):
                        raise RuntimeError(f"目标图表不存在：{dashboard_id}/{chart_id}")
                    before = json.dumps(view, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                    view["sql"] = repair_sql(chart_id, str(view.get("sql") or ""))
                    canvas[chart_id] = configure_view(view, config)
                    after = json.dumps(canvas[chart_id], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                    if before != after:
                        touched.append(chart_id)
                new_canvas = json.dumps(canvas, ensure_ascii=False, separators=(",", ":"))
                _verify_canvas(canvas, dashboard_id)
                new_canvases[dashboard_id] = new_canvas
                changed[dashboard_id] = touched

            result: dict[str, Any] = {
                "apply": apply,
                "batch_id": BATCH_ID,
                "dashboard_ids": dashboard_ids,
                "changed": changed,
            }
            if not apply:
                conn.rollback()
                return result

            backup = _backup(original_rows)
            for dashboard_id in dashboard_ids:
                row = by_id[dashboard_id]
                new_datasource = 6 if dashboard_id == "ef9af92c3d6744d780f82cba4c534482" else row["datasource"]
                cur.execute(
                    """
                    UPDATE public.core_dashboard
                    SET canvas_view_info = %s, datasource = %s, update_time = %s
                    WHERE id = %s AND tenant_id = %s AND canvas_view_info = %s
                      AND COALESCE(delete_flag, 0) = 0
                    """,
                    (new_canvases[dashboard_id], new_datasource, int(time.time() * 1000), dashboard_id, TENANT_ID, row["canvas_view_info"]),
                )
                if cur.rowcount != 1:
                    raise RuntimeError(f"CAS 更新失败：{dashboard_id}")
                chart_ids = sorted(TARGETS[dashboard_id])
                classifications = {chart_id: "approved_repair" for chart_id in chart_ids}
                verification = {
                    chart_id: {"parameter_type": "yyyymmdd_number", "expression": TARGETS[dashboard_id][chart_id]["expression"]}
                    for chart_id in chart_ids
                }
                cur.execute(
                    """
                    INSERT INTO public.core_dashboard_date_filter_migration_audit
                    (id, batch_id, tenant_id, dashboard_id, chart_ids, classification_json,
                     original_canvas, original_canvas_sha256, migrated_canvas, migrated_canvas_sha256,
                     verification_json, status, created_time)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'applied',%s)
                    ON CONFLICT (batch_id, dashboard_id) DO NOTHING
                    """,
                    (
                        uuid.uuid4().hex,
                        BATCH_ID,
                        TENANT_ID,
                        dashboard_id,
                        json.dumps(chart_ids, ensure_ascii=False, separators=(",", ":")),
                        json.dumps(classifications, ensure_ascii=False, separators=(",", ":")),
                        row["canvas_view_info"],
                        _sha256(str(row["canvas_view_info"])),
                        new_canvases[dashboard_id],
                        _sha256(new_canvases[dashboard_id]),
                        json.dumps(verification, ensure_ascii=False, separators=(",", ":")),
                        int(time.time() * 1000),
                    ),
                )
            conn.commit()
            result["backup"] = backup
            return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="备份并写入修复")
    args = parser.parse_args()
    print(json.dumps(migrate(apply=args.apply), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
