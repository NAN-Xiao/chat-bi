"""Verify the knowledge-base lifecycle SQLModel contracts."""

from __future__ import annotations

import os
import subprocess
import sys

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from apps.knowledge_base.lifecycle_models import (
    KnowledgeBaseVersion,
    KnowledgeIndexStatus,
    KnowledgeMigrationPhase,
    KnowledgeMigrationState,
    KnowledgePublishJob,
    KnowledgeStorageProbe,
    KnowledgeStorageProbeReceipt,
    KnowledgeVersionStatus,
)
from apps.knowledge_base.models import KnowledgeBase


def _constraint(table, name: str, constraint_type):
    return next(
        constraint
        for constraint in table.constraints
        if constraint.name == name and isinstance(constraint, constraint_type)
    )


def test_lifecycle_enums_match_the_database_contract() -> None:
    assert [status.value for status in KnowledgeVersionStatus] == [
        "DRAFT",
        "VALIDATING",
        "VALIDATION_FAILED",
        "READY_TO_PUBLISH",
        "PUBLISHING",
        "PUBLISHED",
        "PUBLISH_FAILED",
        "SUPERSEDED",
        "ARCHIVED",
    ]
    assert [phase.value for phase in KnowledgeMigrationPhase] == [
        "LEGACY_OPEN",
        "CUTOVER_BARRIER",
        "V2_ACTIVE",
    ]
    assert [status.value for status in KnowledgeIndexStatus] == [
        "NOT_REQUIRED",
        "PENDING",
        "PROCESSING",
        "READY",
        "FAILED",
    ]


def test_lifecycle_models_have_composite_pointer_contracts() -> None:
    assert KnowledgeBaseVersion.__tablename__ == "knowledge_base_version"
    assert KnowledgePublishJob.__tablename__ == "knowledge_publish_job"
    assert KnowledgeMigrationState.__tablename__ == "knowledge_migration_state"
    assert KnowledgeStorageProbe.__tablename__ == "knowledge_storage_probe"
    assert KnowledgeStorageProbeReceipt.__tablename__ == "knowledge_storage_probe_receipt"

    version_unique = _constraint(
        KnowledgeBaseVersion.__table__,
        "uq_knowledge_base_version_knowledge_tenant_id",
        UniqueConstraint,
    )
    assert [column.name for column in version_unique.columns] == [
        "knowledge_base_id",
        "tenant_id",
        "id",
    ]

    for pointer in ("draft_version_id", "current_version_id", "publishing_version_id"):
        constraint = _constraint(
            KnowledgeBase.__table__,
            f"fk_knowledge_base_{pointer}_version",
            ForeignKeyConstraint,
        )
        assert [column.name for column in constraint.columns] == [
            "id",
            "tenant_id",
            pointer,
        ]
        assert [element.target_fullname for element in constraint.elements] == [
            "knowledge_base_version.knowledge_base_id",
            "knowledge_base_version.tenant_id",
            "knowledge_base_version.id",
        ]
        assert constraint.deferrable is True
        assert constraint.initially == "DEFERRED"


def test_knowledge_base_has_lifecycle_identity_and_audit_columns() -> None:
    expected_columns = {
        "knowledge_type",
        "stable_key",
        "draft_version_id",
        "current_version_id",
        "publishing_version_id",
        "archived",
        "update_by",
        "publish_by",
        "publish_time",
    }
    assert expected_columns <= set(KnowledgeBase.__table__.columns.keys())

    stable_key_unique = _constraint(
        KnowledgeBase.__table__,
        "uq_knowledge_base_tenant_scope_stable_key",
        UniqueConstraint,
    )
    assert [column.name for column in stable_key_unique.columns] == [
        "tenant_id",
        "visibility_scope",
        "stable_key",
    ]


def test_lifecycle_models_expose_partial_uniqueness_and_singletons() -> None:
    version_indexes = {index.name: index for index in KnowledgeBaseVersion.__table__.indexes}
    active_draft = version_indexes["uq_knowledge_base_version_active_draft"]
    assert active_draft.unique is True
    assert [column.name for column in active_draft.columns] == ["knowledge_base_id"]
    assert "PUBLISH_FAILED" in str(active_draft.dialect_options["postgresql"]["where"])

    job_indexes = {index.name: index for index in KnowledgePublishJob.__table__.indexes}
    active_job = job_indexes["uq_knowledge_publish_job_active_knowledge_base"]
    assert active_job.unique is True
    assert [column.name for column in active_job.columns] == ["knowledge_base_id"]
    assert "RUNNING" in str(active_job.dialect_options["postgresql"]["where"])

    for model, constraint_name in (
        (KnowledgeMigrationState, "ck_knowledge_migration_state_singleton"),
        (KnowledgeStorageProbe, "ck_knowledge_storage_probe_singleton"),
    ):
        singleton = _constraint(model.__table__, constraint_name, CheckConstraint)
        assert "id = 1" in str(singleton.sqltext)


def test_lifecycle_model_defaults_keep_v2_inactive() -> None:
    migration_state = KnowledgeMigrationState()
    version = KnowledgeBaseVersion(
        knowledge_base_id=1,
        tenant_id=1,
        version_number=1,
        payload={},
    )

    assert migration_state.id == 1
    assert migration_state.phase == KnowledgeMigrationPhase.LEGACY_OPEN
    assert version.status == KnowledgeVersionStatus.DRAFT
    assert version.index_status == KnowledgeIndexStatus.NOT_REQUIRED


def test_models_entrypoint_registers_lifecycle_metadata() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from apps.knowledge_base.models import KnowledgeBase; "
            "from sqlmodel import SQLModel; "
            "print([table.name for table in SQLModel.metadata.sorted_tables])",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )

    assert result.returncode == 0, result.stderr
    assert "knowledge_base_version" in result.stdout
