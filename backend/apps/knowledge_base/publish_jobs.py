"""Database-authoritative state transitions for knowledge publish jobs."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, or_, update
from sqlmodel import Session, select

from apps.knowledge_base.lifecycle_models import (
    ACTIVE_PUBLISH_JOB_STATUSES,
    KnowledgeBaseVersion,
    KnowledgePublishJob,
)
from apps.knowledge_base.models import KnowledgeBase

PUBLISH_CONFIRMATION_FAILED_CODE = "KNOWLEDGE_PUBLISH_CONFIRMATION_TIMEOUT"
PUBLISH_CONFIRMATION_FAILED_MESSAGE = "发布任务无法确认，已停止本次发布。"
PUBLISH_TASK_FAILED_CODE = "KNOWLEDGE_PUBLISH_TASK_FAILED"
PUBLISH_TASK_FAILED_MESSAGE = "发布任务执行失败，已停止本次发布。"
PUBLISH_TASK_STATE_MISMATCH_CODE = "KNOWLEDGE_PUBLISH_TASK_STATE_MISMATCH"
PUBLISH_TASK_STATE_MISMATCH_MESSAGE = "发布任务状态异常，已停止本次发布。"
PUBLISH_ENQUEUE_REJECTED_MESSAGE = "发布任务提交失败，已停止本次发布。"


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
