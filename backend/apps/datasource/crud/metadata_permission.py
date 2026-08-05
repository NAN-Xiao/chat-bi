"""Normalize metadata targets and calculate denied canonical object keys."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlmodel import Session

from apps.datasource.crud.metadata_permission_authority import (
    METADATA_PERMISSION_TYPES,
    MetadataPermissionValidationError,
    TrackingAuthority,
    load_optional_tracking_authority,
    load_tracking_authority,
    physical_field_key,
    require_bound_context,
    semantic_event_key,
    table_identity,
    target_not_found,
)
from apps.datasource.crud.permission import (
    get_user_permission_rules,
    permission_applies_to_user,
)
from apps.datasource.crud.permission_rules import (
    list_permission_records,
    parse_json_list,
)
from apps.datasource.crud.semantic_object_key import (
    SemanticObjectKey,
    canonical_object_key,
)
from apps.datasource.models.datasource import CoreField, CoreTable
from apps.system.models.tenant import TenantTrackingFieldModel
from common.sql_json_paths import json_paths_intersect, normalize_json_path

__all__ = [
    "METADATA_PERMISSION_TYPES",
    "MetadataPermissionService",
    "MetadataPermissionValidationError",
]


class MetadataPermissionService:
    @staticmethod
    def normalize_permission_targets(
        *,
        session: Session,
        current_user: Any,
        tenant_id: int,
        datasource_id: int,
        permission_type: str,
        targets: Any,
    ) -> list[dict[str, Any]]:
        normalized_type = str(permission_type or "").strip().lower()
        if normalized_type not in METADATA_PERMISSION_TYPES:
            raise MetadataPermissionValidationError(
                "PERMISSION_TYPE_UNSUPPORTED",
                "不支持的权限类型。",
            )
        if not isinstance(targets, list) or not targets:
            raise MetadataPermissionValidationError(
                "METADATA_PERMISSION_TARGET_REQUIRED",
                "请选择需要限制的权限对象。",
            )
        require_bound_context(
            session,
            current_user=current_user,
            tenant_id=tenant_id,
            datasource_id=datasource_id,
        )

        authority = None
        if normalized_type in {"event", "event_property"}:
            authority = load_tracking_authority(
                session,
                tenant_id=tenant_id,
                datasource_id=datasource_id,
            )
        normalized: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        for target in targets:
            if not isinstance(target, dict):
                raise target_not_found()
            entry = MetadataPermissionService._normalize_target(
                session=session,
                tenant_id=tenant_id,
                datasource_id=datasource_id,
                permission_type=normalized_type,
                target=target,
                authority=authority,
            )
            canonical_key = str(entry["canonical_key"])
            if canonical_key not in seen_keys:
                seen_keys.add(canonical_key)
                normalized.append(entry)
        return normalized

    @staticmethod
    def _normalize_target(
        *,
        session: Session,
        tenant_id: int,
        datasource_id: int,
        permission_type: str,
        target: dict[str, Any],
        authority: TrackingAuthority | None,
    ) -> dict[str, Any]:
        enabled = bool(target.get("enable", False))
        if permission_type == "schema":
            catalog_key = str(target.get("catalog_key") or "").strip()
            schema_key = str(target.get("schema_key") or "").strip()
            match = session.execute(
                select(CoreTable.id).where(
                    CoreTable.ds_id == int(datasource_id),
                    CoreTable.checked.is_(True),
                    CoreTable.catalog_key == catalog_key,
                    CoreTable.schema_key == schema_key,
                ).limit(1)
            ).first()
            if match is None:
                raise target_not_found()
            key = SemanticObjectKey(
                object_type="SCHEMA",
                tenant_id=int(tenant_id),
                datasource_id=int(datasource_id),
                catalog=catalog_key,
                schema=schema_key,
            )
            return {
                "object_type": "SCHEMA",
                "catalog_key": catalog_key,
                "schema_key": schema_key,
                "canonical_key": canonical_object_key(key),
                "enable": enabled,
            }

        if authority is None:
            raise target_not_found()
        event_name = str(target.get("event_name") or "").strip()
        event = next((item for item in authority.events if item.name == event_name), None)
        if event is None:
            raise target_not_found()
        if permission_type == "event":
            key = semantic_event_key(
                authority,
                tenant_id=tenant_id,
                datasource_id=datasource_id,
                event=event,
            )
            return {
                "object_type": "EVENT",
                "event_name": event.name,
                "canonical_key": canonical_object_key(key),
                "enable": enabled,
            }

        property_key = str(target.get("event_property_key") or "").strip()
        property_definition = next(
            (item for item in event.properties if item.key == property_key),
            None,
        )
        if property_definition is None:
            raise target_not_found()
        key = semantic_event_key(
            authority,
            tenant_id=tenant_id,
            datasource_id=datasource_id,
            event=event,
            property_definition=property_definition,
        )
        return {
            "object_type": "EVENT_PROPERTY",
            "event_name": event.name,
            "event_property_key": property_definition.key,
            "canonical_key": canonical_object_key(key),
            "enable": enabled,
        }

    @staticmethod
    def resolve_denied_objects(
        *,
        session: Session,
        current_user: Any,
        tenant_id: int,
        datasource_id: int,
    ) -> frozenset[str]:
        require_bound_context(
            session,
            current_user=current_user,
            tenant_id=tenant_id,
            datasource_id=datasource_id,
        )
        rules = get_user_permission_rules(session, current_user, datasource_id)
        permission_ids = {
            int(value)
            for rule in rules
            for value in parse_json_list(rule.permission_list)
            if str(value).strip().isdigit()
        }
        permissions = list_permission_records(
            session,
            ids=sorted(permission_ids),
            ds_id=int(datasource_id),
            enable=True,
        )
        permissions = [
            item
            for item in permissions
            if permission_applies_to_user(item, rules, current_user)
        ]
        denied: set[str] = set()
        denied_schemas: set[tuple[str, str]] = set()
        denied_table_ids: set[int] = set()
        denied_fields: set[tuple[int, str]] = set()
        denied_json_paths: set[tuple[int, str, str]] = set()

        for permission in permissions:
            permission_type = str(permission.type or "").strip().lower()
            if permission_type in METADATA_PERMISSION_TYPES:
                normalized = MetadataPermissionService.normalize_permission_targets(
                    session=session,
                    current_user=current_user,
                    tenant_id=tenant_id,
                    datasource_id=datasource_id,
                    permission_type=permission_type,
                    targets=parse_json_list(permission.permissions),
                )
                for entry in normalized:
                    if entry["enable"]:
                        continue
                    denied.add(str(entry["canonical_key"]))
                    if permission_type == "schema":
                        denied_schemas.add(
                            (str(entry["catalog_key"]), str(entry["schema_key"]))
                        )
                continue
            if permission_type == "table" and permission.table_id is not None:
                table = table_identity(
                    session,
                    datasource_id=datasource_id,
                    table_id=int(permission.table_id),
                )
                denied_table_ids.add(table.id)
                denied.add(
                    canonical_object_key(
                        SemanticObjectKey(
                            object_type="TABLE",
                            tenant_id=tenant_id,
                            datasource_id=datasource_id,
                            catalog=table.catalog,
                            schema=table.schema,
                            table=table.table,
                        )
                    )
                )
                continue
            if permission_type == "column" and permission.table_id is not None:
                MetadataPermissionService._collect_denied_columns(
                    session=session,
                    tenant_id=tenant_id,
                    datasource_id=datasource_id,
                    table_id=int(permission.table_id),
                    entries=parse_json_list(permission.permissions),
                    denied=denied,
                    denied_fields=denied_fields,
                    denied_json_paths=denied_json_paths,
                )

        if not permissions:
            return frozenset()
        authority = load_optional_tracking_authority(
            session,
            tenant_id=tenant_id,
            datasource_id=datasource_id,
        )
        if authority is None:
            return frozenset(denied)
        schema_denied = (authority.table.catalog, authority.table.schema) in denied_schemas
        event_field_denied = (
            authority.table.id,
            authority.event_name_field,
        ) in denied_fields
        for event in authority.events:
            event_key = canonical_object_key(
                semantic_event_key(
                    authority,
                    tenant_id=tenant_id,
                    datasource_id=datasource_id,
                    event=event,
                )
            )
            inherited_event_denial = (
                schema_denied
                or authority.table.id in denied_table_ids
                or event_field_denied
                or event_key in denied
            )
            if inherited_event_denial:
                denied.add(event_key)
            for property_definition in event.properties:
                path_denied = any(
                    table_id == authority.table.id
                    and source_field == property_definition.source_field
                    and property_definition.json_path is not None
                    and json_paths_intersect(property_definition.json_path, denied_path)
                    for table_id, source_field, denied_path in denied_json_paths
                )
                if (
                    inherited_event_denial
                    or (authority.table.id, property_definition.source_field) in denied_fields
                    or path_denied
                ):
                    denied.add(
                        canonical_object_key(
                            semantic_event_key(
                                authority,
                                tenant_id=tenant_id,
                                datasource_id=datasource_id,
                                event=event,
                                property_definition=property_definition,
                            )
                        )
                    )
        return frozenset(denied)

    @staticmethod
    def _collect_denied_columns(
        *,
        session: Session,
        tenant_id: int,
        datasource_id: int,
        table_id: int,
        entries: list[Any],
        denied: set[str],
        denied_fields: set[tuple[int, str]],
        denied_json_paths: set[tuple[int, str, str]],
    ) -> None:
        table = table_identity(
            session,
            datasource_id=datasource_id,
            table_id=table_id,
        )
        for entry in entries:
            if not isinstance(entry, dict) or bool(entry.get("enable", True)):
                continue
            field_id = entry.get("field_id")
            if isinstance(field_id, str) and field_id.startswith("tracking:"):
                field_name = field_id.rsplit(":", 1)[-1]
                row = session.execute(
                    select(
                        TenantTrackingFieldModel.source_field,
                        TenantTrackingFieldModel.json_path,
                    ).where(
                        TenantTrackingFieldModel.tenant_id == int(tenant_id),
                        TenantTrackingFieldModel.datasource_id == int(datasource_id),
                        TenantTrackingFieldModel.table_name == table.name,
                        TenantTrackingFieldModel.field_name == field_name,
                    )
                ).one_or_none()
                if row is None:
                    raise target_not_found()
                source_field = physical_field_key(
                    session,
                    datasource_id=datasource_id,
                    table_id=table.id,
                    field_name=str(row.source_field or ""),
                )
                json_path = normalize_json_path(row.json_path)
                if not json_path:
                    raise target_not_found()
                denied_json_paths.add((table.id, source_field, json_path))
                denied.add(
                    canonical_object_key(
                        SemanticObjectKey(
                            object_type="JSON_PATH",
                            tenant_id=tenant_id,
                            datasource_id=datasource_id,
                            catalog=table.catalog,
                            schema=table.schema,
                            table=table.table,
                            field=source_field,
                            json_path=json_path,
                        )
                    )
                )
                continue
            try:
                physical_id = int(field_id)
            except (TypeError, ValueError) as exc:
                raise target_not_found() from exc
            row = session.execute(
                select(CoreField.field_key).where(
                    CoreField.id == physical_id,
                    CoreField.table_id == table.id,
                    CoreField.ds_id == int(datasource_id),
                    CoreField.checked.is_(True),
                )
            ).scalar_one_or_none()
            if row is None:
                raise target_not_found()
            field_key = str(row)
            denied_fields.add((table.id, field_key))
            denied.add(
                canonical_object_key(
                    SemanticObjectKey(
                        object_type="FIELD",
                        tenant_id=tenant_id,
                        datasource_id=datasource_id,
                        catalog=table.catalog,
                        schema=table.schema,
                        table=table.table,
                        field=field_key,
                    )
                )
            )
