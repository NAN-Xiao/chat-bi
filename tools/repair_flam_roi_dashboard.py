# -*- coding: utf-8 -*-
"""修复 flam ROI_flame 图表的日期格式和中文列名。"""

from __future__ import annotations

import argparse
import copy
import json
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from core_system_db import core_system_db_config


ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = ROOT / ".codex-runtime" / "pg-backups"

SYSTEM_DB = core_system_db_config()
TENANT_ID = 7477202383789887488
DASHBOARD_ID = 7483782536305315840
CHART_ID = 7484789862231445504
CHART_TITLE = "ROI_flame"

CHINESE_FIELDS = (
    "日期",
    "广告活动名称",
    "广告活动ID",
    "广告渠道",
    "地区",
    "安装数",
    "投放成本",
    "单次安装成本",
    "首日收入",
    "3日收入",
    "首日ROI",
    "3日ROI",
)

LEGACY_SELECT_BLOCK = """SELECT
    campaign_name,
    all_campaign_id,
    all_dt,
    CASE
        WHEN campaign_name = 'Organic' THEN '自然流量'
        WHEN campaign_name LIKE '%_AEO_%' THEN 'AEO'
        WHEN campaign_name LIKE '%_VO_%' THEN 'VO'
        WHEN campaign_name LIKE '%_2.5_%' THEN 'Google2.5'
        WHEN campaign_name LIKE '%_1.0_%' THEN 'Google1.0'
        WHEN campaign_name LIKE '%_MAI_%' THEN 'MAI'
        ELSE 'other'
    END AS ad_channel,
    CASE
        WHEN campaign_name LIKE 'Flame_%'
             AND campaign_name LIKE '%US_%'
            THEN 'US'
        WHEN campaign_name LIKE 'Flame_%'
             AND campaign_name LIKE '%T2_%'
            THEN 'T2'
        WHEN campaign_name LIKE 'Flame_%'
             AND campaign_name LIKE '%PH_%'
            THEN 'T3'
        WHEN campaign_name LIKE 'Flame_%'
             AND campaign_name LIKE '%PH/ID_%'
            THEN 'T3'
        WHEN campaign_name LIKE 'Flame_%'
             AND campaign_name LIKE '%BR%'
            THEN 'T3'
        WHEN campaign_name LIKE 'Flame_%'
             AND campaign_name LIKE '%T3%'
            THEN 'T3'
        ELSE 'other'
    END AS region,
    SUM(installs) AS installs,
    SUM(costmoney) AS cost,
    SUM(costmoney) / SUM(installs) AS cpi,
    SUM(paysum_1) AS pay1,
    SUM(paysum_3) AS pay3,
    SUM(paysum_1) / SUM(costmoney) * 100 AS roi1,
    SUM(paysum_3) / SUM(costmoney) * 100 AS roi3"""

REPAIRED_SELECT_BLOCK = """SELECT
    campaign_name AS `广告活动名称`,
    all_campaign_id AS `广告活动ID`,
    DATE_FORMAT(
        CAST(all_dt AS DATE),
        '%Y-%m-%d'
    ) AS `日期`,
    CASE
        WHEN campaign_name = 'Organic' THEN '自然流量'
        WHEN campaign_name LIKE '%_AEO_%' THEN 'AEO'
        WHEN campaign_name LIKE '%_VO_%' THEN 'VO'
        WHEN campaign_name LIKE '%_2.5_%' THEN 'Google2.5'
        WHEN campaign_name LIKE '%_1.0_%' THEN 'Google1.0'
        WHEN campaign_name LIKE '%_MAI_%' THEN 'MAI'
        ELSE 'other'
    END AS `广告渠道`,
    CASE
        WHEN campaign_name LIKE 'Flame_%'
             AND campaign_name LIKE '%US_%'
            THEN 'US'
        WHEN campaign_name LIKE 'Flame_%'
             AND campaign_name LIKE '%T2_%'
            THEN 'T2'
        WHEN campaign_name LIKE 'Flame_%'
             AND campaign_name LIKE '%PH_%'
            THEN 'T3'
        WHEN campaign_name LIKE 'Flame_%'
             AND campaign_name LIKE '%PH/ID_%'
            THEN 'T3'
        WHEN campaign_name LIKE 'Flame_%'
             AND campaign_name LIKE '%BR%'
            THEN 'T3'
        WHEN campaign_name LIKE 'Flame_%'
             AND campaign_name LIKE '%T3%'
            THEN 'T3'
        ELSE 'other'
    END AS `地区`,
    SUM(installs) AS `安装数`,
    SUM(costmoney) AS `投放成本`,
    SUM(costmoney) / SUM(installs) AS `单次安装成本`,
    SUM(paysum_1) AS `首日收入`,
    SUM(paysum_3) AS `3日收入`,
    SUM(paysum_1) / SUM(costmoney) * 100 AS `首日ROI`,
    SUM(paysum_3) / SUM(costmoney) * 100 AS `3日ROI`"""


