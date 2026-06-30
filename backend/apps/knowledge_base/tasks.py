from __future__ import annotations

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


def _decode_markdown(path: Path) -> str:
    """
    是什么：_decode_markdown 是 backend/apps/knowledge_base/tasks.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _decode_markdown 的语义处理后端业务相关逻辑，并把结果返回或写入状态。
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
    是什么：_local_name 是 backend/apps/knowledge_base/tasks.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _local_name 的语义处理后端业务相关逻辑，并把结果返回或写入状态。
    """
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _paragraph_text(paragraph: ET.Element) -> str:
    """
    是什么：_paragraph_text 是 backend/apps/knowledge_base/tasks.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _paragraph_text 的语义处理后端业务相关逻辑，并把结果返回或写入状态。
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
    是什么：_decode_docx 是 backend/apps/knowledge_base/tasks.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：围绕 _decode_docx 的语义处理后端业务相关逻辑，并把结果返回或写入状态。
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
    是什么：_extract_content 是 backend/apps/knowledge_base/tasks.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：解析、转换或格式化后端业务相关数据，生成后续流程可使用的结构。
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


@task_handler("knowledge_base.process_document")
def process_knowledge_base_document(payload: dict[str, Any]) -> dict[str, Any]:
    """
    是什么：process_knowledge_base_document 是 backend/apps/knowledge_base/tasks.py 中的同步函数。
    谁调用：由后端业务代码、框架回调或测试代码按需调用。
    做了什么：执行后端业务主流程，协调下游服务并处理结果或异常。
    """
    record_id = int(payload["id"])
    tenant_id = int(payload.get("tenant_id") or current_task_tenant_id())

    with Session(engine) as session:
        record = session.get(KnowledgeBase, record_id)
        if record is None or int(record.tenant_id) != tenant_id:
            return {"id": record_id, "tenant_id": tenant_id, "status": "missing"}

        now = datetime.now()
        record.status = KnowledgeBaseStatusEnum.PROCESSING
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
            record.status = KnowledgeBaseStatusEnum.FAILED
            record.error_message = str(exc)[:1000]
        record.update_time = datetime.now()
        session.add(record)
        session.commit()

        return {
            "id": record_id,
            "tenant_id": tenant_id,
            "status": record.status.value if hasattr(record.status, "value") else record.status,
        }
