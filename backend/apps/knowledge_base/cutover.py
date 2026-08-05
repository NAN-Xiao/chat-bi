"""Capability matrix derived from database phase and rollout switches."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlmodel import Session

from apps.knowledge_base.lifecycle_models import KnowledgeMigrationPhase
from apps.knowledge_base.repository import KnowledgeMigrationStateRepository
from common.core.config import settings

KnowledgeManagementMode = Literal["LEGACY", "UPGRADING", "V2", "MAINTENANCE"]


@dataclass(frozen=True)
class KnowledgeCapabilities:
    phase: KnowledgeMigrationPhase
    management_mode: KnowledgeManagementMode
    legacy_write_enabled: bool
    v2_write_enabled: bool
    runtime_context_enabled: bool


def get_capabilities(
    session: Session,
    *,
    management_enabled: bool | None = None,
    runtime_enabled: bool | None = None,
) -> KnowledgeCapabilities:
    row = KnowledgeMigrationStateRepository.get(session)
    phase = KnowledgeMigrationPhase(row.phase)
    management_flag = (
        settings.KNOWLEDGE_MANAGEMENT_V2_ENABLED
        if management_enabled is None
        else management_enabled
    )
    runtime_flag = (
        settings.KNOWLEDGE_RUNTIME_CONTEXT_ENABLED
        if runtime_enabled is None
        else runtime_enabled
    )

    if phase == KnowledgeMigrationPhase.LEGACY_OPEN:
        return KnowledgeCapabilities(
            phase=phase,
            management_mode="UPGRADING" if management_flag else "LEGACY",
            legacy_write_enabled=True,
            v2_write_enabled=False,
            runtime_context_enabled=False,
        )
    if phase == KnowledgeMigrationPhase.CUTOVER_BARRIER:
        return KnowledgeCapabilities(
            phase=phase,
            management_mode="MAINTENANCE",
            legacy_write_enabled=False,
            v2_write_enabled=False,
            runtime_context_enabled=False,
        )
    return KnowledgeCapabilities(
        phase=phase,
        management_mode="V2" if management_flag else "MAINTENANCE",
        legacy_write_enabled=False,
        v2_write_enabled=management_flag,
        runtime_context_enabled=runtime_flag,
    )
