"""Publish API boundary; queue/job creation is completed by the publish task."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlmodel import select

from apps.knowledge_base.api._helpers import (
    record_tenant_id,
    resolve_record,
    serialize_error,
    unexpected_error,
    v2_write_error,
)
from apps.knowledge_base.cutover import get_capabilities
from apps.knowledge_base.errors import KnowledgeBusinessError
from apps.knowledge_base.lifecycle_models import KnowledgePublishJob
from apps.knowledge_base.permissions import KnowledgePermissionService
from apps.knowledge_base.publish_jobs import prepare_publish_job
from apps.knowledge_base.reconciliation import reconcile_publish_jobs
from common.core.deps import CurrentUser, SessionDep


logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["KnowledgeBase"],
    prefix="/knowledge-base",
    include_in_schema=False,
)


class PublishRequest(BaseModel):
    version_id: int
    revision: int = Field(ge=1)
    content_hash: str


def _job_response(job: KnowledgePublishJob) -> dict[str, Any]:
    return {
        "id": int(job.id),
        "knowledge_base_id": int(job.knowledge_base_id),
        "version_id": int(job.version_id),
        "revision": int(job.revision),
        "content_hash": job.content_hash,
        "status": job.status,
        "task_id": job.task_id,
        "stage": job.stage,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "heartbeat_at": job.heartbeat_at,
        "deadline_at": job.deadline_at,
    }


@router.post("/{id}/publish")
async def publish_knowledge(
    id: int,
    body: PublishRequest,
    session: SessionDep,
    current_user: CurrentUser,
):
    capabilities = get_capabilities(session)
    blocked = v2_write_error(capabilities)
    if blocked is not None:
        return serialize_error(blocked)
    try:
        record = resolve_record(session, knowledge_base_id=id, user=current_user)
        tenant_id = record_tenant_id(record, current_user)
        KnowledgePermissionService().require_manage(current_user, record)
        job = prepare_publish_job(
            session,
            tenant_id=tenant_id,
            knowledge_base_id=id,
            version_id=body.version_id,
            revision=body.revision,
            content_hash=body.content_hash,
            actor_id=int(current_user.id),
        )
        session.commit()
        try:
            await reconcile_publish_jobs(session, job_id=int(job.id), limit=1)
        except Exception:
            # The DB job is durable; the periodic reconciler can retry queue confirmation.
            session.rollback()
            logger.exception("Knowledge publish queue confirmation failed: job_id=%s", job.id)
        session.refresh(job)
        return _job_response(job)
    except KnowledgeBusinessError as error:
        session.rollback()
        return serialize_error(error)
    except Exception:
        session.rollback()
        return unexpected_error()


@router.get("/{id}/publish-job")
async def get_publish_job(
    id: int,
    session: SessionDep,
    current_user: CurrentUser,
):
    try:
        record = resolve_record(session, knowledge_base_id=id, user=current_user)
        tenant_id = record_tenant_id(record, current_user)
        job = session.exec(
            select(KnowledgePublishJob)
            .where(
                KnowledgePublishJob.knowledge_base_id == id,
                KnowledgePublishJob.tenant_id == tenant_id,
            )
            .order_by(KnowledgePublishJob.update_time.desc(), KnowledgePublishJob.id.desc())
        ).first()
        return _job_response(job) if job is not None else None
    except KnowledgeBusinessError as error:
        return serialize_error(error)
    except Exception:
        return unexpected_error()
