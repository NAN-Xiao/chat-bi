from __future__ import annotations

from typing import Any

from sqlmodel import select

from apps.datasource.crud.permission_rules import RULE_SCOPE_PLATFORM
from apps.datasource.models.datasource import CoreField, CoreTable
from apps.system.models.tenant import TenantTrackingFieldModel
from common.core.deps import SessionDep
from common.sql_json_paths import normalize_json_path


def _entry_value_matches(entry: dict[str, Any], key: str, expected: Any) -> bool:
    if key not in entry or entry.get(key) in (None, ""):
        return True
    if key == "is_json_subfield":
        return entry.get(key) is expected
    return str(entry.get(key)).strip() == str(expected).strip()


def _physical_field_entry(
        session: SessionDep,
        table: CoreTable,
        raw_entry: dict[str, Any],
) -> dict[str, Any]:
    field_id = raw_entry.get("field_id")
    if isinstance(field_id, bool):
        raise ValueError("字段权限包含无效物理字段")
    try:
        normalized_id = int(field_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("字段权限包含无效字段 ID") from exc
    field = session.exec(
        select(CoreField).where(
            CoreField.id == normalized_id,
            CoreField.table_id == int(table.id),
        )
    ).first()
    if field is None:
        raise ValueError("字段权限中的物理字段不属于目标表")
    if not _entry_value_matches(raw_entry, "field_name", field.field_name):
        raise ValueError("字段权限中的物理字段名称与字段 ID 不一致")
    return {
        "field_id": int(field.id),
        "field_name": field.field_name,
        "field_comment": field.custom_comment or field.field_comment or "",
        "enable": bool(raw_entry.get("enable", True)),
    }


def _tracking_field_entry(
        session: SessionDep,
        *,
        tenant_id: int,
        datasource_id: int,
        table: CoreTable,
        raw_entry: dict[str, Any],
) -> dict[str, Any]:
    field_id = str(raw_entry.get("field_id") or "").strip()
    prefix = f"tracking:{table.table_name}:"
    if not field_id.startswith(prefix):
        raise ValueError("JSON 子字段权限 ID 与目标表不一致")
    field_name = field_id[len(prefix):].strip()
    if not field_name:
        raise ValueError("JSON 子字段权限缺少字段名称")

    tracking = session.exec(
        select(
            TenantTrackingFieldModel.field_name,
            TenantTrackingFieldModel.field_comment,
            TenantTrackingFieldModel.source_field,
            TenantTrackingFieldModel.json_path,
        ).where(
            TenantTrackingFieldModel.tenant_id == int(tenant_id),
            TenantTrackingFieldModel.datasource_id == int(datasource_id),
            TenantTrackingFieldModel.table_name == table.table_name,
            TenantTrackingFieldModel.field_name == field_name,
        )
    ).first()
    if tracking is None:
        raise ValueError("当前工作空间不存在该 JSON 子字段")

    canonical_name = str(tracking.field_name or "").strip()
    source_field = str(tracking.source_field or "").strip()
    json_path = normalize_json_path(tracking.json_path)
    if not canonical_name or not source_field or not json_path:
        raise ValueError("JSON 子字段元数据不完整")
    source_exists = session.exec(
        select(CoreField.id).where(
            CoreField.table_id == int(table.id),
            CoreField.field_name == source_field,
        )
    ).first()
    if source_exists is None:
        raise ValueError("JSON 子字段宿主列不属于目标表")

    expected = {
        "field_name": canonical_name,
        "source_field": source_field,
        "json_path": json_path,
        "is_json_subfield": True,
    }
    for key, value in expected.items():
        if not _entry_value_matches(raw_entry, key, value):
            raise ValueError(f"JSON 子字段权限的 {key} 与工作空间元数据不一致")

    return {
        "field_id": f"tracking:{table.table_name}:{canonical_name}",
        "field_name": canonical_name,
        "field_comment": str(tracking.field_comment or ""),
        "source_field": source_field,
        "json_path": json_path,
        "is_json_subfield": True,
        "enable": bool(raw_entry.get("enable", True)),
    }


def normalize_permission_field_entries(
        session: SessionDep,
        *,
        tenant_id: int,
        scope: str,
        datasource_id: int,
        table: CoreTable,
        entries: Any,
) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        raise ValueError("字段权限配置必须是列表")
    normalized: list[dict[str, Any]] = []
    for raw_entry in entries:
        if not isinstance(raw_entry, dict):
            raise ValueError("字段权限条目格式无效")
        field_id = raw_entry.get("field_id")
        is_tracking = bool(raw_entry.get("is_json_subfield")) or (
            isinstance(field_id, str) and field_id.strip().startswith("tracking:")
        )
        if is_tracking:
            if str(scope or "").strip().upper() == RULE_SCOPE_PLATFORM:
                raise ValueError("平台全局权限不能引用工作空间 JSON 子字段")
            normalized.append(_tracking_field_entry(
                session,
                tenant_id=int(tenant_id),
                datasource_id=int(datasource_id),
                table=table,
                raw_entry=raw_entry,
            ))
        else:
            normalized.append(_physical_field_entry(session, table, raw_entry))
    return normalized
