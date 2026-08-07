"""Build validation metadata from the authorized workspace datasource."""

from __future__ import annotations

from apps.datasource.crud.permission_scope import PermissionScopeService
from apps.datasource.crud.semantic_object_key import SemanticObjectKey, canonical_object_key
from apps.datasource.models.datasource import CoreDatasource, CoreField, CoreTable
from apps.db.db import get_sqlglot_dialect
from apps.knowledge_base.validators import ValidationContext
from apps.datasource.crud.metadata_permission_authority import (
    load_optional_tracking_authority,
    semantic_event_key,
)
from apps.system.schemas.access_context import current_tenant_id
from sqlmodel import select


def _qualified_table(table: CoreTable) -> str:
    return ".".join(
        item
        for item in (table.catalog_key, table.schema_key, table.table_key)
        if str(item or "").strip()
    )


def build_validation_context(*, session, current_user, datasource_id: int) -> ValidationContext:
    """Return only catalog objects allowed for the current user and datasource."""
    tenant_id = current_tenant_id(current_user)
    if tenant_id is None:
        raise ValueError("当前未进入工作空间，无法读取数据源目录。")
    snapshot = PermissionScopeService.build_snapshot(
        session=session,
        current_user=current_user,
        tenant_id=int(tenant_id),
        datasource_id=int(datasource_id),
    )
    datasource = session.get(CoreDatasource, int(datasource_id))
    if datasource is None:
        raise ValueError("当前数据源不存在或已失效。")

    tables = session.exec(
        select(CoreTable).where(
            CoreTable.ds_id == int(datasource_id),
            CoreTable.checked.is_(True),
        )
    ).all()
    table_ids = [int(item.id) for item in tables]
    fields = session.exec(
        select(CoreField).where(
            CoreField.ds_id == int(datasource_id),
            CoreField.table_id.in_(table_ids),
            CoreField.checked.is_(True),
        )
    ).all() if table_ids else []
    fields_by_table: dict[int, list[str]] = {}
    for field in fields:
        table = next((item for item in tables if int(item.id) == int(field.table_id)), None)
        if table is None:
            continue
        key = canonical_object_key(
            SemanticObjectKey(
                object_type="FIELD",
                tenant_id=int(tenant_id),
                datasource_id=int(datasource_id),
                catalog=str(table.catalog_key or ""),
                schema=str(table.schema_key or ""),
                table=str(table.table_key or ""),
                field=str(field.field_key or ""),
            )
        )
        if key in snapshot.allowed_object_keys and key not in snapshot.denied_object_keys:
            fields_by_table.setdefault(int(field.table_id), []).append(str(field.field_key or field.field_name or ""))

    catalog: dict[str, list[str]] = {}
    for table in tables:
        table_key = canonical_object_key(
            SemanticObjectKey(
                object_type="TABLE",
                tenant_id=int(tenant_id),
                datasource_id=int(datasource_id),
                catalog=str(table.catalog_key or ""),
                schema=str(table.schema_key or ""),
                table=str(table.table_key or ""),
            )
        )
        if table_key not in snapshot.allowed_object_keys or table_key in snapshot.denied_object_keys:
            continue
        qualified = _qualified_table(table)
        if qualified:
            catalog[qualified] = sorted(set(fields_by_table.get(int(table.id), [])))

    event_names: list[str] = []
    json_paths: dict[str, list[str]] = {}
    authority = load_optional_tracking_authority(
        session,
        tenant_id=int(tenant_id),
        datasource_id=int(datasource_id),
    )
    if authority is not None:
        for event in authority.events:
            event_key = canonical_object_key(
                semantic_event_key(
                    authority,
                    tenant_id=int(tenant_id),
                    datasource_id=int(datasource_id),
                    event=event,
                )
            )
            if event_key not in snapshot.allowed_object_keys or event_key in snapshot.denied_object_keys:
                continue
            event_names.append(event.name)
            for property_definition in event.properties:
                if not property_definition.json_path:
                    continue
                json_paths.setdefault(
                    ".".join(
                        part
                        for part in (
                            authority.table.schema,
                            authority.table.table,
                            property_definition.source_field,
                        )
                        if part
                    ),
                    [],
                ).append(property_definition.json_path)

    return ValidationContext(
        dialect=get_sqlglot_dialect(str(datasource.type or "postgres")) or "postgres",
        tables=catalog,
        json_paths={key: sorted(set(value)) for key, value in json_paths.items()},
        event_names=tuple(sorted(set(event_names))),
    )
