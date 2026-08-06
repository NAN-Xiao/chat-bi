from __future__ import annotations

from apps.knowledge_base.normalizers import content_hash_for_payload, normalize_payload
from apps.knowledge_base.schemas import (
    BusinessKnowledgePayload,
    DocumentPayload,
    JsonFieldKnowledgePayload,
    KnowledgePayloadAdapter,
)
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


def test_datasource_neutral_document_rejects_bare_table_name_from_qualified_catalog() -> None:
    payload = DocumentPayload(
        knowledge_type="DOCUMENT",
        markdown="orders 是订单明细表。",
        datasource_neutral=True,
    )

    scoped_report = validate_payload(
        payload,
        context=validation_context(tables={"public.orders": {"id"}}),
    )
    unscoped_report = validate_payload(payload, context=ValidationContext())

    assert scoped_report.errors[0].code == "KNOWLEDGE_DOCUMENT_NOT_NEUTRAL"
    assert unscoped_report.valid


def test_datasource_neutral_document_detects_catalog_identifiers_case_insensitively() -> None:
    payload = DocumentPayload(
        knowledge_type="DOCUMENT",
        markdown="orders 的 amount 位于 $.meta.code，事件为 purchase。",
        datasource_neutral=True,
    )
    context = validation_context(
        tables={"Analytics.Public.Orders": {"Amount", "payload"}},
        event_names={"PURCHASE"},
        json_paths={"Analytics.Public.Orders.payload": {"$.Meta.Code"}},
    )

    report = validate_payload(payload, context=context)

    assert report.errors[0].code == "KNOWLEDGE_DOCUMENT_NOT_NEUTRAL"


def test_document_requires_non_empty_markdown() -> None:
    report = validate_payload(DocumentPayload(knowledge_type="DOCUMENT", markdown=" \n\t"), context=validation_context())
    assert report.errors[0].code == "KNOWLEDGE_DOCUMENT_MARKDOWN_REQUIRED"


def test_datasource_bound_document_requires_declared_physical_object() -> None:
    report = validate_payload(DocumentPayload(knowledge_type="DOCUMENT", markdown="订单表 orders 用于收入分析。", datasource_neutral=False), context=validation_context())
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
            {
                "object_type": "TABLE",
                "catalog": "ghost",
                "schema": "public",
                "table": "orders",
            }
        ],
    )

    incomplete_codes = {issue.code for issue in validate_payload(incomplete, context=context).errors}
    ghost_codes = {issue.code for issue in validate_payload(ghost, context=context).errors}

    assert "KNOWLEDGE_RELATED_OBJECT_INCOMPLETE" in incomplete_codes
    assert "KNOWLEDGE_RELATED_OBJECT_NOT_FOUND" in ghost_codes


def test_business_sql_must_be_one_read_only_statement() -> None:
    payload = BusinessKnowledgePayload(knowledge_type="BUSINESS", term="收入", definition="订单金额之和", examples=[{"name": "错误", "question": "收入", "sql": "select 1; delete from orders"}])
    assert validate_payload(payload, context=validation_context()).errors[0].code == "KNOWLEDGE_SQL_NOT_READ_ONLY"


def test_business_sql_rejects_select_into_and_for_update() -> None:
    for sql in (
        "select * into archive from public.orders",
        "select * from public.orders for update",
    ):
        payload = BusinessKnowledgePayload(
            knowledge_type="BUSINESS",
            term="收入",
            definition="订单金额之和",
            examples=[{"name": "错误", "question": "收入", "sql": sql}],
        )

        report = validate_payload(payload, context=validation_context())

        assert report.errors[0].code == "KNOWLEDGE_SQL_NOT_READ_ONLY"


def test_read_only_sql_rejects_into_and_lock_anywhere_in_ast() -> None:
    assert _read_only_statement(
        "with staged as (select * into archive from public.orders) select * from staged",
        "postgres",
    ) is None
    assert _read_only_statement(
        "(select * from public.orders for update) union all select * from public.orders",
        "postgres",
    ) is None


