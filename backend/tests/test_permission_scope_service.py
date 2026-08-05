"""Verify semantic permission epoch storage invariants."""

from __future__ import annotations

import os
import subprocess
import sys

from sqlalchemy import CheckConstraint

from apps.datasource.models.datasource import SemanticScopeEpoch, SemanticScopeType


def _constraint(table, name: str, constraint_type):
    return next(
        constraint
        for constraint in table.constraints
        if constraint.name == name and isinstance(constraint, constraint_type)
    )


def test_semantic_scope_types_cover_all_authority_domains() -> None:
    assert [scope.value for scope in SemanticScopeType] == [
        "PERMISSION",
        "SYSTEM_ROLE",
        "MEMBERSHIP",
        "DATASOURCE_ACCESS",
        "DATASOURCE_ROLE",
        "TRACKING",
        "DATASOURCE_BINDING",
        "SCHEMA",
    ]


def test_semantic_epoch_has_full_nullable_scope_key() -> None:
    assert SemanticScopeEpoch.__tablename__ == "semantic_scope_epoch"
    indexes = {index.name: index for index in SemanticScopeEpoch.__table__.indexes}
    scope_index = indexes["uq_semantic_scope_epoch_scope"]
    assert scope_index.unique is True
    expression = ", ".join(str(item) for item in scope_index.expressions)
    assert "scope_type" in expression
    assert "tenant_id" in expression
    assert "COALESCE(datasource_id, 0)" in expression
    assert "COALESCE(subject_id, 0)" in expression


def test_semantic_epoch_model_defaults_and_scope_check() -> None:
    row = SemanticScopeEpoch(
        scope_type=SemanticScopeType.SCHEMA,
        tenant_id=2,
    )
    assert row.epoch == 0
    assert row.datasource_id is None
    assert row.subject_id is None

    constraint = _constraint(
        SemanticScopeEpoch.__table__,
        "ck_semantic_scope_epoch_scope_type",
        CheckConstraint,
    )
    expression = str(constraint.sqltext)
    for scope in SemanticScopeType:
        assert scope.value in expression


def test_datasource_entrypoint_registers_semantic_epoch_metadata() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from apps.datasource.models.datasource import CoreDatasource; "
            "from sqlmodel import SQLModel; "
            "print([table.name for table in SQLModel.metadata.sorted_tables])",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )

    assert result.returncode == 0, result.stderr
    assert "semantic_scope_epoch" in result.stdout


def test_semantic_epoch_migration_uses_named_expression_index() -> None:
    from tests.test_semantic_object_key import _load_migration, _offline_sql

    sql = _offline_sql(_load_migration(), "upgrade")
    assert "CREATE TABLE semantic_scope_epoch" in sql
    assert "CREATE UNIQUE INDEX uq_semantic_scope_epoch_scope" in sql
    assert "scope_type, tenant_id, COALESCE(datasource_id, 0), COALESCE(subject_id, 0)" in sql
