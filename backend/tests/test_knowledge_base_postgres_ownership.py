"""Verify active-draft and version-ownership constraints on PostgreSQL."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.knowledge_migration_support import (
    IsolatedMigrationDatabase,
    migration_database_fixture,  # noqa: F401
)


def test_second_active_draft_is_rejected(
    migrated_database: IsolatedMigrationDatabase,
) -> None:
    with pytest.raises(IntegrityError):
        with migrated_database.engine.begin() as connection:
            knowledge_id = connection.execute(
                text(
                    "INSERT INTO knowledge_base (tenant_id, name) "
                    "VALUES (93001, :name) RETURNING id"
                ),
                {"name": f"draft-{uuid4().hex}"},
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO knowledge_base_version "
                    "(knowledge_base_id, tenant_id, version_number, status) "
                    "VALUES (:knowledge_id, 93001, 1, 'DRAFT')"
                ),
                {"knowledge_id": knowledge_id},
            )
            connection.execute(
                text(
                    "INSERT INTO knowledge_base_version "
                    "(knowledge_base_id, tenant_id, version_number, status) "
                    "VALUES (:knowledge_id, 93001, 2, 'VALIDATING')"
                ),
                {"knowledge_id": knowledge_id},
            )


def test_chunk_cannot_reference_version_from_another_tenant(
    migrated_database: IsolatedMigrationDatabase,
) -> None:
    with migrated_database.engine.begin() as connection:
        knowledge_id = connection.execute(
            text(
                "INSERT INTO knowledge_base (tenant_id, name) "
                "VALUES (93002, :name) RETURNING id"
            ),
            {"name": f"owner-{uuid4().hex}"},
        ).scalar_one()
        version_id = connection.execute(
            text(
                "INSERT INTO knowledge_base_version "
                "(knowledge_base_id, tenant_id, version_number, status) "
                "VALUES (:knowledge_id, 93002, 1, 'PUBLISHED') RETURNING id"
            ),
            {"knowledge_id": knowledge_id},
        ).scalar_one()

    with pytest.raises(IntegrityError):
        with migrated_database.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO knowledge_base_chunk "
                    "(knowledge_base_id, version_id, tenant_id, visibility_scope, "
                    "chunk_index, content, content_hash) "
                    "VALUES (:knowledge_id, :version_id, 93003, 'ADMIN_PUBLIC', "
                    "0, 'cross-tenant', :content_hash)"
                ),
                {
                    "knowledge_id": knowledge_id,
                    "version_id": version_id,
                    "content_hash": "b" * 64,
                },
            )
