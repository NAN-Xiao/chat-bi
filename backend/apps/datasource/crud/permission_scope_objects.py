"""Canonical object projection for one permission snapshot."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlmodel import Session

from apps.datasource.crud.metadata_permission_authority import (
    load_optional_tracking_authority,
    semantic_event_key,
)
from apps.datasource.crud.permission_scope import stable_permission_hash
from apps.datasource.crud.semantic_object_key import (
    SemanticObjectKey,
    canonical_object_key,
    normalize_catalog_identifier,
)
from apps.datasource.models.datasource import CoreDatasource, CoreField, CoreTable
from apps.system.models.tenant import TenantTrackingFieldModel
from common.sql_json_paths import normalize_json_path


class PermissionObjectProjectionError(ValueError):
    pass


def row_constraints_hash(constraints: list[dict]) -> str:
    ordered = sorted(
        constraints,
        key=lambda item: json.dumps(
            item,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ),
    )
    return stable_permission_hash(ordered)


def build_allowed_object_keys(
    session: Session,
    *,
    tenant_id: int,
    datasource: CoreDatasource,
) -> set[str]:
    datasource_id = int(datasource.id)
    tables = session.execute(
        select(CoreTable).where(
            CoreTable.ds_id == datasource_id,
            CoreTable.checked.is_(True),
        )
    ).scalars().all()
    table_ids = [int(table.id) for table in tables]
    fields = (
        session.execute(
            select(CoreField).where(
                CoreField.ds_id == datasource_id,
                CoreField.table_id.in_(table_ids),
                CoreField.checked.is_(True),
            )
        ).scalars().all()
        if table_ids
        else []
    )
    table_by_id = {int(table.id): table for table in tables}
    result: set[str] = set()
    for table in tables:
        common = {
            "tenant_id": tenant_id,
            "datasource_id": datasource_id,
            "catalog": str(table.catalog_key or ""),
            "schema": str(table.schema_key or ""),
        }
        result.add(canonical_object_key(SemanticObjectKey(object_type="SCHEMA", **common)))
        result.add(
            canonical_object_key(
                SemanticObjectKey(
                    object_type="TABLE",
                    table=str(table.table_key or ""),
                    **common,
                )
            )
        )
    for field in fields:
        table = table_by_id.get(int(field.table_id))
        if table is None:
            raise PermissionObjectProjectionError("field references missing table")
        result.add(
            canonical_object_key(
                SemanticObjectKey(
                    object_type="FIELD",
                    tenant_id=tenant_id,
                    datasource_id=datasource_id,
                    catalog=str(table.catalog_key or ""),
                    schema=str(table.schema_key or ""),
                    table=str(table.table_key or ""),
                    field=str(field.field_key or ""),
                )
            )
        )

    authority = load_optional_tracking_authority(
        session,
        tenant_id=tenant_id,
        datasource_id=datasource_id,
    )
    if authority is not None:
        for event in authority.events:
            result.add(
                canonical_object_key(
                    semantic_event_key(
                        authority,
                        tenant_id=tenant_id,
                        datasource_id=datasource_id,
                        event=event,
                    )
                )
            )
            for property_definition in event.properties:
                result.add(
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
                if property_definition.json_path:
                    result.add(
                        canonical_object_key(
                            SemanticObjectKey(
                                object_type="JSON_PATH",
                                tenant_id=tenant_id,
                                datasource_id=datasource_id,
                                catalog=authority.table.catalog,
                                schema=authority.table.schema,
                                table=authority.table.table,
                                field=property_definition.source_field,
                                json_path=property_definition.json_path,
                            )
                        )
                    )

    _add_tracking_json_paths(
        session,
        tenant_id=tenant_id,
        datasource=datasource,
        tables=tables,
        fields=fields,
        result=result,
    )
    return result


def _add_tracking_json_paths(
    session: Session,
    *,
    tenant_id: int,
    datasource: CoreDatasource,
    tables: list[CoreTable],
    fields: list[CoreField],
    result: set[str],
) -> None:
    datasource_id = int(datasource.id)
    tracking_fields = session.execute(
        select(
            TenantTrackingFieldModel.table_name,
            TenantTrackingFieldModel.source_field,
            TenantTrackingFieldModel.json_path,
        ).where(
            TenantTrackingFieldModel.tenant_id == tenant_id,
            TenantTrackingFieldModel.datasource_id == datasource_id,
            TenantTrackingFieldModel.json_path.is_not(None),
        )
    ).all()
    fields_by_table: dict[int, dict[str, CoreField]] = {}
    for field in fields:
        fields_by_table.setdefault(int(field.table_id), {})[str(field.field_key or "")] = field
    for tracking_field in tracking_fields:
        matching_tables = [
            table for table in tables if str(table.table_name) == str(tracking_field.table_name)
        ]
        if len(matching_tables) != 1:
            raise PermissionObjectProjectionError("tracking table is missing or ambiguous")
        table = matching_tables[0]
        field_key = normalize_catalog_identifier(
            tracking_field.source_field,
            dialect=datasource.type,
        )
        if field_key not in fields_by_table.get(int(table.id), {}):
            raise PermissionObjectProjectionError("tracking source field is missing")
        json_path = normalize_json_path(tracking_field.json_path)
        if not json_path:
            raise PermissionObjectProjectionError("tracking JSON path is invalid")
        result.add(
            canonical_object_key(
                SemanticObjectKey(
                    object_type="JSON_PATH",
                    tenant_id=tenant_id,
                    datasource_id=datasource_id,
                    catalog=str(table.catalog_key or ""),
                    schema=str(table.schema_key or ""),
                    table=str(table.table_key or ""),
                    field=field_key,
                    json_path=json_path,
                )
            )
        )
