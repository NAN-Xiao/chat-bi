"""Verify retrieval, audit, and semantic-object projection schema contracts."""

from __future__ import annotations

import importlib.util
import inspect
from io import StringIO
from pathlib import Path
from types import ModuleType

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from apps.knowledge_base.audit_models import KnowledgeRetrievalLog, SemanticContextAudit
from apps.knowledge_base.object_projection_models import (
    DataSkillObjectProjection,
    SemanticObjectReference,
    SemanticObjectResolution,
)
from apps.knowledge_base.retrieval_models import (
    KnowledgeBaseApplicability,
    KnowledgeBaseChunk,
    KnowledgeBaseSourceReference,
    KnowledgeBaseWorkspaceOverride,
)

MIGRATION_FILENAME = "154_knowledge_base_retrieval_projection.py"


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


def test_projection_models_expose_expected_tables() -> None:
    assert KnowledgeBaseChunk.__tablename__ == "knowledge_base_chunk"
    assert KnowledgeBaseWorkspaceOverride.__tablename__ == (
        "knowledge_base_workspace_override"
    )
    assert KnowledgeBaseApplicability.__tablename__ == "knowledge_base_applicability"
    assert KnowledgeBaseSourceReference.__tablename__ == (
        "knowledge_base_source_reference"
    )
    assert KnowledgeRetrievalLog.__tablename__ == "knowledge_retrieval_log"
    assert SemanticContextAudit.__tablename__ == "semantic_context_audit"
    assert SemanticObjectReference.__tablename__ == "semantic_object_reference"
    assert SemanticObjectResolution.__tablename__ == "semantic_object_resolution"
    assert DataSkillObjectProjection.__tablename__ == "data_skill_object_projection"


def test_chunk_uses_composite_version_ownership_and_stable_order() -> None:
    owner = _constraint(
        KnowledgeBaseChunk.__table__,
        "fk_knowledge_base_chunk_version",
        ForeignKeyConstraint,
    )
    assert [column.name for column in owner.columns] == [
        "knowledge_base_id",
        "tenant_id",
        "version_id",
    ]
    assert [element.target_fullname for element in owner.elements] == [
        "knowledge_base_version.knowledge_base_id",
        "knowledge_base_version.tenant_id",
        "knowledge_base_version.id",
    ]

    ordering = _constraint(
        KnowledgeBaseChunk.__table__,
        "uq_knowledge_base_chunk_version_index",
        UniqueConstraint,
    )
    assert [column.name for column in ordering.columns] == [
        "version_id",
        "chunk_index",
    ]

    embedding = KnowledgeBaseChunk.__table__.columns["embedding"].type
    assert getattr(embedding, "dim", None) is None
    assert all(
        "hnsw" not in index.name.lower() and "ivfflat" not in index.name.lower()
        for index in KnowledgeBaseChunk.__table__.indexes
    )


def test_reference_owner_columns_are_exclusive() -> None:
    owner = _constraint(
        SemanticObjectReference.__table__,
        "ck_semantic_object_reference_owner",
        CheckConstraint,
    )
    expression = str(owner.sqltext)
    for owner_type in ("KNOWLEDGE_VERSION", "KNOWLEDGE_CHUNK", "DATA_SKILL"):
        assert owner_type in expression
    for column in ("version_id", "chunk_id", "skill_id"):
        assert column in expression

    uniqueness = _constraint(
        SemanticObjectReference.__table__,
        "uq_semantic_object_reference_owner_declared_source",
        UniqueConstraint,
    )
    assert [column.name for column in uniqueness.columns] == [
        "owner_type",
        "owner_id",
        "declared_key",
        "source_kind",
    ]


def test_resolution_canonical_key_matches_status() -> None:
    state = _constraint(
        SemanticObjectResolution.__table__,
        "ck_semantic_object_resolution_canonical_state",
        CheckConstraint,
    )
    expression = str(state.sqltext)
    assert "status = 'RESOLVED'" in expression
    assert "canonical_key IS NOT NULL" in expression
    assert "status <> 'RESOLVED'" in expression
    assert "canonical_key IS NULL" in expression

    uniqueness = _constraint(
        SemanticObjectResolution.__table__,
        "uq_semantic_object_resolution_context",
        UniqueConstraint,
    )
    assert [column.name for column in uniqueness.columns] == [
        "reference_id",
        "tenant_id",
        "datasource_id",
        "physical_schema_hash",
    ]


def test_projection_uniqueness_contracts() -> None:
    contracts = (
        (
            KnowledgeBaseWorkspaceOverride,
            "uq_knowledge_base_workspace_override_tenant_knowledge",
            ["tenant_id", "knowledge_base_id"],
        ),
        (
            KnowledgeBaseApplicability,
            "uq_knowledge_base_applicability_context",
            ["version_id", "tenant_id", "datasource_id", "physical_schema_hash"],
        ),
        (
            KnowledgeBaseSourceReference,
            "uq_knowledge_base_source_reference_version_source",
            ["version_id", "source_type", "source_id"],
        ),
        (
            DataSkillObjectProjection,
            "uq_data_skill_object_projection_skill",
            ["skill_id"],
        ),
    )
    for model, constraint_name, columns in contracts:
        constraint = _constraint(model.__table__, constraint_name, UniqueConstraint)
        assert [column.name for column in constraint.columns] == columns


def test_retrieval_audits_do_not_store_question_text() -> None:
    columns = set(KnowledgeRetrievalLog.__table__.columns.keys())
    assert "query_hash" in columns
    assert "query" not in columns
    assert "question" not in columns

    context_columns = set(SemanticContextAudit.__table__.columns.keys())
    assert {
        "permission_version",
        "schema_hash",
        "knowledge_snapshot",
        "skill_snapshot",
        "warnings",
    } <= context_columns
    assert "question" not in context_columns


def test_projection_revision_is_linear_and_offline_safe() -> None:
    module = _load_migration()
    assert module.revision == "154knowledgeretrieval"
    assert module.down_revision == "153knowledgeversion"
    source = inspect.getsource(module)
    for forbidden in (
        "EmbeddingModelCache",
        "get_redis_client",
        "AppFileUtils",
        "open(",
    ):
        assert forbidden not in source


def test_projection_upgrade_and_downgrade_cover_all_tables() -> None:
    module = _load_migration()
    upgrade_sql = _offline_sql(module, "upgrade")
    downgrade_sql = _offline_sql(_load_migration(), "downgrade")

    tables = (
        "knowledge_base_chunk",
        "knowledge_base_workspace_override",
        "knowledge_base_applicability",
        "knowledge_base_source_reference",
        "knowledge_retrieval_log",
        "semantic_context_audit",
        "semantic_object_reference",
        "semantic_object_resolution",
        "data_skill_object_projection",
    )
    for table in tables:
        assert f"CREATE TABLE {table}" in upgrade_sql
        assert f"DROP TABLE {table}" in downgrade_sql

    lowered = upgrade_sql.lower()
    assert "vector" in lowered
    assert "hnsw" not in lowered
    assert "ivfflat" not in lowered
