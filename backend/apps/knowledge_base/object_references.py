"""Build immutable semantic-object references from knowledge payloads.

The projector deliberately stores declarations, not user permissions.  Platform
knowledge therefore remains datasource-neutral until ``object_resolution`` is
called for a consuming workspace.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from apps.datasource.crud.semantic_object_key import DeclaredObjectPath
from apps.knowledge_base.errors import KnowledgeBusinessError
from apps.knowledge_base.object_sql import (
    SqlObjectExtractionError,
    extract_sql_object_paths,
)
from apps.knowledge_base.schemas import (
    DocumentPayload,
    KnowledgePayload,
    SemanticObjectReferenceInput,
)
from common.sql_json_paths import normalize_json_path

_SQL_BLOCK = re.compile(r"```sql\s*\n(.*?)```", re.IGNORECASE | re.DOTALL)


class ObjectReferenceValidationError(KnowledgeBusinessError):
    """A safe, user-visible error raised when a declaration is incomplete."""

    def __init__(self, *, code: str, message: str, field_path: str | None = None):
        super().__init__(
            code=code,
            message=message,
            status_code=400,
            field_path=field_path,
            error_type="VALIDATION",
        )


@dataclass(frozen=True)
class ReferenceProjectionContext:
    tenant_id: int | None = None
    datasource_id: int | None = None
    dialect: str = "postgres"
    scope: str = "WORKSPACE"


@dataclass(frozen=True)
class ProjectedObjectReference:
    """The in-memory shape used before rows are persisted."""

    object_type: str
    declared_path: DeclaredObjectPath
    declared_key: str
    source_kind: str
    datasource_id: int | None = None
    resolution_status: str = "UNRESOLVED"

    @property
    def catalog_name(self) -> str | None:
        return self.declared_path.catalog

    @property
    def schema_name(self) -> str | None:
        return self.declared_path.schema

    @property
    def table_name(self) -> str | None:
        return self.declared_path.table

    @property
    def field_name(self) -> str | None:
        return self.declared_path.field

    @property
    def json_path(self) -> str | None:
        return self.declared_path.json_path

    @property
    def event_name(self) -> str | None:
        return self.declared_path.event_name

    @property
    def event_property_key(self) -> str | None:
        return self.declared_path.event_property_key


def project_version_references(
    payload: KnowledgePayload,
    context: ReferenceProjectionContext | Mapping[str, object] | None = None,
    *,
    projection_context: ReferenceProjectionContext | Mapping[str, object] | None = None,
) -> list[ProjectedObjectReference]:
    """Project all explicit and AST references for one immutable version."""
    resolved_context = _context(context or projection_context)
    return _deduplicate(_document_references(payload, resolved_context))


def project_chunk_references(
    payload: KnowledgePayload,
    context: ReferenceProjectionContext | Mapping[str, object] | None = None,
    *,
    chunk_text: str | None = None,
    projection_context: ReferenceProjectionContext | Mapping[str, object] | None = None,
) -> list[ProjectedObjectReference]:
    """Project references for a chunk, inheriting version declarations by default."""
    resolved_context = _context(context or projection_context)
    if not chunk_text:
        return project_version_references(payload, resolved_context)
    blocks = _SQL_BLOCK.findall(chunk_text)
    references = _explicit_references(payload.object_references, resolved_context, "EXPLICIT")
    references.extend(_sql_references(blocks, resolved_context, source_kind="SQL_AST"))
    return _deduplicate(references)


def _context(value: ReferenceProjectionContext | Mapping[str, object] | None) -> ReferenceProjectionContext:
    if value is None:
        return ReferenceProjectionContext()
    if isinstance(value, ReferenceProjectionContext):
        return value
    return ReferenceProjectionContext(
        tenant_id=int(value["tenant_id"]) if value.get("tenant_id") is not None else None,
        datasource_id=int(value["datasource_id"]) if value.get("datasource_id") is not None else None,
        dialect=str(value.get("dialect") or "postgres"),
        scope=str(value.get("scope") or "WORKSPACE"),
    )


def _document_references(payload: DocumentPayload, context: ReferenceProjectionContext) -> list[ProjectedObjectReference]:
    references = _explicit_references(payload.object_references, context, "EXPLICIT")
    blocks = _SQL_BLOCK.findall(payload.markdown)
    if blocks:
        if payload.datasource_neutral:
            raise ObjectReferenceValidationError(
                code="KNOWLEDGE_DOCUMENT_NOT_NEUTRAL",
                message="数据源无关文档不能包含 SQL。",
                field_path="markdown",
            )
        references.extend(_sql_references(blocks, context, source_kind="SQL_AST"))
    return _assert_sql_objects_declared(references)


def _explicit_references(
    values: Iterable[SemanticObjectReferenceInput],
    context: ReferenceProjectionContext,
    source_kind: str,
) -> list[ProjectedObjectReference]:
    references: list[ProjectedObjectReference] = []
    for index, value in enumerate(values):
        path = value.as_declared_path()
        if not _path_complete(path):
            raise ObjectReferenceValidationError(
                code="KNOWLEDGE_OBJECT_REFERENCE_INCOMPLETE",
                message="对象引用声明不完整。",
                field_path=f"object_references[{index}]",
            )
        references.append(_project(path, context, source_kind))
    return references


def _sql_references(
    sql_values: Iterable[str],
    context: ReferenceProjectionContext,
    *,
    source_kind: str,
    dialect: str | None = None,
) -> list[ProjectedObjectReference]:
    references: list[ProjectedObjectReference] = []
    sql_dialect = dialect or context.dialect
    try:
        paths = extract_sql_object_paths(sql_values, dialect=sql_dialect)
    except SqlObjectExtractionError as exc:
        raise ObjectReferenceValidationError(code=exc.code, message=exc.message) from exc
    for path in paths:
        references.append(_project(path, context, source_kind))
    return references


def _assert_sql_objects_declared(
    explicit_and_ast: list[ProjectedObjectReference],
) -> list[ProjectedObjectReference]:
    explicit = [item for item in explicit_and_ast if item.source_kind == "EXPLICIT"]
    ast = [item for item in explicit_and_ast if item.source_kind == "SQL_AST"]
    _assert_ast_subset_of_explicit(ast, explicit, field_path="markdown")
    return _deduplicate(explicit_and_ast)


def _assert_ast_subset_of_explicit(
    ast: Iterable[ProjectedObjectReference],
    explicit: Iterable[ProjectedObjectReference],
    *,
    field_path: str,
) -> None:
    explicit_values = tuple(explicit)
    for reference in ast:
        if not any(_explicit_covers_ast(item, reference) for item in explicit_values):
            raise ObjectReferenceValidationError(
                code="KNOWLEDGE_UNDECLARED_OBJECT_REFERENCE",
                message="SQL 实际引用的对象未在知识声明中登记。",
                field_path=field_path,
            )


def _explicit_covers_ast(
    explicit: ProjectedObjectReference,
    ast: ProjectedObjectReference,
) -> bool:
    if explicit.declared_key == ast.declared_key:
        return True
    explicit_path = explicit.declared_path
    ast_path = ast.declared_path
    same_table = (
        _identifier(explicit_path.catalog) == _identifier(ast_path.catalog)
        and _identifier(explicit_path.schema) == _identifier(ast_path.schema)
        and _identifier(explicit_path.table) == _identifier(ast_path.table)
    )
    if not same_table:
        return False
    if explicit_path.object_type == "TABLE":
        return ast_path.object_type in {"TABLE", "FIELD", "JSON_PATH"}
    if explicit_path.object_type in {"FIELD", "JSON_PATH"}:
        return ast_path.object_type == "TABLE"
    return False


def _project(path: DeclaredObjectPath, context: ReferenceProjectionContext, source_kind: str) -> ProjectedObjectReference:
    return ProjectedObjectReference(
        object_type=path.object_type,
        declared_path=path,
        declared_key=_declared_key(path),
        source_kind=source_kind,
        datasource_id=context.datasource_id if context.scope != "PLATFORM_PUBLIC" else None,
    )


def _deduplicate(values: Iterable[ProjectedObjectReference]) -> list[ProjectedObjectReference]:
    result: list[ProjectedObjectReference] = []
    seen: set[tuple[str, str, str]] = set()
    for value in values:
        key = (value.declared_key, value.source_kind, value.object_type)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _declared_key(path: DeclaredObjectPath) -> str:
    values = dataclasses.asdict(path)
    normalized = {
        key: _identifier(value) if key != "json_path" else normalize_json_path(value)
        for key, value in values.items()
        if value is not None
    }
    encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _identifier(value: object) -> str:
    return str(value or "").strip().strip('`"[]').casefold()


def _path_complete(path: DeclaredObjectPath) -> bool:
    required = {
        "SCHEMA": path.schema,
        "TABLE": path.table,
        "FIELD": path.table and path.field,
        "JSON_PATH": path.table and path.field and path.json_path,
        "EVENT": path.table and path.event_name,
        "EVENT_PROPERTY": path.table and path.event_name and path.event_property_key,
    }
    return bool(required.get(path.object_type))


def _same_path(left: DeclaredObjectPath, right: DeclaredObjectPath) -> bool:
    return _declared_key(left) == _declared_key(right)
