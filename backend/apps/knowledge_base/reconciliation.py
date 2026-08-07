"""Reconcile database publish jobs with their exact Redis task identity."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlmodel import Session

from apps.knowledge_base.lifecycle_models import KnowledgePublishJob
from apps.knowledge_base.publish_jobs import (
    fail_publish_job_after_confirmation,
    fail_publish_job_after_enqueue_rejection,
    fail_publish_job_from_inconsistent_task,
    fail_publish_job_from_task,
    keep_publish_job_pending_confirmation,
    list_due_publish_job_ids,
    lock_publish_job,
    mark_publish_job_queued,
    mark_publish_job_running,
    replace_missing_publish_task,
)
from common.core.config import settings
from common.core.task_queue import (
    EnqueueOutcome,
    EnqueueResult,
    confirm_or_repair_task,
    enqueue_task_confirmed,
)


def _deadline_reached(job: KnowledgePublishJob, now: datetime) -> bool:
    return job.deadline_at is not None and job.deadline_at <= now


def _enqueue_attempts_exhausted(job: KnowledgePublishJob) -> bool:
    return int(job.enqueue_attempts) >= max(1, int(job.max_attempts))


PERMANENT_ENQUEUE_REJECTION_CODES = frozenset(
    {
        "TASK_HANDLER_NOT_REGISTERED",
        "TENANT_SUBSCRIPTION_SUSPENDED",
        "TENANT_TASK_QUOTA_EXCEEDED",
    }
)


def _is_permanent_enqueue_rejection(result: EnqueueResult) -> bool:
    return (
        result.outcome is EnqueueOutcome.REJECTED
        and result.error_code in PERMANENT_ENQUEUE_REJECTION_CODES
    )


def _new_summary() -> dict[str, int]:
    return {
        "examined": 0,
        "pending_confirmation": 0,
        "queued": 0,
        "running": 0,
        "requeued": 0,
        "failed": 0,
    }


async def _enqueue_publish_job(
    session: Session,
    *,
    job: KnowledgePublishJob,
    now: datetime,
    queue_name: str,
    summary: dict[str, int],
) -> EnqueueResult:
    result = await enqueue_task_confirmed(
        "knowledge_base.publish",
        {"job_id": int(job.id), "tenant_id": int(job.tenant_id)},
        created_by=job.create_by,
        tenant_id=int(job.tenant_id),
        queue_name=queue_name,
        max_attempts=int(job.max_attempts),
        dedupe_key=f"knowledge-publish:{job.id}",
    )
    task_id = str(result.task["id"]) if result.task and result.task.get("id") else None
    if result.outcome is EnqueueOutcome.ENQUEUED and task_id:
        if replace_missing_publish_task(
            session,
            job=job,
            task_id=task_id,
            status="QUEUED",
            error_code=None,
            now=now,
        ):
            summary["queued"] += 1
            summary["requeued"] += 1
        return result

    error_code = result.error_code or "TASK_QUEUE_CONFIRMATION_REQUIRED"
    pending_status = "QUEUED" if job.status == "QUEUED" else "QUEUING"
    if replace_missing_publish_task(
        session,
        job=job,
        task_id=task_id,
        status=pending_status,
        error_code=error_code,
        now=now,
    ) and result.outcome is EnqueueOutcome.UNKNOWN:
        summary["pending_confirmation"] += 1
    return result


def _fail_permanent_enqueue_rejection(
    session: Session,
    *,
    job: KnowledgePublishJob,
    result: EnqueueResult,
    now: datetime,
    summary: dict[str, int],
) -> bool:
    if not _is_permanent_enqueue_rejection(result):
        return False
    refreshed = lock_publish_job(session, int(job.id))
    if refreshed is None:
        session.rollback()
        return True
    if fail_publish_job_after_enqueue_rejection(
        session,
        job=refreshed,
        error_code=str(result.error_code),
        now=now,
    ):
        summary["failed"] += 1
    return True


def _advance_confirmed_job(
    session: Session,
    *,
    job: KnowledgePublishJob,
    result: EnqueueResult,
    now: datetime,
    summary: dict[str, int],
) -> None:
    task = result.task or {}
    task_id = str(task.get("id") or job.task_id)
    task_status = str(task.get("status") or "")
    if task_status == "running":
        if mark_publish_job_running(
            session,
            job=job,
            task_id=task_id,
            now=now,
        ):
            summary["running"] += 1
        return
    if task_status == "pending":
        if mark_publish_job_queued(
            session,
            job=job,
            task_id=task_id,
            now=now,
        ):
            summary["queued"] += 1
        return
    if task_status == "succeeded":
        if fail_publish_job_from_inconsistent_task(session, job=job, now=now):
            summary["failed"] += 1
        return
    if task_status == "failed":
        if fail_publish_job_from_task(session, job=job, now=now):
            summary["failed"] += 1
        return
    session.commit()


async def _finish_deadline_enqueue_confirmation(
    session: Session,
    *,
    job: KnowledgePublishJob,
    result: EnqueueResult,
    now: datetime,
    queue_name: str,
    summary: dict[str, int],
) -> None:
    if result.outcome is EnqueueOutcome.ENQUEUED:
        return

    task_id = str(result.task.get("id")) if result.task and result.task.get("id") else None
    confirmation = None
    if result.outcome is EnqueueOutcome.UNKNOWN and task_id:
        confirmation = await confirm_or_repair_task(
            task_id,
            tenant_id=int(job.tenant_id),
            queue_name=queue_name,
        )

    refreshed = lock_publish_job(session, int(job.id))
    if refreshed is None:
        session.rollback()
        return
    if confirmation is not None and confirmation.outcome is EnqueueOutcome.ENQUEUED:
        _advance_confirmed_job(
            session,
            job=refreshed,
            result=confirmation,
            now=now,
            summary=summary,
        )
        return
    if fail_publish_job_after_confirmation(session, job=refreshed, now=now):
        if result.outcome is EnqueueOutcome.UNKNOWN:
            summary["pending_confirmation"] = max(
                0,
                summary["pending_confirmation"] - 1,
            )
        summary["failed"] += 1


async def _reconcile_locked_job(
    session: Session,
    *,
    job: KnowledgePublishJob,
    now: datetime,
    queue_name: str,
    summary: dict[str, int],
) -> None:
    if not job.task_id:
        if _enqueue_attempts_exhausted(job):
            if fail_publish_job_after_confirmation(session, job=job, now=now):
                summary["failed"] += 1
            return
        result = await _enqueue_publish_job(
            session,
            job=job,
            now=now,
            queue_name=queue_name,
            summary=summary,
        )
        if _fail_permanent_enqueue_rejection(
            session,
            job=job,
            result=result,
            now=now,
            summary=summary,
        ):
            return
        if _deadline_reached(job, now):
            await _finish_deadline_enqueue_confirmation(
                session,
                job=job,
                result=result,
                now=now,
                queue_name=queue_name,
                summary=summary,
            )
        return

    result = await confirm_or_repair_task(
        str(job.task_id),
        tenant_id=int(job.tenant_id),
        queue_name=queue_name,
    )
    if result.outcome is EnqueueOutcome.ENQUEUED:
        _advance_confirmed_job(
            session,
            job=job,
            result=result,
            now=now,
            summary=summary,
        )
        return

    if _deadline_reached(job, now):
        if fail_publish_job_after_confirmation(session, job=job, now=now):
            summary["failed"] += 1
        return

    if result.outcome is EnqueueOutcome.REJECTED and result.error_code == "TASK_NOT_FOUND":
        if _enqueue_attempts_exhausted(job):
            if fail_publish_job_after_confirmation(session, job=job, now=now):
                summary["failed"] += 1
            return
        enqueue_result = await _enqueue_publish_job(
            session,
            job=job,
            now=now,
            queue_name=queue_name,
            summary=summary,
        )
        _fail_permanent_enqueue_rejection(
            session,
            job=job,
            result=enqueue_result,
            now=now,
            summary=summary,
        )
        return

    if keep_publish_job_pending_confirmation(
        session,
        job=job,
        error_code=result.error_code or "TASK_QUEUE_CONFIRMATION_REQUIRED",
        now=now,
    ):
        summary["pending_confirmation"] += 1


async def reconcile_publish_jobs(
    session: Session,
    *,
    now: datetime | None = None,
    queue_name: str | None = None,
    limit: int = 100,
    job_id: int | None = None,
) -> dict[str, Any]:
    resolved_now = now or datetime.utcnow()
    resolved_queue = queue_name or settings.TASK_QUEUE_NAME
    summary = _new_summary()
    job_ids = [int(job_id)] if job_id is not None else list_due_publish_job_ids(
        session,
        now=resolved_now,
        queue_timeout_seconds=settings.KNOWLEDGE_PUBLISH_QUEUE_TIMEOUT_SECONDS,
        limit=limit,
    )
    session.rollback()

    for job_id in job_ids:
        job = lock_publish_job(session, job_id)
        if job is None:
            session.rollback()
            continue
        summary["examined"] += 1
        await _reconcile_locked_job(
            session,
            job=job,
            now=resolved_now,
            queue_name=resolved_queue,
            summary=summary,
        )
    return summary
