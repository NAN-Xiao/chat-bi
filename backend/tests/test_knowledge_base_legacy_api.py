"""Verify legacy knowledge writes are fenced by the migration phase."""

from __future__ import annotations

import asyncio
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException, UploadFile

from apps.knowledge_base.api import knowledge_base as legacy_api
from apps.knowledge_base.models import (
    KnowledgeBase,
    KnowledgeBaseStatusEnum,
    KnowledgeBaseVisibilityScopeEnum,
)
from apps.knowledge_base.repository import KnowledgeBusinessError
from common.core.config import Settings


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


class _ApiSession:
    def __init__(self, record: KnowledgeBase | None = None) -> None:
        self.record = record
        self.added: list[KnowledgeBase] = []
        self.deleted: list[KnowledgeBase] = []
        self.commits = 0
        self.rollbacks = 0

    def get(self, _model, _record_id):
        return self.record

    def add(self, record: KnowledgeBase) -> None:
        if record.id is None:
            record.id = 1
        self.record = record
        self.added.append(record)

    def delete(self, record: KnowledgeBase) -> None:
        self.deleted.append(record)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def refresh(self, _record: KnowledgeBase) -> None:
        return None


def _record(*, status: KnowledgeBaseStatusEnum = KnowledgeBaseStatusEnum.PENDING) -> KnowledgeBase:
    return KnowledgeBase(
        id=1,
        tenant_id=7,
        create_by=11,
        name="Legacy document",
        visibility_scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC,
        status=status,
        file_id="legacy.md",
        file_name="legacy.md",
        file_ext=".md",
    )


def _install_api_dependencies(monkeypatch, calls: dict[str, int]) -> None:
    monkeypatch.setattr(legacy_api, "_require_scope_manage", lambda *_args: None)
    monkeypatch.setattr(legacy_api, "_require_record_manage", lambda *_args: None)
    monkeypatch.setattr(legacy_api, "_scope_tenant_id", lambda *_args: 7)
    monkeypatch.setattr(legacy_api, "validate_workspace_tenant", lambda _session, tenant_id: tenant_id)
    monkeypatch.setattr(legacy_api, "_serialize_record", lambda _user, record: record)
    monkeypatch.setattr(legacy_api, "register_builtin_tasks", lambda: None)

    async def save_upload(_file):
        calls["save_upload"] += 1
        return "new.md", "new.md", ".md"

    async def enqueue(*_args, **_kwargs):
        calls["enqueue"] += 1
        return {"id": "task-1"}

    monkeypatch.setattr(legacy_api, "_save_upload", save_upload)
    monkeypatch.setattr(legacy_api, "enqueue_task", enqueue)
    monkeypatch.setattr(
        legacy_api.AppFileUtils,
        "delete_file",
        lambda *_args: calls.__setitem__("delete_file", calls["delete_file"] + 1),
    )


def test_knowledge_v2_management_defaults_enabled_and_runtime_disabled() -> None:
    settings = Settings(
        _env_file=None,
        SECRET_KEY="test-secret",
    )

    assert settings.KNOWLEDGE_MANAGEMENT_V2_ENABLED is True
    assert settings.KNOWLEDGE_RUNTIME_CONTEXT_ENABLED is False


def test_knowledge_v2_management_accepts_explicit_disable(monkeypatch) -> None:
    monkeypatch.setenv("KNOWLEDGE_MANAGEMENT_V2_ENABLED", "false")
    settings = Settings(
        _env_file=None,
        SECRET_KEY="test-secret",
    )

    assert settings.KNOWLEDGE_MANAGEMENT_V2_ENABLED is False


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("legacy.docx", b"not markdown"),
        ("legacy.md", b"# missing second-level heading"),
    ],
)
def test_legacy_upload_rejects_invalid_markdown_before_writing(
    monkeypatch,
    tmp_path,
    filename,
    content,
) -> None:
    monkeypatch.setattr(legacy_api.settings, "UPLOAD_DIR", str(tmp_path))
    with pytest.raises(HTTPException) as caught:
        asyncio.run(
            legacy_api._save_upload(
                UploadFile(filename=filename, file=BytesIO(content))
            )
        )
    assert getattr(caught.value, "status_code", None) == 422
    assert str(getattr(caught.value, "detail", "")).startswith("格式错误")
    assert list(tmp_path.iterdir()) == []


def test_legacy_source_replacement_keeps_old_file_until_commit(monkeypatch) -> None:
    calls = {"save_upload": 0, "enqueue": 0, "delete_file": 0}
    _install_api_dependencies(monkeypatch, calls)
    deleted_files: list[str] = []
    cleaned_files: list[tuple[str | None, ...]] = []
    monkeypatch.setattr(
        legacy_api.AppFileUtils,
        "delete_file",
        lambda file_id: deleted_files.append(str(file_id)),
    )
    monkeypatch.setattr(
        legacy_api,
        "cleanup_unreferenced_source_files",
        lambda _session, file_ids: cleaned_files.append(tuple(file_ids)),
    )
    monkeypatch.setattr(
        legacy_api.KnowledgeMigrationStateRepository,
        "lock_for_legacy_write",
        lambda _session: None,
    )

    class _FailingCommitSession(_ApiSession):
        def commit(self) -> None:
            super().commit()
            raise RuntimeError("database commit failed")

    session = _FailingCommitSession(_record())
    with pytest.raises(RuntimeError, match="database commit failed"):
        asyncio.run(
            legacy_api.save_knowledge_base(
                session=session,
                current_user=SimpleNamespace(id=11),
                background_tasks=BackgroundTasks(),
                id=1,
                name="Legacy document",
                description="",
                active=True,
                visibility_scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC.value,
                file=UploadFile(filename="replacement.md", file=BytesIO(b"content")),
                tenant_id=None,
            )
        )

    assert session.rollbacks == 1
    assert deleted_files == ["new.md"]
    assert cleaned_files == []


