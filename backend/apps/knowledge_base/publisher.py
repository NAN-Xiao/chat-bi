"""Crash-safe publication of immutable knowledge versions."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete
from sqlmodel import Session, select

from apps.ai_model.embedding import EmbeddingModelCache
from apps.datasource.embedding.utils import (
    embedding_model_identity,
    embedding_payload_signature,
)
from apps.knowledge_base.chunking import KnowledgeChunkDraft, chunk_knowledge
from apps.knowledge_base.errors import KnowledgeBusinessError
from apps.knowledge_base.lifecycle_models import (
    KnowledgeBaseVersion,
    KnowledgePublishJob,
)
from apps.knowledge_base.models import KnowledgeBase
from apps.knowledge_base.object_projection_models import SemanticObjectReference
from apps.knowledge_base.object_references import (
    ReferenceProjectionContext,
    project_chunk_references,
    project_version_references,
)
from apps.knowledge_base.publish_jobs import (
    fail_publish_job_from_task,
    finalize_publish_job,
)
from apps.knowledge_base.retrieval_models import KnowledgeBaseChunk
from apps.knowledge_base.schemas import KnowledgePayloadAdapter
from common.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PublishedArtifact:
    chunks: tuple[KnowledgeChunkDraft, ...]
    vectors: tuple[tuple[float, ...], ...]
    model_identity: str
    embedding_signature: str
    dimension: int


class KnowledgePublisher:
    """Keep external embedding work outside the final pointer transaction."""

    def __init__(
        self,
        session: Session,
        *,
        embedding_model: Any | None = None,
        chunker: Callable[..., list[KnowledgeChunkDraft]] = chunk_knowledge,
    ) -> None:
        self.session = session
        self.embedding_model = embedding_model
        self.chunker = chunker

    def publish_version(
        self,
        job_id: int,
        *,
        task_id: str | None = None,
        publish_by: int | None = None,
    ) -> dict[str, Any]:
        job, version, record = self._claim(job_id, task_id=task_id)
        try:
            payload = KnowledgePayloadAdapter.validate_python(version.payload)
            chunks = self._chunk(payload, version, job_id=int(job.id))
            references = project_version_references(
                payload,
                ReferenceProjectionContext(
                    tenant_id=int(version.tenant_id),
                    scope=_scope_value(record.visibility_scope),
                ),
            )
            artifact = self._embed(job, version, chunks)
            self._assert_snapshot(job_id, job.revision, job.content_hash, version.id)
            self._persist_artifacts(
                version=version,
                record=record,
                payload=payload,
                references=references,
                artifact=artifact,
                job_id=int(job.id),
            )
            if not finalize_publish_job(self.session, job_id=int(job.id), now=datetime.utcnow()):
                raise KnowledgeBusinessError(
                    code="KNOWLEDGE_PUBLISH_SNAPSHOT_STALE",
                    message="发布快照已失效，请重新发布。",
                    status_code=409,
                    error_type="CONFLICT",
                )
            self.session.commit()
            return {"job_id": int(job.id), "version_id": int(version.id), "status": "SUCCEEDED"}
        except Exception as exc:
            self.session.rollback()
            logger.exception("Knowledge publication failed: job_id=%s", job_id)
            self._fail(job_id, exc)
            return {
                "job_id": int(job_id),
                "version_id": int(getattr(version, "id", 0) or 0),
                "status": "FAILED",
                "error_code": "KNOWLEDGE_PUBLISH_FAILED",
                "error_message": _safe_error_message(exc),
            }

    def _claim(self, job_id: int, *, task_id: str | None) -> tuple[Any, Any, Any]:
        job = self.session.exec(
            select(KnowledgePublishJob)
            .where(KnowledgePublishJob.id == int(job_id))
            .with_for_update()
            .execution_options(populate_existing=True)
        ).first()
        if job is None:
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_PUBLISH_JOB_NOT_FOUND",
                message="发布任务不存在。",
                status_code=404,
                error_type="NOT_FOUND",
            )
        if str(job.status) not in {"QUEUING", "QUEUED", "RUNNING"}:
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_PUBLISH_JOB_FINISHED",
                message="发布任务已经结束，请刷新任务状态。",
                status_code=409,
                error_type="CONFLICT",
            )
        if task_id and job.task_id and str(job.task_id) != str(task_id):
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_PUBLISH_TASK_STALE",
                message="发布任务已被其他 Worker 接管。",
                status_code=409,
                error_type="CONFLICT",
            )
        if task_id and not job.task_id:
            job.task_id = str(task_id)
        job.status = "RUNNING"
        job.stage = "PARSE"
        job.attempt = int(job.attempt or 0) + 1
        job.heartbeat_at = datetime.utcnow()
        job.update_time = datetime.utcnow()
        self.session.add(job)
        self.session.commit()
        version = self.session.exec(
            select(KnowledgeBaseVersion)
            .where(
                KnowledgeBaseVersion.id == job.version_id,
                KnowledgeBaseVersion.knowledge_base_id == job.knowledge_base_id,
                KnowledgeBaseVersion.tenant_id == job.tenant_id,
            )
            .execution_options(populate_existing=True)
        ).first()
        record = self.session.exec(
            select(KnowledgeBase)
            .where(
                KnowledgeBase.id == job.knowledge_base_id,
                KnowledgeBase.tenant_id == job.tenant_id,
            )
            .execution_options(populate_existing=True)
        ).first()
        if version is None or record is None or record.publishing_version_id != version.id:
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_PUBLISH_SNAPSHOT_STALE",
                message="发布快照已失效，请重新发布。",
                status_code=409,
                error_type="CONFLICT",
            )
        if int(version.revision) != int(job.revision) or version.content_hash != job.content_hash:
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_PUBLISH_SNAPSHOT_STALE",
                message="发布快照已失效，请重新发布。",
                status_code=409,
                error_type="CONFLICT",
            )
        return job, version, record

    def _chunk(self, payload: Any, version: Any, *, job_id: int) -> list[KnowledgeChunkDraft]:
        self._set_stage(job_id=job_id, stage="CHUNK")
        return self.chunker(
            payload=payload,
            chunk_size=settings.KNOWLEDGE_CHUNK_SIZE,
            overlap=settings.KNOWLEDGE_CHUNK_OVERLAP,
        )

    def _embed(self, job: Any, version: Any, chunks: list[KnowledgeChunkDraft]) -> PublishedArtifact:
        self._set_stage(job_id=int(job.id), stage="EMBED")
        model = self.embedding_model or EmbeddingModelCache.get_model()
        texts = [chunk.content for chunk in chunks]
        if not texts:
            raise ValueError("知识内容为空，无法建立检索索引。")
        vectors: list[list[float]] = []
        batch_size = max(1, int(getattr(getattr(model, "config", None), "batch_size", 32)))
        for start in range(0, len(texts), batch_size):
            self._assert_snapshot(int(job.id), int(job.revision), str(job.content_hash), int(version.id))
            batch = texts[start:start + batch_size]
            batch_vectors = model.embed_documents(batch)
            if len(batch_vectors) != len(batch):
                raise ValueError("Embedding 返回数量与知识切片数量不一致。")
            vectors.extend([[float(value) for value in vector] for vector in batch_vectors])
            self._heartbeat(int(job.id), stage="EMBED")
        dimension = len(vectors[0]) if vectors else 0
        if dimension <= 0 or any(len(vector) != dimension for vector in vectors):
            raise ValueError("Embedding 向量维度不一致。")
        model_identity = embedding_model_identity(model)
        signature = embedding_payload_signature(model_identity, dimension)
        return PublishedArtifact(
            chunks=tuple(chunks),
            vectors=tuple(tuple(vector) for vector in vectors),
            model_identity=model_identity,
            embedding_signature=signature,
            dimension=dimension,
        )

    def _persist_artifacts(
        self,
        *,
        version: Any,
        record: Any,
        payload: Any,
        references: list[Any],
        artifact: PublishedArtifact,
        job_id: int,
    ) -> None:
        self._set_stage(job_id=job_id, stage="FINALIZE")
        self.session.exec(
            delete(SemanticObjectReference).where(
                SemanticObjectReference.owner_type == "KNOWLEDGE_VERSION",
                SemanticObjectReference.version_id == int(version.id),
            )
        )
        self.session.exec(
            delete(KnowledgeBaseChunk).where(KnowledgeBaseChunk.version_id == int(version.id))
        )
        for reference in references:
            self.session.add(self._reference_row(reference, version=version))
        self.session.flush()
        for chunk, vector in zip(artifact.chunks, artifact.vectors, strict=True):
            row = KnowledgeBaseChunk(
                knowledge_base_id=int(version.knowledge_base_id),
                version_id=int(version.id),
                tenant_id=int(version.tenant_id),
                visibility_scope=_scope_value(record.visibility_scope),
                chunk_index=int(chunk.chunk_index),
                section_path=chunk.section_path,
                source_block_id=chunk.source_block_id,
                content=chunk.content,
                token_count=chunk.token_count,
                content_hash=chunk.content_hash,
                embedding_model=artifact.model_identity,
                embedding_signature=artifact.embedding_signature,
                embedding_dimension=artifact.dimension,
                embedding=list(vector),
                create_time=datetime.utcnow(),
            )
            self.session.add(row)
            self.session.flush()
            if not references:
                continue
            for reference in project_chunk_references(payload, chunk_text=chunk.content):
                self.session.add(self._reference_row(reference, version=version, chunk=row))
        version.index_status = "READY"
        self.session.add(version)
        self.session.flush()

    @staticmethod
    def _reference_row(reference: Any, *, version: Any, chunk: Any | None = None) -> SemanticObjectReference:
        path = reference.declared_path
        owner_type = "KNOWLEDGE_CHUNK" if chunk is not None else "KNOWLEDGE_VERSION"
        return SemanticObjectReference(
            tenant_id=int(version.tenant_id),
            owner_type=owner_type,
            owner_id=int(chunk.id if chunk is not None else version.id),
            knowledge_base_id=int(version.knowledge_base_id),
            version_id=int(version.id),
            chunk_id=int(chunk.id) if chunk is not None else None,
            object_type=reference.object_type,
            datasource_id=reference.datasource_id,
            catalog_name=path.catalog,
            schema_name=path.schema,
            table_name=path.table,
            field_name=path.field,
            json_path=path.json_path,
            event_name=path.event_name,
            event_property_key=path.event_property_key,
            declared_key=reference.declared_key,
            resolution_status=reference.resolution_status,
            source_kind=reference.source_kind,
            create_time=datetime.utcnow(),
        )

    def _assert_snapshot(self, job_id: int, revision: int, content_hash: str, version_id: int) -> None:
        row = self.session.exec(
            select(KnowledgePublishJob).where(KnowledgePublishJob.id == int(job_id))
        ).first()
        if row is None or str(row.status) not in {"RUNNING", "QUEUED", "QUEUING"}:
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_PUBLISH_TASK_STALE",
                message="发布任务已停止，索引构建已取消。",
                status_code=409,
                error_type="CONFLICT",
            )
        if int(row.revision) != int(revision) or row.content_hash != content_hash or int(row.version_id) != int(version_id):
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_PUBLISH_SNAPSHOT_STALE",
                message="发布快照已失效，请重新发布。",
                status_code=409,
                error_type="CONFLICT",
            )

    def _heartbeat(self, job_id: int, *, stage: str) -> None:
        row = self.session.exec(
            select(KnowledgePublishJob).where(KnowledgePublishJob.id == int(job_id))
        ).first()
        if row is None:
            raise ValueError("发布任务不存在。")
        row.stage = stage
        row.heartbeat_at = datetime.utcnow()
        row.update_time = datetime.utcnow()
        self.session.add(row)
        self.session.commit()

    def _set_stage(self, *, job_id: int, stage: str) -> None:
        job = self.session.exec(
            select(KnowledgePublishJob).where(KnowledgePublishJob.id == int(job_id))
        ).first()
        if job is not None:
            self._heartbeat(int(job.id), stage=stage)

    def _fail(self, job_id: int, error: Exception) -> None:
        job = self.session.exec(
            select(KnowledgePublishJob).where(KnowledgePublishJob.id == int(job_id))
        ).first()
        if job is None:
            self.session.rollback()
            return
        fail_publish_job_from_task(self.session, job=job, now=datetime.utcnow())


def _safe_error_message(error: Exception) -> str:
    if isinstance(error, KnowledgeBusinessError):
        return error.message
    if isinstance(error, ValueError):
        return str(error)[:500] or "知识索引构建失败。"
    return "知识索引构建失败，请稍后重试。"


def _scope_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")
