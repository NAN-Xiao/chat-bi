"""Durable publish-job preparation and source-file download contracts."""

from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote

import pytest
from fastapi import UploadFile

from apps.knowledge_base.api import versions
from apps.knowledge_base.errors import KnowledgeBusinessError
from apps.knowledge_base.lifecycle_models import (
    KnowledgeBaseVersion,
    KnowledgeMigrationPhase,
    KnowledgePublishJob,
    KnowledgeVersionStatus,
)
from apps.knowledge_base.models import KnowledgeBase, KnowledgeBaseVisibilityScopeEnum
from apps.knowledge_base.publish_jobs import finalize_publish_job, prepare_publish_job


class _Result:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value


class _PublishSession:
    def __init__(self, *, existing_job=None):
        self.record = KnowledgeBase(
            id=11,
            tenant_id=7,
            name="收入知识",
            visibility_scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC,
            draft_version_id=12,
        )
        self.version = KnowledgeBaseVersion(
            id=12,
            knowledge_base_id=11,
            tenant_id=7,
            version_number=1,
            revision=3,
            status=KnowledgeVersionStatus.READY_TO_PUBLISH,
            content_hash="a" * 64,
            payload={"knowledge_type": "DOCUMENT", "markdown": "收入"},
        )
        self.job = existing_job
        self.added = []

    def exec(self, statement):
        sql = str(statement)
        if "knowledge_publish_job" in sql:
            return _Result(self.job)
        if "knowledge_base_version" in sql:
            return _Result(self.version)
        return _Result(self.record)

    def add(self, value):
        self.added.append(value)
        if isinstance(value, KnowledgePublishJob):
            value.id = 99
            self.job = value

    def flush(self):
        return None


def _prepare(session):
    return prepare_publish_job(
        session,
        tenant_id=7,
        knowledge_base_id=11,
        version_id=12,
        revision=3,
        content_hash="a" * 64,
        actor_id=1,
    )


def test_duplicate_publish_returns_the_same_database_job():
    session = _PublishSession()
    first = _prepare(session)
    second = _prepare(session)
    assert first.id == 99
    assert second.id == first.id
    assert len(session.added) == 1
    assert session.version.status == "PUBLISHING"
    assert session.record.publishing_version_id == 12


def test_publish_requires_the_latest_ready_snapshot():
    session = _PublishSession()
    session.version.revision = 2
    with pytest.raises(KnowledgeBusinessError) as caught:
        _prepare(session)
    assert caught.value.code == "KNOWLEDGE_VERSION_NOT_READY"
    assert caught.value.message == "知识尚未通过最新校验，请重新校验后发布。"


def test_publish_rejects_a_different_active_job():
    session = _PublishSession(existing_job=None)
    session.record.publishing_version_id = 99
    with pytest.raises(KnowledgeBusinessError) as caught:
        _prepare(session)
    assert caught.value.code == "KNOWLEDGE_PUBLISHING"


def test_finalize_second_version_supersedes_current_version():
    job = KnowledgePublishJob(
        id=99,
        tenant_id=7,
        knowledge_base_id=11,
        version_id=13,
        revision=1,
        content_hash="b" * 64,
        status="RUNNING",
    )
    current = KnowledgeBaseVersion(
        id=12,
        knowledge_base_id=11,
        tenant_id=7,
        version_number=1,
        revision=1,
        status=KnowledgeVersionStatus.PUBLISHED,
        content_hash="a" * 64,
        payload={"knowledge_type": "DOCUMENT", "markdown": "旧版本"},
    )
    target = KnowledgeBaseVersion(
        id=13,
        knowledge_base_id=11,
        tenant_id=7,
        version_number=2,
        revision=1,
        status=KnowledgeVersionStatus.PUBLISHING,
        index_status="READY",
        content_hash="b" * 64,
        payload={"knowledge_type": "DOCUMENT", "markdown": "新版本"},
    )
    record = KnowledgeBase(
        id=11,
        tenant_id=7,
        name="收入知识",
        visibility_scope=KnowledgeBaseVisibilityScopeEnum.ADMIN_PUBLIC,
        current_version_id=12,
        publishing_version_id=13,
        draft_version_id=13,
    )

    class _FinalizeSession:
        def __init__(self):
            self.results = iter((job, target, record, current))

        def exec(self, _statement):
            return _Result(next(self.results))

        def add(self, _value):
            return None

        def add_all(self, _values):
            return None

        def flush(self):
            return None

    assert finalize_publish_job(_FinalizeSession(), job_id=99)
    assert current.status == "SUPERSEDED"
    assert target.status == "PUBLISHED"
    assert record.current_version_id == 13
    assert record.publishing_version_id is None


