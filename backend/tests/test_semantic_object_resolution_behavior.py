"""Behavioral tests for consuming-workspace object resolution."""

from __future__ import annotations

from apps.datasource.crud.semantic_object_key import DeclaredObjectPath
from apps.knowledge_base.object_references import ProjectedObjectReference
from apps.knowledge_base.object_resolution import resolve_references_for_context


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
