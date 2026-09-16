"""
脚本说明：这个脚本放后端业务里较长或较复杂的处理流程，把一次任务分成可维护的步骤。
"""
from __future__ import annotations

import logging
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from sqlmodel import Session

from apps.knowledge_base.context import KnowledgeContextError, build_knowledge_context, lock_knowledge_activation
from apps.knowledge_base.models import KnowledgeBase, KnowledgeBaseStatusEnum
from common.core.db import engine
from common.core.task_queue import current_task_context, current_task_tenant_id, task_handler
from common.utils.file_utils import AppFileUtils

logger = logging.getLogger(__name__)
KNOWLEDGE_PROCESS_FAILED_MESSAGE = "文档处理失败，请确认文件格式和内容后重试。"


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
            raise ValueError("Word 文档结构无效，缺少正文内容。") from exc

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
        raise ValueError("知识库源文件不存在。")
    path = Path(AppFileUtils.get_file_path(record.file_id))
    if not path.exists():
        raise ValueError("知识库源文件不存在。")

    ext = (record.file_ext or path.suffix or "").lower()
    if ext in {".md", ".markdown"}:
        content = _decode_markdown(path)
    elif ext == ".docx":
        content = _decode_docx(path)
    else:
        raise ValueError(f"不支持的知识库文件类型：{ext or '未知类型'}。")
    if not content:
        raise ValueError("文档正文为空，无法处理。")
    return content


@task_handler("knowledge_base.process_document")
def process_knowledge_base_document(payload: dict[str, Any]) -> dict[str, Any]:
    """
    是什么：process_knowledge_base_document 是一个可以复用的小步骤，负责后端业务相关的一件事。
    谁调用：后端其他代码在需要这个功能时会调用它。
    做了什么：把后端业务的主要流程跑起来，一步步调用需要的处理。
    """
    record_id = int(payload["id"])
    tenant_id = int(payload.get("tenant_id") or current_task_tenant_id())
    expected_file_id = payload.get("file_id")

    with Session(engine) as session:
        record = session.get(KnowledgeBase, record_id, with_for_update=True)
        if record is None or int(record.tenant_id) != tenant_id:
            return {"id": record_id, "tenant_id": tenant_id, "status": "missing"}
        if "file_id" not in payload:
            # Narrow rollout support for already-queued legacy jobs: the stored
            # task ID must prove that this job still owns the current upload.
            legacy_task_id = (current_task_context() or {}).get("id")
            if not legacy_task_id or record.task_id != legacy_task_id:
                return {"id": record_id, "tenant_id": tenant_id, "status": "superseded"}
            expected_file_id = record.file_id
            logger.info("Processing verified legacy knowledge upload task: id=%s task_id=%s", record_id, legacy_task_id)
        if record.file_id != expected_file_id:
            return {"id": record_id, "tenant_id": tenant_id, "status": "superseded"}
        if record.status not in {KnowledgeBaseStatusEnum.PENDING, KnowledgeBaseStatusEnum.PROCESSING}:
            return {"id": record_id, "tenant_id": tenant_id, "status": record.status}

        now = datetime.now()
        record.status = KnowledgeBaseStatusEnum.PROCESSING
        record.error_message = None
        record.update_time = now
        session.add(record)
        session.commit()
        session.refresh(record)

        try:
            content = _extract_content(record)
            error = None
        except Exception as exc:
            logger.exception(
                "Knowledge base document processing failed: id=%s tenant_id=%s",
                record_id,
                tenant_id,
            )
            content = None
            message = str(exc).strip()
            error = (
                message[:1000]
                if isinstance(exc, ValueError)
                and message
                and any("\u4e00" <= char <= "\u9fff" for char in message)
                else KNOWLEDGE_PROCESS_FAILED_MESSAGE
            )

        # Reload under a row lock so replacement and manual deactivation during
        # extraction cannot be overwritten by this processing task.
        session.refresh(record, with_for_update=True)
        if record.file_id != expected_file_id:
            return {"id": record_id, "tenant_id": tenant_id, "status": "superseded"}
        if record.status != KnowledgeBaseStatusEnum.PROCESSING:
            return {"id": record_id, "tenant_id": tenant_id, "status": record.status}

        if error is None:
            record.content = content
            record.status = KnowledgeBaseStatusEnum.READY
            record.error_message = None
            if record.active:
                lock_knowledge_activation(session)
                session.add(record)
                session.flush()
                try:
                    build_knowledge_context(
                        session, tenant_id=tenant_id, surface="knowledge_base_activation",
                    )
                except KnowledgeContextError as exc:
                    record.active = False
                    record.error_message = exc.message
        else:
            record.status = KnowledgeBaseStatusEnum.FAILED
            record.active = False
            record.error_message = error
        record.update_time = datetime.now()
        session.add(record)
        session.commit()

        return {
            "id": record_id,
            "tenant_id": tenant_id,
            "status": record.status.value if hasattr(record.status, "value") else record.status,
        }
