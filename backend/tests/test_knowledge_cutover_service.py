"""Verify transactional knowledge cutover transitions."""

from __future__ import annotations

import pytest

from apps.knowledge_base.cutover_readiness import CutoverReadinessReport
from apps.knowledge_base.cutover_service import (
    KnowledgeCutoverError,
    KnowledgeCutoverService,
)
from apps.knowledge_base.lifecycle_models import (
    KnowledgeMigrationPhase,
    KnowledgeMigrationState,
)


class _Result:
    def __init__(self, row: KnowledgeMigrationState) -> None:
        self.row = row

    def one(self) -> KnowledgeMigrationState:
        return self.row


class _Session:
    def __init__(self, phase: KnowledgeMigrationPhase) -> None:
        self.row = KnowledgeMigrationState(phase=phase, revision=3)
        self.commits = 0
        self.added = []

    def scalars(self, _statement):
        return _Result(self.row)

    def add(self, row) -> None:
        self.added.append(row)

    def commit(self) -> None:
        self.commits += 1


def _report(*, ready: bool = True, phase: str = "LEGACY_OPEN") -> CutoverReadinessReport:
    return CutoverReadinessReport(
        phase=phase,
        revision=3,
        ready_for_cutover=ready,
        legacy_backfill_remaining=0,
        parity_mismatch_count=0,
        mismatch_ids=(),
        pending_index_count=0,
        pending_projection_count=0,
        active_publish_job_count=0,
        overdue_publish_job_count=0,
        storage_probe_ready=True,
        compatible_builds_confirmed=True,
        expected_worker_count=1,
        code="READY" if ready else "KNOWLEDGE_CUTOVER_NOT_READY",
        message="知识库已满足切换条件。" if ready else "仍有未完成任务。",
    )


def _loader(report: CutoverReadinessReport):
    def load(*_args, **_kwargs) -> CutoverReadinessReport:
        return report

    return load


def test_enter_barrier_changes_phase_with_revision_cas() -> None:
    session = _Session(KnowledgeMigrationPhase.LEGACY_OPEN)
    service = KnowledgeCutoverService(session, readiness_loader=_loader(_report()))

    result = service.enter_barrier()

    assert session.row.phase == KnowledgeMigrationPhase.CUTOVER_BARRIER
    assert session.row.revision == 4
    assert session.commits == 1
    assert result.phase == "CUTOVER_BARRIER"
    assert result.code == "CUTOVER_BARRIER_ENTERED"


def test_enter_barrier_fails_closed_when_readiness_fails() -> None:
    session = _Session(KnowledgeMigrationPhase.LEGACY_OPEN)
    service = KnowledgeCutoverService(
        session,
        readiness_loader=_loader(_report(ready=False)),
    )

    with pytest.raises(KnowledgeCutoverError) as caught:
        service.enter_barrier()

    assert caught.value.code == "KNOWLEDGE_CUTOVER_NOT_READY"
    assert session.row.phase == KnowledgeMigrationPhase.LEGACY_OPEN
    assert session.commits == 0


def test_activate_v2_requires_barrier_and_final_readiness() -> None:
    session = _Session(KnowledgeMigrationPhase.CUTOVER_BARRIER)
    service = KnowledgeCutoverService(
        session,
        readiness_loader=_loader(_report(phase="CUTOVER_BARRIER")),
    )

    result = service.activate_v2()

    assert session.row.phase == KnowledgeMigrationPhase.V2_ACTIVE
    assert result.code == "V2_ACTIVATED"
    assert result.ready_for_cutover is True


def test_activate_v2_rejects_unexpected_phase() -> None:
    session = _Session(KnowledgeMigrationPhase.LEGACY_OPEN)
    service = KnowledgeCutoverService(session, readiness_loader=_loader(_report()))

    with pytest.raises(KnowledgeCutoverError) as caught:
        service.activate_v2()

    assert caught.value.code == "KNOWLEDGE_CUTOVER_PHASE_CONFLICT"
    assert session.commits == 0


def test_return_legacy_is_only_allowed_from_barrier() -> None:
    session = _Session(KnowledgeMigrationPhase.CUTOVER_BARRIER)
    service = KnowledgeCutoverService(
        session,
        readiness_loader=_loader(_report(phase="CUTOVER_BARRIER")),
    )

    result = service.return_legacy()

    assert session.row.phase == KnowledgeMigrationPhase.LEGACY_OPEN
    assert result.code == "LEGACY_RESTORED"
    assert result.ready_for_cutover is False


def test_return_legacy_never_accepts_v2_active() -> None:
    session = _Session(KnowledgeMigrationPhase.V2_ACTIVE)
    service = KnowledgeCutoverService(session, readiness_loader=_loader(_report()))

    with pytest.raises(KnowledgeCutoverError):
        service.return_legacy()

    assert session.commits == 0
