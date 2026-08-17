"""Deterministic parsing, standardization, and heading-aware chunking."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from apps.knowledge_base.markdown_template import parse_knowledge_markdown_file
from apps.knowledge_base.normalizers import normalize_markdown, standardized_content
from apps.knowledge_base.schemas import DocumentPayload, KnowledgePayload
from common.core.config import settings

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
    source_block_id: str | None = None


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
        if extension not in {".md", ".markdown"}:
            raise ValueError(f"不支持的知识源格式: {extension}")
        content = parse_knowledge_markdown_file(path).markdown
        source_format = "markdown"
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
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[KnowledgeChunkDraft]:
    """Produce stable chunks, preserving section paths and bounded overlap."""
    chunk_size = int(settings.KNOWLEDGE_CHUNK_SIZE if chunk_size is None else chunk_size)
    overlap = int(settings.KNOWLEDGE_CHUNK_OVERLAP if overlap is None else overlap)
    if chunk_size <= 0:
        raise ValueError("切片长度必须大于 0。")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("切片重叠长度必须小于切片长度。")
    if isinstance(payload, DocumentPayload):
        result: list[KnowledgeChunkDraft] = []
        for block in payload.blocks:
            if not block.enabled:
                continue
            section_text = normalize_markdown(f"# {block.title or '正文'}\n\n{block.markdown}")
            for content in _bounded_chunks(section_text, chunk_size=chunk_size, overlap=overlap):
                result.append(KnowledgeChunkDraft(
                    chunk_index=len(result),
                    section_path=block.title or "正文",
                    content=content,
                    content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    token_count=_estimate_tokens(content),
                    source_block_id=block.id,
                ))
        return result
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
                    source_block_id=None,
                )
            )
    return result


def _ensure_file_size(path: Path) -> None:
    if path.stat().st_size > int(settings.KNOWLEDGE_FILE_MAX_BYTES):
        raise ValueError("知识源文件超过允许大小。")


def _split_sections(content: str) -> Iterable[tuple[str, str]]:
    lines = content.splitlines()
    heading_stack: list[str] = []
    section_lines: list[str] = []
    section_path = "正文"
    fenced = False

    def flush() -> tuple[str, str] | None:
        text = normalize_markdown("\n".join(section_lines))
        body = normalize_markdown("\n".join(section_lines[1:])) if section_lines and _HEADING.match(section_lines[0]) else text
        if not text or (section_lines and _HEADING.match(section_lines[0]) and not body):
            return None
        return section_path, text

    for line in lines:
        match = None if fenced else _HEADING.match(line)
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
        if re.match(r"^\s*(```|~~~)", line):
            fenced = not fenced
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
        protected = _protected_range_at(text, end)
        if protected is not None and protected[1] > end:
            end = protected[1]
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
        protected_start = _protected_range_at(text, next_start)
        if protected_start is not None:
            next_start = (
                protected_start[1]
                if protected_start[0] <= start
                else protected_start[0]
            )
        if next_start <= start:
            next_start = end
        start = next_start


def _protected_range_at(text: str, position: int) -> tuple[int, int] | None:
    """Return the full fenced-code span containing a character position."""
    fence = re.compile(r"^\s*(```|~~~)", re.MULTILINE)
    matches = list(fence.finditer(text))
    if len(matches) < 2:
        return None
    for index in range(0, len(matches) - 1, 2):
        start = matches[index].start()
        end = matches[index + 1].end()
        if start <= position < end:
            return start, end
    return None


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)
