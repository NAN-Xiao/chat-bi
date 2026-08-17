from __future__ import annotations

from apps.knowledge_base.normalizers import (
    content_hash_for_payload,
    normalize_payload,
)
from apps.knowledge_base.schemas import DocumentPayload, KnowledgePayloadAdapter
from apps.knowledge_base.validators import (
    ValidationContext,
    _read_only_statement,
    validate_payload,
)


def validation_context(**overrides: object) -> ValidationContext:
    values: dict[str, object] = {
        "dialect": "postgres",
        "tables": {"orders": {"id", "amount", "payload", "event_name", "event_time"}},
    }
    values.update(overrides)
    return ValidationContext(**values)


def test_datasource_neutral_document_rejects_sql() -> None:
    report = validate_payload(
        DocumentPayload(
            knowledge_type="DOCUMENT",
            markdown="```sql\nselect * from orders\n```",
            datasource_neutral=True,
        ),
        context=ValidationContext(),
    )
    assert report.errors[0].code == "KNOWLEDGE_DOCUMENT_NOT_NEUTRAL"


def test_datasource_neutral_document_rejects_catalog_identifiers_case_insensitively() -> None:
    payload = DocumentPayload(
        knowledge_type="DOCUMENT",
        markdown="orders 的 amount 位于 $.meta.code，事件为 purchase。",
        datasource_neutral=True,
    )
    report = validate_payload(
        payload,
        context=validation_context(
            tables={"Analytics.Public.Orders": {"Amount", "payload"}},
            event_names={"PURCHASE"},
            json_paths={"Analytics.Public.Orders.payload": {"$.Meta.Code"}},
        ),
    )
    assert report.errors[0].code == "KNOWLEDGE_DOCUMENT_NOT_NEUTRAL"


def test_datasource_neutral_document_without_catalog_context_stays_valid() -> None:
    payload = DocumentPayload(
        knowledge_type="DOCUMENT",
        markdown="orders 是订单明细表。",
        datasource_neutral=True,
    )
    assert validate_payload(payload, context=ValidationContext()).valid


def test_document_requires_non_empty_markdown() -> None:
    report = validate_payload(
        DocumentPayload(knowledge_type="DOCUMENT", markdown=" \n\t"),
        context=validation_context(),
    )
    assert report.errors[0].code == "KNOWLEDGE_DOCUMENT_BLOCK_MARKDOWN_REQUIRED"
    assert report.errors[0].field_path == "blocks[0].markdown"


def test_datasource_bound_document_requires_declared_physical_object() -> None:
    report = validate_payload(
        DocumentPayload(
            knowledge_type="DOCUMENT",
            markdown="订单表 orders 用于收入分析。",
            datasource_neutral=False,
        ),
        context=validation_context(),
    )
    assert report.errors[0].code == "KNOWLEDGE_DOCUMENT_OBJECT_NOT_DECLARED"


def test_datasource_bound_document_validates_declared_object_against_catalog() -> None:
    context = validation_context(tables={"analytics.public.orders": {"id"}})
    incomplete = DocumentPayload(
        knowledge_type="DOCUMENT",
        markdown="orders 是订单明细表。",
        datasource_neutral=False,
        object_references=[{"object_type": "TABLE", "table": "orders"}],
    )
    ghost = DocumentPayload(
        knowledge_type="DOCUMENT",
        markdown="通用说明。",
        datasource_neutral=False,
        object_references=[
            {"object_type": "TABLE", "catalog": "ghost", "schema": "public", "table": "orders"}
        ],
    )
    incomplete_codes = {issue.code for issue in validate_payload(incomplete, context=context).errors}
    ghost_codes = {issue.code for issue in validate_payload(ghost, context=context).errors}
    assert "KNOWLEDGE_RELATED_OBJECT_INCOMPLETE" in incomplete_codes
    assert "KNOWLEDGE_RELATED_OBJECT_NOT_FOUND" in ghost_codes


def test_document_sql_must_be_one_read_only_statement() -> None:
    for sql in (
        "select 1; delete from orders",
        "select * into archive from orders",
        "select * from orders for update",
    ):
        payload = DocumentPayload(
            knowledge_type="DOCUMENT",
            markdown=f"```sql\n{sql}\n```",
            datasource_neutral=False,
            object_references=[{"object_type": "TABLE", "table": "orders"}],
        )
        codes = {issue.code for issue in validate_payload(payload, context=validation_context()).errors}
        assert "KNOWLEDGE_SQL_NOT_READ_ONLY" in codes
        assert _read_only_statement(sql, "postgres") is None


def test_document_sql_objects_must_be_explicitly_declared() -> None:
    payload = DocumentPayload(
        knowledge_type="DOCUMENT",
        markdown="```sql\nselect * from secret_payments\n```",
        datasource_neutral=False,
        object_references=[{"object_type": "TABLE", "table": "orders"}],
    )
    context = validation_context(tables={"orders": {"id"}, "secret_payments": {"id"}})
    codes = {issue.code for issue in validate_payload(payload, context=context).errors}
    assert "KNOWLEDGE_SQL_OBJECT_NOT_DECLARED" in codes


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


def test_object_reference_normalizes_blank_optional_identifiers() -> None:
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
    reference = payload.object_references[0]
    assert reference.schema == "public"
    assert reference.table == "orders"
    assert reference.field is None
