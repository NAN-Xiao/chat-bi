"""Verify deterministic legacy source fingerprints and migration mapping."""

from __future__ import annotations

from datetime import datetime

from apps.knowledge_base.backfill import (
    MIGRATION_VERSION,
    _build_version,
    _migration_fingerprint,
    legacy_source_fingerprint,
)
from apps.knowledge_base.lifecycle_models import (
    KnowledgeIndexStatus,
    KnowledgeVersionStatus,
)


class _Legacy:
    id = 7
    tenant_id = 3
    status = "READY"
    content = "# Revenue\r\n"
    update_time = datetime(2026, 8, 6, 12, 0, 0)
    file_id = "file-7"
    file_name = "revenue.md"
    file_ext = ".md"
    create_by = 11
    publish_by = 12


def test_legacy_source_fingerprint_is_stable_and_source_scoped() -> None:
    first = legacy_source_fingerprint(_Legacy())
    second = legacy_source_fingerprint(_Legacy())
    changed = _Legacy()
    changed.file_id = "file-8"

    assert first == second
    assert first != legacy_source_fingerprint(changed)
    assert len(first) == 64


def test_ready_legacy_row_maps_to_published_pending_index() -> None:
    version = _build_version(_Legacy(), "f" * 64, [])

    assert version.status == KnowledgeVersionStatus.PUBLISHED
    assert version.index_status == KnowledgeIndexStatus.PENDING
    assert version.file_id == "file-7"
    assert version.parser_version == MIGRATION_VERSION
    assert _migration_fingerprint(version) == "f" * 64
    assert version.payload["markdown"] == "# Revenue\n"


def test_unready_legacy_row_maps_to_editable_draft() -> None:
    record = _Legacy()
    record.status = "FAILED"
    record.content = None
    version = _build_version(record, "a" * 64, [])

    assert version.status == KnowledgeVersionStatus.DRAFT
    assert version.index_status == KnowledgeIndexStatus.NOT_REQUIRED
    assert version.error_message == "旧知识尚未完成解析，已创建可编辑草稿。"
    assert version.validation_report["valid"] is False
