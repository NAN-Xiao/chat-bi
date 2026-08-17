"""Deterministic standardization and full-replacement chunking tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.knowledge_base.chunking import chunk_knowledge, parse_and_normalize_version
from apps.knowledge_base.markdown_template import KNOWLEDGE_MARKDOWN_PARSER_VERSION
from apps.knowledge_base.schemas import DocumentPayload, document_blocks_from_markdown


def test_same_document_has_stable_normalized_content_and_chunks(tmp_path: Path):
    source = tmp_path / "knowledge.md"
    source.write_text(
        "# 收入\n\n订单收入说明\n\n## SQL\n\n```sql\nselect sum(amount) from orders\n```\n",
        encoding="utf-8",
    )
    first = parse_and_normalize_version(source)
    second = parse_and_normalize_version(source)
    first_chunks = chunk_knowledge(source=source, chunk_size=40, overlap=8)
    second_chunks = chunk_knowledge(source=source, chunk_size=40, overlap=8)
    assert first.normalized_content == second.normalized_content
    assert first.parser_version == KNOWLEDGE_MARKDOWN_PARSER_VERSION == "markdown-v1"
    assert [(item.section_path, item.content_hash) for item in first_chunks] == [
        (item.section_path, item.content_hash) for item in second_chunks
    ]


def test_reupload_does_not_merge_missing_old_section():
    chunks = chunk_knowledge(
        DocumentPayload(knowledge_type="DOCUMENT", markdown="# Kept\nnew"),
        chunk_size=1200,
        overlap=150,
    )
    assert all("Removed section" not in chunk.content for chunk in chunks)


def test_document_blocks_have_stable_business_text():
    payload = DocumentPayload(
        knowledge_type="DOCUMENT",
        markdown="# 收入\n\n订单金额总和\n\n## SQL\n\n```sql\nselect sum(amount) from orders\n```",
    )
    chunks = chunk_knowledge(payload)
    assert chunks
    assert all(chunk.content_hash for chunk in chunks)
    assert all(chunk.token_count > 0 for chunk in chunks)


def test_chunk_overlap_and_validation_are_bounded():
    payload = DocumentPayload(knowledge_type="DOCUMENT", markdown="# A\n" + ("word " * 80))
    chunks = chunk_knowledge(payload, chunk_size=50, overlap=10)
    assert len(chunks) > 1
    assert all(len(chunk.content) <= 50 for chunk in chunks)
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))


def test_fenced_sql_comments_are_not_treated_as_headings():
    payload = DocumentPayload(
        knowledge_type="DOCUMENT",
        markdown="# 收入\n\n```sql\nselect 1\n# keep this SQL comment\n```\n\n正文",
    )
    parsed = parse_and_normalize_version(payload=payload)
    assert sum("# keep this SQL comment" in content for _, content in parsed.sections) == 1
    assert all(path != "keep this SQL comment" for path, _ in parsed.sections)


def test_different_fence_marker_inside_code_is_not_treated_as_a_close(tmp_path: Path):
    source = tmp_path / "nested-fence-example.md"
    source.write_text(
        "# 标题\n\n## 章节\n\n```markdown\n~~~\n## 代码中的伪章节\n~~~\n```\n",
        encoding="utf-8",
    )

    parsed = parse_and_normalize_version(source)
    blocks = document_blocks_from_markdown(parsed.normalized_content)

    assert any("## 代码中的伪章节" in content for _, content in parsed.sections)
    assert all(path != "标题 / 代码中的伪章节" for path, _ in parsed.sections)
    assert len(blocks) == 1
    assert blocks[0]["title"] == "章节"
    assert "## 代码中的伪章节" in blocks[0]["markdown"]


@pytest.mark.parametrize("extension", [".docx", ".xlsx", ".txt"])
def test_non_markdown_sources_are_rejected(extension: str, tmp_path: Path):
    source = tmp_path / f"knowledge{extension}"
    source.write_bytes(b"unsupported")
    with pytest.raises(ValueError, match="不支持的知识源格式"):
        parse_and_normalize_version(source)
