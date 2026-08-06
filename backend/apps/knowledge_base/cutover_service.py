"""Transactional phase transitions for knowledge-base V2."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import datetime

from sqlalchemy import select
from sqlmodel import Session

from apps.knowledge_base.cutover_readiness import (
    CutoverReadinessReport,
    collect_cutover_readiness,
)
from apps.knowledge_base.lifecycle_models import (
    KnowledgeMigrationPhase,
    KnowledgeMigrationState,
)


class KnowledgeCutoverError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


ReadinessLoader = Callable[..., CutoverReadinessReport]


class KnowledgeCutoverService:
    def __init__(
        self,
        session: Session,
        *,
        active_consumers: Iterable[tuple[str, str]] = (),
        compatible_builds_confirmed: bool = False,
        readiness_loader: ReadinessLoader = collect_cutover_readiness,
    ) -> None:
        self.session = session
        self.active_consumers = tuple(active_consumers)
        self.compatible_builds_confirmed = compatible_builds_confirmed
        self.readiness_loader = readiness_loader

    def status(self) -> CutoverReadinessReport:
        return self._readiness()

    def verify(self) -> CutoverReadinessReport:
        return self._readiness()

    def enter_barrier(self) -> CutoverReadinessReport:
        row = self._lock_state()
        self._require_phase(row, KnowledgeMigrationPhase.LEGACY_OPEN)
        report = self._readiness()
        self._require_ready(report)
        self._set_phase(row, KnowledgeMigrationPhase.CUTOVER_BARRIER)
        self.session.commit()
        return replace(
            report,
            phase=KnowledgeMigrationPhase.CUTOVER_BARRIER.value,
            revision=int(row.revision),
            code="CUTOVER_BARRIER_ENTERED",
            message="知识库已进入升级屏障，新旧写入均已暂停。",
        )

    def activate_v2(self) -> CutoverReadinessReport:
        row = self._lock_state()
        self._require_phase(row, KnowledgeMigrationPhase.CUTOVER_BARRIER)
        report = self._readiness()
        self._require_ready(report)
        self._set_phase(row, KnowledgeMigrationPhase.V2_ACTIVE)
        self.session.commit()
        return replace(
            report,
            phase=KnowledgeMigrationPhase.V2_ACTIVE.value,
            revision=int(row.revision),
            ready_for_cutover=True,
            code="V2_ACTIVATED",
            message="知识库 V2 已激活，旧写入入口已永久关闭。",
        )

    def return_legacy(self) -> CutoverReadinessReport:
        row = self._lock_state()
        self._require_phase(row, KnowledgeMigrationPhase.CUTOVER_BARRIER)
        self._set_phase(row, KnowledgeMigrationPhase.LEGACY_OPEN)
        self.session.commit()
        return replace(
            self._readiness(),
            phase=KnowledgeMigrationPhase.LEGACY_OPEN.value,
            revision=int(row.revision),
            ready_for_cutover=False,
            code="LEGACY_RESTORED",
            message="知识库已退出升级屏障并恢复旧写入。",
        )

    def _readiness(self) -> CutoverReadinessReport:
        return self.readiness_loader(
            self.session,
            active_consumers=self.active_consumers,
            compatible_builds_confirmed=self.compatible_builds_confirmed,
        )

    def _lock_state(self) -> KnowledgeMigrationState:
        return self.session.exec(
            select(KnowledgeMigrationState)
            .where(KnowledgeMigrationState.id == 1)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one()

    @staticmethod
    def _require_phase(
        row: KnowledgeMigrationState,
        expected: KnowledgeMigrationPhase,
    ) -> None:
        actual = str(getattr(row.phase, "value", row.phase))
        if actual != expected.value:
            raise KnowledgeCutoverError(
                "KNOWLEDGE_CUTOVER_PHASE_CONFLICT",
                f"数据库阶段已变化，当前为 {actual}，预期为 {expected.value}。",
            )

    @staticmethod
    def _require_ready(report: CutoverReadinessReport) -> None:
        if not report.ready_for_cutover:
            raise KnowledgeCutoverError(report.code, report.message)

    def _set_phase(
        self,
        row: KnowledgeMigrationState,
        phase: KnowledgeMigrationPhase,
    ) -> None:
        row.phase = phase
        row.revision = int(row.revision or 0) + 1
        row.update_time = datetime.utcnow()
        self.session.add(row)
