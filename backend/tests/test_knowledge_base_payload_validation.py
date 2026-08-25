from __future__ import annotations

from apps.knowledge_base.normalizers import content_hash_for_payload, normalize_payload
from apps.knowledge_base.schemas import DocumentPayload, KnowledgePayloadAdapter
from apps.knowledge_base.validators import validate_payload


def test_document_requires_non_empty_markdown() -> None:
    report = validate_payload(DocumentPayload(knowledge_type="DOCUMENT", markdown=" \n\t"))

    assert report.errors[0].code == "KNOWLEDGE_DOCUMENT_BLOCK_MARKDOWN_REQUIRED"
    assert report.errors[0].field_path == "blocks[0].markdown"


def test_validation_only_checks_split_document_structure() -> None:
    payload = DocumentPayload(
        knowledge_type="DOCUMENT",
        markdown=(
            "事件 purchase 使用 $.meta.code。\n\n"
            "```sql\nselect * from orders; delete from secret_payments\n```"
        ),
        datasource_neutral=True,
        object_references=[
            {
                "object_type": "JSON_PATH",
                "schema": "public",
                "table": "orders",
                "field": "payload",
                "json_path": "$.meta.code",
            }
        ],
    )

    assert validate_payload(payload).valid


def test_normalization_hash_ignores_document_line_endings() -> None:
    left = DocumentPayload(
        knowledge_type="DOCUMENT",
        markdown="标题  \r\n\r\n正文\r\n",
        tags=["说明", "通用"],
    )
    right = DocumentPayload(
        knowledge_type="DOCUMENT",
        markdown="标题\n\n正文\n",
        tags=["说明", "通用"],
    )
    assert normalize_payload(left)["blocks"][0]["markdown"] == "标题\n\n正文\n"
    assert content_hash_for_payload(left) == content_hash_for_payload(right)


def test_object_reference_is_stored_without_datasource_validation() -> None:
    payload = KnowledgePayloadAdapter.validate_python(
        {
            "knowledge_type": "DOCUMENT",
            "markdown": "正文",
            "datasource_neutral": False,
            "object_references": [
                {
                    "object_type": "TABLE",
                    "schema": " public ",
                    "table": " orders ",
                    "field": " ",
                }
            ],
        }
    )

    assert validate_payload(payload).valid
