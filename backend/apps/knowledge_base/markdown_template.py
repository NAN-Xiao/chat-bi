"""Strict, versioned format contract for uploaded knowledge Markdown."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode

KNOWLEDGE_MARKDOWN_TEMPLATE_TYPE = "knowledge_document"
KNOWLEDGE_MARKDOWN_TEMPLATE_VERSION = 1
KNOWLEDGE_MARKDOWN_FORMAT_ERROR = "格式错误：请使用下载的 Markdown 模板上传。"


class _UniqueKeySafeLoader(yaml.SafeLoader):
    def construct_mapping(
        self,
        node: MappingNode,
        deep: bool = False,
    ) -> dict[Any, Any]:
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in seen
                seen.add(key)
            except TypeError as exc:
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    "found an unhashable key",
                    key_node.start_mark,
                ) from exc
            if duplicate:
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"found duplicate key {key!r}",
                    key_node.start_mark,
                )
        return super().construct_mapping(node, deep=deep)


class KnowledgeMarkdownFormatError(ValueError):
    def __init__(self, reason: str = "") -> None:
        message = f"{KNOWLEDGE_MARKDOWN_FORMAT_ERROR}{reason}" if reason else KNOWLEDGE_MARKDOWN_FORMAT_ERROR
        super().__init__(message)


@dataclass(frozen=True)
class ParsedKnowledgeMarkdown:
    markdown: str
    template_type: str = KNOWLEDGE_MARKDOWN_TEMPLATE_TYPE
    template_version: int = KNOWLEDGE_MARKDOWN_TEMPLATE_VERSION


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
    if not normalized.startswith("---\n"):
        raise KnowledgeMarkdownFormatError("缺少模板标记。")
    front_matter_end = normalized.find("\n---\n", 4)
    if front_matter_end < 0:
        raise KnowledgeMarkdownFormatError("模板标记未闭合。")

    try:
        metadata = yaml.load(
            normalized[4:front_matter_end],
            Loader=_UniqueKeySafeLoader,
        )
    except yaml.YAMLError as exc:
        raise KnowledgeMarkdownFormatError("模板标记无效。") from exc
    if not isinstance(metadata, dict):
        raise KnowledgeMarkdownFormatError("模板标记无效。")
    if metadata.get("template_type") != KNOWLEDGE_MARKDOWN_TEMPLATE_TYPE:
        raise KnowledgeMarkdownFormatError("模板类型不正确。")
    version = metadata.get("template_version")
    if isinstance(version, bool) or not isinstance(version, int) or version != KNOWLEDGE_MARKDOWN_TEMPLATE_VERSION:
        raise KnowledgeMarkdownFormatError("模板版本不支持。")

    markdown = normalized[front_matter_end + 5 :].strip()
    _validate_markdown_structure(markdown)
    return ParsedKnowledgeMarkdown(markdown=f"{markdown}\n")


def _validate_markdown_structure(markdown: str) -> None:
    lines = markdown.split("\n")
    first_content = next((line.strip() for line in lines if line.strip()), "")
    if re.match(r"^#\s+\S", first_content) is None:
        raise KnowledgeMarkdownFormatError("正文必须以一级标题开始。")
    if not any(re.match(r"^##\s+\S", line.strip()) for line in lines):
        raise KnowledgeMarkdownFormatError("正文至少需要一个二级章节。")
    if not any(
        value
        and re.match(r"^#{1,6}\s+", value) is None
        and re.match(r"^(?:```|~~~)", value) is None
        for value in (line.strip() for line in lines)
    ):
        raise KnowledgeMarkdownFormatError("正文内容不能为空。")
    if not _has_closed_fences(lines):
        raise KnowledgeMarkdownFormatError("代码块未闭合。")


def _has_closed_fences(lines: list[str]) -> bool:
    active_fence: str | None = None
    for line in lines:
        match = re.match(r"^(```|~~~)", line.lstrip())
        if match is None:
            continue
        marker = match.group(1)
        if active_fence is None:
            active_fence = marker
        elif active_fence == marker:
            active_fence = None
    return active_fence is None
