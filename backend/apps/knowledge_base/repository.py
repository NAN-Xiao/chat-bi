"""Database authority for knowledge migration phase transitions."""

from __future__ import annotations

from fastapi import HTTPException
from sqlmodel import Session, select

from apps.knowledge_base.lifecycle_models import (
    KnowledgeMigrationPhase,
    KnowledgeMigrationState,
)


class KnowledgeBusinessError(HTTPException):
    """Expected knowledge error with a stable code and safe Chinese message."""

    def __init__(self, *, code: str, message: str, status_code: int) -> None:
        self.code = code
        self.message = message
        super().__init__(
            status_code=status_code,
            detail={"code": code, "message": message},
        )


class KnowledgeMigrationStateRepository:
    """Read and lock the singleton database migration phase."""

    @staticmethod
    def get(session: Session) -> KnowledgeMigrationState:
        return session.exec(
            select(KnowledgeMigrationState).where(KnowledgeMigrationState.id == 1)
        ).one()

    @staticmethod
    def lock_for_legacy_write(session: Session) -> KnowledgeMigrationState:
        row = session.exec(
            select(KnowledgeMigrationState)
            .where(KnowledgeMigrationState.id == 1)
            .with_for_update(read=True)
        ).one()
        phase = KnowledgeMigrationPhase(row.phase)
        if phase == KnowledgeMigrationPhase.CUTOVER_BARRIER:
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_UPGRADE_IN_PROGRESS",
                message="知识库升级中，请稍后重试。",
                status_code=409,
            )
        if phase == KnowledgeMigrationPhase.V2_ACTIVE:
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_LEGACY_WRITE_DISABLED",
                message="知识库已升级，请刷新页面后重新操作。",
                status_code=410,
            )
        return row