@pytest.mark.parametrize(
    ("active", "expected_code", "expected_message", "expected_status"),
    [
        (False, "KNOWLEDGE_UPGRADE_IN_PROGRESS", "知识库升级中，请稍后重试。", 409),
        (True, "KNOWLEDGE_LEGACY_WRITE_DISABLED", "知识库已升级，请刷新页面后重新操作。", 410),
    ],
)
def test_legacy_save_rejects_before_file_or_task_side_effects(
    monkeypatch,
    active,
    expected_code,
    expected_message,
    expected_status,
) -> None:
    calls = {"save_upload": 0, "enqueue": 0, "delete_file": 0}
    _install_api_dependencies(monkeypatch, calls)
    monkeypatch.setattr(
        legacy_api.KnowledgeMigrationStateRepository,
        "lock_for_legacy_write",
        lambda _session: (_ for _ in ()).throw(_phase_error(active=active)),
    )
    session = _ApiSession()
    background_tasks = BackgroundTasks()
    upload = UploadFile(filename="legacy.md", file=BytesIO(b"content"))

    with pytest.raises(KnowledgeBusinessError) as caught:
        asyncio.run(
            legacy_api.save_knowledge_base(
                session=session,
                current_user=SimpleNamespace(id=11),
                background_tasks=background_tasks,
                id=None,
                name="Legacy document",
                description="",
                active=True,
                visibility_scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC.value,
                file=upload,
                tenant_id=None,
            )
        )

    assert caught.value.status_code == expected_status
    assert caught.value.detail == {"code": expected_code, "message": expected_message}
    assert calls == {"save_upload": 0, "enqueue": 0, "delete_file": 0}
    assert session.added == []
    assert session.commits == 0
    assert background_tasks.tasks == []


def test_legacy_save_rechecks_phase_before_enqueue(monkeypatch) -> None:
    calls = {"save_upload": 0, "enqueue": 0, "delete_file": 0}
    _install_api_dependencies(monkeypatch, calls)
    lock_calls = 0

    def lock_for_legacy_write(_session):
        nonlocal lock_calls
        lock_calls += 1
        if lock_calls == 2:
            raise _phase_error()

    monkeypatch.setattr(
        legacy_api.KnowledgeMigrationStateRepository,
        "lock_for_legacy_write",
        lock_for_legacy_write,
    )
    session = _ApiSession()
    background_tasks = BackgroundTasks()

    with pytest.raises(KnowledgeBusinessError):
        asyncio.run(
            legacy_api.save_knowledge_base(
                session=session,
                current_user=SimpleNamespace(id=11),
                background_tasks=background_tasks,
                id=None,
                name="Legacy document",
                description="",
                active=True,
                visibility_scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC.value,
                file=UploadFile(filename="legacy.md", file=BytesIO(b"content")),
                tenant_id=None,
            )
        )

    assert lock_calls == 2
    assert calls["save_upload"] == 1
    assert calls["enqueue"] == 0
    assert session.commits == 1
    assert background_tasks.tasks == []


def test_legacy_open_keeps_queue_to_background_task_fallback(monkeypatch) -> None:
    calls = {"save_upload": 0, "enqueue": 0, "delete_file": 0}
    _install_api_dependencies(monkeypatch, calls)
    lock_calls = 0

    def lock_for_legacy_write(_session):
        nonlocal lock_calls
        lock_calls += 1

    async def rejected_enqueue(*_args, **_kwargs):
        calls["enqueue"] += 1
        raise RuntimeError("queue unavailable")

    monkeypatch.setattr(
        legacy_api.KnowledgeMigrationStateRepository,
        "lock_for_legacy_write",
        lock_for_legacy_write,
    )
    monkeypatch.setattr(legacy_api, "enqueue_task", rejected_enqueue)
    session = _ApiSession()
    background_tasks = BackgroundTasks()

    result = asyncio.run(
        legacy_api.save_knowledge_base(
            session=session,
            current_user=SimpleNamespace(id=11),
            background_tasks=background_tasks,
            id=None,
            name="Legacy document",
            description="",
            active=True,
            visibility_scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC.value,
            file=UploadFile(filename="legacy.md", file=BytesIO(b"content")),
            tenant_id=None,
        )
    )

    assert result.id == 1
    assert result.knowledge_type == "DOCUMENT"
    assert result.task_id is None
    assert lock_calls == 2
    assert calls["save_upload"] == 1
    assert calls["enqueue"] == 1
    assert session.commits == 2
    assert len(background_tasks.tasks) == 1


def test_legacy_delete_rejects_before_file_or_database_side_effects(monkeypatch) -> None:
    calls = {"save_upload": 0, "enqueue": 0, "delete_file": 0}
    _install_api_dependencies(monkeypatch, calls)
    monkeypatch.setattr(
        legacy_api.KnowledgeMigrationStateRepository,
        "lock_for_legacy_write",
        lambda _session: (_ for _ in ()).throw(_phase_error()),
    )
    session = _ApiSession(_record())

    with pytest.raises(KnowledgeBusinessError):
        asyncio.run(
            legacy_api.delete_knowledge_base(
                session=session,
                current_user=SimpleNamespace(id=11),
                id=1,
            )
        )

    assert calls["delete_file"] == 0
    assert session.deleted == []
