"""Verify database-authoritative knowledge migration capabilities."""

from __future__ import annotations

import pytest
from sqlalchemy.dialects import postgresql

from apps.knowledge_base.cutover import get_capabilities
from apps.knowledge_base.lifecycle_models import (
    KnowledgeMigrationPhase,
    KnowledgeMigrationState,
)
from apps.knowledge_base.repository import (
    KnowledgeBusinessError,
    KnowledgeMigrationStateRepository,
)


class _OneResult:
    def __init__(self, row: KnowledgeMigrationState) -> None:
        self.row = row

    def one(self) -> KnowledgeMigrationState:
        return self.row


class _Session:
    def __init__(self, phase: KnowledgeMigrationPhase) -> None:
        self.row = KnowledgeMigrationState(phase=phase)
        self.statements = []

    def exec(self, statement):
        self.statements.append(statement)
        return _OneResult(self.row)


@pytest.mark.parametrize(
    ("phase", "flag", "legacy_write", "v2_write", "mode"),
    [
        ("LEGACY_OPEN", False, True, False, "LEGACY"),
        ("LEGACY_OPEN", True, True, False, "UPGRADING"),
        ("CUTOVER_BARRIER", False, False, False, "MAINTENANCE"),
        ("CUTOVER_BARRIER", True, False, False, "MAINTENANCE"),
        ("V2_ACTIVE", False, False, False, "MAINTENANCE"),
        ("V2_ACTIVE", True, False, True, "V2"),
    ],
)
def test_capability_matrix(
    phase: str,
    flag: bool,
    legacy_write: bool,
    v2_write: bool,
    mode: str,
) -> None:
    result = get_capabilities(
        _Session(KnowledgeMigrationPhase(phase)),
        management_enabled=flag,
        runtime_enabled=False,
    )

    assert (
        result.management_mode,
        result.legacy_write_enabled,
        result.v2_write_enabled,
    ) == (mode, legacy_write, v2_write)
    assert result.runtime_context_enabled is False


@pytest.mark.parametrize(
    ("phase", "expected"),
    [
        (KnowledgeMigrationPhase.LEGACY_OPEN, False),
        (KnowledgeMigrationPhase.CUTOVER_BARRIER, False),
        (KnowledgeMigrationPhase.V2_ACTIVE, True),
    ],
)
def test_runtime_context_requires_v2_phase(
    phase: KnowledgeMigrationPhase,
    expected: bool,
) -> None:
    result = get_capabilities(
        _Session(phase),
        management_enabled=False,
        runtime_enabled=True,
    )

    assert result.runtime_context_enabled is expected


def test_legacy_write_lock_uses_shared_row_lock() -> None:
    session = _Session(KnowledgeMigrationPhase.LEGACY_OPEN)

    row = KnowledgeMigrationStateRepository.lock_for_legacy_write(session)

    sql = str(
        session.statements[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert row.phase == KnowledgeMigrationPhase.LEGACY_OPEN
    assert "WHERE knowledge_migration_state.id = 1" in sql
    assert "FOR SHARE" in sql


@pytest.mark.parametrize(
    ("phase", "code", "message", "status_code"),
    [
        (
            KnowledgeMigrationPhase.CUTOVER_BARRIER,
            "KNOWLEDGE_UPGRADE_IN_PROGRESS",
            "知识库升级中，请稍后重试。",
            409,
        ),
        (
            KnowledgeMigrationPhase.V2_ACTIVE,
            "KNOWLEDGE_LEGACY_WRITE_DISABLED",
            "知识库已升级，请刷新页面后重新操作。",
            410,
        ),
    ],
)
def test_legacy_write_lock_fails_closed_after_legacy_phase(
    phase: KnowledgeMigrationPhase,
    code: str,
    message: str,
    status_code: int,
) -> None:
    with pytest.raises(KnowledgeBusinessError) as caught:
        KnowledgeMigrationStateRepository.lock_for_legacy_write(_Session(phase))

    assert caught.value.code == code
    assert caught.value.message == message
    assert caught.value.status_code == status_code
    assert caught.value.detail == {"code": code, "message": message}
