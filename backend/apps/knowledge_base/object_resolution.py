"""Resolve projected declarations against the consuming datasource catalog."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlmodel import Session, select

from apps.datasource.crud.semantic_object_key import (
    DeclaredObjectPath,
    SemanticObjectKey,
    canonical_object_key,
    normalize_catalog_identifier,
)
from apps.datasource.crud.semantic_object_resolution import (
    ObjectResolutionStatus,
    resolve_table_key,
)
from apps.datasource.models.datasource import CoreDatasource, CoreField, CoreTable
from apps.knowledge_base.object_references import ProjectedObjectReference


@dataclass(frozen=True)
class ResolvedObjectReference:
    reference: ProjectedObjectReference
    tenant_id: int
    datasource_id: int
    physical_schema_hash: str
    status: str
    canonical_key: str | None
    report: Mapping[str, Any] | None = None
    checked_at: datetime | None = None

    @property
    def declared_key(self) -> str:
        return self.reference.declared_key

    @property
    def object_type(self) -> str:
        return self.reference.object_type


class ObjectResolutionError(ValueError):
    """Internal resolver error; callers should expose only its safe report."""


ResolverCallback = Callable[[DeclaredObjectPath, int, int], SemanticObjectKey | None]


def resolve_references_for_context(
    references: Iterable[ProjectedObjectReference | object],
    *,
    tenant_id: int,
    datasource_id: int,
    schema_hash: str | None = None,
    physical_schema_hash: str | None = None,
    session: Session | None = None,
    resolver: ResolverCallback | None = None,
    catalog: Mapping[str, object] | None = None,
) -> list[ResolvedObjectReference]:
    """Resolve every declaration for one consuming tenant/datasource/hash.

    A database session or callback is authoritative in production.  The small
    catalog mapping is intentionally supported for deterministic unit tests and
    offline publisher validation.  Without one, the function still derives the
    context-specific key but marks the result ``UNRESOLVED`` so it cannot be
    used by permission-filtered retrieval.
    """
    current_hash = str(physical_schema_hash or schema_hash or "").strip()
    if not current_hash:
        raise ValueError("当前数据源缺少物理 Schema 指纹。")
    output: list[ResolvedObjectReference] = []
    for raw_reference in references:
        reference = _projected_reference(raw_reference)
        path = reference.declared_path
        key: SemanticObjectKey | None = None
        report: dict[str, Any] = {}
        status = "UNRESOLVED"
        try:
            if resolver is not None:
                key = resolver(path, int(tenant_id), int(datasource_id))
                status = "RESOLVED" if key is not None else "UNRESOLVED"
            elif session is not None:
                key, status, report = _resolve_with_session(
                    session,
                    path=path,
                    tenant_id=int(tenant_id),
                    datasource_id=int(datasource_id),
                )
            elif catalog is not None:
                key, status, report = _resolve_with_catalog(
                    path,
                    tenant_id=int(tenant_id),
                    datasource_id=int(datasource_id),
                    catalog=catalog,
                )
            else:
                # Keep a context-specific candidate for diagnostics.  It is
                # intentionally still UNRESOLVED and therefore ineligible for
                # retrieval until a catalog-backed call confirms it.
                key = _contextual_candidate(path, tenant_id=int(tenant_id), datasource_id=int(datasource_id))
                report = {"reason": "CATALOG_REQUIRED"}
        except ObjectResolutionError as exc:
            report = {"reason": str(exc)}
            status = "UNRESOLVED"
        canonical = canonical_object_key(key) if key is not None else None
        output.append(
            ResolvedObjectReference(
                reference=reference,
                tenant_id=int(tenant_id),
                datasource_id=int(datasource_id),
                physical_schema_hash=current_hash,
                status=status,
                canonical_key=canonical,
                report=report,
                checked_at=datetime.utcnow(),
            )
        )
    return output


def _projected_reference(reference: ProjectedObjectReference | object) -> ProjectedObjectReference:
    if isinstance(reference, ProjectedObjectReference):
        return reference
    object_type = str(getattr(getattr(reference, "object_type", None), "value", getattr(reference, "object_type", "")))
    source_kind = str(getattr(getattr(reference, "source_kind", None), "value", getattr(reference, "source_kind", "")))
    return ProjectedObjectReference(
        object_type=object_type,
        declared_path=DeclaredObjectPath(
            object_type=object_type,
            catalog=getattr(reference, "catalog_name", None),
            schema=getattr(reference, "schema_name", None),
            table=getattr(reference, "table_name", None),
            field=getattr(reference, "field_name", None),
            json_path=getattr(reference, "json_path", None),
            event_name=getattr(reference, "event_name", None),
            event_property_key=getattr(reference, "event_property_key", None),
        ),
        declared_key=str(getattr(reference, "declared_key", "")),
        source_kind=source_kind,
        datasource_id=getattr(reference, "datasource_id", None),
        resolution_status=str(
            getattr(
                getattr(reference, "resolution_status", None),
                "value",
                getattr(reference, "resolution_status", "UNRESOLVED"),
            )
        ),
    )


def _resolve_with_session(
    session: Session,
    *,
    path: DeclaredObjectPath,
    tenant_id: int,
    datasource_id: int,
) -> tuple[SemanticObjectKey | None, str, dict[str, Any]]:
    datasource = session.execute(
        select(CoreDatasource.type, CoreDatasource.catalog_complete).where(
            CoreDatasource.id == int(datasource_id)
        )
    ).one_or_none()
    if datasource is None or not datasource.catalog_complete:
        return None, "UNRESOLVED", {"reason": "CATALOG_INCOMPLETE"}
    if path.object_type == "TABLE":
        result = resolve_table_key(session, datasource_id=datasource_id, declared=path)
        if result.status is ObjectResolutionStatus.AMBIGUOUS:
            return None, "AMBIGUOUS", {"message": result.message or "表对象存在多个匹配。"}
        if result.status is not ObjectResolutionStatus.RESOLVED or result.key is None:
            return None, "UNRESOLVED", {"message": result.message or "表对象不存在。"}
        return result.key, "RESOLVED", {}
    if path.object_type == "SCHEMA":
        schema_key = normalize_catalog_identifier(path.schema, dialect=str(datasource.type or ""))
        found = session.exec(
            select(CoreTable.id).where(
                CoreTable.ds_id == int(datasource_id),
                CoreTable.checked.is_(True),
                CoreTable.schema_key == schema_key,
            )
        ).first()
        if found is None:
            return None, "UNRESOLVED", {"message": "Schema 在当前数据源中不存在。"}
        return SemanticObjectKey(
            object_type="SCHEMA",
            tenant_id=int(tenant_id),
            datasource_id=int(datasource_id),
            catalog=path.catalog,
            schema=schema_key,
        ), "RESOLVED", {}
    table_key, table_row = _resolve_table_row(
        session,
        datasource_id=datasource_id,
        path=path,
        dialect=str(datasource.type or ""),
    )
    if table_key is None or table_row is None:
        return None, "UNRESOLVED", {"message": "对象所属物理表不存在。"}
    common = {
        "tenant_id": int(tenant_id),
        "datasource_id": int(datasource_id),
        "catalog": table_key.catalog,
        "schema": table_key.schema,
        "table": table_key.table,
    }
    if path.object_type == "SCHEMA":
        return SemanticObjectKey(object_type="SCHEMA", **common), "RESOLVED", {}
    if path.object_type in {"FIELD", "JSON_PATH", "EVENT", "EVENT_PROPERTY"}:
        if path.field and not _field_exists(session, datasource_id, int(table_row.id), path.field, str(datasource.type or "")):
            return None, "UNRESOLVED", {"message": "对象字段不存在。"}
    return SemanticObjectKey(
        object_type=path.object_type,
        field=path.field,
        json_path=path.json_path,
        event_name=path.event_name,
        event_property_key=path.event_property_key,
        **common,
    ), "RESOLVED", {}


def _resolve_table_row(
    session: Session,
    *,
    datasource_id: int,
    path: DeclaredObjectPath,
    dialect: str,
) -> tuple[SemanticObjectKey | None, CoreTable | None]:
    table_key = normalize_catalog_identifier(path.table, dialect=dialect)
    statement = select(CoreTable).where(
        CoreTable.ds_id == int(datasource_id),
        CoreTable.checked.is_(True),
        CoreTable.table_key == table_key,
    )
    if path.catalog is not None:
        statement = statement.where(
            CoreTable.catalog_key == normalize_catalog_identifier(path.catalog, dialect=dialect)
        )
    if path.schema is not None:
        statement = statement.where(
            CoreTable.schema_key == normalize_catalog_identifier(path.schema, dialect=dialect)
        )
    rows = session.exec(statement).all()
    if len(rows) != 1:
        return None, None
    row = rows[0]
    return (
        SemanticObjectKey(
            object_type="TABLE",
            tenant_id=0,
            datasource_id=int(datasource_id),
            catalog=row.catalog_key,
            schema=row.schema_key,
            table=row.table_key,
        ),
        row,
    )


def _field_exists(session: Session, datasource_id: int, table_id: int, field: str, dialect: str) -> bool:
    field_key = normalize_catalog_identifier(field, dialect=dialect)
    return session.exec(
        select(CoreField.id).where(
            CoreField.ds_id == int(datasource_id),
            CoreField.table_id == int(table_id),
            CoreField.checked.is_(True),
            CoreField.field_key == field_key,
        )
    ).first() is not None


def _resolve_with_catalog(
    path: DeclaredObjectPath,
    *,
    tenant_id: int,
    datasource_id: int,
    catalog: Mapping[str, object],
) -> tuple[SemanticObjectKey | None, str, dict[str, Any]]:
    """Resolve against a small canonical-key fixture used by tests/tools."""
    candidates = catalog.get(path.object_type) or catalog.get("objects") or ()
    if isinstance(candidates, Mapping):
        candidates = candidates.values()
    matched: list[DeclaredObjectPath] = []
    for candidate in candidates if isinstance(candidates, Iterable) and not isinstance(candidates, (str, bytes)) else ():
        declared = _as_declared_path(candidate)
        if declared is not None and _matches_path(declared, path):
            matched.append(declared)
    if len(matched) > 1:
        return None, "AMBIGUOUS", {"message": "对象存在多个匹配。"}
    if not matched:
        return None, "UNRESOLVED", {"message": "对象在当前数据源中不存在。"}
    selected = matched[0]
    return (
        SemanticObjectKey(
            object_type=selected.object_type,
            tenant_id=int(tenant_id),
            datasource_id=int(datasource_id),
            catalog=selected.catalog,
            schema=selected.schema,
            table=selected.table,
            field=selected.field,
            json_path=selected.json_path,
            event_name=selected.event_name,
            event_property_key=selected.event_property_key,
        ),
        "RESOLVED",
        {},
    )


def _as_declared_path(value: object) -> DeclaredObjectPath | None:
    if isinstance(value, DeclaredObjectPath):
        return value
    if isinstance(value, Mapping) and value.get("object_type"):
        return DeclaredObjectPath(
            object_type=value["object_type"],
            catalog=value.get("catalog"),
            schema=value.get("schema") or value.get("schema_name"),
            table=value.get("table") or value.get("table_name"),
            field=value.get("field") or value.get("field_name"),
            json_path=value.get("json_path"),
            event_name=value.get("event_name"),
            event_property_key=value.get("event_property_key"),
        )
    return None


def _matches_path(left: DeclaredObjectPath, right: DeclaredObjectPath) -> bool:
    values = ("object_type", "catalog", "schema", "table", "field", "json_path", "event_name", "event_property_key")
    return all(
        str(getattr(left, name) or "").strip().casefold() == str(getattr(right, name) or "").strip().casefold()
        for name in values
    )


def _contextual_candidate(
    path: DeclaredObjectPath,
    *,
    tenant_id: int,
    datasource_id: int,
) -> SemanticObjectKey:
    return SemanticObjectKey(
        object_type=path.object_type,
        tenant_id=int(tenant_id),
        datasource_id=int(datasource_id),
        catalog=path.catalog,
        schema=path.schema,
        table=path.table,
        field=path.field,
        json_path=path.json_path,
        event_name=path.event_name,
        event_property_key=path.event_property_key,
    )