def test_business_sql_objects_must_be_explicitly_declared() -> None:
    payload = BusinessKnowledgePayload(knowledge_type="BUSINESS", term="收入", definition="订单金额之和", related_objects=[{"object_type": "TABLE", "table": "orders"}], examples=[{"name": "错误", "question": "收入", "sql": "select amount from payments"}])
    assert validate_payload(payload, context=validation_context()).errors[0].code == "KNOWLEDGE_SQL_OBJECT_NOT_DECLARED"


def test_business_related_objects_require_complete_catalog_identity() -> None:
    payload = BusinessKnowledgePayload(
        knowledge_type="BUSINESS",
        term="收入",
        definition="订单金额之和",
        related_objects=[{"object_type": "TABLE", "table": "orders", "schema": "public"}],
        examples=[
            {
                "name": "收入",
                "question": "收入是多少",
                "sql": "select amount from analytics.public.orders",
            }
        ],
    )
    context = validation_context(tables={"analytics.public.orders": {"amount"}})

    report = validate_payload(payload, context=context)

    assert report.errors[0].code == "KNOWLEDGE_RELATED_OBJECT_INCOMPLETE"


def test_business_related_objects_and_sql_do_not_cross_match_same_table_in_other_schema() -> None:
    payload = BusinessKnowledgePayload(
        knowledge_type="BUSINESS",
        term="收入",
        definition="订单金额之和",
        related_objects=[
            {"object_type": "TABLE", "catalog": "analytics", "schema": "archive", "table": "orders"}
        ],
        examples=[
            {
                "name": "收入",
                "question": "收入是多少",
                "sql": "select amount from analytics.public.orders",
            }
        ],
    )
    context = validation_context(
        tables={
            "analytics.public.orders": {"amount"},
            "analytics.archive.orders": {"amount"},
        }
    )

    report = validate_payload(payload, context=context)

    assert report.errors[-1].code == "KNOWLEDGE_SQL_OBJECT_NOT_DECLARED"


def test_business_field_and_json_path_declarations_must_match_sql_ast_objects() -> None:
    context = validation_context(
        tables={"analytics.public.orders": {"id", "amount", "payload"}}
    )
    field_payload = BusinessKnowledgePayload(
        knowledge_type="BUSINESS",
        term="收入",
        definition="订单金额之和",
        related_objects=[
            {
                "object_type": "FIELD",
                "catalog": "analytics",
                "schema": "public",
                "table": "orders",
                "field": "amount",
            }
        ],
        examples=[
            {
                "name": "错误字段",
                "question": "收入",
                "sql": "select id from analytics.public.orders",
            }
        ],
    )
    json_payload = BusinessKnowledgePayload(
        knowledge_type="BUSINESS",
        term="收入",
        definition="订单金额之和",
        related_objects=[
            {
                "object_type": "JSON_PATH",
                "catalog": "analytics",
                "schema": "public",
                "table": "orders",
                "field": "payload",
                "json_path": "$.amount",
            }
        ],
        examples=[
            {
                "name": "错误路径",
                "question": "收入",
                "sql": "select JSON_VALUE(payload, '$.other') from analytics.public.orders",
            }
        ],
    )

    field_report = validate_payload(field_payload, context=context)
    json_report = validate_payload(json_payload, context=context)

    assert field_report.errors[-1].code == "KNOWLEDGE_SQL_OBJECT_NOT_DECLARED"
    assert json_report.errors[-1].code == "KNOWLEDGE_SQL_OBJECT_NOT_DECLARED"


