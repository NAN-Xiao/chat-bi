"""
脚本说明：这个脚本放后端业务里较长或较复杂的处理流程，把一次任务分成可维护的步骤。
"""
from __future__ import annotations

from typing import Any

from sqlmodel import Session

from apps.chat.curd.skill_object_projection import rebuild_all_skill_object_projections
from apps.chat.curd.skill_object_references import SKILL_PROJECTOR_VERSION
from apps.knowledge_base.backfill import run_backfill_v2
from apps.knowledge_base.publisher import KnowledgePublisher
from apps.knowledge_base.reconciliation import reconcile_publish_jobs
from apps.knowledge_base.storage_probe import record_storage_probe_receipt
from common.core.db import engine
from common.core.task_queue import (
    current_task_context,
    task_handler,
)


@task_handler("knowledge_base.backfill_v2")
def backfill_knowledge_base_v2(payload: dict[str, Any]) -> dict[str, Any]:
    """Run one registered, resumable legacy-to-V2 backfill task."""
    with Session(engine) as session:
        report = run_backfill_v2(
            session,
            page_size=int(payload.get("page_size") or 100),
            restart_scan=bool(payload.get("restart_scan", False)),
            max_pages=int(payload["max_pages"]) if payload.get("max_pages") else None,
        )
        return report.as_dict()


@task_handler("knowledge_base.project_data_skill_objects")
def project_data_skill_objects(payload: dict[str, Any]) -> dict[str, Any]:
    """Rebuild a bounded batch of existing Data Skill object projections."""
    with Session(engine) as session:
        reports = rebuild_all_skill_object_projections(
            session,
            projector_version=str(payload.get("projector_version") or SKILL_PROJECTOR_VERSION),
            limit=int(payload.get("limit") or 500),
            after_skill_id=int(payload.get("after_skill_id") or 0),
        )
        next_cursor = max((item.skill_id for item in reports), default=None)
        return {
            "scanned": len(reports),
            "ready": sum(item.status == "READY" for item in reports),
            "failed": sum(item.status == "FAILED" for item in reports),
            "deleted": sum(item.status == "DELETED" for item in reports),
            "next_cursor": next_cursor,
            "reports": [item.as_dict() for item in reports],
        }


@task_handler("data_skill.rebuild_object_projections")
def rebuild_data_skill_object_projections(payload: dict[str, Any]) -> dict[str, Any]:
    """Compatibility task name used by the migration runbook."""
    return project_data_skill_objects(payload)


@task_handler("knowledge_base.reconcile_publish_jobs")
async def reconcile_knowledge_publish_jobs(payload: dict[str, Any]) -> dict[str, Any]:
    with Session(engine) as session:
        return await reconcile_publish_jobs(
            session,
            limit=int(payload.get("limit") or 100),
        )


@task_handler("knowledge_base.storage_probe")
def verify_knowledge_storage_probe(payload: dict[str, Any]) -> dict[str, Any]:
    context = current_task_context() or {}
    worker_id = str(context.get("worker") or "")
    queue_name = str(context.get("queue") or "")
    if not worker_id or not queue_name:
        raise ValueError("共享文件存储校验缺少 Worker 身份或队列信息。")
    generation = int(payload["generation"])
    with Session(engine) as session:
        receipt = record_storage_probe_receipt(
            session,
            generation=generation,
            worker_id=worker_id,
            queue_name=queue_name,
        )
        return {
            "generation": generation,
            "worker_id": worker_id,
            "queue_name": queue_name,
            "content_hash": receipt.content_hash,
        }


@task_handler("knowledge_base.publish")
@task_handler("knowledge_base.publish_version")
def publish_knowledge_base_version(payload: dict[str, Any]) -> dict[str, Any]:
    """Run one registered, tenant-scoped knowledge publication job."""
    job_id = int(payload["job_id"])
    context = current_task_context() or {}
    task_id = str(context.get("id") or payload.get("task_id") or "") or None
    with Session(engine) as session:
        return KnowledgePublisher(session).publish_version(job_id, task_id=task_id)
