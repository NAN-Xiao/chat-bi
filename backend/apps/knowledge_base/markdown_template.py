"""Strict content contract for uploaded knowledge Markdown."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

KNOWLEDGE_MARKDOWN_PARSER_VERSION = "markdown-v1"
KNOWLEDGE_MARKDOWN_FORMAT_ERROR = "格式错误：请上传符合要求的 Markdown 文档。"
_FENCE_OPEN = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")


class KnowledgeMarkdownFormatError(ValueError):
    def __init__(self, reason: str = "") -> None:
        message = f"{KNOWLEDGE_MARKDOWN_FORMAT_ERROR}{reason}" if reason else KNOWLEDGE_MARKDOWN_FORMAT_ERROR
        super().__init__(message)


@dataclass(frozen=True)
class ParsedKnowledgeMarkdown:
    markdown: str
    parser_version: str = KNOWLEDGE_MARKDOWN_PARSER_VERSION


def parse_knowledge_markdown_file(path: str | Path) -> ParsedKnowledgeMarkdown:
    return parse_knowledge_markdown_bytes(Path(path).read_bytes())


def parse_knowledge_markdown_bytes(data: bytes) -> ParsedKnowledgeMarkdown:
    try:
        source = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise KnowledgeMarkdownFormatError("文件必须使用 UTF-8 编码。") from exc
    return parse_knowledge_markdown(source)


def parse_knowledge_markdown(source: str) -> ParsedKnowledgeMarkdown:
    normalized = source.replace("\r\n", "\n").replace("\r", "\n")
    markdown = normalized.strip()
    _validate_markdown_structure(markdown)
    return ParsedKnowledgeMarkdown(markdown=f"{markdown}\n")


def _validate_markdown_structure(markdown: str) -> None:
    lines = markdown.split("\n")
    first_content = next((line.strip() for line in lines if line.strip()), "")
    if re.match(r"^#\s+\S", first_content) is None:
        raise KnowledgeMarkdownFormatError("正文必须以一级标题开始。")

    active_fence: str | None = None
    has_second_level_heading = False
    has_meaningful_body = False
    for line in lines:
        stripped = line.strip()
        previous_fence = active_fence
        active_fence = advance_markdown_fence(line, active_fence)
        if previous_fence is not None:
            if active_fence == previous_fence and stripped:
                has_meaningful_body = True
            continue
        if active_fence is not None:
            continue
        if re.match(r"^##\s+\S", stripped):
            has_second_level_heading = True
        elif stripped and re.match(r"^#{1,6}\s+", stripped) is None:
            has_meaningful_body = True

    if not has_second_level_heading:
        raise KnowledgeMarkdownFormatError("正文至少需要一个二级章节。")
    if not has_meaningful_body:
        raise KnowledgeMarkdownFormatError("正文内容不能为空。")
    if active_fence is not None:
        raise KnowledgeMarkdownFormatError("代码块未闭合。")


def advance_markdown_fence(line: str, active_fence: str | None) -> str | None:
    """Advance a CommonMark-style fence without treating another marker as its close."""
    if active_fence is None:
        match = _FENCE_OPEN.match(line)
        return match.group(1) if match is not None else None
    closing = re.match(r"^[ \t]{0,3}(`+|~+)[ \t]*$", line)
    if (
        closing is not None
        and closing.group(1)[0] == active_fence[0]
        and len(closing.group(1)) >= len(active_fence)
    ):
        return None
    return active_fence
