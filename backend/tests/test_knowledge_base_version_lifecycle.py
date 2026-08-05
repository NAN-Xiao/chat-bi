"""Verify lifecycle migration metadata and PostgreSQL DDL invariants."""

from __future__ import annotations

import importlib.util
import inspect
from io import StringIO
from pathlib import Path
from types import ModuleType

from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION_FILENAME = "153_knowledge_base_version_lifecycle.py"


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


def test_lifecycle_revision_is_linear_and_offline_safe() -> None:
    module = _load_migration()
    assert module.revision == "153knowledgeversion"
    assert module.down_revision == "152platformsqlaliasquote"
    source = inspect.getsource(module)
    for forbidden in ("EmbeddingModelCache", "get_redis_client", "AppFileUtils", "open("):
        assert forbidden not in source


def test_lifecycle_upgrade_contains_deferred_pointer_guards() -> None:
    sql = _offline_sql(_load_migration(), "upgrade")

    assert "CREATE TABLE knowledge_base_version" in sql
    assert "CREATE TABLE knowledge_publish_job" in sql
    assert "CREATE TABLE knowledge_migration_state" in sql
    assert "CREATE TABLE knowledge_storage_probe" in sql
    assert "CREATE TABLE knowledge_storage_probe_receipt" in sql
    assert "UNIQUE (knowledge_base_id, tenant_id, id)" in sql
    assert sql.count("DEFERRABLE INITIALLY DEFERRED") >= 3
    assert "CREATE UNIQUE INDEX uq_knowledge_base_version_active_draft" in sql
    assert "CREATE UNIQUE INDEX uq_knowledge_publish_job_active_knowledge_base" in sql
    assert "CREATE CONSTRAINT TRIGGER trg_knowledge_base_pointer_state" in sql
    assert "CREATE CONSTRAINT TRIGGER trg_knowledge_base_version_pointer_state" in sql
    assert "DEFERRABLE INITIALLY DEFERRED" in sql
    assert "FOR UPDATE" in sql
    assert "kb.id = target_knowledge_base_id" in sql
    assert "INSERT INTO knowledge_migration_state" in sql
    assert "'LEGACY_OPEN'" in sql
    for column in (
        "knowledge_type",
        "stable_key",
        "archived",
        "update_by",
        "publish_by",
        "publish_time",
    ):
        assert f"ADD COLUMN {column}" in sql
    assert "UNIQUE (tenant_id, visibility_scope, stable_key)" in sql


def test_lifecycle_downgrade_reverses_upgrade_objects() -> None:
    sql = _offline_sql(_load_migration(), "downgrade")

    assert "DROP TRIGGER IF EXISTS trg_knowledge_base_version_pointer_state" in sql
    assert "DROP TRIGGER IF EXISTS trg_knowledge_base_pointer_state" in sql
    assert "DROP FUNCTION IF EXISTS enforce_knowledge_base_pointer_states" in sql
    for table in (
        "knowledge_storage_probe_receipt",
        "knowledge_storage_probe",
        "knowledge_migration_state",
        "knowledge_publish_job",
        "knowledge_base_version",
    ):
        assert f"DROP TABLE {table}" in sql
    for pointer in ("publishing_version_id", "current_version_id", "draft_version_id"):
        assert f"DROP COLUMN {pointer}" in sql
    for column in (
        "publish_time",
        "publish_by",
        "update_by",
        "archived",
        "stable_key",
        "knowledge_type",
    ):
        assert f"DROP COLUMN {column}" in sql
