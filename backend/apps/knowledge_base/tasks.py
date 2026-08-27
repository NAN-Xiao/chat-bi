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

from apps.knowledge_base.models import KnowledgeBase, KnowledgeBaseStatusEnum
from common.core.db import engine
from common.core.task_queue import current_task_tenant_id, task_handler
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

    with Session(engine) as session:
        record = session.get(KnowledgeBase, record_id)
        if record is None or int(record.tenant_id) != tenant_id:
            return {"id": record_id, "tenant_id": tenant_id, "status": "missing"}

        now = datetime.now()
        record.status = KnowledgeBaseStatusEnum.PROCESSING
        record.active = False
        record.error_message = None
        record.update_time = now
        session.add(record)
        session.commit()
        session.refresh(record)

        try:
            content = _extract_content(record)
            record.content = content
            record.status = KnowledgeBaseStatusEnum.READY
            record.error_message = None
        except Exception as exc:
            logger.exception(
                "Knowledge base document processing failed: id=%s tenant_id=%s",
                record_id,
                tenant_id,
            )
            record.status = KnowledgeBaseStatusEnum.FAILED
            message = str(exc).strip()
            record.error_message = (
                message[:1000]
                if isinstance(exc, ValueError)
                and message
                and any("\u4e00" <= char <= "\u9fff" for char in message)
                else KNOWLEDGE_PROCESS_FAILED_MESSAGE
            )
        record.update_time = datetime.now()
        session.add(record)
        session.commit()

        return {
            "id": record_id,
            "tenant_id": tenant_id,
            "status": record.status.value if hasattr(record.status, "value") else record.status,
        }
