"""Behavioral tests for immutable knowledge object projection."""

from __future__ import annotations

import pytest

from apps.datasource.crud.semantic_object_key import DeclaredObjectPath
from apps.knowledge_base.object_references import (
    ObjectReferenceValidationError,
    ReferenceProjectionContext,
    project_version_references,
)
from apps.knowledge_base.schemas import (
    BusinessKnowledgePayload,
    BusinessSqlExample,
    JsonFieldKnowledgePayload,
    SemanticObjectReferenceInput,
)


def _table(schema: str, name: str) -> SemanticObjectReferenceInput:
    return SemanticObjectReferenceInput(object_type="TABLE", schema=schema, table=name)


def test_business_sql_extra_reference_blocks_projection() -> None:
    payload = BusinessKnowledgePayload(
        knowledge_type="BUSINESS",
        term="收入",
        definition="订单金额总和",
        related_objects=[_table("public", "orders")],
        examples=[
            BusinessSqlExample(
                name="收入",
                question="收入是多少",
                sql="select * from secret.payments",
            )
        ],
    )
    with pytest.raises(ObjectReferenceValidationError) as error:
        project_version_references(payload, ReferenceProjectionContext(dialect="postgres"))
    assert error.value.code == "KNOWLEDGE_UNDECLARED_OBJECT_REFERENCE"


def test_json_field_projects_host_and_path_references() -> None:
    payload = JsonFieldKnowledgePayload(
        knowledge_type="JSON_FIELD",
        schema_name="public",
        table_name="orders",
        source_field="properties",
        json_path="$.channel",
        field_name="channel",
        data_type="string",
        expression="json_extract(properties, '$.channel')",
    )
    references = project_version_references(payload)
    assert {item.object_type for item in references} == {"TABLE", "FIELD", "JSON_PATH"}
    assert sum(item.source_kind == "SQL_AST" for item in references) == 1


def test_declared_key_is_datasource_neutral() -> None:
    path = DeclaredObjectPath(object_type="TABLE", schema="public", table="orders")
    left = project_version_references(
        BusinessKnowledgePayload(knowledge_type="BUSINESS", related_objects=[_table("public", "orders")]),
        ReferenceProjectionContext(datasource_id=10),
    )[0]
    right = project_version_references(
        BusinessKnowledgePayload(knowledge_type="BUSINESS", related_objects=[_table("public", "orders")]),
        ReferenceProjectionContext(datasource_id=11),
    )[0]
    assert left.declared_key == right.declared_key
    assert path.table == left.table_name