def test_business_field_resolution_uses_local_select_alias_scope() -> None:
    payload = BusinessKnowledgePayload(
        knowledge_type="BUSINESS",
        term="敏感字段",
        definition="字段范围校验",
        related_objects=[
            {
                "object_type": "FIELD",
                "catalog": "analytics",
                "schema": "public",
                "table": "orders",
                "field": "secret",
            },
            {
                "object_type": "TABLE",
                "catalog": "analytics",
                "schema": "public",
                "table": "users",
            },
        ],
        examples=[
            {
                "name": "作用域",
                "question": "读取用户标识",
                "sql": (
                    "with c as (select o.secret from analytics.public.orders o) "
                    "select o.id from analytics.public.users o"
                ),
            }
        ],
    )
    context = validation_context(
        tables={
            "analytics.public.orders": {"id", "secret"},
            "analytics.public.users": {"id"},
        }
    )

    report = validate_payload(payload, context=context)

    assert report.valid


def test_business_field_resolution_keeps_unqualified_sqlite_table() -> None:
    payload = BusinessKnowledgePayload(
        knowledge_type="BUSINESS",
        term="金额",
        definition="订单金额",
        related_objects=[
            {"object_type": "FIELD", "table": "orders", "field": "amount"}
        ],
        examples=[
            {
                "name": "金额",
                "question": "订单金额",
                "sql": "select amount from orders",
                "dialect": "sqlite",
            }
        ],
    )
    context = validation_context(
        dialect="sqlite",
        tables={"orders": {"amount"}},
    )

    report = validate_payload(payload, context=context)

    assert report.valid


def test_related_field_uses_full_catalog_identity() -> None:
    payload = BusinessKnowledgePayload(
        knowledge_type="BUSINESS",
        term="收入",
        definition="订单金额之和",
        related_objects=[
            {
                "object_type": "FIELD",
                "catalog": "warehouse",
                "schema": "public",
                "table": "orders",
                "field": "amount",
            }
        ],
    )
    context = validation_context(
        tables={
            "analytics.public.orders": {"amount"},
            "warehouse.public.orders": {"id"},
        }
    )

    report = validate_payload(payload, context=context)

    assert report.errors[0].code == "KNOWLEDGE_RELATED_OBJECT_NOT_FOUND"


def test_event_name_is_unique_across_workspace_tracking_specification() -> None:
    payload = KnowledgePayloadAdapter.validate_python({"knowledge_type": "EVENT", "event_name": "purchase", "table_name": "orders", "event_name_field": "event_name"})
    assert validate_payload(payload, context=validation_context(event_names={"purchase"})).errors[0].code == "KNOWLEDGE_EVENT_NAME_DUPLICATE"


def test_json_payload_rejects_dynamic_path_and_mismatched_expression() -> None:
    payload = JsonFieldKnowledgePayload(knowledge_type="JSON_FIELD", table_name="orders", source_field="payload", json_path="$.amount", field_name="amount", data_type="number", expression="JSON_VALUE(payload, other_path)")
    assert validate_payload(payload, context=validation_context(dialect="postgres")).errors[0].code == "KNOWLEDGE_JSON_EXPRESSION_INVALID"


def test_json_payload_rejects_random_function_subquery_and_foreign_table() -> None:
    for expression in (
        "JSON_VALUE(payload, '$.amount') + RANDOM()",
        "JSON_VALUE((SELECT payload FROM secret), '$.amount')",
    ):
        payload = JsonFieldKnowledgePayload(
            knowledge_type="JSON_FIELD",
            table_name="orders",
            source_field="payload",
            json_path="$.amount",
            field_name="amount",
            data_type="number",
            expression=expression,
        )

        report = validate_payload(payload, context=validation_context())

        assert report.errors[-1].code == "KNOWLEDGE_JSON_EXPRESSION_INVALID"


def test_json_payload_rejects_unknown_json_prefixed_function() -> None:
    payload = JsonFieldKnowledgePayload(
        knowledge_type="JSON_FIELD",
        table_name="orders",
        source_field="payload",
        json_path="$.amount",
        field_name="amount",
        data_type="number",
        expression="JSON_EVIL(JSON_VALUE(payload, '$.amount'))",
    )

    report = validate_payload(payload, context=validation_context())

    assert report.errors[-1].code == "KNOWLEDGE_JSON_EXPRESSION_INVALID"


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
