"""Behavioral tests for consuming-workspace object resolution."""

from __future__ import annotations

from types import SimpleNamespace

from apps.datasource.crud.semantic_object_key import DeclaredObjectPath
from apps.knowledge_base.object_references import ProjectedObjectReference
from apps.knowledge_base.object_projection_models import SemanticObjectReference
from apps.knowledge_base.object_resolution import (
    _resolve_table_row,
    resolve_references_for_context,
)


def test_platform_reference_resolves_independently_per_datasource() -> None:
    reference = ProjectedObjectReference(
        object_type="TABLE",
        declared_path=DeclaredObjectPath(object_type="TABLE", schema="public", table="orders"),
        declared_key="a" * 64,
        source_kind="EXPLICIT",
        datasource_id=None,
    )
    catalog = {
        "TABLE": [DeclaredObjectPath(object_type="TABLE", schema="public", table="orders")]
    }
    left = resolve_references_for_context(
        [reference], tenant_id=2, datasource_id=10, schema_hash="a" * 64, catalog=catalog
    )
    right = resolve_references_for_context(
        [reference], tenant_id=3, datasource_id=11, schema_hash="b" * 64, catalog=catalog
    )
    assert left[0].status == "RESOLVED"
    assert right[0].status == "RESOLVED"
    assert left[0].canonical_key != right[0].canonical_key


def test_missing_catalog_is_not_implicitly_eligible() -> None:
    reference = ProjectedObjectReference(
        object_type="TABLE",
        declared_path=DeclaredObjectPath(object_type="TABLE", schema="public", table="orders"),
        declared_key="a" * 64,
        source_kind="EXPLICIT",
    )
    result = resolve_references_for_context(
        [reference], tenant_id=2, datasource_id=10, schema_hash="a" * 64
    )
    assert result[0].status == "UNRESOLVED"
    assert result[0].canonical_key


def test_persisted_reference_row_is_resolved_like_projected_reference() -> None:
    reference = SemanticObjectReference(
        id=1,
        tenant_id=1,
        owner_type="KNOWLEDGE_VERSION",
        owner_id=7,
        knowledge_base_id=9,
        version_id=7,
        object_type="TABLE",
        schema_name="public",
        table_name="orders",
        declared_key="a" * 64,
        source_kind="EXPLICIT",
    )
    result = resolve_references_for_context(
        [reference],
        tenant_id=2,
        datasource_id=10,
        schema_hash="a" * 64,
        catalog={
            "TABLE": [DeclaredObjectPath(object_type="TABLE", schema="public", table="orders")]
        },
    )

    assert result[0].status == "RESOLVED"
    assert result[0].reference.schema_name == "public"
    assert result[0].reference.table_name == "orders"


def test_table_row_query_returns_core_table_model() -> None:
    class _Result:
        def all(self):
            return [
                SimpleNamespace(
                    id=7,
                    catalog_key="",
                    schema_key="public",
                    table_key="orders",
                )
            ]

    class _Session:
        def exec(self, statement):
            assert statement.__class__.__name__ == "SelectOfScalar"
            return _Result()

    key, row = _resolve_table_row(
        _Session(),
        datasource_id=10,
        path=DeclaredObjectPath(object_type="FIELD", schema="public", table="orders", field="amount"),
        dialect="postgresql",
    )

    assert row.id == 7
    assert key.catalog == ""
    assert key.schema == "public"
    assert key.table == "orders"
