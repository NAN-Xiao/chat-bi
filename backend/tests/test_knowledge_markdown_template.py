"""Strict Markdown document upload contract."""

from __future__ import annotations

import pytest

from apps.knowledge_base.markdown_template import (
    KNOWLEDGE_MARKDOWN_PARSER_VERSION,
    KnowledgeMarkdownFormatError,
    parse_knowledge_markdown,
    parse_knowledge_markdown_bytes,
)


@pytest.mark.parametrize("prefix", [b"", b"\xef\xbb\xbf"])
def test_valid_markdown_accepts_utf8_and_bom(prefix: bytes) -> None:
    parsed = parse_knowledge_markdown_bytes(
        prefix + "# 标题\r\n\r\n## 章节\r\n\r\n有效正文".encode()
    )
    assert parsed.markdown == "# 标题\n\n## 章节\n\n有效正文\n"
    assert parsed.parser_version == KNOWLEDGE_MARKDOWN_PARSER_VERSION == "markdown-v1"


def test_invalid_utf8_is_rejected() -> None:
    with pytest.raises(KnowledgeMarkdownFormatError, match="^格式错误.*UTF-8"):
        parse_knowledge_markdown_bytes(b"\xff\xfe\x00")


@pytest.mark.parametrize(
    ("source", "reason"),
    [
        ("## 章节\n\n正文", "一级标题"),
        ("# 标题\n\n正文", "二级章节"),
        ("# 标题\n\n## 章节", "正文内容不能为空"),
        ("# 标题\n\n```markdown\n## 代码中的伪章节\n正文\n```", "二级章节"),
        ("# 标题\n\n## 章节\n\n```sql\nselect 1", "代码块未闭合"),
        (
            "---\ntemplate_type: knowledge_document\ntemplate_version: 1\n---\n"
            "# 标题\n\n## 章节\n\n正文",
            "一级标题",
        ),
    ],
)
def test_invalid_markdown_structure_is_rejected(source: str, reason: str) -> None:
    with pytest.raises(KnowledgeMarkdownFormatError, match=f"^格式错误.*{reason}"):
        parse_knowledge_markdown(source)


def test_mixed_fence_markers_do_not_close_or_create_sections() -> None:
    parsed = parse_knowledge_markdown(
        "# 标题\n\n## 章节\n\n```markdown\n~~~\n## 代码中的伪章节\n~~~\n```"
    )

    assert "## 代码中的伪章节" in parsed.markdown
