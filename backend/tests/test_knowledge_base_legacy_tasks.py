"""Verify delayed legacy document writes honor the migration phase."""

from __future__ import annotations

import pytest

from apps.knowledge_base import tasks as legacy_tasks
from apps.knowledge_base.models import (
    KnowledgeBase,
    KnowledgeBaseStatusEnum,
    KnowledgeBaseVisibilityScopeEnum,
)
from apps.knowledge_base.repository import KnowledgeBusinessError


def _phase_error(*, active: bool = False) -> KnowledgeBusinessError:
    if active:
        return KnowledgeBusinessError(
            code="KNOWLEDGE_LEGACY_WRITE_DISABLED",
            message="知识库已升级，请刷新页面后重新操作。",
            status_code=410,
        )
    return KnowledgeBusinessError(
        code="KNOWLEDGE_UPGRADE_IN_PROGRESS",
        message="知识库升级中，请稍后重试。",
        status_code=409,
    )


class _WorkerSession:
    def __init__(self, record: KnowledgeBase) -> None:
        self.record = record
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        return None

    def get(self, _model, _record_id):
        return self.record

    def add(self, _record: KnowledgeBase) -> None:
        return None

    def commit(self) -> None:
        self.commits += 1

    def refresh(self, _record: KnowledgeBase) -> None:
        return None

    def rollback(self) -> None:
        self.rollbacks += 1


def _record() -> KnowledgeBase:
    return KnowledgeBase(
        id=1,
        tenant_id=7,
        create_by=11,
        name="Legacy document",
        visibility_scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC,
        status=KnowledgeBaseStatusEnum.PENDING,
        file_id="legacy.md",
        file_name="legacy.md",
        file_ext=".md",
    )


@pytest.mark.parametrize("extract_fails", [False, True])
def test_legacy_worker_started_before_barrier_cannot_write_final_state(
    monkeypatch,
    extract_fails,
) -> None:
    record = _record()
    session = _WorkerSession(record)
    lock_calls = 0

    def lock_for_legacy_write(_session):
        nonlocal lock_calls
        lock_calls += 1
        if lock_calls == 2:
            raise _phase_error()

    def extract_content(_record):
        if extract_fails:
            raise ValueError("invalid document")
        return "new content"

    monkeypatch.setattr(legacy_tasks, "Session", lambda _engine: session)
    monkeypatch.setattr(
        legacy_tasks.KnowledgeMigrationStateRepository,
        "lock_for_legacy_write",
        lock_for_legacy_write,
    )
    monkeypatch.setattr(legacy_tasks, "_extract_content", extract_content)

    result = legacy_tasks.process_knowledge_base_document({"id": 1, "tenant_id": 7})

    assert result["status"] == "REJECTED_BY_PHASE"
    assert result["error_code"] == "KNOWLEDGE_UPGRADE_IN_PROGRESS"
    assert lock_calls == 2
    assert session.commits == 1
    assert session.rollbacks == 1
    assert record.status == KnowledgeBaseStatusEnum.PROCESSING
    assert record.content is None
    assert record.error_message is None


def test_legacy_worker_rejects_before_processing_write(monkeypatch) -> None:
    record = _record()
    session = _WorkerSession(record)
    monkeypatch.setattr(legacy_tasks, "Session", lambda _engine: session)
    monkeypatch.setattr(
        legacy_tasks.KnowledgeMigrationStateRepository,
        "lock_for_legacy_write",
        lambda _session: (_ for _ in ()).throw(_phase_error(active=True)),
    )

    result = legacy_tasks.process_knowledge_base_document({"id": 1, "tenant_id": 7})

    assert result["status"] == "REJECTED_BY_PHASE"
    assert result["error_code"] == "KNOWLEDGE_LEGACY_WRITE_DISABLED"
    assert session.commits == 0
    assert session.rollbacks == 1
    assert record.status == KnowledgeBaseStatusEnum.PENDING


@pytest.mark.parametrize(
    ("extract_fails", "expected_status"),
    [
        (False, KnowledgeBaseStatusEnum.READY),
        (True, KnowledgeBaseStatusEnum.FAILED),
    ],
)
def test_legacy_open_worker_keeps_existing_processing_behavior(
    monkeypatch,
    extract_fails,
    expected_status,
) -> None:
    record = _record()
    session = _WorkerSession(record)
    lock_calls = 0

    def lock_for_legacy_write(_session):
        nonlocal lock_calls
        lock_calls += 1

    def extract_content(_record):
        if extract_fails:
            raise ValueError("invalid document")
        return "new content"

    monkeypatch.setattr(legacy_tasks, "Session", lambda _engine: session)
    monkeypatch.setattr(
        legacy_tasks.KnowledgeMigrationStateRepository,
        "lock_for_legacy_write",
        lock_for_legacy_write,
    )
    monkeypatch.setattr(legacy_tasks, "_extract_content", extract_content)

    result = legacy_tasks.process_knowledge_base_document({"id": 1, "tenant_id": 7})

    assert result["status"] == expected_status.value
    assert lock_calls == 2
    assert session.commits == 2
    assert session.rollbacks == 0
    assert record.status == expected_status
    if extract_fails:
        assert record.content is None
        assert record.error_message == "invalid document"
    else:
        assert record.content == "new content"
        assert record.error_message is None
