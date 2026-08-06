from __future__ import annotations

from apps.knowledge_base.normalizers import content_hash_for_payload, normalize_payload
from apps.knowledge_base.schemas import (
    BusinessKnowledgePayload,
    DocumentPayload,
    JsonFieldKnowledgePayload,
    KnowledgePayloadAdapter,
)
from apps.knowledge_base.validators import ValidationContext, validate_payload


def validation_context(**overrides: object) -> ValidationContext:
    values: dict[str, object] = {
        "dialect": "postgres",
        "tables": {"orders": {"id", "amount", "payload", "event_name", "event_time"}},
    }
    values.update(overrides)
    return ValidationContext(**values)


def test_business_payload_allows_question_and_sql_without_term() -> None:
    from apps.knowledge_base.schemas import KnowledgePayloadAdapter

    payload = KnowledgePayloadAdapter.validate_python({
        "knowledge_type": "BUSINESS",
        "term": None,
        "definition": "",
        "examples": [{"name": "收入", "question": "收入是多少", "sql": "select sum(amount) from orders"}],
    })

    assert payload.examples[0].question == "收入是多少"


def test_datasource_neutral_document_rejects_sql() -> None:
    from apps.knowledge_base.schemas import DocumentPayload
    from apps.knowledge_base.validators import ValidationContext, validate_payload

    report = validate_payload(
        DocumentPayload(
            knowledge_type="DOCUMENT",
            markdown="```sql\nselect * from orders\n```",
            datasource_neutral=True,
        ),
        context=ValidationContext(),
    )

    assert report.errors[0].code == "KNOWLEDGE_DOCUMENT_NOT_NEUTRAL"


def test_document_requires_non_empty_markdown() -> None:
    report = validate_payload(DocumentPayload(knowledge_type="DOCUMENT", markdown=" \n\t"), context=validation_context())
    assert report.errors[0].code == "KNOWLEDGE_DOCUMENT_MARKDOWN_REQUIRED"


def test_datasource_bound_document_requires_declared_physical_object() -> None:
    report = validate_payload(DocumentPayload(knowledge_type="DOCUMENT", markdown="订单表 orders 用于收入分析。", datasource_neutral=False), context=validation_context())
    assert report.errors[0].code == "KNOWLEDGE_DOCUMENT_OBJECT_NOT_DECLARED"


def test_business_sql_must_be_one_read_only_statement() -> None:
    payload = BusinessKnowledgePayload(knowledge_type="BUSINESS", term="收入", definition="订单金额之和", examples=[{"name": "错误", "question": "收入", "sql": "select 1; delete from orders"}])
    assert validate_payload(payload, context=validation_context()).errors[0].code == "KNOWLEDGE_SQL_NOT_READ_ONLY"


def test_business_sql_objects_must_be_explicitly_declared() -> None:
    payload = BusinessKnowledgePayload(knowledge_type="BUSINESS", term="收入", definition="订单金额之和", related_objects=[{"object_type": "TABLE", "table": "orders"}], examples=[{"name": "错误", "question": "收入", "sql": "select amount from payments"}])
    assert validate_payload(payload, context=validation_context()).errors[0].code == "KNOWLEDGE_SQL_OBJECT_NOT_DECLARED"


def test_event_name_is_unique_across_workspace_tracking_specification() -> None:
    payload = KnowledgePayloadAdapter.validate_python({"knowledge_type": "EVENT", "event_name": "purchase", "table_name": "orders", "event_name_field": "event_name"})
    assert validate_payload(payload, context=validation_context(event_names={"purchase"})).errors[0].code == "KNOWLEDGE_EVENT_NAME_DUPLICATE"


def test_json_payload_rejects_dynamic_path_and_mismatched_expression() -> None:
    payload = JsonFieldKnowledgePayload(knowledge_type="JSON_FIELD", table_name="orders", source_field="payload", json_path="$.amount", field_name="amount", data_type="number", expression="JSON_VALUE(payload, other_path)")
    assert validate_payload(payload, context=validation_context(dialect="postgres")).errors[0].code == "KNOWLEDGE_JSON_EXPRESSION_INVALID"


def test_json_payload_requires_existing_host_field_and_valid_type() -> None:
    payload = JsonFieldKnowledgePayload(knowledge_type="JSON_FIELD", table_name="orders", source_field="missing_payload", json_path="$.amount", field_name="amount", data_type="unrecognized", expression="payload::jsonb ->> 'amount'")
    codes = {issue.code for issue in validate_payload(payload, context=validation_context()).errors}
    assert {"KNOWLEDGE_JSON_HOST_FIELD_NOT_FOUND", "KNOWLEDGE_JSON_DATA_TYPE_INVALID"}.issubset(codes)


def test_event_and_json_payloads_reject_empty_required_physical_fields() -> None:
    event = KnowledgePayloadAdapter.validate_python({"knowledge_type": "EVENT", "event_name": "purchase", "table_name": "orders", "event_name_field": ""})
    json_payload = JsonFieldKnowledgePayload(knowledge_type="JSON_FIELD", table_name="orders", source_field="", json_path="$.amount", field_name="", data_type="number", expression="payload::jsonb ->> 'amount'")
    event_codes = {issue.code for issue in validate_payload(event, context=validation_context()).errors}
    json_codes = {issue.code for issue in validate_payload(json_payload, context=validation_context()).errors}
    assert "KNOWLEDGE_EVENT_FIELD_REQUIRED" in event_codes
    assert {"KNOWLEDGE_JSON_HOST_FIELD_REQUIRED", "KNOWLEDGE_JSON_FIELD_NAME_REQUIRED"}.issubset(json_codes)


def test_normalization_hash_ignores_document_line_endings_and_json_key_order() -> None:
    left = DocumentPayload(knowledge_type="DOCUMENT", markdown="标题  \r\n\r\n正文\r\n", tags=["说明", "通用"])
    right = DocumentPayload(knowledge_type="DOCUMENT", markdown="标题\n\n正文\n", tags=["说明", "通用"])
    assert normalize_payload(left)["markdown"] == "标题\n\n正文\n"
    assert content_hash_for_payload(left) == content_hash_for_payload(right)
