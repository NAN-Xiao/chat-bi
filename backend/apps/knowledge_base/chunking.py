"""Deterministic parsing, standardization, and heading-aware chunking."""

from __future__ import annotations

import hashlib
import re
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from apps.knowledge_base.normalizers import normalize_markdown, standardized_content
from apps.knowledge_base.schemas import KnowledgePayload

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass(frozen=True)
class ParsedKnowledge:
    normalized_content: str
    source_format: str
    sections: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class KnowledgeChunkDraft:
    chunk_index: int
    section_path: str
    content: str
    content_hash: str
    token_count: int


def parse_and_normalize_version(
    source: str | Path | None = None,
    *,
    payload: KnowledgePayload | None = None,
    file_ext: str | None = None,
    scope: str = "",
) -> ParsedKnowledge:
    """Parse a source file or payload without retaining any previous version text."""
    if payload is not None:
        content = standardized_content(payload, scope=scope)
        source_format = "payload"
    else:
        if source is None:
            raise ValueError("知识源不能为空。")
        path = Path(source)
        extension = (file_ext or path.suffix).lower()
        if extension in {".md", ".markdown"}:
            content = _decode_markdown(path)
            source_format = "markdown"
        elif extension == ".docx":
            content = _decode_docx(path)
            source_format = "docx"
        else:
            raise ValueError(f"不支持的知识源格式: {extension}")
        content = normalize_markdown(content)
    sections = tuple(_split_sections(content))
    return ParsedKnowledge(
        normalized_content=content,
        source_format=source_format,
        sections=sections,
    )


def chunk_knowledge(
    payload: KnowledgePayload | None = None,
    *,
    source: str | Path | None = None,
    file_ext: str | None = None,
    scope: str = "",
    chunk_size: int = 1200,
    overlap: int = 150,
) -> list[KnowledgeChunkDraft]:
    """Produce stable chunks, preserving section paths and bounded overlap."""
    if chunk_size <= 0:
        raise ValueError("切片长度必须大于 0。")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("切片重叠长度必须小于切片长度。")
    parsed = parse_and_normalize_version(
        source,
        payload=payload,
        file_ext=file_ext,
        scope=scope,
    )
    result: list[KnowledgeChunkDraft] = []
    for section_path, section_text in parsed.sections:
        for content in _bounded_chunks(section_text, chunk_size=chunk_size, overlap=overlap):
            result.append(
                KnowledgeChunkDraft(
                    chunk_index=len(result),
                    section_path=section_path,
                    content=content,
                    content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    token_count=_estimate_tokens(content),
                )
            )
    return result


def _decode_markdown(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _decode_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    root = ET.fromstring(xml)
    paragraphs: list[str] = []
    for paragraph in root.iter():
        if _local_name(paragraph.tag) != "p":
            continue
        parts: list[str] = []
        for node in paragraph.iter():
            name = _local_name(node.tag)
            if name == "t":
                parts.append(node.text or "")
            elif name == "tab":
                parts.append("\t")
            elif name in {"br", "cr"}:
                parts.append("\n")
        value = "".join(parts).strip()
        if value:
            paragraphs.append(value)
    return "\n".join(paragraphs)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _split_sections(content: str) -> Iterable[tuple[str, str]]:
    lines = content.splitlines()
    heading_stack: list[str] = []
    section_lines: list[str] = []
    section_path = "正文"

    def flush() -> tuple[str, str] | None:
        text = normalize_markdown("\n".join(section_lines))
        if not text:
            return None
        return section_path, text

    for line in lines:
        match = _HEADING.match(line)
        if match:
            previous = flush()
            if previous:
                yield previous
            level = len(match.group(1))
            heading_stack[:] = heading_stack[: level - 1]
            heading_stack.append(match.group(2))
            section_path = " / ".join(heading_stack)
            section_lines = [line]
        else:
            section_lines.append(line)
    previous = flush()
    if previous:
        yield previous


def _bounded_chunks(text: str, *, chunk_size: int, overlap: int) -> Iterable[str]:
    if len(text) <= chunk_size:
        yield text
        return
    start = 0
    length = len(text)
    while start < length:
        end = min(length, start + chunk_size)
        if end < length:
            boundary = max(text.rfind("\n", start, end), text.rfind(" ", start, end))
            if boundary > start + chunk_size // 2:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            yield chunk
        if end >= length:
            return
        next_start = max(start + 1, end - overlap)
        start = next_start


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)
