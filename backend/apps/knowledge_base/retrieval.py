"""Permission-first semantic retrieval for knowledge chunks."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from sqlalchemy import and_, exists, or_
from sqlmodel import Session, select

from apps.ai_model.embedding import EmbeddingModelCache
from apps.ai_model.rerank import RerankModelCache
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
    source_block_id: str | None = None
    knowledge_base_name: str | None = None
    version_number: int | None = None
    source_file_name: str | None = None
    vector_score: float | None = None
    rerank_score: float | None = None


@dataclass(frozen=True)
class KnowledgeRetrievalResult:
    query_hash: str
    model_signature: str | None
    citations: tuple[KnowledgeCitation, ...]
    context: str
    warnings: tuple[str, ...] = ()
    failure_type: str | None = None
    latency_ms: int | None = None


def _knowledge_context_wrapper(citation: KnowledgeCitation, *, rank: int) -> tuple[str, str]:
    score = f"{float(citation.score):.6f}"
    return (
        f'<retrieved-knowledge priority="reference-only" rank="{rank}" score="{score}" id="{citation.chunk_id}">',
        "</retrieved-knowledge>",
    )


def _knowledge_context_item(citation: KnowledgeCitation, *, rank: int) -> str:
    prefix, suffix = _knowledge_context_wrapper(citation, rank=rank)
    return f"{prefix}{citation.content}{suffix}"


class KnowledgeRetrievalService:
    """Retrieve only current, applicable, fully authorized knowledge."""

    def __init__(
        self,
        *,
        embedding_model: Any | None = None,
        reranker_model: Any | None = None,
        audit_writer: Callable[..., Any] | None = None,
    ) -> None:
        self.embedding_model = embedding_model
        self.reranker_model = reranker_model
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
            candidate_by_id = {
                int(candidate.id): candidate
                for candidate in candidates
                if getattr(candidate, "id", None) is not None
            }
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
                vector_score = float(cosine_similarity(query_vector, vector))
                scored.append(
                    KnowledgeCitation(
                        chunk_id=int(row.id),
                        knowledge_base_id=int(row.knowledge_base_id),
                        version_id=int(row.version_id),
                        section_path=row.section_path,
                        source_block_id=getattr(row, "source_block_id", None),
                        score=vector_score,
                        vector_score=vector_score,
                        content=row.content,
                        visibility_scope=_scope_value(row.visibility_scope),
                        knowledge_base_name=getattr(candidate_by_id.get(int(row.id)), "knowledge_base_name", None),
                        version_number=_optional_int(getattr(candidate_by_id.get(int(row.id)), "version_number", None)),
                        source_file_name=getattr(candidate_by_id.get(int(row.id)), "source_file_name", None),
                    )
                )
            min_score = float(settings.KNOWLEDGE_RETRIEVAL_MIN_SCORE)
            vector_min_score = float(settings.KNOWLEDGE_RETRIEVAL_VECTOR_MIN_SCORE)
            scored = [item for item in scored if item.score >= vector_min_score]
            scored.sort(key=lambda item: (-item.score, item.chunk_id))
            initial_top_k = max(
                1,
                int(settings.KNOWLEDGE_RETRIEVAL_INITIAL_TOP_K),
                int(top_k or settings.KNOWLEDGE_RETRIEVAL_TOP_K),
            )
            candidates_for_rerank = scored[:initial_top_k]
            model_signature = model_identity
            if settings.KNOWLEDGE_RETRIEVAL_RERANK_ENABLED and candidates_for_rerank:
                try:
                    reranker = self.reranker_model or RerankModelCache.get_model()
                    rerank_scores = reranker.rerank(
                        query_text,
                        [item.content for item in candidates_for_rerank],
                    )
                    reranked: list[KnowledgeCitation] = []
                    for index, rerank_score in rerank_scores:
                        citation = candidates_for_rerank[index]
                        reranked.append(
                            replace(
                                citation,
                                score=float(rerank_score),
                                rerank_score=float(rerank_score),
                            )
                        )
                    scored = reranked
                    model_signature = f"{model_identity};rerank={getattr(getattr(reranker, 'config', None), 'model', 'unknown')}"
                except Exception:
                    logger.exception(
                        "Knowledge rerank failed: tenant_id=%s datasource_id=%s surface=%s",
                        tenant_id,
                        datasource_id,
                        surface,
                    )
                    result = self._result(
                        query_hash,
                        f"{model_identity};rerank=unavailable",
                        (),
                        warnings=("知识重排服务暂时不可用，未向模型提供知识内容。",),
                        failure_type="RERANK_UNAVAILABLE",
                        latency_ms=int((datetime.utcnow() - started).total_seconds() * 1000),
                    )
                    self._audit(surface, permission_snapshot, result, started, request_id=request_id, user_id=user_id)
                    return result
            scored = [item for item in scored if item.score >= min_score]
            scored.sort(key=lambda item: (-item.score, item.chunk_id))
            final_top_k = max(1, int(top_k or settings.KNOWLEDGE_RETRIEVAL_TOP_K))
            scored = scored[:final_top_k]
            bounded = self._bound_context(
                scored,
                top_k=final_top_k,
                max_chars=max(1, int(max_context_chars or settings.KNOWLEDGE_RETRIEVAL_MAX_CONTEXT_CHARS)),
            )
            if not bounded and rows:
                warnings.append("知识向量与当前检索模型不匹配，暂未返回结果。")
            result = self._result(
                query_hash,
                model_signature,
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
                KnowledgeBase.name.label("knowledge_base_name"),
                KnowledgeBaseVersion.version_number.label("version_number"),
                KnowledgeBaseVersion.file_name.label("source_file_name"),
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
            resolution = KnowledgeRetrievalService._load_reference_resolution(
                session,
                reference=reference,
                snapshot=snapshot,
            )
            if resolution is None or not resolution.canonical_key:
                return False
            if resolution.canonical_key not in snapshot.allowed_object_keys:
                return False
            if resolution.canonical_key in snapshot.denied_object_keys:
                return False
        return True

    @staticmethod
    def _load_reference_resolution(
        session: Session,
        *,
        reference: Any,
        snapshot: PermissionScopeSnapshot,
    ) -> Any | None:
        resolution = session.exec(
            select(SemanticObjectResolution).where(
                SemanticObjectResolution.reference_id == int(reference.id),
                SemanticObjectResolution.tenant_id == int(snapshot.tenant_id),
                SemanticObjectResolution.datasource_id == int(snapshot.datasource_id),
                SemanticObjectResolution.physical_schema_hash == snapshot.schema_hash,
                SemanticObjectResolution.status == "RESOLVED",
            )
        ).first()
        if resolution is not None or getattr(reference, "owner_type", None) != "KNOWLEDGE_CHUNK":
            return resolution
        if getattr(reference, "version_id", None) is None:
            return None
        version_reference = session.exec(
            select(SemanticObjectReference).where(
                SemanticObjectReference.owner_type == "KNOWLEDGE_VERSION",
                SemanticObjectReference.version_id == int(reference.version_id),
                SemanticObjectReference.tenant_id == int(reference.tenant_id),
                SemanticObjectReference.declared_key == str(reference.declared_key),
                SemanticObjectReference.source_kind == reference.source_kind,
            )
        ).first()
        if version_reference is None or version_reference.id is None:
            return None
        return session.exec(
            select(SemanticObjectResolution).where(
                SemanticObjectResolution.reference_id == int(version_reference.id),
                SemanticObjectResolution.tenant_id == int(snapshot.tenant_id),
                SemanticObjectResolution.datasource_id == int(snapshot.datasource_id),
                SemanticObjectResolution.physical_schema_hash == snapshot.schema_hash,
                SemanticObjectResolution.status == "RESOLVED",
            )
        ).first()

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
        for rank, citation in enumerate(citations[:top_k], start=1):
            item = _knowledge_context_item(citation, rank=rank)
            separator_size = 1 if selected else 0
            if used + separator_size + len(item) <= max_chars:
                selected.append(citation)
                used += separator_size + len(item)
                continue
            if selected:
                break
            prefix, suffix = _knowledge_context_wrapper(citation, rank=rank)
            content_budget = max_chars - len(prefix) - len(suffix)
            if content_budget < 0:
                break
            selected.append(replace(citation, content=citation.content[:content_budget]))
            break
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
            _knowledge_context_item(item, rank=rank)
            for rank, item in enumerate(citations, start=1)
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


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
