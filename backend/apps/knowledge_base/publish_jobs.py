"""Database-authoritative state transitions for knowledge publish jobs."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, or_, update
from sqlmodel import Session, select

from apps.knowledge_base.errors import KnowledgeBusinessError
from apps.knowledge_base.lifecycle_models import (
    ACTIVE_PUBLISH_JOB_STATUSES,
    KnowledgeBaseVersion,
    KnowledgePublishJob,
)
from apps.knowledge_base.models import KnowledgeBase
from common.core.config import settings

PUBLISH_CONFIRMATION_FAILED_CODE = "KNOWLEDGE_PUBLISH_CONFIRMATION_TIMEOUT"
PUBLISH_CONFIRMATION_FAILED_MESSAGE = "发布任务无法确认，已停止本次发布。"
PUBLISH_TASK_FAILED_CODE = "KNOWLEDGE_PUBLISH_TASK_FAILED"
PUBLISH_TASK_FAILED_MESSAGE = "发布任务执行失败，已停止本次发布。"
PUBLISH_TASK_STATE_MISMATCH_CODE = "KNOWLEDGE_PUBLISH_TASK_STATE_MISMATCH"
PUBLISH_TASK_STATE_MISMATCH_MESSAGE = "发布任务状态异常，已停止本次发布。"
PUBLISH_ENQUEUE_REJECTED_MESSAGE = "发布任务提交失败，已停止本次发布。"


def prepare_publish_job(
    session: Session,
    *,
    tenant_id: int,
    knowledge_base_id: int,
    version_id: int,
    revision: int,
    content_hash: str,
    actor_id: int | None,
    now: datetime | None = None,
) -> KnowledgePublishJob:
    """Claim one immutable draft snapshot and create an idempotent DB job."""
    current_time = now or datetime.now()
    record = session.exec(
        select(KnowledgeBase)
        .where(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.tenant_id == tenant_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if record is None:
        raise KnowledgeBusinessError(
            code="KNOWLEDGE_NOT_FOUND",
            message="知识不存在或已被删除。",
            status_code=404,
            error_type="NOT_FOUND",
        )
    version = session.exec(
        select(KnowledgeBaseVersion)
        .where(
            KnowledgeBaseVersion.id == version_id,
            KnowledgeBaseVersion.knowledge_base_id == knowledge_base_id,
            KnowledgeBaseVersion.tenant_id == tenant_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if version is None:
        raise KnowledgeBusinessError(
            code="KNOWLEDGE_VERSION_NOT_FOUND",
            message="知识版本不存在。",
            status_code=404,
            error_type="NOT_FOUND",
        )

    existing = session.exec(
        select(KnowledgePublishJob)
        .where(
            KnowledgePublishJob.knowledge_base_id == knowledge_base_id,
            KnowledgePublishJob.tenant_id == tenant_id,
            KnowledgePublishJob.version_id == version_id,
            KnowledgePublishJob.revision == revision,
            KnowledgePublishJob.content_hash == content_hash,
            KnowledgePublishJob.status.in_(ACTIVE_PUBLISH_JOB_STATUSES),
        )
        .with_for_update()
    ).first()
    if existing is not None:
        return existing
    if record.publishing_version_id is not None:
        raise KnowledgeBusinessError(
            code="KNOWLEDGE_PUBLISHING",
            message="该知识正在发布中，请稍后再试。",
            status_code=409,
            error_type="CONFLICT",
        )
    if record.draft_version_id != version_id:
        raise KnowledgeBusinessError(
            code="KNOWLEDGE_DRAFT_CONFLICT",
            message="该知识已被其他用户更新，请刷新后重新编辑。",
            status_code=409,
            error_type="CONFLICT",
        )
    status = version.status.value if hasattr(version.status, "value") else str(version.status)
    if status != "READY_TO_PUBLISH" or int(version.revision) != int(revision) or version.content_hash != content_hash:
        raise KnowledgeBusinessError(
            code="KNOWLEDGE_VERSION_NOT_READY",
            message="知识尚未通过最新校验，请重新校验后发布。",
            status_code=409,
            error_type="CONFLICT",
        )

    job = KnowledgePublishJob(
        tenant_id=tenant_id,
        knowledge_base_id=knowledge_base_id,
        version_id=version_id,
        revision=revision,
        content_hash=content_hash,
        status="QUEUING",
        create_by=actor_id,
        create_time=current_time,
        update_time=current_time,
        heartbeat_at=current_time,
        deadline_at=current_time + timedelta(seconds=max(1, int(settings.KNOWLEDGE_PUBLISH_TIMEOUT_SECONDS))),
    )
    session.add(job)
    version.status = "PUBLISHING"
    record.publishing_version_id = version_id
    session.flush()
    return job


def list_due_publish_job_ids(
    session: Session,
    *,
    now: datetime,
    queue_timeout_seconds: int,
    limit: int = 100,
) -> list[int]:
    queue_due_at = now - timedelta(seconds=max(1, int(queue_timeout_seconds)))
    rows = session.exec(
        select(KnowledgePublishJob.id)
        .where(
            KnowledgePublishJob.status.in_(ACTIVE_PUBLISH_JOB_STATUSES),
            or_(
                and_(
                    KnowledgePublishJob.status == "QUEUING",
                    or_(
                        KnowledgePublishJob.last_enqueue_at.is_(None),
                        KnowledgePublishJob.last_enqueue_at <= queue_due_at,
                        KnowledgePublishJob.deadline_at <= now,
                    ),
                ),
                and_(
                    KnowledgePublishJob.status == "QUEUED",
                    or_(
                        KnowledgePublishJob.last_enqueue_at.is_(None),
                        KnowledgePublishJob.last_enqueue_at <= queue_due_at,
                        KnowledgePublishJob.deadline_at <= now,
                    ),
                ),
                and_(
                    KnowledgePublishJob.status == "RUNNING",
                    KnowledgePublishJob.deadline_at <= now,
                ),
            ),
        )
        .order_by(KnowledgePublishJob.update_time, KnowledgePublishJob.id)
        .limit(max(1, int(limit)))
    ).all()
    return [int(job_id) for job_id in rows]


def lock_publish_job(session: Session, job_id: int) -> KnowledgePublishJob | None:
    return session.exec(
        select(KnowledgePublishJob)
        .where(
            KnowledgePublishJob.id == job_id,
            KnowledgePublishJob.status.in_(ACTIVE_PUBLISH_JOB_STATUSES),
        )
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    ).first()


def _commit_cas(session: Session, statement) -> bool:
    result = session.exec(statement)
    changed = int(result.rowcount or 0) == 1
    session.commit()
    return changed


def mark_publish_job_queued(
    session: Session,
    *,
    job: KnowledgePublishJob,
    task_id: str,
    now: datetime,
) -> bool:
    return _commit_cas(
        session,
        update(KnowledgePublishJob)
        .where(
            KnowledgePublishJob.id == job.id,
            KnowledgePublishJob.status == "QUEUING",
        )
        .values(
            status="QUEUED",
            task_id=task_id,
            error_code=None,
            error_message=None,
            update_time=now,
        ),
    )


def mark_publish_job_running(
    session: Session,
    *,
    job: KnowledgePublishJob,
    task_id: str,
    now: datetime,
) -> bool:
    return _commit_cas(
        session,
        update(KnowledgePublishJob)
        .where(
            KnowledgePublishJob.id == job.id,
            KnowledgePublishJob.status.in_(("QUEUING", "QUEUED")),
            KnowledgePublishJob.task_id == task_id,
        )
        .values(
            status="RUNNING",
            error_code=None,
            error_message=None,
            update_time=now,
        ),
    )


def keep_publish_job_pending_confirmation(
    session: Session,
    *,
    job: KnowledgePublishJob,
    error_code: str,
    now: datetime,
) -> bool:
    return _commit_cas(
        session,
        update(KnowledgePublishJob)
        .where(
            KnowledgePublishJob.id == job.id,
            KnowledgePublishJob.status == job.status,
            KnowledgePublishJob.status.in_(("QUEUING", "QUEUED")),
            KnowledgePublishJob.task_id == job.task_id,
        )
        .values(
            error_code=error_code,
            error_message=None,
            update_time=now,
        ),
    )


def replace_missing_publish_task(
    session: Session,
    *,
    job: KnowledgePublishJob,
    task_id: str | None,
    status: str,
    error_code: str | None,
    now: datetime,
) -> bool:
    return _commit_cas(
        session,
        update(KnowledgePublishJob)
        .where(
            KnowledgePublishJob.id == job.id,
            KnowledgePublishJob.status == job.status,
            KnowledgePublishJob.status.in_(("QUEUING", "QUEUED")),
            KnowledgePublishJob.task_id == job.task_id,
        )
        .values(
            status=status,
            task_id=task_id,
            enqueue_attempts=KnowledgePublishJob.enqueue_attempts + 1,
            last_enqueue_at=now,
            error_code=error_code,
            error_message=None,
            update_time=now,
        ),
    )


def _finish_failed_publish_job(
    session: Session,
    *,
    job: KnowledgePublishJob,
    error_code: str,
    error_message: str,
    now: datetime,
) -> bool:
    result = session.exec(
        update(KnowledgePublishJob)
        .where(
            KnowledgePublishJob.id == job.id,
            KnowledgePublishJob.status.in_(ACTIVE_PUBLISH_JOB_STATUSES),
        )
        .values(
            status="FAILED",
            error_code=error_code,
            error_message=error_message,
            update_time=now,
        )
    )
    if int(result.rowcount or 0) != 1:
        session.commit()
        return False

    session.exec(
        update(KnowledgeBaseVersion)
        .where(
            KnowledgeBaseVersion.id == job.version_id,
            KnowledgeBaseVersion.knowledge_base_id == job.knowledge_base_id,
            KnowledgeBaseVersion.tenant_id == job.tenant_id,
            KnowledgeBaseVersion.status == "PUBLISHING",
        )
        .values(
            status="PUBLISH_FAILED",
            error_message=error_message,
        )
    )
    session.exec(
        update(KnowledgeBase)
        .where(
            KnowledgeBase.id == job.knowledge_base_id,
            KnowledgeBase.tenant_id == job.tenant_id,
            KnowledgeBase.publishing_version_id == job.version_id,
        )
        .values(publishing_version_id=None)
    )
    session.commit()
    return True


def fail_publish_job_after_confirmation(
    session: Session,
    *,
    job: KnowledgePublishJob,
    now: datetime,
) -> bool:
    return _finish_failed_publish_job(
        session,
        job=job,
        error_code=PUBLISH_CONFIRMATION_FAILED_CODE,
        error_message=PUBLISH_CONFIRMATION_FAILED_MESSAGE,
        now=now,
    )


def fail_publish_job_from_task(
    session: Session,
    *,
    job: KnowledgePublishJob,
    now: datetime,
) -> bool:
    return _finish_failed_publish_job(
        session,
        job=job,
        error_code=PUBLISH_TASK_FAILED_CODE,
        error_message=PUBLISH_TASK_FAILED_MESSAGE,
        now=now,
    )


def fail_publish_job_from_inconsistent_task(
    session: Session,
    *,
    job: KnowledgePublishJob,
    now: datetime,
) -> bool:
    return _finish_failed_publish_job(
        session,
        job=job,
        error_code=PUBLISH_TASK_STATE_MISMATCH_CODE,
        error_message=PUBLISH_TASK_STATE_MISMATCH_MESSAGE,
        now=now,
    )


def fail_publish_job_after_enqueue_rejection(
    session: Session,
    *,
    job: KnowledgePublishJob,
    error_code: str,
    now: datetime,
) -> bool:
    return _finish_failed_publish_job(
        session,
        job=job,
        error_code=error_code,
        error_message=PUBLISH_ENQUEUE_REJECTED_MESSAGE,
        now=now,
    )


def finalize_publish_job(
    session: Session,
    *,
    job_id: int,
    now: datetime | None = None,
) -> bool:
    """Atomically switch the current version after all derived artifacts are ready."""
    resolved_now = now or datetime.utcnow()
    job = session.exec(
        select(KnowledgePublishJob)
        .where(KnowledgePublishJob.id == int(job_id))
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if job is None or job.status != "RUNNING":
        return False
    version = session.exec(
        select(KnowledgeBaseVersion)
        .where(
            KnowledgeBaseVersion.id == job.version_id,
            KnowledgeBaseVersion.knowledge_base_id == job.knowledge_base_id,
            KnowledgeBaseVersion.tenant_id == job.tenant_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    record = session.exec(
        select(KnowledgeBase)
        .where(
            KnowledgeBase.id == job.knowledge_base_id,
            KnowledgeBase.tenant_id == job.tenant_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if version is None or record is None:
        return False
    if (
        record.publishing_version_id != version.id
        or version.revision != job.revision
        or version.content_hash != job.content_hash
        or str(getattr(version.index_status, "value", version.index_status)) != "READY"
        or str(version.status) not in {"PUBLISHING", "KnowledgeVersionStatus.PUBLISHING"}
    ):
        return False
    if record.current_version_id and record.current_version_id != version.id:
        old = session.exec(
            select(KnowledgeBaseVersion)
            .where(
                KnowledgeBaseVersion.id == record.current_version_id,
                KnowledgeBaseVersion.knowledge_base_id == record.id,
                KnowledgeBaseVersion.tenant_id == record.tenant_id,
            )
            .with_for_update()
        ).first()
        if old is not None:
            old.status = "SUPERSEDED"
            session.add(old)
    version.status = "PUBLISHED"
    version.index_status = "READY"
    version.publish_by = job.create_by
    version.publish_time = resolved_now
    version.error_message = None
    record.current_version_id = version.id
    record.draft_version_id = None
    record.publishing_version_id = None
    record.publish_by = job.create_by
    record.publish_time = resolved_now
    job.status = "SUCCEEDED"
    job.error_code = None
    job.error_message = None
    job.update_time = resolved_now
    session.add_all((version, record, job))
    session.flush()
    return True
