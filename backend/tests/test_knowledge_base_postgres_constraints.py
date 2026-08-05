"""Verify knowledge and semantic constraints on real isolated PostgreSQL."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.knowledge_migration_support import (
    IsolatedMigrationDatabase,
    migration_database_fixture,  # noqa: F401
)


def test_current_pointer_rejects_draft_at_commit(
    migrated_database: IsolatedMigrationDatabase,
) -> None:
    connection = migrated_database.engine.connect()
    transaction = connection.begin()
    try:
        knowledge_id = connection.execute(
            text(
                "INSERT INTO knowledge_base (tenant_id, name) "
                "VALUES (:tenant_id, :name) RETURNING id"
            ),
            {"tenant_id": 91001, "name": f"invalid-{uuid4().hex}"},
        ).scalar_one()
        version_id = connection.execute(
            text(
                "INSERT INTO knowledge_base_version "
                "(knowledge_base_id, tenant_id, version_number, status) "
                "VALUES (:knowledge_id, :tenant_id, 1, 'DRAFT') RETURNING id"
            ),
            {"knowledge_id": knowledge_id, "tenant_id": 91001},
        ).scalar_one()
        connection.execute(
            text(
                "UPDATE knowledge_base SET current_version_id = :version_id "
                "WHERE id = :knowledge_id"
            ),
            {"knowledge_id": knowledge_id, "version_id": version_id},
        )

        with pytest.raises(IntegrityError, match="invalid final state"):
            transaction.commit()
    finally:
        if transaction.is_active:
            transaction.rollback()
        connection.close()


def test_current_pointer_accepts_published_final_state(
    migrated_database: IsolatedMigrationDatabase,
) -> None:
    with migrated_database.engine.begin() as connection:
        knowledge_id = connection.execute(
            text(
                "INSERT INTO knowledge_base (tenant_id, name) "
                "VALUES (:tenant_id, :name) RETURNING id"
            ),
            {"tenant_id": 91002, "name": f"valid-{uuid4().hex}"},
        ).scalar_one()
        version_id = connection.execute(
            text(
                "INSERT INTO knowledge_base_version "
                "(knowledge_base_id, tenant_id, version_number, status) "
                "VALUES (:knowledge_id, :tenant_id, 1, 'PUBLISHED') RETURNING id"
            ),
            {"knowledge_id": knowledge_id, "tenant_id": 91002},
        ).scalar_one()
        connection.execute(
            text(
                "UPDATE knowledge_base SET current_version_id = :version_id "
                "WHERE id = :knowledge_id"
            ),
            {"knowledge_id": knowledge_id, "version_id": version_id},
        )


def test_nullable_epoch_scope_is_unique(
    migrated_database: IsolatedMigrationDatabase,
) -> None:
    tenant_id = 92000 + int(uuid4().hex[:4], 16)
    with migrated_database.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO semantic_scope_epoch (scope_type, tenant_id) "
                "VALUES ('SCHEMA', :tenant_id)"
            ),
            {"tenant_id": tenant_id},
        )

    with pytest.raises(IntegrityError):
        with migrated_database.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO semantic_scope_epoch (scope_type, tenant_id) "
                    "VALUES ('SCHEMA', :tenant_id)"
                ),
                {"tenant_id": tenant_id},
            )


def test_metadata_only_update_preserves_catalog_hash(
    migrated_database: IsolatedMigrationDatabase,
) -> None:
    with migrated_database.engine.begin() as connection:
        datasource_id = connection.execute(
            text(
                "INSERT INTO core_datasource (name, type) "
                "VALUES (:name, 'PostgreSQL') RETURNING id"
            ),
            {"name": f"catalog-{uuid4().hex}"},
        ).scalar_one()
        table_id = connection.execute(
            text(
                "INSERT INTO core_table "
                "(ds_id, checked, table_name, catalog_key, schema_key, table_key) "
                "VALUES (:datasource_id, true, 'orders', '', 'public', 'orders') "
                "RETURNING id"
            ),
            {"datasource_id": datasource_id},
        ).scalar_one()
        connection.execute(
            text(
                "UPDATE core_datasource SET catalog_complete = true, "
                "catalog_incomplete_reason = NULL, physical_schema_hash = :hash "
                "WHERE id = :datasource_id"
            ),
            {"datasource_id": datasource_id, "hash": "a" * 64},
        )
        connection.execute(
            text("UPDATE core_table SET custom_comment = '展示备注' WHERE id = :id"),
            {"id": table_id},
        )
        state = connection.execute(
            text(
                "SELECT catalog_complete, physical_schema_hash "
                "FROM core_datasource WHERE id = :datasource_id"
            ),
            {"datasource_id": datasource_id},
        ).one()

    assert state == (True, "a" * 64)