def repair_sql(sql: str) -> str:
    if REPAIRED_SELECT_BLOCK in sql:
        return sql
    if sql.count(LEGACY_SELECT_BLOCK) != 1:
        raise ValueError("未找到预期的 ROI_flame 输出字段，拒绝自动修改")
    return sql.replace(LEGACY_SELECT_BLOCK, REPAIRED_SELECT_BLOCK, 1)


def repair_chart_config(chart_config: dict[str, Any] | None) -> dict[str, Any]:
    repaired = copy.deepcopy(chart_config or {})
    repaired["x"] = CHINESE_FIELDS[0]
    repaired["y"] = list(CHINESE_FIELDS[1:])
    repaired["series"] = "单次安装成本"
    repaired["columns"] = [CHINESE_FIELDS[0]]
    return repaired


def json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def backup_chart(row: dict[str, Any]) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"flam_roi_flame_before_column_repair_{int(time.time())}.json"
    payload = {key: json_value(value) for key, value in row.items()}
    backup_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return backup_path


def repair_chart(*, apply: bool) -> dict[str, Any]:
    with psycopg.connect(**SYSTEM_DB, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            lock_clause = "FOR UPDATE" if apply else ""
            cur.execute(
                f"""
                SELECT id, tenant_id, roi_dashboard_id, title, sql, chart_config,
                       version, update_by, update_time
                FROM public.core_roi_dashboard_chart
                WHERE id = %s
                  AND tenant_id = %s
                  AND roi_dashboard_id = %s
                  AND title = %s
                  AND deleted = FALSE
                {lock_clause}
                """,
                (CHART_ID, TENANT_ID, DASHBOARD_ID, CHART_TITLE),
            )
            chart = cur.fetchone()
            if not chart:
                raise RuntimeError("未找到目标 ROI_flame 图表")

            repaired_sql = repair_sql(chart["sql"] or "")
            repaired_config = repair_chart_config(chart.get("chart_config"))
            changed = repaired_sql != chart["sql"] or repaired_config != chart.get("chart_config")
            backup_path: Path | None = None

            if apply and changed:
                backup_path = backup_chart(chart)
                cur.execute(
                    """
                    UPDATE public.core_roi_dashboard_chart
                    SET sql = %s,
                        chart_config = %s::jsonb,
                        version = version + 1,
                        update_time = %s
                    WHERE id = %s
                      AND tenant_id = %s
                      AND roi_dashboard_id = %s
                      AND deleted = FALSE
                    """,
                    (
                        repaired_sql,
                        json.dumps(repaired_config, ensure_ascii=False),
                        int(time.time()),
                        CHART_ID,
                        TENANT_ID,
                        DASHBOARD_ID,
                    ),
                )
                if cur.rowcount != 1:
                    raise RuntimeError(f"目标图表更新数量异常: {cur.rowcount}")
                conn.commit()
            else:
                conn.rollback()

    return {
        "chart_id": CHART_ID,
        "changed": changed,
        "applied": bool(apply and changed),
        "fields": list(CHINESE_FIELDS),
        "backup": str(backup_path) if backup_path else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="写入系统数据库；默认仅检查")
    args = parser.parse_args()
    print(json.dumps(repair_chart(apply=args.apply), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
