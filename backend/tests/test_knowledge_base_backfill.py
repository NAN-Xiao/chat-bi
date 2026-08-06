"""Verify deterministic legacy source fingerprints and migration mapping."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from apps.knowledge_base.backfill import (
    MIGRATION_VERSION,
    LegacyV2ParityReport,
    _build_version,
    _migration_fingerprint,
    legacy_source_fingerprint,
    verify_legacy_v2_parity,
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


def test_parity_report_is_redacted_and_fail_closed() -> None:
    report = LegacyV2ParityReport(
        scanned=1,
        mismatch_ids=(7,),
        mismatch_hashes={7: {"expected_payload": "a" * 64, "actual_payload": "b" * 64}},
    )

    assert report.ready_for_cutover is False
    assert report.as_dict()["mismatch_ids"] == [7]
    assert "Revenue" not in str(report.as_dict())


class _ParityResult:
    def __init__(self, values) -> None:
        self.values = values

    def all(self):
        return list(self.values)

    def count(self) -> int:
        return len(self.values)


class _ParitySession:
    def __init__(self, record, version) -> None:
        self.record = record
        self.version = version
        self.exec_count = 0

    def exec(self, _statement):
        self.exec_count += 1
        if self.exec_count == 1:
            return _ParityResult([self.record])
        if self.exec_count == 2:
            return _ParityResult([101])
        return _ParityResult([])

    def get(self, _model, _identity):
        return self.version


def test_parity_requires_ready_index_and_never_compares_document_body() -> None:
    record = SimpleNamespace(
        id=7,
        tenant_id=3,
        status="READY",
        content="# Revenue\n",
        update_time=datetime(2026, 8, 6, 12, 0, 0),
        file_id="file-7",
        current_version_id=70,
        draft_version_id=None,
    )
    version = _build_version(record, legacy_source_fingerprint(record), [])
    version.id = 70
    version.index_status = KnowledgeIndexStatus.READY

    ready = verify_legacy_v2_parity(_ParitySession(record, version))
    version.index_status = KnowledgeIndexStatus.PENDING
    pending = verify_legacy_v2_parity(_ParitySession(record, version))

    assert ready.ready_for_cutover is True
    assert pending.ready_for_cutover is False
    assert pending.mismatch_ids == (7,)
    assert "Revenue" not in str(pending.as_dict())
