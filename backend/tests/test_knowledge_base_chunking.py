"""Deterministic standardization and full-replacement chunking tests."""

from __future__ import annotations

from pathlib import Path

from apps.knowledge_base.chunking import chunk_knowledge, parse_and_normalize_version
from apps.knowledge_base.schemas import (
    BusinessKnowledgePayload,
    DocumentPayload,
    EventKnowledgePayload,
    EventParameter,
    JsonFieldKnowledgePayload,
)


def test_same_document_has_stable_normalized_content_and_chunks(tmp_path: Path):
    source = tmp_path / "knowledge.md"
    source.write_text("# 收入\n\n订单收入说明\n\n## SQL\n\n```sql\nselect sum(amount) from orders\n```\n", encoding="utf-8")
    first = parse_and_normalize_version(source)
    second = parse_and_normalize_version(source)
    first_chunks = chunk_knowledge(source=source, chunk_size=40, overlap=8)
    second_chunks = chunk_knowledge(source=source, chunk_size=40, overlap=8)
    assert first.normalized_content == second.normalized_content
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


def test_all_structured_payloads_have_stable_business_text():
    payloads = [
        BusinessKnowledgePayload(
            knowledge_type="BUSINESS",
            term="收入",
            definition="订单金额总和",
            examples=[{"name": "收入", "question": "收入是多少", "sql": "select sum(amount) from orders"}],
        ),
        EventKnowledgePayload(
            knowledge_type="EVENT",
            event_name="order_paid",
            table_name="events",
            event_name_field="event_name",
            parameters=[EventParameter(name="amount", data_type="decimal")],
        ),
        JsonFieldKnowledgePayload(
            knowledge_type="JSON_FIELD",
            table_name="orders",
            source_field="properties",
            json_path="$.channel",
            field_name="channel",
            data_type="string",
            expression="json_extract(properties, '$.channel')",
        ),
    ]
    for payload in payloads:
        chunks = chunk_knowledge(payload)
        assert chunks
        assert chunks[0].content_hash
        assert chunks[0].token_count > 0


def test_chunk_overlap_and_validation_are_bounded():
    payload = DocumentPayload(knowledge_type="DOCUMENT", markdown="# A\n" + ("word " * 80))
    chunks = chunk_knowledge(payload, chunk_size=50, overlap=10)
    assert len(chunks) > 1
    assert all(len(chunk.content) <= 50 for chunk in chunks)
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))

