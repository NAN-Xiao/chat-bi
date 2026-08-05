"""Verify canonical catalog columns and deterministic revision 155 DDL."""

from __future__ import annotations

import importlib.util
import inspect
from io import StringIO
from pathlib import Path
from types import ModuleType, SimpleNamespace

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import CheckConstraint, UniqueConstraint

from apps.datasource.crud.semantic_object_key import (
    SemanticObjectKey,
    canonical_object_key,
    normalize_catalog_identifier,
    normalized_table_identity,
    physical_schema_hash,
)
from apps.datasource.models.datasource import CoreDatasource, CoreField, CoreTable

MIGRATION_FILENAME = "155_semantic_permission_epoch.py"


def _constraint(table, name: str, constraint_type):
    return next(
        constraint
        for constraint in table.constraints
        if constraint.name == name and isinstance(constraint, constraint_type)
    )


def _load_migration() -> ModuleType:
    module_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / MIGRATION_FILENAME
    )
    spec = importlib.util.spec_from_file_location(module_path.stem, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _offline_sql(module: ModuleType, operation: str) -> str:
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    module.op = Operations(context)
    getattr(module, operation)()
    return output.getvalue()


def test_catalog_keys_are_non_null_and_unique() -> None:
    table_columns = CoreTable.__table__.columns
    for name in ("catalog_key", "schema_key", "table_key"):
        assert table_columns[name].nullable is False
    assert "catalog_name" in table_columns
    assert "schema_name" in table_columns

    table_identity = _constraint(
        CoreTable.__table__,
        "uq_core_table_full_identity",
        UniqueConstraint,
    )
    assert [column.name for column in table_identity.columns] == [
        "ds_id",
        "catalog_key",
        "schema_key",
        "table_key",
    ]

    field_columns = CoreField.__table__.columns
    assert field_columns["field_key"].nullable is False
    field_identity = _constraint(
        CoreField.__table__,
        "uq_core_field_full_identity",
        UniqueConstraint,
    )
    assert [column.name for column in field_identity.columns] == [
        "table_id",
        "field_key",
    ]


def test_datasource_exposes_catalog_completeness_and_schema_hash() -> None:
    columns = CoreDatasource.__table__.columns
    assert columns["catalog_complete"].nullable is False
    assert "catalog_incomplete_reason" in columns
    assert columns["physical_schema_hash"].type.length == 64
    completeness = _constraint(
        CoreDatasource.__table__,
        "ck_core_datasource_catalog_complete_hash",
        CheckConstraint,
    )
    expression = str(completeness.sqltext)
    assert "catalog_complete = false" in expression
    assert "physical_schema_hash IS NOT NULL" in expression


def test_catalog_revision_is_linear_and_offline_safe() -> None:
    module = _load_migration()
    assert module.revision == "155semanticpermepoch"
    assert module.down_revision == "154knowledgeretrieval"
    source = inspect.getsource(module)
    for forbidden in (
        "aes_decrypt",
        "json.loads",
        "EmbeddingModelCache",
        "get_redis_client",
        "AppFileUtils",
        "open(",
    ):
        assert forbidden not in source


def test_catalog_upgrade_backfills_without_inventing_schema() -> None:
    sql = _offline_sql(_load_migration(), "upgrade")

    for column in ("catalog_key", "schema_key", "table_key"):
        assert f"ADD COLUMN {column}" in sql
        assert f"ALTER COLUMN {column} SET NOT NULL" in sql
    assert "ADD COLUMN field_key" in sql
    assert "ALTER COLUMN field_key SET NOT NULL" in sql
    assert "UNIQUE (ds_id, catalog_key, schema_key, table_key)" in sql
    assert "UNIQUE (table_id, field_key)" in sql
    assert "catalog_complete = false" in sql
    assert "LEGACY_CATALOG_REQUIRES_REFRESH" in sql
    assert "dbSchema" not in sql
    assert "LOWER(" not in sql
    assert "CONCAT('__legacy_schema__:', id)" in sql
    assert "CREATE TRIGGER trg_core_table_legacy_catalog_keys" in sql
    assert "CREATE TRIGGER trg_core_field_legacy_catalog_keys" in sql
    assert "CREATE TRIGGER trg_core_table_catalog_invalidation" in sql
    assert "CREATE TRIGGER trg_core_field_catalog_invalidation" in sql
    assert "LEGACY_WRITE_REQUIRES_REFRESH" not in sql


def test_catalog_invalidation_ignores_metadata_only_updates() -> None:
    sql = _offline_sql(_load_migration(), "upgrade")
    normalized_sql = " ".join(sql.split())

    assert (
        "AFTER INSERT OR DELETE OR UPDATE OF ds_id, catalog_name, schema_name, "
        "catalog_key, schema_key, table_name, table_key ON core_table"
    ) in normalized_sql
    assert (
        "AFTER INSERT OR DELETE OR UPDATE OF ds_id, table_id, field_name, "
        "field_type, field_key ON core_field"
    ) in normalized_sql
    assert "AFTER INSERT OR UPDATE OR DELETE ON core_table" not in normalized_sql
    assert "AFTER INSERT OR UPDATE OR DELETE ON core_field" not in normalized_sql


def test_catalog_downgrade_removes_new_contracts() -> None:
    sql = _offline_sql(_load_migration(), "downgrade")

    assert "DROP TABLE semantic_scope_epoch" in sql
    for column in (
        "physical_schema_hash",
        "catalog_incomplete_reason",
        "catalog_complete",
    ):
        assert f"DROP COLUMN {column}" in sql
    for column in ("table_key", "schema_key", "catalog_key", "schema_name", "catalog_name"):
        assert f"DROP COLUMN {column}" in sql
    assert "DROP COLUMN field_key" in sql


def test_same_table_name_in_two_schemas_has_distinct_keys() -> None:
    left = SemanticObjectKey(
        object_type="TABLE",
        tenant_id=2,
        datasource_id=9,
        schema="public",
        table="orders",
    )
    right = SemanticObjectKey(
        object_type="TABLE",
        tenant_id=2,
        datasource_id=9,
        schema="archive",
        table="orders",
    )

    assert canonical_object_key(left) != canonical_object_key(right)


def test_identifier_normalization_follows_dialect_quoting_rules() -> None:
    assert normalize_catalog_identifier("Orders", dialect="postgres") == "orders"
    assert normalize_catalog_identifier('"Orders"', dialect="postgres") == "Orders"
    assert normalize_catalog_identifier("orders", dialect="oracle") == "ORDERS"
    assert normalize_catalog_identifier("`Orders`", dialect="mysql") == "orders"


def test_physical_schema_hash_is_order_stable_and_type_sensitive() -> None:
    table = SimpleNamespace(
        id=1,
        catalog_key="",
        schema_key="public",
        table_key="orders",
    )
    amount = SimpleNamespace(table_id=1, field_key="amount", field_type="numeric")
    created = SimpleNamespace(table_id=1, field_key="created_at", field_type="timestamp")

    first = physical_schema_hash([table], [amount, created])
    reordered = physical_schema_hash([table], [created, amount])
    changed = physical_schema_hash(
        [table],
        [SimpleNamespace(table_id=1, field_key="amount", field_type="text"), created],
    )

    assert first == reordered
    assert len(first) == 64
    assert changed != first


def test_catalog_identity_uses_configured_postgres_schema() -> None:
    identity = normalized_table_identity(
        datasource_type="pg",
        configuration={"database": "app", "dbSchema": "analytics"},
        table_name="Orders",
    )

    assert identity.catalog_name is None
    assert identity.schema_name == "analytics"
    assert identity.catalog_key == ""
    assert identity.schema_key == "analytics"
    assert identity.table_key == "Orders"
    assert identity.complete is True


def test_catalog_identity_does_not_invent_required_schema() -> None:
    identity = normalized_table_identity(
        datasource_type="oracle",
        configuration={"database": "app", "dbSchema": ""},
        table_name="ORDERS",
    )

    assert identity.schema_name is None
    assert identity.schema_key == ""
    assert identity.complete is False
    assert identity.incomplete_reason == "CATALOG_SCHEMA_REQUIRED"
