"""Redacted audit writers for retrieval and semantic-context snapshots."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlmodel import Session

from apps.knowledge_base.audit_models import KnowledgeRetrievalLog, SemanticContextAudit


def new_request_id() -> str:
    return uuid4().hex


def write_retrieval_audit(
    *,
    session: Session,
    request_id: str,
    surface: str,
    snapshot: Any,
    result: Any,
    user_id: int | None = None,
) -> None:
    """Persist only identifiers and safe retrieval scores, never query/content text."""
    row = KnowledgeRetrievalLog(
        request_id=str(request_id)[:64],
        surface=str(surface)[:64],
        tenant_id=int(snapshot.tenant_id),
        user_id=int(user_id) if user_id is not None else int(getattr(snapshot, "user_id", 0) or 0) or None,
        datasource_id=int(snapshot.datasource_id),
        query_hash=str(result.query_hash),
        model_signature=result.model_signature,
        hit_snapshot=[
            {
                "chunk_id": str(item.chunk_id),
                "knowledge_base_id": str(item.knowledge_base_id),
                "version_id": str(item.version_id),
                "section_path": item.section_path,
                "score": round(float(item.score), 6),
                "visibility_scope": item.visibility_scope,
            }
            for item in result.citations
        ],
        latency_ms=result.latency_ms,
        warnings=[{"message": str(item)} for item in result.warnings],
        failure_type=_safe_failure_type(result.failure_type),
        create_time=datetime.utcnow(),
    )
    session.add(row)
    session.flush()


def write_semantic_context_audit(
    *,
    session: Session,
    request_id: str,
    surface: str,
    semantic: Any,
) -> None:
    snapshot = semantic.permission_snapshot
    row = SemanticContextAudit(
        request_id=str(request_id)[:64],
        tenant_id=int(snapshot.tenant_id),
        user_id=int(snapshot.user_id),
        datasource_id=int(snapshot.datasource_id),
        surface=str(surface)[:64],
        permission_version=str(snapshot.permission_version),
        schema_hash=str(snapshot.schema_hash),
        knowledge_snapshot=[
            {
                "chunk_id": str(item.chunk_id),
                "knowledge_base_id": str(item.knowledge_base_id),
                "version_id": str(item.version_id),
                "section_path": item.section_path,
                "score": round(float(item.score), 6),
                "visibility_scope": item.visibility_scope,
            }
            for item in semantic.knowledge_citations
        ],
        skill_snapshot=[
            {
                "skill_id": str(item.skill_id),
                "selection_mode": item.selection_mode,
                "source_hash": item.source_hash,
            }
            for item in semantic.selected_skills
        ],
        warnings=[{"message": str(item)} for item in semantic.warnings],
        create_time=datetime.utcnow(),
    )
    session.add(row)
    session.flush()


def _safe_failure_type(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value).split(".")[-1][:64]
