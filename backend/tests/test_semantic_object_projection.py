"""Behavioral tests for immutable knowledge object projection."""

from __future__ import annotations

import pytest

from apps.datasource.crud.semantic_object_key import DeclaredObjectPath
from apps.knowledge_base.object_references import (
    ObjectReferenceValidationError,
    ReferenceProjectionContext,
    project_version_references,
)
from apps.knowledge_base.schemas import DocumentPayload, SemanticObjectReferenceInput


def _table(schema: str, name: str) -> SemanticObjectReferenceInput:
    return SemanticObjectReferenceInput(object_type="TABLE", schema=schema, table=name)


def test_document_sql_extra_reference_blocks_projection() -> None:
    payload = DocumentPayload(
        knowledge_type="DOCUMENT",
        markdown="```sql\nselect * from secret.payments\n```",
        datasource_neutral=False,
        object_references=[_table("public", "orders")],
    )
    with pytest.raises(ObjectReferenceValidationError) as error:
        project_version_references(payload, ReferenceProjectionContext(dialect="postgres"))
    assert error.value.code == "KNOWLEDGE_UNDECLARED_OBJECT_REFERENCE"


def test_document_projects_explicit_table_field_and_json_path_references() -> None:
    payload = DocumentPayload(
        knowledge_type="DOCUMENT",
        markdown="JSON 渠道字段说明。",
        datasource_neutral=False,
        object_references=[
            {"object_type": "TABLE", "schema": "public", "table": "orders"},
            {
                "object_type": "FIELD",
                "schema": "public",
                "table": "orders",
                "field": "properties",
            },
            {
                "object_type": "JSON_PATH",
                "schema": "public",
                "table": "orders",
                "field": "properties",
                "json_path": "$.channel",
            },
        ],
    )
    references = project_version_references(payload)
    assert {item.object_type for item in references} == {"TABLE", "FIELD", "JSON_PATH"}
    assert all(item.source_kind == "EXPLICIT" for item in references)


def test_declared_key_is_datasource_neutral() -> None:
    path = DeclaredObjectPath(object_type="TABLE", schema="public", table="orders")
    payload = DocumentPayload(
        knowledge_type="DOCUMENT",
        markdown="订单说明。",
        datasource_neutral=False,
        object_references=[_table("public", "orders")],
    )
    left = project_version_references(payload, ReferenceProjectionContext(datasource_id=10))[0]
    right = project_version_references(payload, ReferenceProjectionContext(datasource_id=11))[0]
    assert left.declared_key == right.declared_key
    assert path.table == left.table_name
