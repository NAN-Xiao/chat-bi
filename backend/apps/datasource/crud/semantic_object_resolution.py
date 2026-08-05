"""Database-backed resolution of declared semantic object paths."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sqlalchemy import select
from sqlmodel import Session

from apps.datasource.crud.semantic_object_key import (
    DeclaredObjectPath,
    SemanticObjectKey,
    normalize_catalog_identifier,
)
from apps.datasource.models.datasource import (
    CoreDatasource,
    CoreDatasourceTenantBinding,
    CoreTable,
)


class ObjectResolutionStatus(str, Enum):
    RESOLVED = "RESOLVED"
    MISSING = "MISSING"
    AMBIGUOUS = "AMBIGUOUS"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True)
class ObjectResolutionResult:
    status: ObjectResolutionStatus
    key: SemanticObjectKey | None = None
    message: str | None = None


def _missing(message: str) -> ObjectResolutionResult:
    return ObjectResolutionResult(status=ObjectResolutionStatus.MISSING, message=message)


def resolve_table_key(
    session: Session,
    *,
    datasource_id: int,
    declared: DeclaredObjectPath,
) -> ObjectResolutionResult:
    if declared.object_type != "TABLE" or not str(declared.table or "").strip():
        return _missing("表对象声明不完整。")

    datasource = session.execute(
        select(
            CoreDatasource.type,
            CoreDatasource.catalog_complete,
            CoreDatasource.physical_schema_hash,
        ).where(CoreDatasource.id == int(datasource_id))
    ).one_or_none()
    if datasource is None:
        return _missing("当前数据源不存在或不可用。")
    if not datasource.catalog_complete or not datasource.physical_schema_hash:
        return ObjectResolutionResult(
            status=ObjectResolutionStatus.INCOMPLETE,
            message="当前数据源目录不完整，请先刷新数据源结构。",
        )

    tenant_ids = session.execute(
        select(CoreDatasourceTenantBinding.tenant_id).where(
            CoreDatasourceTenantBinding.datasource_id == int(datasource_id)
        )
    ).scalars().all()
    if len(tenant_ids) != 1:
        return _missing("当前数据源未绑定唯一工作空间，无法解析对象。")

    dialect = datasource.type
    table_key = normalize_catalog_identifier(declared.table, dialect=dialect)
    statement = select(
        CoreTable.catalog_key,
        CoreTable.schema_key,
        CoreTable.table_key,
    ).where(
        CoreTable.ds_id == int(datasource_id),
        CoreTable.checked.is_(True),
        CoreTable.table_key == table_key,
    )
    if declared.catalog is not None:
        statement = statement.where(
            CoreTable.catalog_key
            == normalize_catalog_identifier(declared.catalog, dialect=dialect)
        )
    if declared.schema is not None:
        statement = statement.where(
            CoreTable.schema_key
            == normalize_catalog_identifier(declared.schema, dialect=dialect)
        )
    matches = session.execute(statement).all()
    if not matches:
        return _missing(f"对象 {declared.table} 在当前数据源中不存在。")
    if len(matches) > 1:
        return ObjectResolutionResult(
            status=ObjectResolutionStatus.AMBIGUOUS,
            message=f"对象 {declared.table} 在当前数据源中存在多个匹配，请指定 Schema。",
        )

    match = matches[0]
    return ObjectResolutionResult(
        status=ObjectResolutionStatus.RESOLVED,
        key=SemanticObjectKey(
            object_type="TABLE",
            tenant_id=int(tenant_ids[0]),
            datasource_id=int(datasource_id),
            catalog=match.catalog_key,
            schema=match.schema_key,
            table=match.table_key,
        ),
    )
