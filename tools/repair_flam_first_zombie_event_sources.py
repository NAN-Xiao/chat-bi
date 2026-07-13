"""按已采样确认的工作簿修复 First Zombie 事件参数来源字段。"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from apps.system.crud.tracking_excel import parse_tracking_excel  # noqa: E402
from apps.system.schemas.tenant_schema import TenantTrackingConfigDTO  # noqa: E402
from core_system_db import core_system_db_config  # noqa: E402
from flam_first_zombie_dashboard_sql import DATASOURCE_ID, TENANT_ID  # noqa: E402

EXPECTED_TOTAL = 755
EXPECTED_DISTRIBUTION = {"personal": 469, "ext": 286}
VERIFIED_PAYMENT_PROPERTIES = {
    "money": "$.money",
    "orderId": "$.orderId",
    "productid": "$.productid",
}
DEFAULT_BACKUP_DIR = ROOT / ".codex-runtime" / "event-source-backups"


def _properties(mappings: list[dict[str, Any]]):
    for mapping in mappings or []:
        if not isinstance(mapping, dict):
            continue
        event_name = str(mapping.get("event_name") or "").strip()
        for prop in mapping.get("properties") or []:
            if isinstance(prop, dict):
                yield event_name, prop


def source_distribution(mappings: list[dict[str, Any]]) -> dict[str, int]:
    """统计事件属性使用的 JSON 宿主字段。"""
    result: dict[str, int] = {}
    for _event_name, prop in _properties(mappings):
        source = str(prop.get("source_field") or "").strip() or "<empty>"
        result[source] = result.get(source, 0) + 1
    return result


def _find_property(
    mappings: list[dict[str, Any]],
    event_name: str,
    property_name: str,
) -> dict[str, Any] | None:
    for current_event, prop in _properties(mappings):
        if current_event != event_name:
            continue
        raw_name = str(prop.get("property_name") or "").strip()
        child_name = raw_name.split(".", 1)[-1]
        if child_name == property_name:
            return prop
    return None


def validate_target_mappings(
    mappings: list[dict[str, Any]],
    *,
    expected_total: int = EXPECTED_TOTAL,
    expected_distribution: dict[str, int] | None = None,
) -> dict[str, int]:
    """在写库前验证采样工作簿的关键不变量。"""
    expected = expected_distribution or EXPECTED_DISTRIBUTION
    distribution = source_distribution(mappings)
    actual_total = sum(distribution.values())
    if actual_total != expected_total:
        raise ValueError(f"事件属性数量不匹配：期望 {expected_total}，实际 {actual_total}")
    if distribution != expected:
        raise ValueError(f"来源字段分布不匹配：期望 {expected}，实际 {distribution}")

    for property_name, json_path in VERIFIED_PAYMENT_PROPERTIES.items():
        prop = _find_property(mappings, "ServerPayLog", property_name)
        if not prop:
            raise ValueError(f"缺少 ServerPayLog.{property_name}")
        source_field = str(prop.get("source_field") or "").strip()
        actual_path = str(prop.get("json_path") or "").strip()
        if source_field != "personal" or actual_path != json_path:
            raise ValueError(
                f"ServerPayLog.{property_name} 必须映射到 personal/{json_path}，"
                f"实际为 {source_field or '<empty>'}/{actual_path or '<empty>'}"
            )
    return distribution


def repair_summary(
    current_mappings: list[dict[str, Any]],
    target_mappings: list[dict[str, Any]],
) -> dict[str, Any]:
    """生成 dry-run 与应用后的统一摘要。"""
    return {
        "changed": current_mappings != target_mappings,
        "current_distribution": source_distribution(current_mappings),
        "target_distribution": source_distribution(target_mappings),
    }


def load_repaired_mappings(workbook_path: Path) -> list[dict[str, Any]]:
    """复用平台 Excel 解析器读取修复工作簿。"""
    parsed = parse_tracking_excel(
        workbook_path.read_bytes(),
        TenantTrackingConfigDTO(
            tenant_id=TENANT_ID,
            datasource_id=DATASOURCE_ID,
            enabled=True,
        ),
        physical_schema={},
        datasource_type="mysql",
    )
    mappings = [item for item in parsed.editor.event_name_mappings or [] if isinstance(item, dict)]
    validate_target_mappings(mappings)
    return mappings


def _write_backup(
    mappings: list[dict[str, Any]],
    backup_dir: Path,
) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    target = backup_dir / f"first-zombie-event-sources-{timestamp}.json"
    target.write_text(
        json.dumps(
            {
                "tenant_id": TENANT_ID,
                "datasource_id": DATASOURCE_ID,
                "backed_up_at": int(time.time()),
                "event_name_mappings": mappings,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return target


def repair_event_sources(
    workbook_path: Path,
    *,
    apply: bool = False,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
) -> dict[str, Any]:
    """校验目标工作簿，并可选地在事务内更新唯一配置行。"""
    target_mappings = load_repaired_mappings(workbook_path)
    db = core_system_db_config()
    with psycopg.connect(**db) as conn:
        with conn.cursor() as cur:
            suffix = " FOR UPDATE" if apply else ""
            cur.execute(
                """
                SELECT event_name_mappings
                FROM public.sys_tenant_tracking_config
                WHERE tenant_id = %s AND datasource_id = %s
                """ + suffix,
                (TENANT_ID, DATASOURCE_ID),
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("目标工作空间和数据源的事件字典配置不存在")
            current_mappings = row[0] or []
            summary = repair_summary(current_mappings, target_mappings)
            summary.update(
                {
                    "tenant_id": TENANT_ID,
                    "datasource_id": DATASOURCE_ID,
                    "applied": False,
                    "backup_path": None,
                }
            )
            if not apply or not summary["changed"]:
                return summary

            backup_path = _write_backup(current_mappings, backup_dir)
            cur.execute(
                """
                UPDATE public.sys_tenant_tracking_config
                SET event_name_mappings = %s, update_by = %s, update_time = %s
                WHERE tenant_id = %s AND datasource_id = %s
                """,
                (Jsonb(target_mappings), 1, int(time.time()), TENANT_ID, DATASOURCE_ID),
            )
            if cur.rowcount != 1:
                raise RuntimeError(f"配置更新行数异常：{cur.rowcount}")
            summary["applied"] = True
            summary["backup_path"] = str(backup_path.resolve())
        conn.commit()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, required=True, help="已采样确认的修复工作簿")
    parser.add_argument("--apply", action="store_true", help="实际更新数据库；默认仅 dry-run")
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    args = parser.parse_args()
    result = repair_event_sources(
        args.workbook.resolve(),
        apply=args.apply,
        backup_dir=args.backup_dir.resolve(),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
