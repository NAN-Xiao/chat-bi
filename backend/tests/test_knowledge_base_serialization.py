"""Verify that the V2 list contract exposes fields required by management UI."""

from datetime import datetime

from apps.knowledge_base.api._helpers import serialize_record
from apps.knowledge_base.models import (
    KnowledgeBase,
    KnowledgeBaseStatusEnum,
    KnowledgeBaseVisibilityScopeEnum,
)


def test_serialize_record_includes_processing_and_source_fields() -> None:
    updated_at = datetime(2026, 8, 6, 12, 30, 0)
    record = KnowledgeBase(
        id=17,
        tenant_id=8,
        name="订单口径",
        visibility_scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC,
        status=KnowledgeBaseStatusEnum.READY,
        file_id="file-17",
        file_name="orders.md",
        file_ext="md",
        update_time=updated_at,
    )

    result = serialize_record(record, can_manage=True)

    assert result["status"] == "READY"
    assert result["file_id"] == "file-17"
    assert result["file_name"] == "orders.md"
    assert result["file_ext"] == "md"
    assert result["update_time"] == updated_at
