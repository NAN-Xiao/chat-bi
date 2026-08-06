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

import sqlglot

from apps.datasource.crud.semantic_object_key import DeclaredObjectPath
from apps.knowledge_base.errors import KnowledgeBusinessError
from apps.knowledge_base.object_sql import (
    SqlObjectExtractionError,
    extract_sql_object_paths,
)
from apps.knowledge_base.schemas import (
    BusinessKnowledgePayload,
    DocumentPayload,
    EventKnowledgePayload,
    JsonFieldKnowledgePayload,
    KnowledgePayload,
    SemanticObjectReferenceInput,
)
from common.sql_json_paths import extract_json_accesses, normalize_json_path

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
    if isinstance(payload, DocumentPayload):
        references = _document_references(payload, resolved_context)
    elif isinstance(payload, BusinessKnowledgePayload):
        references = _business_references(payload, resolved_context)
    elif isinstance(payload, EventKnowledgePayload):
        references = _event_references(payload, resolved_context)
    elif isinstance(payload, JsonFieldKnowledgePayload):
        references = _json_field_references(payload, resolved_context)
    else:
        raise ObjectReferenceValidationError(
            code="KNOWLEDGE_PAYLOAD_INVALID",
            message="知识类型不支持对象引用投影。",
        )
    return _deduplicate(references)


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
    if isinstance(payload, DocumentPayload):
        blocks = _SQL_BLOCK.findall(chunk_text)
        references = _explicit_references(payload.object_references, resolved_context, "EXPLICIT")
        references.extend(_sql_references(blocks, resolved_context, source_kind="SQL_AST"))
        return _deduplicate(references)
    return project_version_references(payload, resolved_context)


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


def _business_references(payload: BusinessKnowledgePayload, context: ReferenceProjectionContext) -> list[ProjectedObjectReference]:
    references = _explicit_references(payload.related_objects, context, "EXPLICIT")
    for index, example in enumerate(payload.examples):
        ast_references = _sql_references(
            [example.sql],
            context,
            source_kind="SQL_AST",
            dialect=example.dialect or context.dialect,
        )
        _assert_ast_subset_of_explicit(
            ast_references,
            references,
            field_path=f"examples[{index}].sql",
        )
        references.extend(ast_references)
    return _deduplicate(references)


def _event_references(payload: EventKnowledgePayload, context: ReferenceProjectionContext) -> list[ProjectedObjectReference]:
    table = DeclaredObjectPath(object_type="TABLE", table=payload.table_name)
    references = [_project(table, context, "STRUCTURED_PAYLOAD")]
    fields = [payload.event_name_field, payload.event_time_field]
    fields.extend(parameter.name for parameter in payload.parameters)
    for field in fields:
        if field:
            references.append(
                _project(
                    DeclaredObjectPath(object_type="FIELD", table=payload.table_name, field=field),
                    context,
                    "STRUCTURED_PAYLOAD",
                )
            )
    references.append(
        _project(
            DeclaredObjectPath(
                object_type="EVENT",
                table=payload.table_name,
                field=payload.event_name_field,
                event_name=payload.event_name,
            ),
            context,
            "STRUCTURED_PAYLOAD",
        )
    )
    for parameter in payload.parameters:
        references.append(
            _project(
                DeclaredObjectPath(
                    object_type="EVENT_PROPERTY",
                    table=payload.table_name,
                    field=parameter.name,
                    event_name=payload.event_name,
                    event_property_key=parameter.name,
                ),
                context,
                "STRUCTURED_PAYLOAD",
            )
        )
    return references


def _json_field_references(payload: JsonFieldKnowledgePayload, context: ReferenceProjectionContext) -> list[ProjectedObjectReference]:
    base = {
        "schema": payload.schema_name,
        "table": payload.table_name,
    }
    references = [
        _project(DeclaredObjectPath(object_type="TABLE", **base), context, "STRUCTURED_PAYLOAD"),
        _project(DeclaredObjectPath(object_type="FIELD", field=payload.source_field, **base), context, "STRUCTURED_PAYLOAD"),
        _project(DeclaredObjectPath(object_type="JSON_PATH", field=payload.source_field, json_path=normalize_json_path(payload.json_path), **base), context, "STRUCTURED_PAYLOAD"),
    ]
    try:
        statement = sqlglot.parse_one(f"SELECT {payload.expression}", read=context.dialect)
        extraction = extract_json_accesses(statement, dialect=context.dialect)
    except Exception as exc:
        raise ObjectReferenceValidationError(
            code="KNOWLEDGE_JSON_EXPRESSION_REFERENCE_MISMATCH",
            message="JSON 表达式与声明的宿主字段或 JSON Path 不一致。",
            field_path="expression",
        ) from exc
    expected_path = references[-1].declared_path
    if extraction.issues or not any(
        access.source_field.casefold() == str(payload.source_field).casefold()
        and normalize_json_path(access.json_path) == normalize_json_path(payload.json_path)
        for access in extraction.accesses
    ):
        raise ObjectReferenceValidationError(
            code="KNOWLEDGE_JSON_EXPRESSION_REFERENCE_MISMATCH",
            message="JSON 表达式与声明的宿主字段或 JSON Path 不一致。",
            field_path="expression",
        )
    ast_references = [_project(expected_path, context, "SQL_AST")]
    return _deduplicate([*references, *ast_references])


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
    explicit_keys = {item.declared_key for item in explicit}
    for reference in ast:
        if reference.declared_key not in explicit_keys:
            raise ObjectReferenceValidationError(
                code="KNOWLEDGE_UNDECLARED_OBJECT_REFERENCE",
                message="SQL 实际引用的对象未在知识声明中登记。",
                field_path=field_path,
            )


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
