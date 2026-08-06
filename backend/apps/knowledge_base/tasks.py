"""
脚本说明：这个脚本放后端业务里较长或较复杂的处理流程，把一次任务分成可维护的步骤。
"""
from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from sqlmodel import Session

from apps.knowledge_base.models import KnowledgeBase, KnowledgeBaseStatusEnum
from apps.knowledge_base.publisher import KnowledgePublisher
from apps.knowledge_base.reconciliation import reconcile_publish_jobs
from apps.knowledge_base.repository import (
    KnowledgeBusinessError,
    KnowledgeMigrationStateRepository,
)
from apps.knowledge_base.storage_probe import record_storage_probe_receipt
from common.core.db import engine
from common.core.task_queue import (
    current_task_context,
    current_task_tenant_id,
    task_handler,
)
from common.utils.file_utils import AppFileUtils


def _decode_markdown(path: Path) -> str:
    """
    是什么：_decode_markdown 是一个可以复用的小步骤，负责后端业务相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端业务里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return data.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace").strip()


def _local_name(tag: str) -> str:
    """
    是什么：_local_name 是一个可以复用的小步骤，负责后端业务相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端业务里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _paragraph_text(paragraph: ET.Element) -> str:
    """
    是什么：_paragraph_text 是一个可以复用的小步骤，负责后端业务相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端业务里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    parts: list[str] = []
    for node in paragraph.iter():
        name = _local_name(node.tag)
        if name == "t":
            parts.append(node.text or "")
        elif name == "tab":
            parts.append("\t")
        elif name in {"br", "cr"}:
            parts.append("\n")
    return "".join(parts).strip()


def _decode_docx(path: Path) -> str:
    """
    是什么：_decode_docx 是一个可以复用的小步骤，负责后端业务相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端业务里这一步需要处理的内容整理好，交给后面的代码继续用。
    """
    with zipfile.ZipFile(path) as archive:
        try:
            document_xml = archive.read("word/document.xml")
        except KeyError as exc:
            raise ValueError("Word document is missing word/document.xml") from exc

    root = ET.fromstring(document_xml)
    paragraphs = [
        text
        for text in (_paragraph_text(paragraph) for paragraph in root.iter() if _local_name(paragraph.tag) == "p")
        if text
    ]
    return "\n".join(paragraphs).strip()


def _extract_content(record: KnowledgeBase) -> str:
    """
    是什么：_extract_content 是一个可以复用的小步骤，负责后端业务相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端业务的原始内容拆开、转换或整理，变成程序更好处理的格式。
    """
    if not record.file_id:
        raise ValueError("Knowledge base file is missing")
    path = Path(AppFileUtils.get_file_path(record.file_id))
    if not path.exists():
        raise ValueError("Knowledge base file does not exist")

    ext = (record.file_ext or path.suffix or "").lower()
    if ext in {".md", ".markdown"}:
        content = _decode_markdown(path)
    elif ext == ".docx":
        content = _decode_docx(path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")
    if not content:
        raise ValueError("Document content is empty")
    return content


def _phase_rejected_result(
    record_id: int,
    tenant_id: int,
    error: KnowledgeBusinessError,
) -> dict[str, Any]:
    return {
        "id": record_id,
        "tenant_id": tenant_id,
        "status": "REJECTED_BY_PHASE",
        "error_code": error.code,
    }


@task_handler("knowledge_base.process_document")
def process_knowledge_base_document(payload: dict[str, Any]) -> dict[str, Any]:
    """
    是什么：process_knowledge_base_document 是一个可以复用的小步骤，负责后端业务相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端业务的主要流程跑起来，一步步调用需要的处理。
    """
    record_id = int(payload["id"])
    tenant_id = int(payload.get("tenant_id") or current_task_tenant_id())

    with Session(engine) as session:
        record = session.get(KnowledgeBase, record_id)
        if record is None or int(record.tenant_id) != tenant_id:
            return {"id": record_id, "tenant_id": tenant_id, "status": "missing"}

        try:
            KnowledgeMigrationStateRepository.lock_for_legacy_write(session)
        except KnowledgeBusinessError as exc:
            session.rollback()
            return _phase_rejected_result(record_id, tenant_id, exc)

        now = datetime.now()
        record.status = KnowledgeBaseStatusEnum.PROCESSING
        record.error_message = None
        record.update_time = now
        session.add(record)
        session.commit()
        session.refresh(record)

        try:
            content = _extract_content(record)
            target_status = KnowledgeBaseStatusEnum.READY
            error_message = None
        except Exception as exc:
            content = None
            target_status = KnowledgeBaseStatusEnum.FAILED
            error_message = str(exc)[:1000]

        try:
            KnowledgeMigrationStateRepository.lock_for_legacy_write(session)
        except KnowledgeBusinessError as exc:
            session.rollback()
            return _phase_rejected_result(record_id, tenant_id, exc)

        if target_status == KnowledgeBaseStatusEnum.READY:
            record.content = content
        record.status = target_status
        record.error_message = error_message
        record.update_time = datetime.now()
        session.add(record)
        session.commit()

        return {
            "id": record_id,
            "tenant_id": tenant_id,
            "status": record.status.value if hasattr(record.status, "value") else record.status,
        }


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


@task_handler("knowledge_base.publish_version")
def publish_knowledge_base_version(payload: dict[str, Any]) -> dict[str, Any]:
    """Run one registered, tenant-scoped knowledge publication job."""
    job_id = int(payload["job_id"])
    context = current_task_context() or {}
    task_id = str(context.get("id") or payload.get("task_id") or "") or None
    with Session(engine) as session:
        return KnowledgePublisher(session).publish_version(job_id, task_id=task_id)
