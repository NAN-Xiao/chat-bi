"""Permission-first semantic retrieval for knowledge chunks."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import and_, exists, or_
from sqlmodel import Session, select

from apps.ai_model.embedding import EmbeddingModelCache
from apps.datasource.crud.permission_scope import PermissionScopeSnapshot
from apps.datasource.embedding.utils import (
    cosine_similarity,
    embedding_model_identity,
    embedding_payload_signature,
)
from apps.knowledge_base.lifecycle_models import KnowledgeBaseVersion
from apps.knowledge_base.models import KnowledgeBase, KnowledgeBaseVisibilityScopeEnum
from apps.knowledge_base.object_projection_models import (
    SemanticObjectReference,
    SemanticObjectResolution,
)
from apps.knowledge_base.retrieval_models import (
    KnowledgeApplicabilityStatus,
    KnowledgeBaseApplicability,
    KnowledgeBaseChunk,
    KnowledgeBaseWorkspaceOverride,
)
from common.core.config import settings


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KnowledgeCitation:
    chunk_id: int
    knowledge_base_id: int
    version_id: int
    section_path: str | None
    score: float
    content: str
    visibility_scope: str


@dataclass(frozen=True)
class KnowledgeRetrievalResult:
    query_hash: str
    model_signature: str | None
    citations: tuple[KnowledgeCitation, ...]
    context: str
    warnings: tuple[str, ...] = ()
    failure_type: str | None = None
    latency_ms: int | None = None


class KnowledgeRetrievalService:
    """Retrieve only current, applicable, fully authorized knowledge."""

    def __init__(
        self,
        *,
        embedding_model: Any | None = None,
        audit_writer: Callable[..., Any] | None = None,
    ) -> None:
        self.embedding_model = embedding_model
        self.audit_writer = audit_writer

    def search(
        self,
        *,
        session: Session,
        tenant_id: int,
        datasource_id: int,
        surface: str,
        query: str,
        permission_snapshot: PermissionScopeSnapshot,
        top_k: int | None = None,
        max_context_chars: int | None = None,
        request_id: str | None = None,
        user_id: int | None = None,
    ) -> KnowledgeRetrievalResult:
        started = datetime.utcnow()
        query_text = str(query or "").strip()
        query_hash = hashlib.sha256(query_text.encode("utf-8")).hexdigest()
        warnings: list[str] = []
        if not query_text:
            return self._result(query_hash, None, (), warnings=("检索问题不能为空。",), failure_type="EMPTY_QUERY")
        if int(permission_snapshot.tenant_id) != int(tenant_id) or int(permission_snapshot.datasource_id) != int(datasource_id):
            return self._result(
                query_hash,
                None,
                (),
                warnings=("权限上下文与当前工作空间或数据源不一致。",),
                failure_type="PERMISSION_CONTEXT_MISMATCH",
            )
        try:
            candidates = self._load_candidate_metadata(
                session,
                tenant_id=int(tenant_id),
                datasource_id=int(datasource_id),
                schema_hash=permission_snapshot.schema_hash,
            )
            eligible_ids: list[int] = []
            for candidate in candidates:
                if hasattr(candidate, "applicability_status") and candidate.applicability_status is None:
                    applicability = self._evaluate_applicability(
                        session,
                        tenant_id=int(tenant_id),
                        datasource_id=int(datasource_id),
                        version_id=int(candidate.version_id),
                        physical_schema_hash=permission_snapshot.schema_hash,
                    )
                    if not applicability.eligible:
                        continue
                references = self._load_candidate_references(
                    session,
                    chunk_id=int(candidate.id),
                    version_id=int(candidate.version_id),
                )
                if self._references_allowed(
                    session,
                    references,
                    snapshot=permission_snapshot,
                ):
                    eligible_ids.append(int(candidate.id))
            if not eligible_ids:
                warnings.append("当前权限和数据源下没有可用的知识内容。")
                result = self._result(query_hash, None, (), warnings=tuple(warnings), failure_type="NO_ELIGIBLE_KNOWLEDGE")
                self._audit(surface, permission_snapshot, result, started, request_id=request_id, user_id=user_id)
                return result
            rows = self._load_allowed_chunks(session, eligible_ids)
            model = self.embedding_model or EmbeddingModelCache.get_model()
            model_identity = embedding_model_identity(model)
            query_vector = model.embed_query(query_text)
            scored: list[KnowledgeCitation] = []
            for row in rows:
                vector = _vector(row.embedding)
                if not vector or len(vector) != len(query_vector):
                    continue
                expected_signature = embedding_payload_signature(model_identity, len(vector))
                if row.embedding_signature != expected_signature:
                    continue
                scored.append(
                    KnowledgeCitation(
                        chunk_id=int(row.id),
                        knowledge_base_id=int(row.knowledge_base_id),
                        version_id=int(row.version_id),
                        section_path=row.section_path,
                        score=float(cosine_similarity(query_vector, vector)),
                        content=row.content,
                        visibility_scope=_scope_value(row.visibility_scope),
                    )
                )
            min_score = float(settings.KNOWLEDGE_RETRIEVAL_MIN_SCORE)
            scored = [item for item in scored if item.score >= min_score]
            scored.sort(key=lambda item: (-item.score, item.chunk_id))
            bounded = self._bound_context(
                scored,
                top_k=max(1, int(top_k or settings.KNOWLEDGE_RETRIEVAL_TOP_K)),
                max_chars=max(1, int(max_context_chars or settings.KNOWLEDGE_RETRIEVAL_MAX_CONTEXT_CHARS)),
            )
            if not bounded and rows:
                warnings.append("知识向量与当前检索模型不匹配，暂未返回结果。")
            result = self._result(
                query_hash,
                model_identity,
                tuple(bounded),
                warnings=tuple(warnings),
                latency_ms=int((datetime.utcnow() - started).total_seconds() * 1000),
            )
            self._audit(surface, permission_snapshot, result, started, request_id=request_id, user_id=user_id)
            return result
        except Exception as exc:
            logger.exception(
                "Knowledge retrieval failed: tenant_id=%s datasource_id=%s surface=%s",
                tenant_id,
                datasource_id,
                surface,
            )
            result = self._result(
                query_hash,
                None,
                (),
                warnings=("知识检索暂时不可用，请稍后重试。",),
                failure_type=type(exc).__name__,
                latency_ms=int((datetime.utcnow() - started).total_seconds() * 1000),
            )
            self._audit(surface, permission_snapshot, result, started, request_id=request_id, user_id=user_id)
            return result

    @staticmethod
    def _load_candidate_metadata(session: Session, *, tenant_id: int, datasource_id: int, schema_hash: str):
        scope = KnowledgeBaseVisibilityScopeEnum.PLATFORM_PUBLIC.value
        statement = (
            select(
                KnowledgeBaseChunk.id,
                KnowledgeBaseChunk.knowledge_base_id,
                KnowledgeBaseChunk.version_id,
                KnowledgeBaseChunk.tenant_id,
                KnowledgeBaseChunk.visibility_scope,
                KnowledgeBaseChunk.embedding_signature,
                KnowledgeBaseApplicability.status.label("applicability_status"),
            )
            .join(
                KnowledgeBaseVersion,
                and_(
                    KnowledgeBaseVersion.id == KnowledgeBaseChunk.version_id,
                    KnowledgeBaseVersion.knowledge_base_id == KnowledgeBaseChunk.knowledge_base_id,
                    KnowledgeBaseVersion.tenant_id == KnowledgeBaseChunk.tenant_id,
                ),
            )
            .join(
                KnowledgeBase,
                and_(
                    KnowledgeBase.id == KnowledgeBaseChunk.knowledge_base_id,
                    KnowledgeBase.tenant_id == KnowledgeBaseChunk.tenant_id,
                ),
            )
            .where(
                KnowledgeBaseVersion.status == "PUBLISHED",
                KnowledgeBase.current_version_id == KnowledgeBaseVersion.id,
                KnowledgeBase.archived.is_(False),
                KnowledgeBase.active.is_(True),
                ~exists(
                    select(KnowledgeBaseWorkspaceOverride.id).where(
                        KnowledgeBaseWorkspaceOverride.tenant_id == int(tenant_id),
                        KnowledgeBaseWorkspaceOverride.knowledge_base_id == KnowledgeBase.id,
                        KnowledgeBaseWorkspaceOverride.enabled.is_(False),
                    )
                ),
                or_(
                    and_(KnowledgeBase.visibility_scope == scope, KnowledgeBaseChunk.tenant_id == KnowledgeBase.tenant_id),
                    and_(KnowledgeBase.visibility_scope != scope, KnowledgeBaseChunk.tenant_id == int(tenant_id)),
                ),
            )
            .outerjoin(
                KnowledgeBaseApplicability,
                and_(
                    KnowledgeBaseApplicability.version_id == KnowledgeBaseVersion.id,
                    KnowledgeBaseApplicability.knowledge_base_id == KnowledgeBaseVersion.knowledge_base_id,
                    KnowledgeBaseApplicability.tenant_id == int(tenant_id),
                    KnowledgeBaseApplicability.datasource_id == int(datasource_id),
                    KnowledgeBaseApplicability.physical_schema_hash == schema_hash,
                ),
            )
            .where(
                or_(
                    KnowledgeBaseApplicability.id.is_(None),
                    KnowledgeBaseApplicability.status == KnowledgeApplicabilityStatus.VALID.value,
                )
            )
        )
        return session.exec(statement).all()

    @staticmethod
    def _evaluate_applicability(
        session: Session,
        *,
        tenant_id: int,
        datasource_id: int,
        version_id: int,
        physical_schema_hash: str,
    ):
        from apps.knowledge_base.applicability import KnowledgeApplicabilityService

        return KnowledgeApplicabilityService().evaluate(
            session=session,
            tenant_id=int(tenant_id),
            datasource_id=int(datasource_id),
            version_id=int(version_id),
            physical_schema_hash=str(physical_schema_hash),
        )

    @staticmethod
    def _load_candidate_references(session: Session, *, chunk_id: int, version_id: int) -> list[Any]:
        chunk_refs = session.exec(
            select(SemanticObjectReference).where(
                SemanticObjectReference.owner_type == "KNOWLEDGE_CHUNK",
                SemanticObjectReference.chunk_id == int(chunk_id),
            )
        ).all()
        if chunk_refs:
            return list(chunk_refs)
        return list(
            session.exec(
                select(SemanticObjectReference).where(
                    SemanticObjectReference.owner_type == "KNOWLEDGE_VERSION",
                    SemanticObjectReference.version_id == int(version_id),
                )
            ).all()
        )

    @staticmethod
    def _references_allowed(
        session: Session,
        references: Iterable[Any],
        *,
        snapshot: PermissionScopeSnapshot,
    ) -> bool:
        for reference in references:
            if reference.datasource_id is not None and int(reference.datasource_id) != int(snapshot.datasource_id):
                return False
            resolution = session.exec(
                select(SemanticObjectResolution).where(
                    SemanticObjectResolution.reference_id == int(reference.id),
                    SemanticObjectResolution.tenant_id == int(snapshot.tenant_id),
                    SemanticObjectResolution.datasource_id == int(snapshot.datasource_id),
                    SemanticObjectResolution.physical_schema_hash == snapshot.schema_hash,
                    SemanticObjectResolution.status == "RESOLVED",
                )
            ).first()
            if resolution is None or not resolution.canonical_key:
                return False
            if resolution.canonical_key not in snapshot.allowed_object_keys:
                return False
            if resolution.canonical_key in snapshot.denied_object_keys:
                return False
        return True

    @staticmethod
    def _load_allowed_chunks(session: Session, ids: list[int]) -> list[Any]:
        return list(
            session.exec(
                select(KnowledgeBaseChunk).where(KnowledgeBaseChunk.id.in_(ids))
            ).all()
        )

    @staticmethod
    def _bound_context(
        citations: list[KnowledgeCitation], *, top_k: int, max_chars: int
    ) -> list[KnowledgeCitation]:
        selected: list[KnowledgeCitation] = []
        used = 0
        for citation in citations[:top_k]:
            item = f"[{citation.knowledge_base_id}:{citation.chunk_id}] {citation.content}\n"
            if selected and used + len(item) > max_chars:
                break
            if not selected and len(item) > max_chars:
                item = item[:max_chars]
            selected.append(citation)
            used += len(item)
        return selected

    @staticmethod
    def _result(
        query_hash: str,
        model_signature: str | None,
        citations: tuple[KnowledgeCitation, ...],
        *,
        warnings: tuple[str, ...] = (),
        failure_type: str | None = None,
        latency_ms: int | None = None,
    ) -> KnowledgeRetrievalResult:
        context = "\n".join(
            f"<retrieved-knowledge priority=\"reference-only\" id=\"{item.chunk_id}\">{item.content}</retrieved-knowledge>"
            for item in citations
        )
        return KnowledgeRetrievalResult(
            query_hash=query_hash,
            model_signature=model_signature,
            citations=citations,
            context=context,
            warnings=warnings,
            failure_type=failure_type,
            latency_ms=latency_ms,
        )

    def _audit(
        self,
        surface: str,
        snapshot: PermissionScopeSnapshot,
        result: KnowledgeRetrievalResult,
        started: datetime,
        *,
        request_id: str | None = None,
        user_id: int | None = None,
    ) -> None:
        if self.audit_writer is not None:
            try:
                self.audit_writer(
                    surface=surface,
                    snapshot=snapshot,
                    result=result,
                    started=started,
                    request_id=request_id,
                    user_id=user_id,
                )
            except Exception:
                # Auditing is diagnostic metadata and must not change retrieval behavior.
                logger.warning("Knowledge retrieval audit write failed", exc_info=True)


def _vector(value: Any) -> list[float] | None:
    if value is None:
        return None
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return None


def _scope_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")