def test_download_uses_version_binding_and_does_not_expose_storage_id(monkeypatch, tmp_path: Path):
    file_id = "immutable-source.md"
    (tmp_path / file_id).write_text("收入版本", encoding="utf-8")

    class _Result:
        def first(self):
            return SimpleNamespace(
                id=12,
                knowledge_base_id=11,
                tenant_id=7,
                file_id=file_id,
                file_name="收入说明.md",
            )

    class _Session:
        def exec(self, _statement):
            return _Result()

    monkeypatch.setattr(versions, "resolve_record", lambda *_args, **_kwargs: SimpleNamespace(id=11))
    monkeypatch.setattr(versions, "record_tenant_id", lambda *_args, **_kwargs: 7)
    monkeypatch.setattr(versions.settings, "UPLOAD_DIR", str(tmp_path))
    response = asyncio.run(
        versions.download_version_source(
            id=11,
            version_id=12,
            session=_Session(),
            current_user=SimpleNamespace(id=1),
        )
    )
    assert Path(response.path) == tmp_path / file_id
    assert file_id not in response.headers.get("content-disposition", "")
    assert "收入说明.md" in unquote(response.headers["content-disposition"])


def test_conflicting_source_upload_cleans_only_request_staged_file(monkeypatch, tmp_path: Path):
    deleted: list[str] = []

    class _Result:
        def first(self):
            return SimpleNamespace(
                id=12,
                knowledge_base_id=11,
                tenant_id=7,
                payload={"knowledge_type": "DOCUMENT", "markdown": "旧正文"},
            )

    class _Session:
        def exec(self, _statement):
            return _Result()

        def rollback(self):
            return None

    class _Service:
        def save_draft(self, **_kwargs):
            raise KnowledgeBusinessError(
                code="KNOWLEDGE_DRAFT_CONFLICT",
                message="该知识已被其他用户更新，请刷新后重新编辑。",
                status_code=409,
                error_type="CONFLICT",
            )

    monkeypatch.setattr(
        versions,
        "get_capabilities",
        lambda _session: SimpleNamespace(
            phase=KnowledgeMigrationPhase.V2_ACTIVE,
            management_mode="V2",
            v2_write_enabled=True,
        ),
    )
    monkeypatch.setattr(versions, "resolve_record", lambda *_args, **_kwargs: SimpleNamespace(id=11))
    monkeypatch.setattr(versions, "record_tenant_id", lambda *_args, **_kwargs: 7)
    monkeypatch.setattr(versions, "KnowledgeLifecycleService", lambda *_args: _Service())
    monkeypatch.setattr(versions.settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(versions.AppFileUtils, "delete_file", lambda file_id: deleted.append(file_id))

    response = asyncio.run(
        versions.replace_draft_source_file(
            id=11,
            session=_Session(),
            current_user=SimpleNamespace(id=1),
            version_id=12,
            revision=1,
            file=UploadFile(filename="new.md", file=BytesIO(b"new")),
        )
    )
    assert response.status_code == 409
    assert response.body.decode("utf-8").startswith('{"code":"KNOWLEDGE_DRAFT_CONFLICT"')
    assert len(deleted) == 1
    assert deleted[0].startswith(".knowledge-stage-")
