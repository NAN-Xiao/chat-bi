"""Strict Markdown template upload contract."""

from __future__ import annotations

import pytest

from apps.knowledge_base.markdown_template import (
    KnowledgeMarkdownFormatError,
    parse_knowledge_markdown,
    parse_knowledge_markdown_bytes,
)


def _template(markdown: str, *, template_type: str = "knowledge_document", version: object = 1) -> str:
    return (
        "---\n"
        f"template_type: {template_type}\n"
        f"template_version: {version}\n"
        "---\n"
        f"{markdown.strip()}\n"
    )


@pytest.mark.parametrize("prefix", [b"", b"\xef\xbb\xbf"])
def test_valid_template_accepts_utf8_and_bom_and_strips_front_matter(prefix: bytes) -> None:
    parsed = parse_knowledge_markdown_bytes(
        prefix + _template("# 标题\n\n## 章节\n\n有效正文").encode("utf-8")
    )
    assert parsed.template_type == "knowledge_document"
    assert parsed.template_version == 1
    assert parsed.markdown == "# 标题\n\n## 章节\n\n有效正文\n"
    assert "template_type" not in parsed.markdown


def test_invalid_utf8_is_rejected() -> None:
    with pytest.raises(KnowledgeMarkdownFormatError, match="^格式错误.*UTF-8"):
        parse_knowledge_markdown_bytes(b"\xff\xfe\x00")


@pytest.mark.parametrize(
    ("source", "reason"),
    [
        ("# 标题\n\n## 章节\n\n正文", "缺少模板标记"),
        (
            "---\ntemplate_type: bad\ntemplate_type: knowledge_document\n"
            "template_version: 1\n---\n# 标题\n\n## 章节\n\n正文",
            "模板标记无效",
        ),
        (_template("# 标题\n\n## 章节\n\n正文", template_type="event"), "模板类型不正确"),
        (_template("# 标题\n\n## 章节\n\n正文", version=2), "模板版本不支持"),
        (_template("# 标题\n\n## 章节\n\n正文", version="true"), "模板版本不支持"),
        (
            "---\ntemplate_type: knowledge_document\ntemplate_version: 1\n"
            "template_version: 2\n---\n# 标题\n\n## 章节\n\n正文\n",
            "模板标记无效",
        ),
        (_template("## 章节\n\n正文"), "一级标题"),
        (_template("# 标题\n\n正文"), "二级章节"),
        (_template("# 标题\n\n## 章节"), "正文内容不能为空"),
        (_template("# 标题\n\n## 章节\n\n```sql\nselect 1"), "代码块未闭合"),
    ],
)
def test_invalid_template_contract_is_rejected(source: str, reason: str) -> None:
    with pytest.raises(KnowledgeMarkdownFormatError, match=f"^格式错误.*{reason}"):
        parse_knowledge_markdown(source)
