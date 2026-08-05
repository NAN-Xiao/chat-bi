"""Authoritative catalog and tracking resolution for metadata permissions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlmodel import Session

from apps.datasource.crud.binding import get_bound_datasource_id_for_tenant
from apps.datasource.crud.semantic_object_key import (
    DeclaredObjectPath,
    SemanticObjectKey,
    normalize_catalog_identifier,
)
from apps.datasource.crud.semantic_object_resolution import (
    ObjectResolutionStatus,
    resolve_table_key,
)
from apps.datasource.models.datasource import CoreDatasource, CoreField, CoreTable
from apps.system.models.tenant import (
    TenantTrackingConfigModel,
    TenantTrackingFieldModel,
)
from apps.system.schemas.access_context import (
    current_tenant_id,
    is_global_platform_context,
)
from common.sql_json_paths import normalize_json_path

METADATA_PERMISSION_TYPES = frozenset({"schema", "event", "event_property"})


class MetadataPermissionValidationError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class TableIdentity:
    id: int
    name: str
    catalog: str
    schema: str
    table: str


@dataclass(frozen=True)
class EventProperty:
    key: str
    source_field: str
    json_path: str | None


@dataclass(frozen=True)
class EventDefinition:
    name: str
    properties: tuple[EventProperty, ...]


@dataclass(frozen=True)
class TrackingAuthority:
    table: TableIdentity
    event_name_field: str
    events: tuple[EventDefinition, ...]


def target_not_found() -> MetadataPermissionValidationError:
    return MetadataPermissionValidationError(
        "METADATA_PERMISSION_TARGET_NOT_FOUND",
        "权限对象不存在或不属于当前工作空间。",
        status_code=404,
    )


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _event_names(mapping: dict[str, Any]) -> list[str]:
    values = [mapping.get(key) for key in ("event_name", "eventName", "name", "value")]
    if isinstance(mapping.get("events"), list):
        values.extend(mapping["events"])
    result: list[str] = []
    for value in values:
        name = str(value or "").strip()
        if name and name not in result:
            result.append(name)
    return result


def _property_key(value: dict[str, Any]) -> str:
    for key in ("property_name", "propertyName", "field_name", "fieldName", "name"):
        text = str(value.get(key) or "").strip()
        if text:
            return text
    return ""


def require_bound_context(
    session: Session,
    *,
    current_user: Any,
    tenant_id: int,
    datasource_id: int,
) -> None:
    user_tenant_id = current_tenant_id(current_user)
    if not is_global_platform_context(current_user) and user_tenant_id != int(tenant_id):
        raise target_not_found()
    if get_bound_datasource_id_for_tenant(session, int(tenant_id)) != int(datasource_id):
        raise target_not_found()


def table_identity(session: Session, *, datasource_id: int, table_id: int) -> TableIdentity:
    row = session.execute(
        select(
            CoreTable.id,
            CoreTable.table_name,
            CoreTable.catalog_key,
            CoreTable.schema_key,
            CoreTable.table_key,
        ).where(
            CoreTable.id == int(table_id),
            CoreTable.ds_id == int(datasource_id),
            CoreTable.checked.is_(True),
        )
    ).one_or_none()
    if row is None:
        raise target_not_found()
    return TableIdentity(
        id=int(row.id),
        name=str(row.table_name or ""),
        catalog=str(row.catalog_key or ""),
        schema=str(row.schema_key or ""),
        table=str(row.table_key or ""),
    )


def _resolve_tracking_table(
    session: Session,
    *,
    datasource_id: int,
    table_name: str,
) -> TableIdentity:
    result = resolve_table_key(
        session,
        datasource_id=int(datasource_id),
        declared=DeclaredObjectPath(object_type="TABLE", table=table_name),
    )
    if result.status is not ObjectResolutionStatus.RESOLVED or result.key is None:
        raise target_not_found()
    key = result.key
    row = session.execute(
        select(CoreTable.id, CoreTable.table_name).where(
            CoreTable.ds_id == int(datasource_id),
            CoreTable.checked.is_(True),
            CoreTable.catalog_key == str(key.catalog or ""),
            CoreTable.schema_key == str(key.schema or ""),
            CoreTable.table_key == str(key.table or ""),
        )
    ).one_or_none()
    if row is None:
        raise target_not_found()
    return TableIdentity(
        id=int(row.id),
        name=str(row.table_name or ""),
        catalog=str(key.catalog or ""),
        schema=str(key.schema or ""),
        table=str(key.table or ""),
    )


def physical_field_key(
    session: Session,
    *,
    datasource_id: int,
    table_id: int,
    field_name: str,
) -> str:
    dialect = session.execute(
        select(CoreDatasource.type).where(CoreDatasource.id == int(datasource_id))
    ).scalar_one_or_none()
    key = normalize_catalog_identifier(field_name, dialect=dialect)
    row = session.execute(
        select(CoreField.field_key).where(
            CoreField.table_id == int(table_id),
            CoreField.ds_id == int(datasource_id),
            CoreField.checked.is_(True),
            CoreField.field_key == key,
        )
    ).scalar_one_or_none()
    if row is None:
        raise target_not_found()
    return str(row)


def _tracking_field_override(
    session: Session,
    *,
    tenant_id: int,
    datasource_id: int,
    table_name: str,
    property_name: str,
) -> tuple[str | None, str | None]:
    row = session.execute(
        select(
            TenantTrackingFieldModel.source_field,
            TenantTrackingFieldModel.json_path,
        ).where(
            TenantTrackingFieldModel.tenant_id == int(tenant_id),
            TenantTrackingFieldModel.datasource_id == int(datasource_id),
            TenantTrackingFieldModel.table_name == table_name,
            TenantTrackingFieldModel.field_name == property_name,
        )
    ).one_or_none()
    if row is None:
        return None, None
    return (
        str(row.source_field or "").strip() or None,
        normalize_json_path(row.json_path),
    )


def load_tracking_authority(
    session: Session,
    *,
    tenant_id: int,
    datasource_id: int,
) -> TrackingAuthority:
    row = session.execute(
        select(
            TenantTrackingConfigModel.default_event_table,
            TenantTrackingConfigModel.default_event_name_field,
            TenantTrackingConfigModel.event_name_mappings,
        ).where(
            TenantTrackingConfigModel.tenant_id == int(tenant_id),
            TenantTrackingConfigModel.datasource_id == int(datasource_id),
            TenantTrackingConfigModel.enabled.is_(True),
        )
    ).one_or_none()
    if row is None:
        raise target_not_found()
    table_name = str(row.default_event_table or "").strip()
    event_name_field = str(row.default_event_name_field or "").strip()
    if not table_name or not event_name_field:
        raise target_not_found()
    table = _resolve_tracking_table(
        session,
        datasource_id=datasource_id,
        table_name=table_name,
    )
    event_name_field_key = physical_field_key(
        session,
        datasource_id=datasource_id,
        table_id=table.id,
        field_name=event_name_field,
    )

    events: list[EventDefinition] = []
    seen_events: set[str] = set()
    for mapping in _json_list(row.event_name_mappings):
        if not isinstance(mapping, dict):
            continue
        mapping_names = _event_names(mapping)
        for event_name in mapping_names:
            if event_name in seen_events:
                raise MetadataPermissionValidationError(
                    "METADATA_EVENT_DUPLICATE",
                    "当前工作空间存在重复事件名称，请先修正事件字典。",
                )
            seen_events.add(event_name)

        properties: list[EventProperty] = []
        seen_properties: set[str] = set()
        raw_properties = mapping.get("properties")
        for raw_property in raw_properties if isinstance(raw_properties, list) else []:
            if not isinstance(raw_property, dict):
                continue
            property_name = _property_key(raw_property)
            if not property_name or property_name in seen_properties:
                if property_name:
                    raise MetadataPermissionValidationError(
                        "METADATA_EVENT_PROPERTY_DUPLICATE",
                        "当前事件存在重复属性标识，请先修正事件字典。",
                    )
                continue
            seen_properties.add(property_name)
            source_field = str(raw_property.get("source_field") or "").strip()
            json_path = normalize_json_path(raw_property.get("json_path"))
            if not source_field:
                override_source, override_path = _tracking_field_override(
                    session,
                    tenant_id=tenant_id,
                    datasource_id=datasource_id,
                    table_name=table_name,
                    property_name=property_name,
                )
                source_field = override_source or property_name
                json_path = json_path or override_path
            source_field_key = physical_field_key(
                session,
                datasource_id=datasource_id,
                table_id=table.id,
                field_name=source_field,
            )
            properties.append(
                EventProperty(
                    key=property_name,
                    source_field=source_field_key,
                    json_path=json_path,
                )
            )
        for event_name in mapping_names:
            events.append(EventDefinition(name=event_name, properties=tuple(properties)))

    return TrackingAuthority(
        table=table,
        event_name_field=event_name_field_key,
        events=tuple(events),
    )


def load_optional_tracking_authority(
    session: Session,
    *,
    tenant_id: int,
    datasource_id: int,
) -> TrackingAuthority | None:
    configured = session.execute(
        select(TenantTrackingConfigModel.id).where(
            TenantTrackingConfigModel.tenant_id == int(tenant_id),
            TenantTrackingConfigModel.datasource_id == int(datasource_id),
            TenantTrackingConfigModel.enabled.is_(True),
        )
    ).first()
    if configured is None:
        return None
    return load_tracking_authority(
        session,
        tenant_id=tenant_id,
        datasource_id=datasource_id,
    )


def semantic_event_key(
    authority: TrackingAuthority,
    *,
    tenant_id: int,
    datasource_id: int,
    event: EventDefinition,
    property_definition: EventProperty | None = None,
) -> SemanticObjectKey:
    return SemanticObjectKey(
        object_type="EVENT_PROPERTY" if property_definition else "EVENT",
        tenant_id=int(tenant_id),
        datasource_id=int(datasource_id),
        catalog=authority.table.catalog,
        schema=authority.table.schema,
        table=authority.table.table,
        field=(property_definition.source_field if property_definition else authority.event_name_field),
        json_path=property_definition.json_path if property_definition else None,
        event_name=event.name,
        event_property_key=property_definition.key if property_definition else None,
    )
